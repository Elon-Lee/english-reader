#!/usr/bin/env python3
"""Acceptance tests for PostgreSQL-native private import tasks."""
from __future__ import annotations

import http.client
import json
import os
import shutil
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
from saas_imports import WorkspaceImportService
from saas_media import MediaService
from saas_membership import MembershipService
from saas_workspace import WorkspaceService

TEST_URL=os.environ.get("SHIYUE_SAAS_TEST_DATABASE_URL","")

def assert_safe_database(url:str)->None:
    if not urlsplit(url).path.rsplit("/",1)[-1].endswith("_test"):
        raise RuntimeError("SHIYUE_SAAS_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用数据库。")

class WorkspaceImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert_safe_database(TEST_URL);cls.temp=tempfile.TemporaryDirectory(prefix="shiyue-phase8-");cls.root=Path(cls.temp.name)/"media";cls.root.mkdir()
        cls.environment={"DATABASE_URL":TEST_URL,"SHIYUE_SAAS_ENABLED":"1","SESSION_SECRET":"test-only-session-secret-that-is-at-least-32-characters","BOOTSTRAP_ADMIN_EMAIL":"admin@local.test","BOOTSTRAP_ADMIN_PASSWORD":"phase8 admin password","MEDIA_ROOT":str(cls.root)}
        cls.fake_ocr=Path(cls.temp.name)/"fake_pdf_ocr.py";cls.fake_ocr.write_text("#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\nPath(sys.argv[2]).write_text(json.dumps([{'page':1,'lines':[{'text':'PDF native first sentence.'},{'text':'PDF native second sentence!'}]}]))\n",encoding="utf-8");cls.fake_ocr.chmod(0o755)
        cls.fake_model=Path(cls.temp.name)/"fake-model.bin";cls.fake_model.write_bytes(b"model")
        cls.fake_whisper=Path(cls.temp.name)/"fake_whisper.py";cls.fake_whisper.write_text("#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\nprefix=Path(sys.argv[sys.argv.index('-of')+1])\nprefix.with_suffix('.json').write_text(json.dumps({'transcription':[{'text':'Hello private audio.', 'offsets':{'from':0,'to':1200}, 'tokens':[{'text':' Hello','p':0.9}]},{'text':'Second audio sentence!', 'offsets':{'from':3000,'to':4200}, 'tokens':[{'text':' Second','p':0.9}]}]}))\n",encoding="utf-8");cls.fake_whisper.chmod(0o755)
        cls.fake_ytdlp=Path(cls.temp.name)/"fake_ytdlp.py";cls.fake_ytdlp.write_text("""#!/usr/bin/env python3
import json,subprocess,sys
from pathlib import Path
args=sys.argv[1:]
if '--dump-single-json' in args:
 print(json.dumps({'id':'fake123','title':'Private YouTube','channel':'Test Channel','duration':2,'subtitles':{'en':[{'ext':'vtt','url':'https://example.test/caption?lang=en'}]},'automatic_captions':{'zh-CN':[{'ext':'vtt','url':'https://example.test/caption?lang=zh-CN'}]}}));raise SystemExit
template=Path(args[args.index('-o')+1])
if '--skip-download' in args:
 target=Path(str(template).replace('%(ext)s','srt'));target.parent.mkdir(parents=True,exist_ok=True);target.write_text('1\\n00:00:00,000 --> 00:00:01,000\\nCaption text.\\n');raise SystemExit
target=Path(str(template).replace('%(ext)s','mp4'));target.parent.mkdir(parents=True,exist_ok=True)
subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=c=green:s=320x180:d=2','-f','lavfi','-i','sine=frequency=500:duration=2','-shortest','-c:v','mpeg4','-c:a','aac',str(target)],check=True)
""",encoding="utf-8");cls.fake_ytdlp.chmod(0o755)
        cls.failing_ytdlp=Path(cls.temp.name)/"failing_ytdlp.py";cls.failing_ytdlp.write_text("#!/usr/bin/env python3\nimport sys\nprint('ERROR: simulated yt-dlp failure',file=sys.stderr)\nraise SystemExit(2)\n",encoding="utf-8");cls.failing_ytdlp.chmod(0o755)
        cls.accounts=SaaSService(TEST_URL,cls.environment);cls.accounts.migrate();cls.memberships=MembershipService(cls.accounts);cls.media=MediaService(cls.accounts,cls.memberships,cls.root);cls.imports=WorkspaceImportService(cls.accounts,cls.memberships,cls.media);cls.pdf_imports=WorkspaceImportService(cls.accounts,cls.memberships,cls.media,cls.fake_ocr);cls.mp3_imports=WorkspaceImportService(cls.accounts,cls.memberships,cls.media,whisper_cli=cls.fake_whisper,whisper_model=cls.fake_model,audio_duration=lambda path:4.2);cls.video_imports=WorkspaceImportService(cls.accounts,cls.memberships,cls.media,whisper_cli=cls.fake_whisper,whisper_model=cls.fake_model,audio_duration=lambda path:2.0);cls.youtube_imports=WorkspaceImportService(cls.accounts,cls.memberships,cls.media,whisper_cli=cls.fake_whisper,whisper_model=cls.fake_model,audio_duration=lambda path:2.0,yt_dlp=cls.fake_ytdlp,node=Path(sys.executable));cls.failing_youtube_imports=WorkspaceImportService(cls.accounts,cls.memberships,cls.media,whisper_cli=cls.fake_whisper,whisper_model=cls.fake_model,audio_duration=lambda path:2.0,yt_dlp=cls.failing_ytdlp,node=Path(sys.executable));cls.workspace=WorkspaceService(cls.accounts)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        for path in self.root.rglob("*"):
            if path.is_file():path.unlink()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""TRUNCATE TABLE workspace_import_tasks,workspace_activity_events,workspace_progress,workspace_settings,security_events,account_deletion_requests,asset_usage,asset_variants,media_assets,admin_audit_logs,platform_settings,
                member_invite_rewards,member_invites,member_invite_allowances,reward_activity_events,reward_daily_activity,reward_redemptions,reward_ledger,checkins,
                official_book_unlocks,user_library,catalog_book_tags,catalog_books,catalog_tags,catalog_series,membership_audit,usage_ledger,quota_reservations,usage_periods,subscriptions,manual_orders,assets,
                content_sentence_grammar,content_learning_daily,content_word_annotations,content_vocabulary,content_books,invitation_uses,invitations,password_reset_tokens,email_verifications,user_sessions,devices,user_roles,users,roles RESTART IDENTITY CASCADE""")
        self.admin=self.accounts.bootstrap_admin();assert self.admin
        invite=self.accounts.create_invitation("IMPORT-TEST",max_uses=10,created_by=str(self.admin["id"]))
        self.owner=self.accounts.register("import-owner@local.test","import owner password",invite["code"])["user"]
        self.other=self.accounts.register("import-other@local.test","import other password",invite["code"])["user"]
        self.verify(str(self.owner["id"]));self.verify(str(self.other["id"]))

    def verify(self,user_id:str)->None:
        raw="verify-"+new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:cursor.execute("INSERT INTO email_verifications(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",(new_id(),user_id,token_hash(raw),utcnow()+timedelta(days=1)))
        self.accounts.verify_email(raw)

    def test_text_task_upload_complete_idempotency_and_owner_isolation(self):
        owner,other=str(self.owner["id"]),str(self.other["id"])
        created=self.imports.create(owner,"text","我的测试文本","lesson.md","text-task-1")
        duplicate=self.imports.create(owner,"text","ignored","lesson.md","text-task-1")
        self.assertFalse(created["idempotent"]);self.assertTrue(duplicate["idempotent"]);self.assertEqual(created["task"]["id"],duplicate["task"]["id"]);self.assertEqual(created["task"]["planVersion"],"free-v1")
        task_id=created["task"]["id"]
        uploaded=self.imports.upload(owner,task_id,"lesson.md",b"First private sentence.\n\nSecond private sentence!","text/markdown")
        self.assertEqual(uploaded["status"],"queued")
        with self.assertRaises(SaaSError) as denied:self.imports.complete(other,task_id)
        self.assertEqual(denied.exception.code,"import_task_not_found")
        completed=self.imports.complete(owner,task_id)
        self.assertEqual(completed["task"]["status"],"complete")
        book_id=completed["task"]["outputBookId"]
        reader=self.workspace.reader(owner,book_id)["book"]
        self.assertEqual(len(reader["sentences"]),2)
        self.assertEqual(reader["mediaAssets"][0]["id"],completed["task"]["sourceAssetId"])
        self.assertEqual(self.workspace.list_books(other)["books"],[])
        repeat=self.imports.complete(owner,task_id);self.assertTrue(repeat["idempotent"])

    def test_mp3_reservation_cancellation_and_source_asset_release(self):
        owner=str(self.owner["id"])
        created=self.imports.create(owner,"mp3","试听","sample.mp3","mp3-task-1")
        task_id=created["task"]["id"]
        usage=self.memberships.usage(owner);mp3=next(row for row in usage["usage"] if row["feature"]=="mp3_imports");self.assertEqual(mp3["reserved"],1)
        self.imports.upload(owner,task_id,"sample.mp3",b"not-a-real-mp3","audio/mpeg")
        cancelled=self.imports.cancel(owner,task_id);self.assertEqual(cancelled["task"]["status"],"cancelled")
        usage=self.memberships.usage(owner);mp3=next(row for row in usage["usage"] if row["feature"]=="mp3_imports");storage=next(row for row in usage["usage"] if row["feature"]=="storage_bytes")
        self.assertEqual(mp3["reserved"],0);self.assertEqual(storage["used"],0)

    def test_mp3_native_whisper_processor_creates_timed_private_audio_book(self):
        owner=str(self.owner["id"])
        created=self.mp3_imports.create(owner,"mp3","私人音频","native.mp3","native-mp3-task")
        task_id=created["task"]["id"]
        self.mp3_imports.upload(owner,task_id,"native.mp3",b"fake-mp3","audio/mpeg")
        completed=self.mp3_imports.complete(owner,task_id)
        self.assertEqual(completed["task"]["status"],"complete")
        reader=self.workspace.reader(owner,completed["task"]["outputBookId"])["book"]
        self.assertEqual(reader["resourceType"],"audio")
        self.assertEqual(round(reader["duration"],1),4.2)
        self.assertEqual([sentence["text"] for sentence in reader["sentences"]],["Hello private audio.","Second audio sentence!"])
        self.assertTrue(reader["sentences"][0]["words"][0]["start"]>=0)
        usage=self.memberships.usage(owner);mp3=next(row for row in usage["usage"] if row["feature"]=="mp3_imports")
        self.assertEqual(mp3["used"],1);self.assertEqual(mp3["reserved"],0)

    def test_pdf_document_uses_native_ocr_processor_and_creates_private_book(self):
        owner=str(self.owner["id"])
        created=self.pdf_imports.create(owner,"document","PDF native","native.pdf","pdf-task-1")
        task_id=created["task"]["id"]
        self.pdf_imports.upload(owner,task_id,"native.pdf",b"%PDF-fake","application/pdf")
        completed=self.pdf_imports.complete(owner,task_id)
        self.assertEqual(completed["task"]["status"],"complete")
        reader=self.workspace.reader(owner,completed["task"]["outputBookId"])["book"]
        self.assertEqual(reader["resourceType"],"document")
        self.assertEqual([item["text"] for item in reader["sentences"]],["PDF native first sentence.","PDF native second sentence!"])

    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg is required for the native video acceptance test")
    def test_video_native_ffmpeg_processor_registers_variants_and_isolates_tenant(self):
        owner,other=str(self.owner["id"]),str(self.other["id"]);sample=Path(self.temp.name)/"sample-video.mp4"
        subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i","color=c=blue:s=320x180:d=2","-f","lavfi","-i","sine=frequency=440:duration=2","-shortest","-c:v","mpeg4","-c:a","aac",str(sample)],check=True,timeout=30)
        created=self.video_imports.create(owner,"video","私人视频","lesson.mp4","native-video-task");task_id=created["task"]["id"]
        self.video_imports.upload(owner,task_id,"lesson.mp4",sample.read_bytes(),"video/mp4")
        completed=self.video_imports.complete(owner,task_id);self.assertEqual(completed["task"]["status"],"complete")
        asset_id=completed["task"]["sourceAssetId"];reader=self.workspace.reader(owner,completed["task"]["outputBookId"])["book"]
        self.assertEqual(reader["resourceType"],"video");self.assertEqual(round(reader["duration"],1),2.0)
        self.assertEqual([sentence["text"] for sentence in reader["sentences"]],["Hello private audio.","Second audio sentence!"])
        self.assertTrue(self.media.stream(owner,asset_id,"audio")["path"].is_file());self.assertTrue(self.media.stream(owner,asset_id,"cover")["path"].is_file())
        with self.assertRaises(SaaSError) as denied:self.media.stream(other,asset_id,"audio")
        self.assertEqual(denied.exception.code,"media_access_denied")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT variant_name FROM asset_variants WHERE asset_id=%s AND deleted_at IS NULL ORDER BY variant_name",(asset_id,));self.assertEqual([row["variant_name"] for row in self.accounts._many(cursor)],["audio","cover"])
        usage=self.memberships.usage(owner);video=next(row for row in usage["usage"] if row["feature"]=="video_imports");storage=next(row for row in usage["usage"] if row["feature"]=="storage_bytes")
        self.assertEqual(video["used"],1);self.assertEqual(video["reserved"],0);self.assertGreater(storage["used"],sample.stat().st_size)

    def test_video_processing_failure_releases_quota_and_source_space(self):
        owner=str(self.owner["id"]);created=self.video_imports.create(owner,"video","损坏视频","broken.mp4","broken-video-task");task_id=created["task"]["id"]
        uploaded=self.video_imports.upload(owner,task_id,"broken.mp4",b"not-a-video","video/mp4")
        with self.assertRaises(SaaSError) as failed:self.video_imports.complete(owner,task_id)
        self.assertEqual(failed.exception.code,"video_processing_failed")
        task=self.video_imports.list(owner)["tasks"][0];self.assertEqual(task["status"],"failed")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT status FROM media_assets WHERE id=%s",(uploaded["sourceAssetId"],));self.assertEqual((self.accounts._one(cursor)or{})["status"],"deleted")
        usage=self.memberships.usage(owner);video=next(row for row in usage["usage"] if row["feature"]=="video_imports");storage=next(row for row in usage["usage"] if row["feature"]=="storage_bytes")
        self.assertEqual(video["used"],0);self.assertEqual(video["reserved"],0);self.assertEqual(storage["used"],0)

    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg is required for the native YouTube acceptance test")
    def test_youtube_native_downloader_reuses_video_processor_and_preserves_captions(self):
        owner,other=str(self.owner["id"]),str(self.other["id"]);url="https://www.youtube.com/watch?v=fake123"
        created=self.youtube_imports.create(owner,"youtube","","","native-youtube-task",url);completed=self.youtube_imports.complete(owner,created["task"]["id"])
        self.assertEqual(completed["task"]["status"],"complete");asset_id=completed["task"]["sourceAssetId"]
        reader=self.workspace.reader(owner,completed["task"]["outputBookId"])["book"];self.assertEqual(reader["resourceType"],"youtube");self.assertEqual(reader["title"],"Private YouTube")
        variants=reader["mediaAssets"][0]["variants"];self.assertEqual([item["name"] for item in variants],["audio","cover","subtitles-en","subtitles-zh-CN"])
        self.assertTrue(self.media.stream(owner,asset_id,"subtitles-en")["path"].is_file())
        with self.assertRaises(SaaSError) as denied:self.media.stream(other,asset_id,"subtitles-zh-CN")
        self.assertEqual(denied.exception.code,"media_access_denied")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT data_json FROM content_books WHERE id=%s",(completed["task"]["outputBookId"],));data=(self.accounts._one(cursor)or{})["data_json"]
        data=data if isinstance(data,dict) else json.loads(data);self.assertEqual(data["youtube"]["youtubeId"],"fake123");self.assertTrue(data["youtube"]["youtubeSubtitleDownloaded"]);self.assertTrue(data["youtube"]["youtubeChineseSubtitleDownloaded"])
        usage=self.memberships.usage(owner);youtube=next(row for row in usage["usage"] if row["feature"]=="youtube_imports");video=next(row for row in usage["usage"] if row["feature"]=="video_imports")
        self.assertEqual(youtube["used"],1);self.assertEqual(youtube["reserved"],0);self.assertEqual(video["used"],0)

    def test_youtube_download_failure_releases_reservation(self):
        owner=str(self.owner["id"]);url="https://youtu.be/failure"
        created=self.failing_youtube_imports.create(owner,"youtube","Failure","","failed-youtube-task",url)
        with self.assertRaises(SaaSError) as failed:self.failing_youtube_imports.complete(owner,created["task"]["id"])
        self.assertEqual(failed.exception.code,"youtube_download_failed")
        usage=self.memberships.usage(owner);youtube=next(row for row in usage["usage"] if row["feature"]=="youtube_imports");self.assertEqual(youtube["used"],0);self.assertEqual(youtube["reserved"],0)

    def test_http_text_upload_complete_and_cancel(self):
        with socket.socket() as probe:probe.bind(("127.0.0.1",0));port=probe.getsockname()[1]
        root=Path(__file__).resolve().parents[1];environment={**os.environ,**self.environment,"READER_HOST":"127.0.0.1","READER_PORT":str(port)};process=subprocess.Popen([sys.executable,str(root/"tools/reader_server.py")],cwd=root,env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True);connection=None
        try:
            deadline=time.time()+10
            while time.time()<deadline:
                try:
                    connection=http.client.HTTPConnection("127.0.0.1",port,timeout=1);connection.request("GET","/api/health");response=connection.getresponse();response.read();connection.close();connection=None
                    if response.status==200:break
                except OSError:time.sleep(.1)
            else:self.fail("import server did not start")
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("POST","/api/auth/login",json.dumps({"email":"import-owner@local.test","password":"import owner password"}),{"Content-Type":"application/json","X-Device-Id":"phase8-owner-device-1"});response=connection.getresponse();self.assertEqual(response.status,200);headers=response.getheaders();response.read();connection.close();connection=None
            cookies="; ".join(value.split(";",1)[0] for name,value in headers if name.lower()=="set-cookie");csrf=next(value.split("=",1)[1] for value in cookies.split("; ") if value.startswith("shiyue_csrf="))
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("POST","/api/workspace/imports",json.dumps({"kind":"text","title":"HTTP text","filename":"http.txt","idempotencyKey":"http-text-task"}),{"Content-Type":"application/json","Cookie":cookies,"X-CSRF-Token":csrf});response=connection.getresponse();created=json.loads(response.read());self.assertEqual(response.status,201);task_id=created["task"]["id"];connection.close();connection=None
            source=b"HTTP first. HTTP second?";connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("POST",f"/api/workspace/imports/{task_id}/upload",source,{"Content-Type":"text/plain","Content-Length":str(len(source)),"X-Upload-Filename":"http.txt","Cookie":cookies,"X-CSRF-Token":csrf});response=connection.getresponse();self.assertEqual(response.status,200);response.read();connection.close();connection=None
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("POST",f"/api/workspace/imports/{task_id}/complete",json.dumps({}),{"Content-Type":"application/json","Cookie":cookies,"X-CSRF-Token":csrf});response=connection.getresponse();completed=json.loads(response.read());self.assertEqual(response.status,200);self.assertEqual(completed["task"]["status"],"complete");connection.close();connection=None
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("GET","/api/workspace/imports",headers={"Cookie":cookies});response=connection.getresponse();tasks=json.loads(response.read());self.assertEqual(response.status,200);self.assertEqual(tasks["tasks"][0]["id"],task_id);connection.close();connection=None
        finally:
            if connection:connection.close()
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()
            if process.stderr:process.stderr.close()

if __name__=="__main__":unittest.main()
