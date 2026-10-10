#!/usr/bin/env python3
"""Real PostgreSQL acceptance tests for Phase 4 rewards and invites."""
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

from saas_auth import SaaSError, SaaSService, new_id, token_hash, utcnow
from saas_catalog import CatalogService
from saas_membership import MembershipService
from saas_rewards import RewardService, local_day

TEST_URL=os.environ.get("SHIYUE_SAAS_TEST_DATABASE_URL","")

def assert_safe_database(url:str)->None:
    if not urlsplit(url).path.rsplit("/",1)[-1].endswith("_test"):
        raise RuntimeError("SHIYUE_SAAS_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用数据库。")

class PhaseFourPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert_safe_database(TEST_URL)
        cls.environment={"DATABASE_URL":TEST_URL,"SHIYUE_SAAS_ENABLED":"1","SESSION_SECRET":"test-only-session-secret-that-is-at-least-32-characters","BOOTSTRAP_ADMIN_EMAIL":"admin@local.test","BOOTSTRAP_ADMIN_PASSWORD":"phase4 admin password"}
        cls.accounts=SaaSService(TEST_URL,cls.environment);cls.accounts.migrate();cls.memberships=MembershipService(cls.accounts);cls.catalog=CatalogService(cls.accounts,cls.memberships);cls.rewards=RewardService(cls.accounts,cls.memberships)

    def setUp(self):
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""TRUNCATE TABLE member_invite_rewards,member_invites,member_invite_allowances,reward_activity_events,reward_daily_activity,reward_redemptions,reward_ledger,checkins,
                official_book_unlocks,user_library,catalog_book_tags,catalog_books,catalog_tags,catalog_series,membership_audit,usage_ledger,quota_reservations,usage_periods,subscriptions,manual_orders,assets,
                content_sentence_grammar,content_learning_daily,content_word_annotations,content_vocabulary,content_books,invitation_uses,invitations,password_reset_tokens,email_verifications,user_sessions,devices,user_roles,users,roles RESTART IDENTITY CASCADE""")
        self.admin=self.accounts.bootstrap_admin();assert self.admin
        invitation=self.accounts.create_invitation("REWARD-TEST",max_uses=30,created_by=str(self.admin["id"]))
        self.user=self.accounts.register("learner@local.test","learner password phase four",invitation["code"])["user"]
        self.verify(str(self.user["id"]))

    def verify(self,user_id:str)->None:
        raw="verify-"+new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO email_verifications(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",(new_id(),user_id,token_hash(raw),utcnow()+timedelta(days=1)))
        self.accounts.verify_email(raw)

    def award(self,user_id:str,points:int,key:str="seed"):
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                user=self.rewards._user(cursor,user_id);return self.rewards._award(cursor,user_id,"seed",key,points,local_day(user["timezone"]),{})

    def test_checkin_streak_and_monthly_cap_are_idempotent(self):
        user_id=str(self.user["id"]);today=local_day("Asia/Shanghai")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                for offset in (2,1):
                    cursor.execute("INSERT INTO checkins(id,user_id,checkin_day,timezone,kind,streak_count) VALUES(%s,%s,%s,'Asia/Shanghai','regular',1)",(new_id(),user_id,today-timedelta(days=offset)))
        result=self.rewards.checkin(user_id)
        self.assertEqual(result["streak"],3);self.assertEqual(result["pointsGranted"],3)
        with self.assertRaises(SaaSError) as duplicate:self.rewards.checkin(user_id)
        self.assertEqual(duplicate.exception.code,"already_checked_in")
        other=self.accounts.register("cap@local.test","cap password phase four",self.accounts.create_invitation("CAP-TEST",max_uses=1,created_by=str(self.admin["id"]))["code"])["user"]
        self.verify(str(other["id"]))
        self.assertEqual(self.award(str(other["id"]),90,"one"),90)
        self.assertEqual(self.award(str(other["id"]),20,"two"),10)
        self.assertEqual(self.rewards.status(str(other["id"]))["monthEarned"],100)

    def test_makeup_card_and_activity_rewards_are_atomic(self):
        user_id=str(self.user["id"]);self.award(user_id,20,"makeup-funds")
        redemption=self.rewards.redeem(user_id,"makeup_card_1","makeup-redemption")
        self.assertEqual(redemption["redemption"]["rewardType"],"makeup_card")
        yesterday=(local_day("Asia/Shanghai")-timedelta(days=1)).isoformat()
        checked=self.rewards.checkin(user_id,yesterday);self.assertEqual(checked["kind"],"makeup")
        with self.assertRaises(SaaSError) as repeat:self.rewards.checkin(user_id,yesterday)
        self.assertEqual(repeat.exception.code,"already_checked_in")
        first=self.rewards.activity(user_id,599,4,0,"reading-a");self.assertEqual(first["pointsGranted"],0)
        second=self.rewards.activity(user_id,1,1,0,"reading-b");self.assertEqual(second["pointsGranted"],2)
        review=self.rewards.activity(user_id,0,0,1,"review-a");self.assertEqual(review["pointsGranted"],2)
        duplicate=self.rewards.activity(user_id,0,0,1,"review-a");self.assertTrue(duplicate["idempotent"])

    def test_redemption_credits_membership_quota_once(self):
        user_id=str(self.user["id"]);self.award(user_id,20,"context-funds")
        first=self.rewards.redeem(user_id,"ai_context_10","context-redemption")
        second=self.rewards.redeem(user_id,"ai_context_10","context-redemption")
        self.assertFalse(first["idempotent"]);self.assertTrue(second["idempotent"])
        usage=self.memberships.usage(user_id);context=next(row for row in usage["usage"] if row["feature"]=="ai_context_generations")
        self.assertEqual(context["available"],30)
        self.assertEqual(self.rewards.status(user_id)["balance"],0)

    def test_completed_official_book_awards_once(self):
        user_id=str(self.user["id"]);source_id="reward-source";data={"id":source_id,"title":"奖励读物","englishTitle":"Reward Reader","sentences":[{"id":"s1","text":"A reward sentence.","words":[{"text":"A"}]}]}
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO content_books(id,owner_id,title,english_title,series,level,source_type,source_path,status,visibility,cover_url,page_base_url,audio_url,pdf_url,video_url,duration,alignment,data_json,quality_json,created_at,updated_at)
                VALUES(%s,%s,'奖励读物','Reward Reader','Reward Series','1','book','reward/source','ready','private','','','','','',60,'',%s::jsonb,'{}'::jsonb,NOW(),NOW())""",(source_id,self.admin["id"],json.dumps(data)))
        book_id=self.catalog.review(str(self.admin["id"]),source_id,"public_domain","published",{})["book"]["id"]
        self.catalog.add_or_unlock(user_id,book_id,True)
        self.rewards.activity(user_id,60,1,0,"complete-book-reading")
        self.assertEqual(self.rewards.complete_book(user_id,book_id)["pointsGranted"],10)
        self.assertEqual(self.rewards.complete_book(user_id,book_id)["pointsGranted"],0)
        self.assertEqual(self.rewards.status(user_id)["balance"],10)

    def test_member_invite_rewards_effective_learning_and_first_paid(self):
        inviter_id=str(self.user["id"])
        self.memberships.create_manual_order(str(self.admin["id"]),inviter_id,"advanced-v1",utcnow()-timedelta(minutes=1),utcnow()+timedelta(days=30))
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO member_invite_allowances(id,user_id,quantity_remaining,source,created_by) VALUES(%s,%s,1,'test',%s)",(new_id(),inviter_id,self.admin["id"]))
        invite=self.rewards.issue_invite(inviter_id)
        invitee=self.accounts.register("invitee@local.test","invitee password phase four",invite["code"])["user"]
        invitee_id=str(invitee["id"]);self.verify(invitee_id)
        self.rewards.activity(invitee_id,600,5,0,"invitee-effective")
        self.memberships.create_manual_order(str(self.admin["id"]),invitee_id,"advanced-v1",utcnow()-timedelta(minutes=1),utcnow()+timedelta(days=30))
        self.rewards.on_first_paid(invitee_id);self.rewards.on_first_paid(invitee_id)
        status=self.rewards.status(inviter_id);self.assertEqual(status["balance"],40)
        self.assertEqual(status["invites"][0]["status"],"paid")
        self.assertEqual(status["inviteAllowance"],0)
        with self.assertRaises(SaaSError) as no_more:self.rewards.issue_invite(inviter_id)
        self.assertEqual(no_more.exception.code,"invite_not_available")

    def test_http_checkin_status_catalog_and_redemption(self):
        user_id=str(self.user["id"]);self.award(user_id,20,"http-funds")
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
            else:self.fail("reward server did not start: "+(process.stderr.read() if process.stderr else ""))
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection);connection.request("POST","/api/auth/login",json.dumps({"email":"learner@local.test","password":"learner password phase four"}),{"Content-Type":"application/json","X-Device-Id":"phase4-http-device-1"});response=connection.getresponse();self.assertEqual(response.status,200);headers=response.getheaders();response.read();connection.close();connections.remove(connection)
            values=[value.split(";",1)[0] for name,value in headers if name.lower()=="set-cookie"];cookies="; ".join(values);csrf=next(value.split("=",1)[1] for value in values if value.startswith("shiyue_csrf="))
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection);connection.request("GET","/api/rewards/catalog",headers={"Cookie":cookies});response=connection.getresponse();catalog=json.loads(response.read());self.assertEqual(response.status,200);self.assertEqual(len(catalog["rewards"]),5);connection.close();connections.remove(connection)
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection);connection.request("POST","/api/checkins",json.dumps({}),{"Content-Type":"application/json","Cookie":cookies,"X-CSRF-Token":csrf});response=connection.getresponse();checked=json.loads(response.read());self.assertEqual(response.status,200);self.assertEqual(checked["status"],"checked_in");connection.close();connections.remove(connection)
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection);connection.request("POST","/api/rewards/redeem",json.dumps({"code":"ai_context_10","idempotencyKey":"http-redeem"}),{"Content-Type":"application/json","Cookie":cookies,"X-CSRF-Token":csrf});response=connection.getresponse();redeemed=json.loads(response.read());self.assertEqual(response.status,200);self.assertEqual(redeemed["redemption"]["code"],"ai_context_10");connection.close();connections.remove(connection)
        finally:
            for connection in connections:connection.close()
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()
            if process.stderr:process.stderr.close()

if __name__=="__main__":unittest.main()
