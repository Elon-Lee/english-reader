#!/usr/bin/env python3
"""Acceptance tests for PostgreSQL owner-scoped private workspace APIs."""
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

from saas_auth import SaaSError, SaaSService, new_id, token_hash, utcnow
from saas_catalog import CatalogService
from saas_media import MediaService
from saas_membership import MembershipService
from saas_workspace import WorkspaceService

TEST_URL=os.environ.get("SHIYUE_SAAS_TEST_DATABASE_URL","")

def assert_safe_database(url:str)->None:
    if not urlsplit(url).path.rsplit("/",1)[-1].endswith("_test"):
        raise RuntimeError("SHIYUE_SAAS_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用数据库。")

class PrivateWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert_safe_database(TEST_URL);cls.temp=tempfile.TemporaryDirectory(prefix="shiyue-phase7-");cls.root=Path(cls.temp.name)/"media";cls.root.mkdir()
        cls.environment={"DATABASE_URL":TEST_URL,"SHIYUE_SAAS_ENABLED":"1","SESSION_SECRET":"test-only-session-secret-that-is-at-least-32-characters","BOOTSTRAP_ADMIN_EMAIL":"admin@local.test","BOOTSTRAP_ADMIN_PASSWORD":"phase7 admin password","MEDIA_ROOT":str(cls.root)}
        cls.accounts=SaaSService(TEST_URL,cls.environment);cls.accounts.migrate();cls.memberships=MembershipService(cls.accounts);cls.workspace=WorkspaceService(cls.accounts);cls.catalog=CatalogService(cls.accounts,cls.memberships);cls.media=MediaService(cls.accounts,cls.memberships,cls.root)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        for path in self.root.rglob("*"):
            if path.is_file():path.unlink()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""TRUNCATE TABLE workspace_activity_events,workspace_progress,workspace_settings,security_events,account_deletion_requests,asset_usage,asset_variants,media_assets,admin_audit_logs,platform_settings,
                member_invite_rewards,member_invites,member_invite_allowances,reward_activity_events,reward_daily_activity,reward_redemptions,reward_ledger,checkins,
                official_book_unlocks,user_library,catalog_book_tags,catalog_books,catalog_tags,catalog_series,membership_audit,usage_ledger,quota_reservations,usage_periods,subscriptions,manual_orders,assets,
                content_sentence_grammar,content_learning_daily,content_word_annotations,content_vocabulary,content_books,invitation_uses,invitations,password_reset_tokens,email_verifications,user_sessions,devices,user_roles,users,roles RESTART IDENTITY CASCADE""")
        self.admin=self.accounts.bootstrap_admin();assert self.admin
        invitation=self.accounts.create_invitation("WORKSPACE-TEST",max_uses=10,created_by=str(self.admin["id"]))
        self.owner=self.accounts.register("workspace-owner@local.test","workspace owner password",invitation["code"])["user"]
        self.other=self.accounts.register("workspace-other@local.test","workspace other password",invitation["code"])["user"]
        self.verify(str(self.owner["id"]));self.verify(str(self.other["id"]))
        self.book_id=self.create_private_book(str(self.owner["id"]))

    def verify(self,user_id:str)->None:
        raw="verify-"+new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:cursor.execute("INSERT INTO email_verifications(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",(new_id(),user_id,token_hash(raw),utcnow()+timedelta(days=1)))
        self.accounts.verify_email(raw)

    def create_private_book(self,owner_id:str)->str:
        book_id="private-workspace-book";data={"id":book_id,"title":"私人读物","englishTitle":"Private Reader","sentences":[{"id":"s1","text":"My private first sentence.","translation":"我的私人第一句。","words":[{"text":"My"}]},{"id":"s2","text":"My private second sentence.","words":[{"text":"My"}]}]}
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:cursor.execute("""INSERT INTO content_books(id,owner_id,title,english_title,series,level,source_type,source_path,status,visibility,cover_url,page_base_url,audio_url,pdf_url,video_url,duration,alignment,data_json,quality_json,created_at,updated_at)
            VALUES(%s,%s,'私人读物','Private Reader','Private Series','1','book','private/workspace-book','ready','private','','','','','',60,'',%s::jsonb,'{}'::jsonb,NOW(),NOW())""",(book_id,owner_id,json.dumps(data)))
        path=self.root/"private"/"workspace.mp3";path.parent.mkdir(exist_ok=True);path.write_bytes(b"private-audio")
        self.asset=self.media.register(owner_id,owner_id,"private","private/workspace.mp3","audio","audio/mpeg",content_book_id=book_id)
        return book_id

    def test_owner_isolation_reader_vocab_annotation_and_activity(self):
        owner_id,other_id=str(self.owner["id"]),str(self.other["id"])
        books=self.workspace.list_books(owner_id)["books"];self.assertEqual(books[0]["id"],self.book_id);self.assertEqual(books[0]["mediaCount"],1)
        self.assertEqual(self.workspace.list_books(other_id)["books"],[])
        reader=self.workspace.reader(owner_id,self.book_id)["book"];self.assertEqual(len(reader["sentences"]),2);self.assertEqual(reader["mediaAssets"][0]["id"],self.asset["id"])
        with self.assertRaises(SaaSError) as denied:self.workspace.reader(other_id,self.book_id)
        self.assertEqual(denied.exception.code,"workspace_book_not_found")
        saved=self.workspace.save_vocabulary(owner_id,self.book_id,"s1",0,{"word":"My","meaning":"我的"});self.assertEqual(saved["payload"]["word"],"My")
        self.workspace.annotate(owner_id,self.book_id,"s1",0,{"note":"private note"})
        self.assertEqual(len(self.workspace.vocabulary(owner_id,self.book_id)["items"]),1)
        self.assertEqual(self.workspace.annotations(owner_id,self.book_id)["items"][0]["payload"]["note"],"private note")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:cursor.execute("UPDATE content_books SET visibility='blocked' WHERE id=%s",(self.book_id,))
        self.assertEqual(self.workspace.vocabulary(owner_id)["items"],[]);self.assertEqual(self.workspace.annotations(owner_id)["items"],[])
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:cursor.execute("UPDATE content_books SET visibility='private' WHERE id=%s",(self.book_id,))
        first=self.workspace.activity(owner_id,self.book_id,600,5,"s2","workspace-event",2,1,1,1);second=self.workspace.activity(owner_id,self.book_id,600,5,"s2","workspace-event",2,1,1,1)
        self.assertFalse(first["idempotent"]);self.assertTrue(second["idempotent"])
        days=self.workspace.learning_days(owner_id)["days"];self.assertEqual(days[0]["payload"]["sentences"],5);self.assertEqual(days[0]["payload"]["lookups"],2);self.assertEqual(days[0]["payload"]["reviews"],1);self.assertEqual(days[0]["payload"]["shadow_attempts"],1);self.assertEqual(days[0]["payload"]["sessions"],1)

    def test_unlocked_official_reader_can_save_and_reload_word_rating(self):
        owner_id=str(self.owner["id"]);catalog_id="catalog-workspace-book"
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO catalog_books(id,source_content_book_id,title,english_title,rights_status,publication_status)
                VALUES(%s,%s,'官方读物','Official Reader','licensed','published')""",(catalog_id,self.book_id))
                cursor.execute("SELECT id FROM usage_periods WHERE user_id=%s ORDER BY starts_at DESC LIMIT 1",(owner_id,));period=self.accounts._one(cursor)
                cursor.execute("INSERT INTO user_library(id,user_id,catalog_book_id) VALUES(%s,%s,%s)",(new_id(),owner_id,catalog_id))
        saved=self.workspace.save_vocabulary(owner_id,catalog_id,"s1",0,{"word":"My","rating":"easy"})
        self.assertEqual(saved["bookId"],catalog_id)
        items=self.workspace.vocabulary(owner_id,catalog_id)["items"]
        self.assertEqual(items[0]["bookId"],catalog_id);self.assertEqual(items[0]["payload"]["rating"],"easy")
        progress=self.workspace.save_progress(owner_id,catalog_id,"s2");self.assertEqual(progress["lastSentenceId"],"s2")
        official_reader=self.catalog.reader(owner_id,catalog_id)["book"];self.assertEqual(official_reader["progress"]["lastSentenceId"],"s2")
        with self.assertRaises(SaaSError) as denied:self.workspace.save_vocabulary(str(self.other["id"]),catalog_id,"s1",0,{"word":"My","rating":"hard"})
        self.assertEqual(denied.exception.code,"learning_book_not_found")

    def test_trial_media_is_clipped_and_full_source_remains_private(self):
        catalog_id='catalog-trial-video'
        source=self.root/'trial-video.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=green:s=160x90:r=25','-t','10','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True,capture_output=True)
        low=self.root/'trial-low.mp4'
        subprocess.run(['ffmpeg','-v','error','-i',str(source),'-vf','scale=80:44','-c:v','libx264','-pix_fmt','yuv420p',str(low)],check=True,capture_output=True)
        owner_id,viewer_id=str(self.owner['id']),str(self.other['id'])
        asset=self.media.register(owner_id,owner_id,'private','trial-video.mp4','video','video/mp4',content_book_id=self.book_id,variants=[{'name':'low','storagePath':'trial-low.mp4','contentType':'video/mp4'}])
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE content_books SET duration=10 WHERE id=%s",(self.book_id,))
                cursor.execute("INSERT INTO catalog_books(id,source_content_book_id,title,rights_status,publication_status) VALUES(%s,%s,'Trial','licensed','published')",(catalog_id,self.book_id))
        with self.assertRaises(SaaSError):self.media.stream(viewer_id,asset['id'])
        with self.assertRaises(SaaSError) as high:self.media.trial_stream(viewer_id,asset['id'],catalog_id)
        self.assertEqual(high.exception.code,'video_quality_membership_required')
        preview=self.media.trial_stream(viewer_id,asset['id'],catalog_id,'low')
        probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(preview['path'])],check=True,capture_output=True,text=True)
        self.assertGreaterEqual(float(probe.stdout),.96)
        self.assertLessEqual(float(probe.stdout),1.04)
        reader=self.catalog.reader(viewer_id,catalog_id,trial=True)['book']
        self.assertFalse(reader['canWatchHdVideo'])
        self.assertTrue(any('trialBook=' in item['url'] for item in reader['mediaAssets']))
        self.memberships.create_manual_order(str(self.admin['id']),viewer_id,'advanced-v1',utcnow()-timedelta(minutes=1),utcnow()+timedelta(days=30))
        self.assertTrue(self.catalog.reader(viewer_id,catalog_id,trial=True)['book']['canWatchHdVideo'])
        self.assertTrue(self.media.trial_stream(viewer_id,asset['id'],catalog_id)['path'].is_file())
        with self.assertRaises(SaaSError):self.media.trial_stream(viewer_id,asset['id'],'unrelated-book')
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:cursor.execute("UPDATE catalog_books SET publication_status='archived' WHERE id=%s",(catalog_id,))
        with self.assertRaises(SaaSError):self.media.trial_stream(viewer_id,asset['id'],catalog_id)

    def test_http_workspace_media_and_reward_activity(self):
        with socket.socket() as probe:probe.bind(("127.0.0.1",0));port=probe.getsockname()[1]
        environment={**os.environ,**self.environment,"READER_HOST":"127.0.0.1","READER_PORT":str(port)};root=Path(__file__).resolve().parents[1];process=subprocess.Popen([sys.executable,str(root/"tools/reader_server.py")],cwd=root,env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True);connection=None
        try:
            deadline=time.time()+10
            while time.time()<deadline:
                try:
                    connection=http.client.HTTPConnection("127.0.0.1",port,timeout=1);connection.request("GET","/api/health");response=connection.getresponse();response.read();connection.close();connection=None
                    if response.status==200:break
                except OSError:time.sleep(.1)
            else:self.fail("workspace server did not start")
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("POST","/api/auth/login",json.dumps({"email":"workspace-owner@local.test","password":"workspace owner password"}),{"Content-Type":"application/json","X-Device-Id":"phase7-owner-device-1"});response=connection.getresponse();self.assertEqual(response.status,200);headers=response.getheaders();response.read();connection.close();connection=None
            cookies="; ".join(value.split(";",1)[0] for name,value in headers if name.lower()=="set-cookie");csrf=next(value.split("=",1)[1] for value in cookies.split("; ") if value.startswith("shiyue_csrf="))
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("GET","/api/workspace/books",headers={"Cookie":cookies});response=connection.getresponse();books=json.loads(response.read());self.assertEqual(response.status,200);self.assertEqual(books["books"][0]["id"],self.book_id);connection.close();connection=None
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("GET",f"/api/workspace/books/{self.book_id}/reader",headers={"Cookie":cookies});response=connection.getresponse();reader=json.loads(response.read());self.assertEqual(response.status,200);asset=reader["book"]["mediaAssets"][0];connection.close();connection=None
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("GET",asset["url"],headers={"Cookie":cookies,"Range":"bytes=0-6"});response=connection.getresponse();self.assertEqual(response.status,206);self.assertEqual(response.read(),b"private");connection.close();connection=None
            payload={"bookId":self.book_id,"readingSeconds":600,"sentences":5,"reviews":1,"lookups":2,"lastSentenceId":"s2","idempotencyKey":"phase7-http-activity"};connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("POST","/api/workspace/activity",json.dumps(payload),{"Content-Type":"application/json","Cookie":cookies,"X-CSRF-Token":csrf});response=connection.getresponse();activity=json.loads(response.read());self.assertEqual(response.status,200);self.assertFalse(activity["idempotent"]);self.assertEqual(activity["reviews"],1);connection.close();connection=None
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("GET","/api/rewards/status",headers={"Cookie":cookies});response=connection.getresponse();status=json.loads(response.read());self.assertEqual(response.status,200);self.assertEqual(status["balance"],4);connection.close();connection=None
        finally:
            if connection:connection.close()
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()
            if process.stderr:process.stderr.close()

if __name__=="__main__":unittest.main()
