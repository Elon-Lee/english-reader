#!/usr/bin/env python3
"""Acceptance tests for PostgreSQL-native private import tasks."""
from __future__ import annotations

import http.client
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from unittest.mock import patch
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from saas_auth import SaaSError, SaaSService, new_id, token_hash, utcnow
from saas_catalog import CatalogService
from saas_imports import WorkspaceImportService
from saas_media import MediaService
from saas_resources import ResourceService
from saas_workspace import WorkspaceService
from manual_caption_alignment import MODEL_FILE

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
 target=Path(str(template).replace('%(ext)s','srt'));target.parent.mkdir(parents=True,exist_ok=True);text='这是中文字幕。' if 'chinese' in str(template) else 'Caption text.';target.write_text('1\\n00:00:00,000 --> 00:00:01,000\\n'+text+'\\n');raise SystemExit
target=Path(str(template).replace('%(ext)s','mp4'));target.parent.mkdir(parents=True,exist_ok=True)
subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=c=green:s=320x180:d=2','-f','lavfi','-i','sine=frequency=500:duration=2','-shortest','-c:v','mpeg4','-c:a','aac',str(target)],check=True)
""",encoding="utf-8");cls.fake_ytdlp.chmod(0o755)
        cls.failing_ytdlp=Path(cls.temp.name)/"failing_ytdlp.py";cls.failing_ytdlp.write_text("#!/usr/bin/env python3\nimport sys\nprint('ERROR: simulated yt-dlp failure',file=sys.stderr)\nraise SystemExit(2)\n",encoding="utf-8");cls.failing_ytdlp.chmod(0o755)
        cls.accounts=SaaSService(TEST_URL,cls.environment);cls.accounts.migrate();cls.resources=ResourceService(cls.accounts);cls.media=MediaService(cls.accounts,cls.resources,cls.root);cls.imports=WorkspaceImportService(cls.accounts,cls.resources,cls.media);cls.pdf_imports=WorkspaceImportService(cls.accounts,cls.resources,cls.media,cls.fake_ocr);cls.mp3_imports=WorkspaceImportService(cls.accounts,cls.resources,cls.media,whisper_cli=cls.fake_whisper,whisper_model=cls.fake_model,audio_duration=lambda path:4.2);cls.video_imports=WorkspaceImportService(cls.accounts,cls.resources,cls.media,whisper_cli=cls.fake_whisper,whisper_model=cls.fake_model,audio_duration=lambda path:2.0);cls.youtube_imports=WorkspaceImportService(cls.accounts,cls.resources,cls.media,whisper_cli=cls.fake_whisper,whisper_model=cls.fake_model,audio_duration=lambda path:2.0,yt_dlp=cls.fake_ytdlp,node=Path(sys.executable));cls.failing_youtube_imports=WorkspaceImportService(cls.accounts,cls.resources,cls.media,whisper_cli=cls.fake_whisper,whisper_model=cls.fake_model,audio_duration=lambda path:2.0,yt_dlp=cls.failing_ytdlp,node=Path(sys.executable));cls.workspace=WorkspaceService(cls.accounts)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        ctc_environment=patch.dict(os.environ,{"SHIYUE_CTC_PYTHON":str(Path(self.temp.name)/"missing-ctc-python")})
        ctc_environment.start();self.addCleanup(ctc_environment.stop)
        for path in self.root.rglob("*"):
            if path.is_file():path.unlink()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""TRUNCATE TABLE workspace_import_tasks,workspace_activity_events,workspace_progress,workspace_settings,security_events,account_deletion_requests,asset_usage,asset_variants,media_assets,admin_audit_logs,platform_settings,
                member_invite_rewards,member_invites,member_invite_allowances,reward_activity_events,reward_daily_activity,reward_redemptions,reward_ledger,checkins,
                official_book_unlocks,user_library,catalog_book_tags,catalog_books,catalog_tags,catalog_series,resource_audit,usage_ledger,quota_reservations,usage_periods,subscriptions,manual_orders,assets,
                content_sentence_grammar,content_learning_daily,content_word_annotations,content_vocabulary,content_books,invitation_uses,invitations,password_reset_tokens,email_verifications,user_sessions,devices,user_roles,users,roles RESTART IDENTITY CASCADE""")
        self.admin=self.accounts.bootstrap_admin();assert self.admin
        invite=self.accounts.create_invitation("IMPORT-TEST",max_uses=10,created_by=str(self.admin["id"]))
        self.owner=self.accounts.register("import-owner@local.test","import owner password",invite["code"])["user"]
        self.other=self.accounts.register("import-other@local.test","import other password",invite["code"])["user"]
        self.verify(str(self.owner["id"]));self.verify(str(self.other["id"]))
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                for user in (self.owner,self.other):
                    cursor.execute("""INSERT INTO subscriptions(id,user_id,plan_version_id,status,starts_at,ends_at)
                        VALUES(%s,%s,'commerce-advanced-30-v2','active',NOW()-INTERVAL '1 day',NOW()+INTERVAL '30 days')""",(new_id(),user['id']))

    def verify(self,user_id:str)->None:
        raw="verify-"+new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:cursor.execute("INSERT INTO email_verifications(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",(new_id(),user_id,token_hash(raw),utcnow()+timedelta(days=1)))
        self.accounts.verify_email(raw)

    @staticmethod
    def speech_epub():
        content=io.BytesIO()
        with zipfile.ZipFile(content,'w') as archive:
            archive.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>')
            archive.writestr('book.opf','<package><manifest><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="one"/></spine></package>')
            archive.writestr('one.xhtml','<html><body><p>A quiet morning is a good time to read a book.</p><p>The story begins in a small village near the sea.</p></body></html>')
        return content.getvalue()

    def speech_task(self,service=None,user=None,key='speech-task'):
        service=service or self.imports;user=user or str(self.owner['id'])
        with patch('kokoro_speech.options',return_value={'available':True}):
            task=service.create(user,'document','AI narration','narration.epub',key,metadata={'speechSynthesis':{'engine':'kokoro','voice':'af_heart'}})['task']['id']
        service.upload(user,task,'narration.epub',self.speech_epub(),'application/epub+zip')
        return task

    def speech_stub(self,service,data,source,task_id,user_id,request):
        # Test-only output exercises atomic registration; real inference has its own opt-in test.
        from kokoro_speech import attach_timing
        attach_timing(data,{'duration':len(data['sentences']), 'sentences':[
            {'id':s['id'],'start':i,'end':i+1,'words':[]} for i,s in enumerate(data['sentences'])]},request)
        target=source.parent/'test-generated.mp3';target.write_bytes(b'test-only-generated-audio')
        return {'name':'audio','storagePath':target.relative_to(service.media.media_root).as_posix(),'contentType':'audio/mpeg'}

    def test_speech_import_is_atomic_idempotent_and_owner_scoped(self):
        owner=str(self.owner['id']);task=self.speech_task()
        with patch('kokoro_speech.generate',side_effect=self.speech_stub) as generator:
            result=self.imports.complete(owner,task)['task']
            self.assertEqual(result['status'],'complete')
            self.assertTrue(self.imports.complete(owner,task)['idempotent'])
            generator.assert_called_once()
        book=self.workspace.reader(owner,result['outputBookId'])['book']
        self.assertTrue(book['speechSynthesis']['synthetic']);self.assertEqual(book['resourceType'],'audio')
        self.assertEqual(book['readingDocument']['format'],'epub')
        self.assertEqual(book['sentences'][1]['start'],1)
        self.assertFalse(any('start' in word for s in book['sentences'] for word in s['words']))
        with self.assertRaises(SaaSError):self.workspace.reader(str(self.other['id']),book['id'])
        asset=book['mediaAssets'][0]
        with self.assertRaises(SaaSError):self.media.stream(str(self.other['id']),asset['id'],'audio')
        self.assertGreater(asset['bytes'],len(self.speech_epub()))
        self.workspace.delete_book(owner,book['id'],book['title'])
        self.assertFalse(list(self.root.rglob('test-generated.mp3')))

    def test_speech_cancellation_and_quota_failure_remove_unpublished_audio(self):
        owner=str(self.owner['id'])
        for mode in ('cancel','quota','after-attach'):
            task=self.speech_task(key='speech-'+mode)
            def generate(*args):
                variant=self.speech_stub(*args)
                if mode=='cancel':self.imports.cancel(owner,task)
                return variant
            with patch('kokoro_speech.generate',side_effect=generate):
                if mode=='quota':
                    with patch.object(self.media,'_private_bytes',return_value=1024**3):
                        with self.assertRaises(SaaSError) as error:self.imports.complete(owner,task)
                        self.assertEqual(error.exception.code,'quota_exceeded')
                elif mode=='after-attach':
                    register=self.media.add_variants
                    def register_then_fail(*args,**kwargs):
                        register(*args,**kwargs)
                        raise SaaSError('test_publish_failure','测试最终入库失败',422)
                    with patch.object(self.media,'add_variants',side_effect=register_then_fail):
                        with self.assertRaises(SaaSError):self.imports.complete(owner,task)
                else:
                    with self.assertRaises(SaaSError):self.imports.complete(owner,task)
            state=next(t for t in self.imports.list(owner)['tasks'] if t['id']==task)
            self.assertEqual(state['status'],'cancelled' if mode=='cancel' else 'failed')
            with self.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM asset_variants WHERE asset_id=%s AND variant_name='audio'",(state['sourceAssetId'],))
                    self.assertEqual(cursor.fetchone()[0],0)
            self.assertFalse(list((self.root/'private-uploads'/owner/task).rglob('test-generated.mp3')))
            if mode=='quota':
                self.imports.retry(owner,task)
                with patch('kokoro_speech.generate',side_effect=self.speech_stub):
                    self.assertEqual(self.imports.complete(owner,task)['task']['status'],'complete')

    def test_speech_missing_runtime_and_failure_are_actionable(self):
        owner=str(self.owner['id'])
        with patch('kokoro_speech.options',return_value={'available':False}):
            with self.assertRaises(SaaSError) as error:
                self.imports.create(owner,'document','AI','book.epub','speech-unavailable',metadata={'speechSynthesis':{'engine':'kokoro'}})
            self.assertEqual(error.exception.code,'speech_unavailable')
        task=self.speech_task()
        with patch('kokoro_speech.generate',side_effect=SaaSError('speech_generation_failed','生成失败',422)):
            with self.assertRaises(SaaSError):self.imports.complete(owner,task)
        self.assertEqual(self.imports.list(owner)['tasks'][0]['status'],'failed')
        self.assertEqual(self.workspace.list_books(owner)['books'],[])

    def test_speech_rejects_companion_upload_and_runs_official_import_without_subscription(self):
        owner=str(self.owner['id']);task=self.speech_task()
        with self.assertRaises(SaaSError) as conflict:self.imports.upload_audio(owner,task,'narration.mp3',b'original')
        self.assertEqual(conflict.exception.code,'speech_audio_conflict')
        import hashlib
        with self.assertRaises(SaaSError) as conflict:
            self.imports.audio_upload().put(owner,task,'narration.mp3',1,0,hashlib.sha256(b'x').hexdigest(),b'x')
        self.assertEqual(conflict.exception.code,'speech_audio_conflict')
        official=WorkspaceImportService(self.accounts,self.resources,self.media,official=True)
        admin=str(self.admin['id']);task=self.speech_task(official,admin,'official-speech')
        with self.assertRaises(SaaSError):self.imports.complete(admin,task)
        with patch('kokoro_speech.generate',side_effect=self.speech_stub):
            result=official.complete(admin,task)['task']
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT visibility,data_json FROM content_books WHERE id=%s',(result['outputBookId'],))
                row=self.accounts._one(cursor);self.assertEqual(row['visibility'],'draft')
                self.assertTrue(row['data_json']['speechSynthesis']['synthetic'])
        self.assertEqual(self.workspace.list_books(admin)['books'],[])
        catalog=CatalogService(self.accounts,self.resources)
        reviewed=catalog.review(admin,result['outputBookId'],'licensed','published')['book']
        reader=catalog.reader(owner,reviewed['id'],trial=True)['book']
        self.assertTrue(reader['speechSynthesis']['synthetic'])
        self.assertTrue(all(v['contentType'].startswith('audio/') for a in reader['mediaAssets'] for v in a['variants']))

    @unittest.skipUnless(os.environ.get('SHIYUE_RUN_KOKORO_TEST')=='1','Opt in to real local Kokoro inference')
    def test_real_kokoro_epub_and_pdf_generate_playable_audio_with_timeline(self):
        from kokoro_speech import options
        self.assertTrue(options()['available'])
        owner=str(self.owner['id'])
        stream=b'BT /F1 20 Tf 60 730 Td (A quiet morning is a good time to read a book.) Tj 0 -40 Td (The story begins in a small village near the sea.) Tj ET'
        objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
                 b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
                 b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
                 b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
        pdf=b'%PDF-1.4\n';offsets=[0]
        for index,item in enumerate(objects,1):
            offsets.append(len(pdf));pdf+=f'{index} 0 obj\n'.encode()+item+b'\nendobj\n'
        xref=len(pdf);pdf+=b'xref\n0 6\n0000000000 65535 f \n'
        pdf+=b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
        pdf+=f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
        pdf_service=(WorkspaceImportService(self.accounts,self.resources,self.media,pdf_ocr=Path(os.environ['SHIYUE_KOKORO_TEST_PDF_OCR']))
                     if os.environ.get('SHIYUE_KOKORO_TEST_PDF_OCR') else self.pdf_imports)
        for filename,content,service in [('narration.epub',self.speech_epub(),self.imports),('narration.pdf',pdf,pdf_service)]:
            with self.subTest(filename=filename):
                task=service.create(owner,'document','Real narration',filename,'real-'+filename,metadata={'speechSynthesis':{'engine':'kokoro','voice':'bf_emma' if filename.endswith('pdf') else 'af_heart'}})['task']['id']
                service.upload(owner,task,filename,content)
                result=service.complete(owner,task)['task'];self.assertEqual(result['status'],'complete')
                book=self.workspace.reader(owner,result['outputBookId'])['book']
                self.assertTrue(book['speechSynthesis']['synthetic']);self.assertGreater(book['duration'],1)
                self.assertTrue(all(0<=s['start']<s['end']<=book['duration'] for s in book['sentences']))
                asset=self.media.stream(owner,book['mediaAssets'][0]['id'],'audio')
                self.assertGreater(asset['target']['byte_size'],1000)
                self.assertGreater(float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nk=1:nw=1',str(asset['path'])],text=True)),1)
                self.assertTrue(service.complete(owner,task)['idempotent'])

    @unittest.skipUnless(os.environ.get('SHIYUE_RUN_KOKORO_TEST')=='1','Opt in to real local Kokoro cancellation')
    def test_real_kokoro_cancellation_stops_process_and_cleans_temporary_audio(self):
        import threading
        owner=str(self.owner['id']);task=self.speech_task(key='real-cancel')
        launched=threading.Event();processes=[];spawn=subprocess.Popen
        def capture(command,*args,**kwargs):
            process=spawn(command,*args,**kwargs)
            if any(str(arg).endswith('kokoro_worker.py') for arg in command):
                processes.append(process);launched.set()
            return process
        with patch('kokoro_speech.subprocess.Popen',side_effect=capture):
            result=self.imports.submit_complete(owner,task)
            self.assertTrue(result['asynchronous'])
            self.assertTrue(launched.wait(15))
            self.imports.cancel(owner,task)
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if processes[0].poll() is not None and not list(self.root.rglob('.kokoro-*')):break
                time.sleep(.05)
            else:self.fail('Cancelled Kokoro worker did not stop and clean temporary files')
        self.assertEqual(self.imports.list(owner)['tasks'][0]['status'],'cancelled')
        self.assertEqual(self.workspace.list_books(owner)['books'],[])
        self.assertFalse(list(self.root.rglob('*.mp3')))

    def test_text_task_upload_complete_idempotency_and_owner_isolation(self):
        owner,other=str(self.owner["id"]),str(self.other["id"])
        created=self.imports.create(owner,"text","我的测试文本","lesson.md","text-task-1")
        duplicate=self.imports.create(owner,"text","ignored","lesson.md","text-task-1")
        self.assertFalse(created["idempotent"]);self.assertTrue(duplicate["idempotent"]);self.assertEqual(created["task"]["id"],duplicate["task"]["id"]);self.assertNotIn("planVersion",created["task"])
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
        self.assertIsNone(reader.get("readingDocument"))
        self.assertEqual(reader["mediaAssets"][0]["id"],completed["task"]["sourceAssetId"])
        self.assertEqual(self.workspace.list_books(other)["books"],[])
        repeat=self.imports.complete(owner,task_id);self.assertTrue(repeat["idempotent"])

    def test_epub_import_persists_original_blocks_and_isolates_reader(self):
        owner,other=str(self.owner['id']),str(self.other['id'])
        content=io.BytesIO()
        with zipfile.ZipFile(content,'w') as archive:
            archive.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>')
            archive.writestr('book.opf','<package><manifest><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="one"/></spine></package>')
            archive.writestr('one.xhtml','<html><body><h1>Chapter One</h1><p>“Original punctuation,” she said.<br/>The same paragraph continues!</p><p>A separate original paragraph.</p></body></html>')
        task=self.imports.create(owner,'document','Original EPUB','original.epub','structured-epub')['task']['id']
        self.imports.upload(owner,task,'original.epub',content.getvalue(),'application/epub+zip')
        result=self.imports.complete(owner,task)['task']
        self.assertEqual(result['status'],'complete')
        book=self.workspace.reader(owner,result['outputBookId'])['book']
        document=book['readingDocument']
        self.assertEqual(document['source']['spine'],[{'href':'one.xhtml','section':'section-1','layout':'reflow'}])
        self.assertEqual((document['version'],document['format'],document['pagination']),(1,'epub','reflow'))
        self.assertEqual([b['text'] for b in document['blocks']],['Chapter One','“Original punctuation,” she said.\nThe same paragraph continues!','A separate original paragraph.'])
        sentences={s['id']:s for s in book['sentences']}
        for block in document['blocks']:
            for word in block['words']:
                self.assertEqual(block['text'][word['start']:word['end']],sentences[word['sentenceId']]['words'][word['wordIndex']]['text'])
        with self.assertRaises(SaaSError):self.workspace.reader(other,result['outputBookId'])
        location={'format':'epub','chapter':0,'offset':23}
        self.workspace.save_progress(owner,result['outputBookId'],book['sentences'][0]['id'],reading_location=location)
        self.assertEqual(self.workspace.reader(owner,result['outputBookId'])['book']['progress']['readingLocation'],location)
        with self.assertRaises(SaaSError):self.workspace.save_progress(other,result['outputBookId'],book['sentences'][0]['id'],reading_location=location)
        with self.assertRaises(SaaSError):self.workspace.save_progress(owner,result['outputBookId'],book['sentences'][0]['id'],reading_location={**location,'chapter':3})
        self.assertTrue(self.imports.complete(owner,task)['idempotent'])
        self.workspace.delete_book(owner,book['id'],book['title'])
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1 FROM workspace_settings WHERE user_id=%s AND key=%s',(owner,'source-position:'+book['id']))
                self.assertIsNone(cursor.fetchone())

    def test_document_companion_audio_variant_isolation_idempotency_and_delete(self):
        owner,other=str(self.owner['id']),str(self.other['id'])
        task=self.imports.create(owner,'text','Paired','paired.txt','paired-document')['task']['id']
        self.imports.upload(owner,task,'paired.txt',b'First sentence. Another sentence.','text/plain')
        with patch.object(self.imports,'audio_duration',return_value=4.2):
            with self.assertRaises(SaaSError):self.imports.upload_audio(other,task,'paired.mp3',b'audio')
            with self.assertRaises(SaaSError):self.imports.upload_audio(owner,task,'wrong.mp3',b'audio')
            self.imports.upload_audio(owner,task,'paired.mp3',b'audio')
            self.imports.upload_audio(owner,task,'paired.mp3',b'audio')
            with self.assertRaises(SaaSError):self.imports.upload_audio(owner,task,'paired.mp3',b'different')
            with patch.object(self.imports,'_align_document_audio',side_effect=lambda data,*args:data) as align:
                done=self.imports.complete(owner,task)['task']
                align.assert_called_once()
        book=self.workspace.reader(owner,done['outputBookId'])['book']
        self.assertEqual(book['resourceType'],'audio');self.assertEqual(book['duration'],4.2)
        variants=book['mediaAssets'][0]['variants'];self.assertEqual(len(variants),1)
        self.assertEqual(variants[0]['contentType'],'audio/mpeg')
        with self.assertRaises(SaaSError):self.workspace.reader(other,book['id'])
        with self.assertRaises(SaaSError):self.imports.upload_audio(owner,task,'paired.mp3',b'audio')
        self.workspace.delete_book(owner,book['id'],book['title'])
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT deleted_at FROM asset_variants WHERE asset_id=%s',(done['sourceAssetId'],))
                self.assertIsNotNone(cursor.fetchone()[0])

    def test_document_alignment_rechecks_cancellation_before_starting_processor(self):
        owner=str(self.owner['id'])
        task=self.imports.create(owner,'text','Cancel','cancel.txt','cancel-alignment')['task']['id']
        self.imports.cancel(owner,task)
        model_home=Path(self.temp.name)/'ctc-model';checkpoint=model_home/'hub/checkpoints'/MODEL_FILE
        checkpoint.parent.mkdir(parents=True,exist_ok=True);checkpoint.write_bytes(b'test model')
        with patch.dict(os.environ,{'SHIYUE_CTC_PYTHON':sys.executable,'SHIYUE_CTC_MODEL_HOME':str(model_home)}):
            with patch('saas_imports.subprocess.run') as processor:
                with self.assertRaises(SaaSError) as error:
                    self.imports._align_document_audio({'sentences':[]},Path('unused.mp3'),task,owner)
                self.assertEqual(error.exception.code,'import_task_terminal')
                processor.assert_not_called()

    def test_document_alignment_requires_installed_acoustic_model(self):
        with patch.dict(os.environ,{'SHIYUE_CTC_MODEL_HOME':str(Path(self.temp.name)/'missing-ctc')}):
            with self.assertRaises(SaaSError) as error:
                self.imports._align_document_audio({'sentences':[]},Path('unused.mp3'),'unused',str(self.owner['id']))
            self.assertEqual(error.exception.code,'alignment_unavailable')

    def test_companion_upload_blocks_early_start_then_clears_on_audio_upload(self):
        owner=str(self.owner['id'])
        task=self.imports.create(owner,'text','Paired','paired.txt','waiting-audio',metadata={'awaitingAudioUpload':True})['task']['id']
        self.imports.upload(owner,task,'paired.txt',b'A real sentence.','text/plain')
        for start in (self.imports.submit_complete,self.imports.complete):
            with self.assertRaises(SaaSError) as error:start(owner,task)
            self.assertEqual(error.exception.code,'companion_audio_pending')
        self.assertEqual(self.imports.list(owner)['tasks'][0]['status'],'queued')
        with patch.object(self.imports,'audio_duration',return_value=4.2):
            self.imports.upload_audio(owner,task,'paired.mp3',b'audio')
        with patch('saas_imports.threading.Thread') as thread:
            self.assertTrue(self.imports.submit_complete(owner,task,background=True)['asynchronous'])
            thread.return_value.start.assert_called_once()

    def test_upload_auto_start_runs_in_background_and_replay_is_idempotent(self):
        owner=str(self.owner['id'])
        task=self.imports.create(owner,'text','Auto','auto.txt','auto-upload')['task']['id']
        self.imports.upload(owner,task,'auto.txt',b'Uploaded text survives disconnect.','text/plain')
        with patch('saas_imports.threading.Thread') as thread:
            submitted=self.imports.submit_complete(owner,task,background=True)
            self.assertTrue(submitted['asynchronous'])
            worker=thread.call_args.kwargs['target']
        worker();worker()
        done=self.imports.list(owner)['tasks'][0]
        self.assertEqual(done['status'],'complete')
        self.assertEqual(len(self.workspace.list_books(owner)['books']),1)

    def test_document_alignment_submission_is_async_and_worker_failure_is_pollable(self):
        owner,other=str(self.owner['id']),str(self.other['id'])
        task=self.imports.create(owner,'text','Async','async.txt','async-document')['task']['id']
        self.imports.upload(owner,task,'async.txt',b'A real sentence.','text/plain')
        with patch.object(self.imports,'audio_duration',return_value=4.2):
            self.imports.upload_audio(owner,task,'async.mp3',b'audio')
            with self.assertRaises(SaaSError):self.imports.submit_complete(other,task)
            with patch('saas_imports.threading.Thread') as thread:
                submitted=self.imports.submit_complete(owner,task)
                self.assertTrue(submitted['asynchronous'])
                self.assertEqual(submitted['task']['status'],'queued')
                thread.return_value.start.assert_called_once()
                worker=thread.call_args.kwargs['target']
            with patch.object(self.imports,'_align_document_audio',side_effect=SaaSError('alignment_rejected','Text does not match audio',422)):
                worker()
        failed=next(t for t in self.imports.list(owner)['tasks'] if t['id']==task)
        self.assertEqual(failed['status'],'failed')
        self.assertIn('Text does not match audio',failed['error'])
        self.assertEqual(self.workspace.list_books(owner)['books'],[])

    def test_document_cannot_attach_another_users_audio(self):
        owner,other=str(self.owner['id']),str(self.other['id'])
        foreign=self.imports.create(other,'mp3','Foreign','book.mp3','foreign-audio')['task']['id']
        uploaded=self.imports.upload(other,foreign,'book.mp3',b'audio','audio/mpeg')
        task=self.imports.create(owner,'text','Document','book.txt','foreign-document',metadata={'matchedAudioAssetId':uploaded['sourceAssetId']})['task']['id']
        self.imports.upload(owner,task,'book.txt',b'This document has text.','text/plain')
        with self.assertRaises(SaaSError) as denied:self.imports.complete(owner,task)
        self.assertEqual(denied.exception.code,'matched_audio_missing')

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
        usage=self.resources.usage(owner);
        self.imports.upload(owner,task_id,"sample.mp3",b"not-a-real-mp3","audio/mpeg")
        cancelled=self.imports.cancel(owner,task_id);self.assertEqual(cancelled["task"]["status"],"cancelled")
        usage=self.resources.usage(owner);storage=next(row for row in usage["usage"] if row["feature"]=="storage_bytes")
        self.assertEqual(storage["used"],0)

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
        usage=self.resources.usage(owner)

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
        self.assertEqual(reader['readingDocument']['format'],'pdf')
        self.assertEqual(reader['readingDocument']['pagination'],'original')
        self.assertEqual([s['page'] for s in reader['sentences']],[1,1])

    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg is required for the native video acceptance test")
    def test_video_native_ffmpeg_processor_registers_variants_and_isolates_tenant(self):
        owner,other=str(self.owner["id"]),str(self.other["id"]);sample=Path(self.temp.name)/"sample-video.mp4"
        subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i","color=c=blue:s=320x180:d=2","-f","lavfi","-i","sine=frequency=440:duration=2","-shortest","-c:v","mpeg4","-c:a","aac",str(sample)],check=True,timeout=30)
        created=self.video_imports.create(owner,"video","私人视频","lesson.mp4","native-video-task");task_id=created["task"]["id"]
        self.video_imports.upload(owner,task_id,"lesson.mp4",sample.read_bytes(),"video/mp4")
        completed=self.video_imports.complete(owner,task_id);self.assertEqual(completed["task"]["status"],"complete")
        asset_id=completed["task"]["sourceAssetId"];reader=self.workspace.reader(owner,completed["task"]["outputBookId"])["book"]
        self.assertEqual(reader["resourceType"],"video");self.assertEqual(round(reader["duration"],1),2.0)
        self.assertTrue(reader["canWatchHdVideo"])
        self.assertEqual([sentence["text"] for sentence in reader["sentences"]],["Hello private audio."])
        self.assertTrue(all(word["end"]<=reader["duration"] for sentence in reader["sentences"] for word in sentence["words"]))
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT data_json FROM content_books WHERE id=%s",(completed["task"]["outputBookId"],))
                stored=self.accounts._one(cursor)["data_json"]
        self.assertEqual(stored["segmentation"]["wordsOutsideMedia"],3)
        self.assertTrue(self.media.stream(owner,asset_id,"audio")["path"].is_file());self.assertTrue(self.media.stream(owner,asset_id,"cover")["path"].is_file())
        self.assertTrue(self.media.stream(owner,asset_id,"low")["path"].is_file())
        self.assertTrue(self.media.stream(owner,asset_id)["path"].is_file())
        with self.assertRaises(SaaSError) as denied:self.media.stream(other,asset_id,"audio")
        self.assertEqual(denied.exception.code,"media_access_denied")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT variant_name FROM asset_variants WHERE asset_id=%s AND deleted_at IS NULL ORDER BY variant_name",(asset_id,));self.assertEqual([row["variant_name"] for row in self.accounts._many(cursor)],["audio","cover","low"])
        usage=self.resources.usage(owner);storage=next(row for row in usage["usage"] if row["feature"]=="storage_bytes")
        self.assertGreater(storage["used"],sample.stat().st_size)
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
        usage=self.resources.usage(owner);storage=next(row for row in usage["usage"] if row["feature"]=="storage_bytes")
        self.assertEqual(storage["used"],len(b"not-a-video"))

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
        catalog=CatalogService(self.accounts,self.resources)
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
        self.assertEqual(data["subtitleAlignment"]["reason"],"aligner_unavailable")
        self.assertEqual(data["sentences"][0]["translation"],"这是中文字幕。")
        self.assertEqual(reader["sentences"][0]["translation"],"这是中文字幕。")
        # Historical books are enriched on read without a write-back or re-import.
        for sentence in data["sentences"]:sentence.pop("translation",None)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:cursor.execute("UPDATE content_books SET data_json=%s::jsonb WHERE id=%s",(json.dumps(data),completed["task"]["outputBookId"]))
        hydrated=self.workspace.reader(owner,completed["task"]["outputBookId"])["book"]
        self.assertEqual(hydrated["sentences"][0]["translation"],"这是中文字幕。")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT data_json FROM content_books WHERE id=%s",(completed["task"]["outputBookId"],));stored=self.accounts._one(cursor)["data_json"]
        if isinstance(stored,str):stored=json.loads(stored)
        self.assertFalse(any(s.get("translation") for s in stored["sentences"]))
        self.media.stream(owner,asset_id,"subtitles-zh-CN")["path"].unlink()
        self.assertFalse(any(s.get("translation") for s in self.workspace.reader(owner,completed["task"]["outputBookId"])["book"]["sentences"]))
        usage=self.resources.usage(owner)


    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg required")
    def test_verified_manual_caption_import_persists_measured_words_without_whisper(self):
        owner,other=str(self.owner["id"]),str(self.other["id"])
        runtime=Path(self.temp.name)/"ctc-python";runtime.touch()
        model_home=Path(self.temp.name)/"ctc-models";checkpoint=model_home/"hub/checkpoints"/MODEL_FILE
        checkpoint.parent.mkdir(parents=True,exist_ok=True);checkpoint.touch()
        def align(command,*args):
            words=[{"text":"Caption","start":.12,"end":.4},{"text":"text","start":.48,"end":.8,"punctuationAfter":".","breakAfter":True}]
            words=[{**w,"timingSource":"manual-caption-ctc","estimated":False,"confidence":.95} for w in words]
            Path(command[command.index("--output")+1]).write_text(json.dumps({"aligned":[{"index":0,"words":words}],"rejected":[]}))
        task=self.youtube_imports.create(owner,"youtube","","","manual-youtube-task","https://youtu.be/fake123")["task"]
        with patch.dict(os.environ,{"SHIYUE_CTC_PYTHON":str(runtime),"SHIYUE_CTC_MODEL_HOME":str(model_home)}),patch.object(self.youtube_imports,"_run_speech_process",side_effect=align),patch.object(self.youtube_imports,"_transcribe_video_audio") as whisper:
            result=self.youtube_imports.complete(owner,task["id"])
        whisper.assert_not_called();self.assertEqual(result["task"]["status"],"complete")
        book_id=result["task"]["outputBookId"]
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT data_json FROM content_books WHERE id=%s",(book_id,));data=self.accounts._one(cursor)["data_json"]
        if isinstance(data,str):data=json.loads(data)
        self.assertEqual(data["alignment"],"manual-caption-ctc")
        self.assertEqual(data["subtitleAlignment"]["status"],"aligned")
        self.assertTrue(data["whisper"]["skipped"])
        self.assertEqual(data["sentences"][0]["text"],"Caption text.")
        self.assertEqual(data["sentences"][0]["words"][0]["start"],.12)
        with self.assertRaises(SaaSError):self.workspace.reader(other,book_id)

    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg required")
    def test_automatic_captions_keep_existing_whisper_route(self):
        owner=str(self.owner["id"]);download=self.youtube_imports._youtube_download
        def automatic(*args):
            source,asset,metadata,captions=download(*args)
            return source,asset,{**metadata,"youtubeSubtitleSource":"auto"},captions
        task=self.youtube_imports.create(owner,"youtube","","","auto-youtube-task","https://youtu.be/fake123")["task"]
        with patch.object(self.youtube_imports,"_youtube_download",side_effect=automatic),patch.object(self.youtube_imports,"_manual_caption_book") as align:
            result=self.youtube_imports.complete(owner,task["id"])
        align.assert_not_called();self.assertEqual(result["task"]["status"],"complete")

    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg required")
    def test_official_import_review_storage_and_permanent_delete(self):
        admin,owner=str(self.admin["id"]),str(self.owner["id"])
        official=WorkspaceImportService(self.accounts,self.resources,self.media,whisper_cli=self.fake_whisper,whisper_model=self.fake_model,audio_duration=lambda path:2.0,yt_dlp=self.fake_ytdlp,node=Path(sys.executable),official=True)
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
        catalog=CatalogService(self.accounts,self.resources)
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
        usage=self.resources.usage(admin)["usage"]
        self.assertEqual(next(row for row in usage if row["feature"]=="storage_bytes")["used"],0)
        self.assertEqual(next(row for row in usage if row["feature"]=="video_library_capacity")["used"],0)
        detail=self.media.user_storage(admin)
        self.assertEqual(detail["total"],1);video=detail["assets"][0]
        self.assertEqual(video["bookId"],book_id);self.assertTrue(video["contentPath"])
        self.assertEqual(video["scope"],"official")
        paths=[self.root/video["storagePath"]]+[self.root/v["storagePath"] for v in video["variants"]]
        low=next(self.root/v["storagePath"] for v in video["variants"] if v["name"]=="low")
        probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","json",str(low)]))["streams"][0]
        self.assertLessEqual(probe["height"],240);self.assertLessEqual(probe["width"],320)
        summary=next(row for row in self.media.user_storage()["users"] if row["id"]==admin)
        self.assertEqual(summary["totalBytes"],sum(path.stat().st_size for path in paths))
        published=catalog.review(admin,book_id,"licensed","published")["book"]
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE content_books SET data_json=jsonb_set(data_json,'{sentences}',(SELECT jsonb_agg(value-'translation') FROM jsonb_array_elements(data_json->'sentences'))) WHERE id=%s",(book_id,))
        self.assertEqual(catalog.reader(owner,published["id"],trial=True)["book"]["sentences"][0]["translation"],"这是中文字幕。")
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

    def test_media_inventory_includes_epub_generated_mp3_and_all_formats(self):
        owner=str(self.owner['id']);admin=str(self.admin['id'])
        (self.root/'narrated.epub').write_bytes(b'epub-source')
        (self.root/'narration.mp3').write_bytes(b'generated-mp3')
        (self.root/'source.pdf').write_bytes(b'pdf')
        original=self.media.register(owner,owner,'private','narrated.epub','audio','application/epub+zip',variants=[{'name':'audio','storagePath':'narration.mp3','contentType':'audio/mpeg'}])
        self.media.register(admin,admin,'official','source.pdf','document','application/pdf',allow_staging=True)
        detail=self.media.user_storage(owner)
        self.assertEqual(detail['total'],1)
        self.assertEqual(detail['assets'][0]['contentType'],'application/epub+zip')
        self.assertEqual(detail['assets'][0]['variants'][0]['contentType'],'audio/mpeg')
        self.assertEqual(detail['assets'][0]['variants'][0]['bytes'],13)
        self.assertTrue(detail['assets'][0]['createdAt'])
        summary=self.media.user_storage()['users']
        self.assertEqual(next(row for row in summary if row['id']==owner)['audioCount'],1)
        self.assertEqual(sum(row['assetCount'] for row in summary),2)
        self.assertEqual(self.media.user_storage(owner,1,1)['assets'],[])
        self.assertEqual(self.media.user_storage('missing')['total'],0)
        from saas_media_analytics import media_statistics
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE media_assets SET created_at='2024-01-31 16:00:00+00'")
                cursor.execute("UPDATE asset_variants SET created_at='2024-02-01 16:00:00+00'")
        stats=media_statistics(self.accounts,'day','2024-02-01','2024-02-03')
        self.assertEqual(stats['summary']['totalBytes'],27)
        self.assertEqual(stats['summary']['originalBytes'],14)
        self.assertEqual(stats['summary']['generatedBytes'],13)
        self.assertEqual([(p['assets'],p['variants'],p['bytes']) for p in stats['history']],[(2,0,14),(0,1,13),(0,0,0)])
        for period in ('month','year'):
            history=media_statistics(self.accounts,period,'2024-01-01','2024-12-31')['history']
            self.assertEqual(sum(p['assets'] for p in history),2)
            self.assertEqual(sum(p['bytes'] for p in history),27)
        self.media.delete(owner,original['id'])
        deleted=media_statistics(self.accounts,'day','2024-02-01','2024-02-03')
        self.assertEqual(deleted['summary']['totalBytes'],3)
        self.assertEqual(sum(p['bytes'] for p in deleted['history']),27)

    def test_youtube_download_failure_releases_reservation(self):
        owner=str(self.owner["id"]);url="https://youtu.be/failure"
        created=self.failing_youtube_imports.create(owner,"youtube","Failure","","failed-youtube-task",url)
        with self.assertRaises(SaaSError) as failed:self.failing_youtube_imports.complete(owner,created["task"]["id"])
        self.assertEqual(failed.exception.code,"youtube_download_failed")
        usage=self.resources.usage(owner);

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
        gateway_headers={'X-Shiyue-Site':'intl','X-Shiyue-Site-Token':new_id(),'X-Shiyue-Original-Host':'127.0.0.1:'+str(port)}
        cn_gateway_token=new_id()
        class GatewayConnection(http.client.HTTPConnection):
            def request(self,method,url,body=None,headers=None,**kwargs):
                return super().request(method,url,body,{**gateway_headers,**(headers or {})},**kwargs)
        connection_patch=patch.object(http.client,'HTTPConnection',GatewayConnection)
        connection_patch.start();self.addCleanup(connection_patch.stop)
        root=Path(__file__).resolve().parents[1];environment={**os.environ,**self.environment,"READER_HOST":"127.0.0.1","READER_PORT":str(port),'INTL_GATEWAY_TOKEN':gateway_headers['X-Shiyue-Site-Token'],'CN_GATEWAY_TOKEN':cn_gateway_token,'INTL_APP_BASE_URL':'http://127.0.0.1:'+str(port),'CN_APP_BASE_URL':'http://127.0.0.1:'+str(port),'SHIYUE_DEPLOYMENT_MODE':'local'};process=subprocess.Popen([sys.executable,str(root/"tools/reader_server.py")],cwd=root,env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True);connection=None
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
            owner_headers={"Content-Type":"application/json","Cookie":cookies,"X-CSRF-Token":csrf}
            self.assertEqual(request('GET','/api/workspace/imports/speech-options')[0],401)
            status,speech_options,_=request('GET','/api/workspace/imports/speech-options',headers=owner_headers)
            self.assertEqual(status,200);self.assertIsInstance(speech_options['available'],bool)
            self.assertEqual({v['value'] for v in speech_options['voices']},{'af_heart','am_michael','bf_emma','bm_george'})
            speech_payload=json.dumps({'kind':'document','filename':'speech.epub','idempotencyKey':'http-speech-csrf','metadata':{'speechSynthesis':{'engine':'kokoro'}}})
            self.assertEqual(request('POST','/api/workspace/imports',speech_payload,{key:value for key,value in owner_headers.items() if key!='X-CSRF-Token'})[0],403)
            self.assertEqual(request('GET','/api/admin/content-imports/speech-options',headers=owner_headers)[0],403)
            status,short_task,_=request('POST','/api/workspace/imports',json.dumps({'kind':'text','title':'Short upload','filename':'short.txt','idempotencyKey':'http-short','metadata':{'awaitingAudioUpload':True}}),owner_headers)
            self.assertEqual(status,201)
            short_id=short_task['task']['id']
            def short_upload(route,declared=None):
                with socket.create_connection(('127.0.0.1',port),timeout=5) as client:
                    headers={**gateway_headers,**owner_headers,'Content-Length':'100' if declared is None else '4','X-Upload-Filename':'short.mp3' if route=='upload-audio' else 'short.txt','X-Import-Start-Processing':'1','Connection':'close'}
                    if declared is not None:headers['X-Upload-Size']=str(declared)
                    raw=f'POST /api/workspace/imports/{short_id}/{route} HTTP/1.1\r\nHost: localhost\r\n'+''.join(f'{key}: {value}\r\n' for key,value in headers.items())+'\r\n'
                    client.sendall(raw.encode()+b'part');client.shutdown(socket.SHUT_WR)
                    response=http.client.HTTPResponse(client);response.begin()
                    self.assertEqual(response.status,400)
                    self.assertEqual(json.loads(response.read())['code'],'incomplete_upload')
            short_upload('upload')
            short_upload('upload',100)
            state=request('GET',f'/api/workspace/imports/{short_id}',headers=owner_headers)[1]['task']
            self.assertEqual(state['status'],'uploading');self.assertFalse(state.get('sourceAssetId'))
            self.assertEqual(request('POST',f'/api/workspace/imports/{short_id}/upload',b'Complete text.',{**owner_headers,'X-Upload-Filename':'short.txt','X-Upload-Size':'14'})[0],200)
            short_upload('upload-audio')
            short_upload('upload-audio',100)
            self.assertEqual(request('POST',f'/api/workspace/imports/{short_id}/complete','{}',owner_headers)[1]['code'],'companion_audio_pending')
            # The resumable transport keeps the same authentication and CSRF gates.
            import hashlib
            chunk=b'a'*(256*1024)
            chunk_path=f'/api/workspace/imports/{short_id}/upload-audio-chunk'
            chunk_headers={**owner_headers,'X-Upload-Filename':'short.mp3','X-Upload-File-Size':str(len(chunk)+5),'X-Upload-Chunk-Index':'0','X-Upload-Size':str(len(chunk)),'X-Upload-SHA256':hashlib.sha256(chunk).hexdigest()}
            self.assertEqual(request('GET',f'/api/workspace/imports/{short_id}/audio-upload')[0],401)
            self.assertEqual(request('POST',chunk_path,chunk,{key:value for key,value in chunk_headers.items() if key not in {'Cookie','X-CSRF-Token'}})[0],401)
            self.assertEqual(request('POST',chunk_path,chunk,{key:value for key,value in chunk_headers.items() if key!='X-CSRF-Token'})[0],403)
            self.assertEqual(request('POST',chunk_path,chunk,chunk_headers)[0],200)
            self.assertEqual(request('POST',chunk_path,chunk,chunk_headers)[0],200)
            status,staged,_=request('GET',f'/api/workspace/imports/{short_id}/audio-upload',headers=owner_headers)
            self.assertEqual(status,200);self.assertEqual(list(staged['received']),['0'])
            finish_path=f'/api/workspace/imports/{short_id}/complete-audio-upload'
            payload=json.dumps({'filename':'short.mp3','totalBytes':len(chunk)+5,'chunkHashes':[hashlib.sha256(chunk).hexdigest(),'0'*64]})
            self.assertEqual(request('POST',finish_path,payload,{key:value for key,value in owner_headers.items() if key!='X-CSRF-Token'})[0],403)
            self.assertEqual(request('POST',finish_path,payload,owner_headers)[1]['code'],'companion_audio_pending')
            with self.accounts.transaction() as db:
                with db.cursor() as cursor:
                    cursor.execute('SELECT COUNT(*) FROM asset_variants WHERE asset_id=(SELECT source_asset_id FROM workspace_import_tasks WHERE id=%s)',(short_id,))
                    self.assertEqual(cursor.fetchone()[0],0)
            status,created,_=request('POST','/api/workspace/imports',json.dumps({'kind':'text','title':'Disconnect','filename':'disconnect.txt','idempotencyKey':'http-disconnect'}),owner_headers)
            self.assertEqual(status,201)
            disconnected_id=created['task']['id']
            upload_path=f'/api/workspace/imports/{disconnected_id}/upload'
            upload_headers={**owner_headers,'Content-Type':'text/plain','X-Upload-Filename':'disconnect.txt','X-Import-Start-Processing':'1'}
            self.assertEqual(request('POST',upload_path,b'Text stays safe.',{key:value for key,value in upload_headers.items() if key!='X-CSRF-Token'})[0],403)
            # Lose the upload response: processing must not depend on a browser /complete.
            disconnected=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
            disconnected.request('POST',upload_path,b'Text stays safe.',upload_headers)
            disconnected.sock.shutdown(socket.SHUT_RDWR);disconnected.close()
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                status,state,_=request('GET',f'/api/workspace/imports/{disconnected_id}',headers=owner_headers)
                if state.get('task',{}).get('status')=='complete':break
                time.sleep(.05)
            else:self.fail(f'Upload did not auto-start after disconnect: {state}')
            self.assertEqual(request('POST',f'/api/workspace/imports/{disconnected_id}/complete','{}',owner_headers)[1]['task']['outputBookId'],state['task']['outputBookId'])
            self.assertEqual(request("GET","/api/admin/content-imports")[0],401)
            self.assertEqual(request("GET","/api/admin/content-imports",headers={"Cookie":cookies})[0],403)
            self.assertEqual(request("GET","/api/admin/media-assets",headers={"Cookie":cookies})[0],403)
            for path in ('/api/admin/media-assets/statistics','/api/admin/server-metrics'):
                self.assertEqual(request('GET',path)[0],401)
                self.assertEqual(request('GET',path,headers={'Cookie':cookies})[0],403)
            self.assertEqual(request("DELETE",f"/api/media/{completed['task']['sourceAssetId']}",headers={"Cookie":cookies,"X-CSRF-Token":csrf})[0],409)
            status,_,headers=request("POST","/api/auth/login",json.dumps({"email":"admin@local.test","password":"phase8 admin password"}),{"Content-Type":"application/json","X-Device-Id":"phase8-admin-http"})
            self.assertEqual(status,200)
            cookies="; ".join(value.split(";",1)[0] for name,value in headers if name.lower()=="set-cookie")
            csrf=next(value.split("=",1)[1] for value in cookies.split("; ") if value.startswith("shiyue_csrf="))
            admin_headers={"Content-Type":"application/json","Cookie":cookies,"X-CSRF-Token":csrf}
            self.assertEqual(request('GET','/api/admin/content-imports/speech-options',headers=admin_headers)[0],200)
            self.assertEqual(request("POST","/api/admin/content-imports","{}",{"Content-Type":"application/json","Cookie":cookies})[0],403)
            status,created,_=request("POST","/api/admin/content-imports",json.dumps({"kind":"text","title":"Official HTTP","filename":"official.txt","idempotencyKey":"http-official"}),admin_headers)
            self.assertEqual(status,201,created);official_id=created["task"]["id"]
            status,_,_=request("POST",f"/api/admin/content-imports/{official_id}/upload",b"Official upload.",{**admin_headers,"Content-Type":"text/plain","X-Upload-Filename":"official.txt","X-Import-Start-Processing":"1"})
            self.assertEqual(status,202)
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                state=request('GET',f'/api/admin/content-imports/{official_id}',headers=admin_headers)[1]
                if state.get('task',{}).get('status')=='complete':break
                time.sleep(.05)
            else:self.fail(f'Official upload did not auto-start: {state}')
            status,done,_=request("POST",f"/api/admin/content-imports/{official_id}/complete","{}",admin_headers)
            self.assertEqual(status,200,done);self.assertEqual(done["task"]["status"],"complete")
            self.assertEqual(request("GET","/api/admin/content-imports",headers=admin_headers)[1]["total"],1)
            self.assertEqual(request("GET","/api/workspace/imports",headers=admin_headers)[1]["total"],0)
            self.assertEqual(len(request("GET","/api/admin/catalog/sources",headers=admin_headers)[1]["sources"]),1)
            status,summary,_=request("GET","/api/admin/media-assets",headers=admin_headers)
            self.assertEqual(status,200);self.assertEqual(len(summary["users"]),2)
            for site in ('cn','intl'):
                headers={**admin_headers,'X-Shiyue-Site':site,'X-Shiyue-Site-Token':cn_gateway_token if site=='cn' else gateway_headers['X-Shiyue-Site-Token']}
                self.assertEqual(request('GET','/api/admin/media-assets/statistics?period=day',headers=headers)[0],200)
                status,snapshot,_=request('GET','/api/admin/server-metrics',headers=headers)
                self.assertEqual(status,200,snapshot)
                self.assertGreater(snapshot['memory']['total'],0)
            self.assertEqual(request("POST","/api/admin/catalog/delete",json.dumps({"sourceBookId":done["task"]["outputBookId"],"confirmTitle":"Official HTTP"}),admin_headers)[0],200)
        finally:
            if connection:connection.close()
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()
            if process.stderr:process.stderr.close()

if __name__=="__main__":unittest.main()
