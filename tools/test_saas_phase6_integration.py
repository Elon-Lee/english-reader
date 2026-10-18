#!/usr/bin/env python3
"""Real PostgreSQL/HTTP acceptance tests for Phase 6 security and media."""
from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from saas_accounts import AccountLifecycleService
from saas_auth import SaaSError, SaaSService, new_id, token_hash, utcnow
from saas_catalog import CatalogService
from saas_media import MediaService
from saas_membership import MembershipService

TEST_URL=os.environ.get("SHIYUE_SAAS_TEST_DATABASE_URL","")
ROOT=Path(__file__).resolve().parents[1]

def assert_safe_database(url:str)->None:
    if not urlsplit(url).path.rsplit("/",1)[-1].endswith("_test"):
        raise RuntimeError("SHIYUE_SAAS_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用数据库。")

class PhaseSixPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert_safe_database(TEST_URL)
        cls.temp=tempfile.TemporaryDirectory(prefix="shiyue-phase6-media-")
        cls.media_root=Path(cls.temp.name)/"media";cls.media_root.mkdir()
        cls.environment={"DATABASE_URL":TEST_URL,"SHIYUE_SAAS_ENABLED":"1","SESSION_SECRET":"test-only-session-secret-that-is-at-least-32-characters","BOOTSTRAP_ADMIN_EMAIL":"admin@local.test","BOOTSTRAP_ADMIN_PASSWORD":"phase6 admin password","MEDIA_ROOT":str(cls.media_root)}
        cls.accounts=SaaSService(TEST_URL,cls.environment);cls.accounts.migrate();cls.memberships=MembershipService(cls.accounts);cls.catalog=CatalogService(cls.accounts,cls.memberships);cls.media=MediaService(cls.accounts,cls.memberships,cls.media_root);cls.lifecycle=AccountLifecycleService(cls.accounts)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        for path in self.media_root.iterdir():
            if path.is_file():path.unlink()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""TRUNCATE TABLE security_events,account_deletion_requests,asset_usage,asset_variants,media_assets,admin_audit_logs,platform_settings,
                member_invite_rewards,member_invites,member_invite_allowances,reward_activity_events,reward_daily_activity,reward_redemptions,reward_ledger,checkins,
                official_book_unlocks,user_library,catalog_book_tags,catalog_books,catalog_tags,catalog_series,membership_audit,usage_ledger,quota_reservations,usage_periods,subscriptions,manual_orders,assets,
                content_sentence_grammar,content_learning_daily,content_word_annotations,content_vocabulary,content_books,invitation_uses,invitations,password_reset_tokens,email_verifications,user_sessions,devices,user_roles,users,roles RESTART IDENTITY CASCADE""")
        self.admin=self.accounts.bootstrap_admin();assert self.admin
        invitation=self.accounts.create_invitation("MEDIA-TEST",max_uses=10,created_by=str(self.admin["id"]))
        self.owner=self.accounts.register("owner@local.test","owner password phase six",invitation["code"])["user"]
        self.other=self.accounts.register("other@local.test","other password phase six",invitation["code"])["user"]
        self.verify(str(self.owner["id"]));self.verify(str(self.other["id"]))

    def verify(self,user_id:str)->None:
        raw="verify-"+new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:cursor.execute("INSERT INTO email_verifications(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",(new_id(),user_id,token_hash(raw),utcnow()+timedelta(days=1)))
        self.accounts.verify_email(raw)

    def make_file(self,name:str,data:bytes)->str:
        path=self.media_root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return str(path.relative_to(self.media_root))

    def publish_book(self)->str:
        source_id="phase6-source";payload={"id":source_id,"title":"安全读物","englishTitle":"Secure Reader","sentences":[{"id":"s1","text":"Secure media sentence.","words":[{"text":"Secure"}]}]}
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:cursor.execute("""INSERT INTO content_books(id,owner_id,title,english_title,series,level,source_type,source_path,status,visibility,cover_url,page_base_url,audio_url,pdf_url,video_url,duration,alignment,data_json,quality_json,created_at,updated_at)
            VALUES(%s,%s,'安全读物','Secure Reader','Security','1','book','security/source','ready','private','','','','','',60,'',%s::jsonb,'{}'::jsonb,NOW(),NOW())""",(source_id,self.admin["id"],json.dumps(payload)))
        return self.catalog.review(str(self.admin["id"]),source_id,"licensed","published",{})["book"]["id"]

    def test_private_media_storage_access_and_logical_deletion_release(self):
        user_id=str(self.owner["id"]);relative=self.make_file("private/notes.bin",b"private-media")
        asset=self.media.register(str(self.owner["id"]),user_id,"private",relative,"upload")
        self.assertEqual(asset["totalBytes"],13)
        stream=self.media.stream(user_id,asset["id"]);self.assertEqual(stream["path"].read_bytes(),b"private-media")
        with self.assertRaises(SaaSError) as denied:self.media.stream(str(self.other["id"]),asset["id"])
        self.assertEqual(denied.exception.code,"media_access_denied")
        usage=self.memberships.usage(user_id);storage=next(row for row in usage["usage"] if row["feature"]=="storage_bytes");self.assertEqual(storage["used"],13)
        self.media.delete(user_id,asset["id"])
        usage=self.memberships.usage(user_id);storage=next(row for row in usage["usage"] if row["feature"]=="storage_bytes");self.assertEqual(storage["used"],0)
        with self.assertRaises(SaaSError):self.media.stream(user_id,asset["id"])

    def test_official_media_requires_unlock_and_range_http(self):
        catalog_id=self.publish_book();relative=self.make_file("official/audio.mp3",b"0123456789abcdef")
        asset=self.media.register(str(self.admin["id"]),str(self.admin["id"]),"official",relative,"audio","audio/mpeg",catalog_id)
        with self.assertRaises(SaaSError) as locked:self.media.stream(str(self.owner["id"]),asset["id"])
        self.assertEqual(locked.exception.code,"media_access_denied")
        self.catalog.add_or_unlock(str(self.owner["id"]),catalog_id,True)
        self.assertEqual(self.media.stream(str(self.owner["id"]),asset["id"])["path"].read_bytes(),b"0123456789abcdef")
        original=self.make_file("official/video.mp4",b"high-video")
        low=self.make_file("official/video-low.mp4",b"low-video")
        video=self.media.register(str(self.admin["id"]),str(self.admin["id"]),"official",original,"video","video/mp4",catalog_id,variants=[{"name":"low","storagePath":low,"contentType":"video/mp4"}])
        self.assertFalse(self.catalog.reader(str(self.owner["id"]),catalog_id)["book"]["canWatchHdVideo"])
        with socket.socket() as probe:probe.bind(("127.0.0.1",0));port=probe.getsockname()[1]
        environment={**os.environ,**self.environment,"READER_HOST":"127.0.0.1","READER_PORT":str(port)};process=subprocess.Popen([sys.executable,str(ROOT/"tools/reader_server.py")],cwd=ROOT,env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        connection=None
        try:
            deadline=time.time()+10
            while time.time()<deadline:
                try:
                    connection=http.client.HTTPConnection("127.0.0.1",port,timeout=1);connection.request("GET","/api/health");response=connection.getresponse();response.read();connection.close();connection=None
                    if response.status==200:break
                except OSError:time.sleep(.1)
            else:self.fail("media server did not start: "+(process.stderr.read() if process.stderr else ""))
            login=self.accounts.login("owner@local.test","owner password phase six","phase6-owner-device-1","Phase6 test")
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("GET",f"/api/media/{asset['id']}",headers={"Cookie":f"shiyue_session={login['sessionToken']}","Range":"bytes=2-6"});response=connection.getresponse();body=response.read();self.assertEqual(response.status,206);self.assertEqual(body,b"23456");self.assertEqual(response.getheader("Content-Range"),"bytes 2-6/16");self.assertEqual(response.getheader("X-Content-Type-Options"),"nosniff");connection.close();connection=None
            cookie={"Cookie":f"shiyue_session={login['sessionToken']}"}
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("GET",f"/api/media/{video['id']}",headers=cookie);response=connection.getresponse();body=json.loads(response.read());self.assertEqual(response.status,403);self.assertEqual(body["code"],"video_quality_membership_required");connection.close();connection=None
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("GET",f"/api/media/{video['id']}?variant=low",headers={**cookie,"Range":"bytes=0-2"});response=connection.getresponse();body=response.read();self.assertEqual(response.status,206);self.assertEqual(body,b"low");connection.close();connection=None
            self.memberships.create_manual_order(str(self.admin["id"]),str(self.owner["id"]),"advanced-v1",utcnow()-timedelta(minutes=1),utcnow()+timedelta(days=30))
            self.assertTrue(self.catalog.reader(str(self.owner["id"]),catalog_id)["book"]["canWatchHdVideo"])
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("GET",f"/api/media/{video['id']}",headers={**cookie,"Range":"bytes=0-3"});response=connection.getresponse();body=response.read();self.assertEqual(response.status,206);self.assertEqual(body,b"high");connection.close();connection=None
        finally:
            if connection:connection.close()
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()
            if process.stderr:process.stderr.close()

    def test_path_traversal_variants_and_deleted_purge_are_safe(self):
        with self.assertRaises(SaaSError) as traversal:self.media.register(str(self.owner["id"]),str(self.owner["id"]),"private","../outside.bin")
        self.assertEqual(traversal.exception.code,"invalid_media_path")
        main=self.make_file("private/source.mp4",b"main");variant=self.make_file("private/source-low.mp4",b"low")
        asset=self.media.register(str(self.owner["id"]),str(self.owner["id"]),"private",main,"video","video/mp4",variants=[{"name":"low","storagePath":variant,"contentType":"video/mp4"}])
        self.assertEqual(self.media.stream(str(self.owner["id"]),asset["id"],"low")["path"].read_bytes(),b"low")
        self.media.delete(str(self.owner["id"]),asset["id"])
        dry=self.media.purge_deleted(self.media_root.parent/"trash",True);self.assertEqual(len(dry["files"]),2);self.assertTrue((self.media_root/main).is_file())
        moved=self.media.purge_deleted(self.media_root.parent/"trash",False);self.assertEqual(len(moved["files"]),2);self.assertFalse((self.media_root/main).exists())

    def test_export_delayed_deletion_cancel_and_cleanup(self):
        user_id=str(self.owner["id"]);relative=self.make_file("private/export.bin",b"export");asset=self.media.register(user_id,user_id,"private",relative)
        exported=self.lifecycle.export(user_id);self.assertEqual(exported["account"]["email"],"owner@local.test");self.assertNotIn("passwordHash",exported["account"]);self.assertEqual(exported["assets"][0]["id"],asset["id"])
        session=self.accounts.login("owner@local.test","owner password phase six","phase6-delete-device","Phase6 test")
        request=self.lifecycle.request_deletion(user_id,"privacy request");self.assertEqual(request["status"],"requested");self.assertIsNone(self.accounts.authenticate(session["sessionToken"]))
        self.assertIsNotNone(self.accounts.login("owner@local.test","owner password phase six","phase6-delete-device","Phase6 test"))
        self.lifecycle.cancel_deletion(user_id)
        again=self.lifecycle.request_deletion(user_id,"final request")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:cursor.execute("UPDATE account_deletion_requests SET scheduled_for=NOW()-INTERVAL '1 second' WHERE user_id=%s",(user_id,))
        result=self.lifecycle.cleanup_due_deletions();self.assertIn(user_id,result["completedUserIds"])
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT status,email FROM users WHERE id=%s",(user_id,));status,email=cursor.fetchone();self.assertEqual(status,"deleted");self.assertTrue(email.endswith("@invalid.local"));cursor.execute("SELECT status FROM media_assets WHERE id=%s",(asset["id"],));self.assertEqual(cursor.fetchone()[0],"deleted")

    def test_rate_limit_headers_legal_pages_and_backup_manifest(self):
        with socket.socket() as probe:probe.bind(("127.0.0.1",0));port=probe.getsockname()[1]
        environment={**os.environ,**self.environment,"READER_HOST":"127.0.0.1","READER_PORT":str(port)};process=subprocess.Popen([sys.executable,str(ROOT/"tools/reader_server.py")],cwd=ROOT,env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        connection=None
        try:
            deadline=time.time()+10
            while time.time()<deadline:
                try:
                    connection=http.client.HTTPConnection("127.0.0.1",port,timeout=1);connection.request("GET","/terms");response=connection.getresponse();body=response.read();self.assertEqual(response.status,200);self.assertIn("拾页用户协议",body.decode());self.assertEqual(response.getheader("X-Frame-Options"),"DENY");self.assertIn("default-src 'self'",response.getheader("Content-Security-Policy"));connection.close();connection=None;break
                except OSError:time.sleep(.1)
            else:self.fail("security server did not start")
            statuses=[]
            for _ in range(11):
                connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("POST","/api/auth/login",json.dumps({"email":"owner@local.test","password":"wrong"}),{"Content-Type":"application/json","X-Device-Id":"phase6-rate-device-1"});response=connection.getresponse();statuses.append(response.status);response.read();connection.close();connection=None
            self.assertEqual(statuses[-1],429)
        finally:
            if connection:connection.close()
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()
            if process.stderr:process.stderr.close()
        with tempfile.TemporaryDirectory(prefix="shiyue-backup-") as backup_root:
            process=subprocess.run([sys.executable,str(ROOT/"tools/saas_backup.py"),"--database-url",TEST_URL,"--media-root",str(self.media_root),"--output-root",backup_root],cwd=ROOT,capture_output=True,text=True,check=True)
            result=json.loads(process.stdout);folder=Path(result["backup"]);self.assertTrue((folder/"database.dump").is_file());self.assertTrue((folder/"media-manifest.json").is_file());self.assertEqual(result["databaseSha256"],__import__("hashlib").sha256((folder/"database.dump").read_bytes()).hexdigest())

if __name__=="__main__":unittest.main()
