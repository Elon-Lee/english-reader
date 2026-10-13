#!/usr/bin/env python3
"""Real PostgreSQL acceptance tests for Phase 5 admin operations."""
from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import time
import unittest
from datetime import timedelta
from urllib.parse import urlsplit

from saas_admin import AdminService
from saas_auth import SaaSError, SaaSService, new_id, token_hash, utcnow
from saas_membership import FEATURES, MembershipService
from saas_rewards import RewardService

TEST_URL=os.environ.get("SHIYUE_SAAS_TEST_DATABASE_URL","")

def assert_safe_database(url:str)->None:
    if not urlsplit(url).path.rsplit("/",1)[-1].endswith("_test"):
        raise RuntimeError("SHIYUE_SAAS_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用数据库。")

class PhaseFivePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert_safe_database(TEST_URL)
        cls.environment={"DATABASE_URL":TEST_URL,"SHIYUE_SAAS_ENABLED":"1","SESSION_SECRET":"test-only-session-secret-that-is-at-least-32-characters","BOOTSTRAP_ADMIN_EMAIL":"admin@local.test","BOOTSTRAP_ADMIN_PASSWORD":"phase5 admin password"}
        cls.accounts=SaaSService(TEST_URL,cls.environment);cls.accounts.migrate();cls.memberships=MembershipService(cls.accounts);cls.rewards=RewardService(cls.accounts,cls.memberships);cls.admin_service=AdminService(cls.accounts,cls.memberships)

    def setUp(self):
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""TRUNCATE TABLE admin_audit_logs,platform_settings,member_invite_rewards,member_invites,member_invite_allowances,reward_activity_events,reward_daily_activity,reward_redemptions,reward_ledger,checkins,
                official_book_unlocks,user_library,catalog_book_tags,catalog_books,catalog_tags,catalog_series,membership_audit,usage_ledger,quota_reservations,usage_periods,subscriptions,manual_orders,assets,
                content_sentence_grammar,content_learning_daily,content_word_annotations,content_vocabulary,content_books,invitation_uses,invitations,invitation_batches,password_reset_tokens,email_verifications,user_sessions,devices,user_roles,users,roles RESTART IDENTITY CASCADE""")
                cursor.execute("DELETE FROM plan_versions WHERE id='advanced-v2'")
        self.admin=self.accounts.bootstrap_admin();assert self.admin
        invitation=self.accounts.create_invitation("ADMIN-TEST",max_uses=10,created_by=str(self.admin["id"]))
        self.user=self.accounts.register("operator-user@local.test","operator user password",invitation["code"])["user"]
        self.verify(str(self.user["id"]))

    def verify(self,user_id:str)->None:
        raw="verify-"+new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO email_verifications(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",(new_id(),user_id,token_hash(raw),utcnow()+timedelta(days=1)))
        self.accounts.verify_email(raw)

    def test_dashboard_users_channel_invites_and_safe_export(self):
        dashboard=self.admin_service.dashboard();self.assertEqual(dashboard["users"]["total"],2)
        created=self.admin_service.create_invitation(str(self.admin["id"]),"CHANNEL-ABC",3,None,"campaign note","wechat")
        self.assertEqual(created["channel"],"wechat")
        rows=self.admin_service.invitations()["invitations"]
        self.assertTrue(any(row["code"]=="CHANNEL-ABC" and row["channel"]=="wechat" for row in rows))
        users=self.admin_service.users()["users"]
        self.assertTrue(any(row["email"]=="operator-user@local.test" for row in users))
        self.assertNotIn("passwordHash",users[0])
        exported=self.admin_service.export_summary();self.assertIn("dashboard",exported);self.assertTrue(all("password" not in key.casefold() for row in exported["users"] for key in row))

    def test_invitation_batches_detail_and_delete_only_unused(self):
        actor=str(self.admin["id"]);created=self.admin_service.create_invitations(actor,"",1,3,None,"batch summary","admin")
        batch_id=created["batch"]["id"];batches=self.admin_service.invitation_batches()["batches"]
        self.assertEqual(sum(1 for row in batches if row["id"]==batch_id),1)
        self.assertEqual(next(row for row in batches if row["id"]==batch_id)["count"],3)
        used_code=created["invitations"][0]["code"]
        self.accounts.register("batch-user@local.test","batch user password",used_code)
        detail=self.admin_service.invitation_batch_detail(batch_id);self.assertEqual(len(detail["invitations"]),3)
        deletable=[row["id"] for row in detail["invitations"] if row["deletable"]]
        self.assertEqual(len(deletable),2)
        deleted=self.admin_service.delete_unused_invitations(actor,batch_id,deletable);self.assertEqual(deleted["deleted"],2);self.assertEqual(deleted["remaining"],1)
        used_id=next(row["id"] for row in detail["invitations"] if row["code"]==used_code)
        with self.assertRaises(SaaSError) as blocked:self.admin_service.delete_unused_invitations(actor,batch_id,[used_id])
        self.assertEqual(blocked.exception.code,"invitation_in_use")

    def test_adjustments_allowances_status_and_audit(self):
        actor,user_id=str(self.admin["id"]),str(self.user["id"])
        granted=self.admin_service.adjust_quota(actor,user_id,"ai_context_generations",5,"support grant","admin-adjust-1")
        self.assertEqual(granted["available"],25)
        deducted=self.admin_service.adjust_quota(actor,user_id,"ai_context_generations",-2,"correction","admin-adjust-2")
        self.assertEqual(deducted["available"],23)
        allowance=self.admin_service.grant_invite_allowance(actor,user_id,2,"campaign allocation")
        self.assertEqual(allowance["quantity"],2)
        self.memberships.create_manual_order(actor,user_id,"advanced-v1",utcnow()-timedelta(minutes=1),utcnow()+timedelta(days=30),"paid")
        detail=self.admin_service.user_detail(user_id)
        self.assertEqual(detail["user"]["id"],user_id)
        self.assertEqual(detail["subscriptions"][0]["planVersion"],"advanced-v1")
        self.assertEqual(detail["orders"][0]["planVersion"],"advanced-v1")
        first=self.rewards.issue_invite(user_id);second=self.rewards.issue_invite(user_id)
        self.assertNotEqual(first["code"],second["code"])
        self.assertEqual(self.rewards.status(user_id)["inviteAllowance"],0)
        audit=self.admin_service.audit()["items"]
        self.assertTrue(any(item["action"]=="quota_adjustment" for item in audit))
        self.assertTrue(any(item["action"]=="invite_allowance_granted" for item in audit))

    def test_suspend_revokes_sessions_and_requires_reason(self):
        actor,user_id=str(self.admin["id"]),str(self.user["id"])
        login=self.accounts.login("operator-user@local.test","operator user password","phase5-user-device-1","Phase5 test")
        with self.assertRaises(SaaSError) as missing:self.admin_service.set_user_status(actor,user_id,"suspended","")
        self.assertEqual(missing.exception.code,"audit_reason_required")
        suspended=self.admin_service.set_user_status(actor,user_id,"suspended","abuse investigation")
        self.assertEqual(suspended["status"],"suspended")
        self.assertIsNone(self.accounts.authenticate(login["sessionToken"]))
        with self.assertRaises(SaaSError) as blocked:self.accounts.login("operator-user@local.test","operator user password","phase5-user-device-1","Phase5 test")
        self.assertEqual(blocked.exception.code,"account_unavailable")
        self.admin_service.set_user_status(actor,user_id,"active","cleared")
        self.assertIsNotNone(self.accounts.login("operator-user@local.test","operator user password","phase5-user-device-1","Phase5 test"))

    def test_new_plan_version_is_immutable_and_existing_period_stays_v1(self):
        actor,user_id=str(self.admin["id"]),str(self.user["id"])
        before=self.memberships.membership(user_id,True)
        quotas={feature:before["plan"]["quotas"][feature] for feature in FEATURES};quotas["ai_context_generations"]=999
        created=self.admin_service.create_plan_version(actor,"advanced-v2","advanced","进阶版 v2",1,30,quotas,{"currency":"CNY","monthly_cents":4900})
        self.assertEqual(created["quotas"]["ai_context_generations"],999)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT limits_json->>'ai_context_generations' FROM usage_periods WHERE user_id=%s",(user_id,))
                self.assertEqual(cursor.fetchone()[0],"20")
        self.assertTrue(any(item["id"]=="advanced-v2" for item in self.admin_service.plan_versions()["planVersions"]))

    def test_http_admin_permissions_csrf_and_operations(self):
        with socket.socket() as probe:probe.bind(("127.0.0.1",0));port=probe.getsockname()[1]
        environment={**os.environ,**self.environment,"READER_HOST":"127.0.0.1","READER_PORT":str(port)};server_path=os.path.join(os.path.dirname(__file__),"reader_server.py")
        process=subprocess.Popen([sys.executable,server_path],cwd=os.path.dirname(__file__),env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True);connections=[]
        try:
            deadline=time.time()+10
            while time.time()<deadline:
                try:
                    connection=http.client.HTTPConnection("127.0.0.1",port,timeout=1);connections.append(connection);connection.request("GET","/api/health");response=connection.getresponse();response.read();connection.close();connections.remove(connection)
                    if response.status==200:break
                except OSError:time.sleep(.1)
            else:self.fail("admin server did not start: "+(process.stderr.read() if process.stderr else ""))
            # A normal member cannot inspect the operating dashboard.
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection);connection.request("POST","/api/auth/login",json.dumps({"email":"operator-user@local.test","password":"operator user password"}),{"Content-Type":"application/json","X-Device-Id":"phase5-http-user-1"});response=connection.getresponse();member_headers=response.getheaders();response.read();connection.close();connections.remove(connection)
            member_cookie="; ".join(value.split(";",1)[0] for name,value in member_headers if name.lower()=="set-cookie")
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection);connection.request("GET","/api/admin/dashboard",headers={"Cookie":member_cookie});response=connection.getresponse();self.assertEqual(response.status,403);response.read();connection.close();connections.remove(connection)
            # Admin can create a channel invitation only with a valid CSRF token.
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection);connection.request("POST","/api/auth/login",json.dumps({"email":"admin@local.test","password":"phase5 admin password"}),{"Content-Type":"application/json","X-Device-Id":"phase5-http-admin-1"});response=connection.getresponse();self.assertEqual(response.status,200);headers=response.getheaders();response.read();connection.close();connections.remove(connection)
            values=[value.split(";",1)[0] for name,value in headers if name.lower()=="set-cookie"];cookies="; ".join(values);csrf=next(value.split("=",1)[1] for value in values if value.startswith("shiyue_csrf="))
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection);connection.request("POST","/api/admin/invitations",json.dumps({"code":"HTTP-CHANNEL","maxUses":2,"channel":"test","note":"http"}),{"Content-Type":"application/json","Cookie":cookies,"X-CSRF-Token":csrf});response=connection.getresponse();created=json.loads(response.read());self.assertEqual(response.status,201);self.assertEqual(created["channel"],"test");connection.close();connections.remove(connection)
        finally:
            for connection in connections:connection.close()
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()
            if process.stderr:process.stderr.close()

if __name__=="__main__":unittest.main()
