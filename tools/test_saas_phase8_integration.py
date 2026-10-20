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
from unittest.mock import patch
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from saas_auth import SaaSError, SaaSService, new_id, token_hash, utcnow
from saas_catalog import CatalogService
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
        cls.fake_whisper=Path(cls.temp.name)/"fake_whisper.py";cls.fake_whisper.write_text("#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\nif '-pp' in sys.argv:\n print('whisper_print_progress_callback: progress =  40%',file=sys.stderr,flush=True)\n print('whisper_print_progress_callback: progress = 100%',file=sys.stderr,flush=True)\nprefix=Path(sys.argv[sys.argv.index('-of')+1])\nprefix.with_suffix('.json').write_text(json.dumps({'transcription':[{'text':'Hello private audio.', 'offsets':{'from':0,'to':1200}, 'tokens':[{'text':' Hello','p':0.9}]},{'text':'Second audio sentence!', 'offsets':{'from':3000,'to':4200}, 'tokens':[{'text':' Second','p':0.9}]}]}))\n",encoding="utf-8");cls.fake_whisper.chmod(0o755)
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
        self.assertFalse(created["idempotent"]);self.assertTrue(duplicate["idempotent"]);self.assertEqual(created["task"]["id"],duplicate["task"]["id"]);self.assertEqual(created["task"]["planVersion"],"free-v2")
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

    def test_abandoned_running_import_is_reclaimed_and_completed(self):
        owner=str(self.owner["id"])
        created=self.imports.create(owner,"text","中断恢复","resume.txt","resume-stale-task")
        task_id=created["task"]["id"]
        self.imports.upload(owner,task_id,"resume.txt",b"Recovery works. Second sentence.","text/plain")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE workspace_import_tasks SET status='running',progress=45,updated_at=NOW()-INTERVAL '4 hours' WHERE id=%s",(task_id,))
        resumed=self.imports.complete(owner,task_id)
        self.assertEqual(resumed["task"]["status"],"complete")
        self.assertEqual(resumed["task"]["progress"],100)

    def test_mp3_reservation_cancellation_and_source_asset_release(self):
        owner=str(self.owner["id"])
        created=self.imports.create(owner,"mp3","试听","sample.mp3","mp3-task-1")
        task_id=created["task"]["id"]
        usage=self.memberships.usage(owner);mp3=next(row for row in usage["usage"] if row["feature"]=="mp3_imports");self.assertEqual(mp3["reserved"],0)
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
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT data_json FROM content_books WHERE id=%s",(completed["task"]["outputBookId"],))
                stored=self.accounts._one(cursor)["data_json"]
        self.assertEqual(stored["whisper"]["timestampMethod"],"segment-estimate")
        self.assertEqual(stored["whisper"]["timingVersion"],3)
        usage=self.memberships.usage(owner);mp3=next(row for row in usage["usage"] if row["feature"]=="mp3_imports")
        self.assertEqual(mp3["used"],0);self.assertEqual(mp3["reserved"],0)
        self.assertEqual(next(row for row in usage["usage"] if row["feature"]=="audio_library_capacity")["used"],1)

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
        self.assertFalse(reader["canWatchHdVideo"])
        self.assertEqual([sentence["text"] for sentence in reader["sentences"]],["Hello private audio."])
        self.assertTrue(all(word["end"]<=reader["duration"] for sentence in reader["sentences"] for word in sentence["words"]))
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT data_json FROM content_books WHERE id=%s",(completed["task"]["outputBookId"],))
                stored=self.accounts._one(cursor)["data_json"]
        self.assertEqual(stored["segmentation"]["wordsOutsideMedia"],3)
        self.assertTrue(self.media.stream(owner,asset_id,"audio")["path"].is_file());self.assertTrue(self.media.stream(owner,asset_id,"cover")["path"].is_file())
        self.assertTrue(self.media.stream(owner,asset_id,"low")["path"].is_file())
        with self.assertRaises(SaaSError) as high:self.media.stream(owner,asset_id)
        self.assertEqual(high.exception.code,"video_quality_membership_required")
        self.memberships.create_manual_order(str(self.admin["id"]),owner,"advanced-v1",utcnow()-timedelta(minutes=1),utcnow()+timedelta(days=30))
        self.assertTrue(self.workspace.reader(owner,completed["task"]["outputBookId"])["book"]["canWatchHdVideo"])
        self.assertTrue(self.media.stream(owner,asset_id)["path"].is_file())
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:cursor.execute("UPDATE subscriptions SET ends_at=NOW()-INTERVAL '1 second' WHERE user_id=%s",(owner,))
        with self.assertRaises(SaaSError) as expired:self.media.stream(owner,asset_id)
        self.assertEqual(expired.exception.code,"video_quality_membership_required")
        with self.assertRaises(SaaSError) as denied:self.media.stream(other,asset_id,"audio")
        self.assertEqual(denied.exception.code,"media_access_denied")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT variant_name FROM asset_variants WHERE asset_id=%s AND deleted_at IS NULL ORDER BY variant_name",(asset_id,));self.assertEqual([row["variant_name"] for row in self.accounts._many(cursor)],["audio","cover","low"])
        usage=self.memberships.usage(owner);video=next(row for row in usage["usage"] if row["feature"]=="video_imports");storage=next(row for row in usage["usage"] if row["feature"]=="storage_bytes")
        self.assertEqual(video["used"],0);self.assertEqual(video["reserved"],0);self.assertGreater(storage["used"],sample.stat().st_size)
        self.assertEqual(next(row for row in usage["usage"] if row["feature"]=="video_library_capacity")["used"],1)

    def test_video_processing_failure_releases_reservation_and_preserves_retry_source(self):
        owner=str(self.owner["id"]);created=self.video_imports.create(owner,"video","损坏视频","broken.mp4","broken-video-task");task_id=created["task"]["id"]
        uploaded=self.video_imports.upload(owner,task_id,"broken.mp4",b"not-a-video","video/mp4")
        with self.assertRaises(SaaSError) as failed:self.video_imports.complete(owner,task_id)
        self.assertEqual(failed.exception.code,"video_processing_failed")
        task=self.video_imports.list(owner)["tasks"][0];self.assertEqual(task["status"],"failed")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT status FROM media_assets WHERE id=%s",(uploaded["sourceAssetId"],));self.assertEqual((self.accounts._one(cursor)or{})["status"],"active")
        usage=self.memberships.usage(owner);video=next(row for row in usage["usage"] if row["feature"]=="video_imports");storage=next(row for row in usage["usage"] if row["feature"]=="storage_bytes")
        self.assertEqual(video["used"],0);self.assertEqual(video["reserved"],0);self.assertEqual(storage["used"],len(b"not-a-video"))

    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg is required for the native YouTube acceptance test")
    def test_youtube_native_downloader_reuses_video_processor_and_preserves_captions(self):
        owner,other=str(self.owner["id"]),str(self.other["id"]);url="https://www.youtube.com/watch?v=fake123";progress_events=[];update=self.youtube_imports._update_progress
        created=self.youtube_imports.create(owner,"youtube","","","native-youtube-task",url)
        with patch.object(self.youtube_imports,"_update_progress",side_effect=lambda *args:(progress_events.append(args),update(*args))[1]):completed=self.youtube_imports.complete(owner,created["task"]["id"])
        self.assertEqual(completed["task"]["status"],"complete");asset_id=completed["task"]["sourceAssetId"]
        self.assertIn(70,[event[1] for event in progress_events]);self.assertIn(85,[event[1] for event in progress_events])
        reader=self.workspace.reader(owner,completed["task"]["outputBookId"])["book"];self.assertEqual(reader["resourceType"],"youtube");self.assertEqual(reader["title"],"Private YouTube")
        summary=self.workspace.list_books(owner)["books"][0]
        self.assertEqual(summary["series"],"Test Channel")
        self.assertEqual(summary["coverUrl"],f"/api/media/{asset_id}?variant=cover")
        catalog=CatalogService(self.accounts,self.memberships)
        with self.assertRaises(SaaSError) as denied:
            catalog.review(str(self.admin["id"]),summary["id"],"licensed","published")
        self.assertEqual(denied.exception.code,"private_content")
        self.assertEqual(catalog.review_sources()["sources"],[])
        migration=(Path(__file__).parent/"saas_migrations/0036_youtube_channel_series.sql").read_text()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE content_books SET series='私人导入' WHERE id=%s",(summary["id"],))
                cursor.execute(migration)
        self.assertEqual(self.workspace.list_books(owner)["books"][0]["series"],"Test Channel")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE content_books SET series='Custom Series' WHERE id=%s",(summary["id"],))
                cursor.execute(migration)
        self.assertEqual(self.workspace.list_books(owner)["books"][0]["series"],"Custom Series")
        variants=reader["mediaAssets"][0]["variants"];self.assertEqual([item["name"] for item in variants],["audio","cover","low","subtitles-en","subtitles-zh-CN"])
        self.assertTrue(self.media.stream(owner,asset_id,"subtitles-en")["path"].is_file())
        with self.assertRaises(SaaSError) as denied:self.media.stream(other,asset_id,"subtitles-zh-CN")
        self.assertEqual(denied.exception.code,"media_access_denied")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT data_json FROM content_books WHERE id=%s",(completed["task"]["outputBookId"],));data=(self.accounts._one(cursor)or{})["data_json"]
        data=data if isinstance(data,dict) else json.loads(data);self.assertEqual(data["youtube"]["youtubeId"],"fake123");self.assertTrue(data["youtube"]["youtubeSubtitleDownloaded"]);self.assertTrue(data["youtube"]["youtubeChineseSubtitleDownloaded"])
        usage=self.memberships.usage(owner);youtube=next(row for row in usage["usage"] if row["feature"]=="youtube_imports");video=next(row for row in usage["usage"] if row["feature"]=="video_imports")
        self.assertEqual(youtube["used"],0);self.assertEqual(youtube["reserved"],0);self.assertEqual(video["used"],0)

    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg required")
    def test_official_import_review_storage_and_permanent_delete(self):
        admin,owner=str(self.admin["id"]),str(self.owner["id"])
        official=WorkspaceImportService(self.accounts,self.memberships,self.media,whisper_cli=self.fake_whisper,whisper_model=self.fake_model,audio_duration=lambda path:2.0,yt_dlp=self.fake_ytdlp,node=Path(sys.executable),official=True)
        with self.assertRaises(SaaSError) as denied:
            official.create(owner,"text","Denied","test.txt","official-denied")
        self.assertEqual(denied.exception.code,"admin_required")
        private=self.imports.create(owner,"text","Private","private.txt","private-forged",metadata={"officialImport":True})["task"]
        self.imports.upload(owner,private["id"],"private.txt",b"Keep private.","text/plain")
        private_book=self.imports.complete(owner,private["id"])["task"]["outputBookId"]
        task=official.create(admin,"youtube","Official video","","official-video","https://youtu.be/fake123")["task"]
        with self.assertRaises(SaaSError):self.imports.complete(admin,task["id"])
        with patch.object(official,"_run_ytdlp",wraps=official._run_ytdlp) as downloader:
            completed=official.complete(admin,task["id"])["task"]
        download_args=next(call.args[0] for call in downloader.call_args_list if "-f" in call.args[0])
        self.assertIn("height<=480",download_args[download_args.index("-f")+1])
        self.assertNotIn("720",download_args[download_args.index("-f")+1])
        book_id,asset_id=completed["outputBookId"],completed["sourceAssetId"]
        catalog=CatalogService(self.accounts,self.memberships)
        sources=catalog.review_sources()["sources"]
        self.assertEqual([row["sourceBookId"] for row in sources],[book_id])
        self.assertEqual(sources[0]["publicationStatus"],"draft")
        self.assertEqual(catalog.catalog(owner)["books"],[])
        self.assertEqual(self.workspace.list_books(admin)["books"],[])
        self.assertEqual(self.imports.list(admin)["total"],0)
        self.assertEqual(official.list(admin)["total"],1)
        # A previously approved personal import becomes private again; official imports stay registered.
        migration=(Path(__file__).parent/"saas_migrations/0037_private_import_ownership.sql").read_text()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO catalog_books(id,source_content_book_id,title,resource_type,rights_status,publication_status) VALUES(%s,%s,'Private','book','licensed','published')",(new_id(),private_book))
                cursor.execute("UPDATE content_books SET visibility='published' WHERE id=%s",(private_book,))
                cursor.execute(migration);cursor.execute(migration)
        self.assertEqual(self.workspace.list_books(owner)["books"][0]["id"],private_book)
        self.assertEqual([row["sourceBookId"] for row in catalog.review_sources()["sources"]],[book_id])
        usage=self.memberships.usage(admin)["usage"]
        self.assertEqual(next(row for row in usage if row["feature"]=="storage_bytes")["used"],0)
        self.assertEqual(next(row for row in usage if row["feature"]=="video_library_capacity")["used"],0)
        detail=self.media.user_storage(admin)
        self.assertEqual(detail["total"],1);video=detail["videos"][0]
        self.assertEqual(video["bookId"],book_id);self.assertTrue(video["contentPath"])
        self.assertEqual(video["scope"],"official")
        paths=[self.root/video["storagePath"]]+[self.root/v["storagePath"] for v in video["variants"]]
        low=next(self.root/v["storagePath"] for v in video["variants"] if v["name"]=="low")
        probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","json",str(low)]))["streams"][0]
        self.assertLessEqual(probe["height"],240);self.assertLessEqual(probe["width"],320)
        summary=next(row for row in self.media.user_storage()["users"] if row["id"]==admin)
        self.assertEqual(summary["totalBytes"],sum(path.stat().st_size for path in paths))
        published=catalog.review(admin,book_id,"licensed","published")["book"]
        expected=f"/api/media/{asset_id}?variant=cover&trialBook={published['id']}"
        self.assertEqual(catalog.detail(published["id"],owner)["book"]["coverUrl"],expected)
        self.assertTrue(self.media.trial_stream(owner,asset_id,published["id"],"cover")["path"].is_file())
        with self.assertRaises(SaaSError):catalog.delete_book(admin,book_id,"wrong title")
        deleted=catalog.delete_book(admin,book_id,"Official video")
        self.assertEqual(deleted["pendingFiles"],0);self.assertGreater(deleted["removedFiles"],0)
        self.assertTrue(all(not path.exists() for path in paths))
        self.assertEqual(self.media.user_storage(admin)["total"],0)
        self.assertEqual(self.workspace.list_books(owner)["books"][0]["id"],private_book)
        private_asset=self.workspace.reader(owner,private_book)["book"]["mediaAssets"][0]["id"]
        private_path=self.media.stream(owner,private_asset)["path"]
        self.workspace.delete_book(owner,private_book,"Private")
        self.assertFalse(private_path.exists())

    def test_youtube_download_failure_releases_reservation(self):
        owner=str(self.owner["id"]);url="https://youtu.be/failure"
        created=self.failing_youtube_imports.create(owner,"youtube","Failure","","failed-youtube-task",url)
        with self.assertRaises(SaaSError) as failed:self.failing_youtube_imports.complete(owner,created["task"]["id"])
        self.assertEqual(failed.exception.code,"youtube_download_failed")
        usage=self.memberships.usage(owner);youtube=next(row for row in usage["usage"] if row["feature"]=="youtube_imports");self.assertEqual(youtube["used"],0);self.assertEqual(youtube["reserved"],0)

    def test_paginated_history_and_delete_invalid_are_owner_scoped(self):
        owner,other=str(self.owner["id"]),str(self.other["id"])
        ids=[]
        for index in range(11):
            ids.append(self.imports.create(owner,"text",f"Task {index}","test.txt",f"page-{index}")["task"]["id"])
        foreign=self.imports.create(other,"text","Other","test.txt","other-failed")["task"]["id"]
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE workspace_import_tasks SET status='failed' WHERE id=ANY(%s)",(ids[:4]+[foreign],))
                cursor.execute("UPDATE workspace_import_tasks SET status='running' WHERE id=%s",(ids[4],))
                cursor.execute("UPDATE workspace_import_tasks SET status='cancelled' WHERE id=%s",(ids[5],))
        first=self.imports.list(owner,8,1);second=self.imports.list(owner,8,2)
        self.assertEqual(first["total"],11);self.assertEqual(first["failedCount"],4);self.assertEqual(first["invalidCount"],5)
        self.assertEqual(len(first["tasks"]),8);self.assertEqual(len(second["tasks"]),3)
        self.assertFalse({t["id"] for t in first["tasks"]}&{t["id"] for t in second["tasks"]})
        self.assertEqual(self.imports.delete_invalid(owner)["deletedCount"],5)
        self.assertEqual(self.imports.delete_invalid(owner)["deletedCount"],0)
        self.assertEqual(self.imports.list(owner)["total"],6)
        self.assertEqual(self.imports.list(other)["failedCount"],1)
        remaining=self.imports.list(owner)
        self.assertEqual(remaining["invalidCount"],0)
        self.assertEqual({t["id"] for t in remaining["tasks"]},set(ids[4:])- {ids[5]})
        cancelled=self.imports.create(owner,"text","Cancelled only","cancel.txt","cancel-only")["task"]["id"]
        self.imports.cancel(owner,cancelled)
        self.assertEqual(self.imports.list(owner)["failedCount"],0)
        self.assertEqual(self.imports.list(owner)["invalidCount"],1)
        self.assertEqual(self.imports.delete_invalid(owner)["deletedCount"],1)
        self.assertEqual(self.imports.list(owner,8,3)["tasks"],[])
        with self.assertRaises(SaaSError):self.imports.list(owner,"invalid",1)

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
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("GET","/api/workspace/imports?page=2&limit=1",headers={"Cookie":cookies});response=connection.getresponse();page=json.loads(response.read());self.assertEqual(response.status,200);self.assertEqual(page["total"],1);self.assertEqual(page["tasks"],[]);connection.close();connection=None
            for headers,expected in [({},401),({"Cookie":cookies},403),({"Cookie":cookies,"X-CSRF-Token":csrf},200)]:
                connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connection.request("POST","/api/workspace/imports/delete-invalid","{}",{"Content-Type":"application/json",**headers});response=connection.getresponse();data=json.loads(response.read());self.assertEqual(response.status,expected,data);connection.close();connection=None
            def request(method,path,body=None,headers=None):
                client=http.client.HTTPConnection("127.0.0.1",port,timeout=10)
                try:
                    client.request(method,path,body,headers or {})
                    response=client.getresponse();return response.status,json.loads(response.read()),response.getheaders()
                finally:client.close()
            self.assertEqual(request("GET","/api/admin/content-imports")[0],401)
            self.assertEqual(request("GET","/api/admin/content-imports",headers={"Cookie":cookies})[0],403)
            self.assertEqual(request("GET","/api/admin/media-assets",headers={"Cookie":cookies})[0],403)
            self.assertEqual(request("DELETE",f"/api/media/{completed['task']['sourceAssetId']}",headers={"Cookie":cookies,"X-CSRF-Token":csrf})[0],409)
            status,_,headers=request("POST","/api/auth/login",json.dumps({"email":"admin@local.test","password":"phase8 admin password"}),{"Content-Type":"application/json","X-Device-Id":"phase8-admin-http"})
            self.assertEqual(status,200)
            cookies="; ".join(value.split(";",1)[0] for name,value in headers if name.lower()=="set-cookie")
            csrf=next(value.split("=",1)[1] for value in cookies.split("; ") if value.startswith("shiyue_csrf="))
            admin_headers={"Content-Type":"application/json","Cookie":cookies,"X-CSRF-Token":csrf}
            self.assertEqual(request("POST","/api/admin/content-imports","{}",{"Content-Type":"application/json","Cookie":cookies})[0],403)
            status,created,_=request("POST","/api/admin/content-imports",json.dumps({"kind":"text","title":"Official HTTP","filename":"official.txt","idempotencyKey":"http-official"}),admin_headers)
            self.assertEqual(status,201,created);official_id=created["task"]["id"]
            status,_,_=request("POST",f"/api/admin/content-imports/{official_id}/upload",b"Official upload.",{**admin_headers,"Content-Type":"text/plain","X-Upload-Filename":"official.txt"})
            self.assertEqual(status,200)
            status,done,_=request("POST",f"/api/admin/content-imports/{official_id}/complete","{}",admin_headers)
            self.assertEqual(status,200,done);self.assertEqual(done["task"]["status"],"complete")
            self.assertEqual(request("GET","/api/admin/content-imports",headers=admin_headers)[1]["total"],1)
            self.assertEqual(request("GET","/api/workspace/imports",headers=admin_headers)[1]["total"],0)
            self.assertEqual(len(request("GET","/api/admin/catalog/sources",headers=admin_headers)[1]["sources"]),1)
            status,summary,_=request("GET","/api/admin/media-assets",headers=admin_headers)
            self.assertEqual(status,200);self.assertEqual(len(summary["users"]),2)
            self.assertEqual(request("POST","/api/admin/catalog/delete",json.dumps({"sourceBookId":done["task"]["outputBookId"],"confirmTitle":"Official HTTP"}),admin_headers)[0],200)
        finally:
            if connection:connection.close()
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()
            if process.stderr:process.stderr.close()

if __name__=="__main__":unittest.main()
