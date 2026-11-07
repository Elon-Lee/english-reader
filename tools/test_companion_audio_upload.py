"""Run against a disposable *_test PostgreSQL database, never production."""
import hashlib
import unittest
from unittest.mock import patch

import test_saas_phase8_integration as phase8
from import_audio_upload import CHUNK_BYTES,CompanionAudioUpload
from saas_auth import SaaSError


class CompanionAudioUploadTests(unittest.TestCase):
    setUpClass=classmethod(phase8.WorkspaceImportTests.setUpClass.__func__)
    tearDownClass=classmethod(phase8.WorkspaceImportTests.tearDownClass.__func__)
    setUp=phase8.WorkspaceImportTests.setUp
    verify=phase8.WorkspaceImportTests.verify

    def pending(self):
        owner=str(self.owner['id'])
        task=self.imports.create(owner,'text','Paired','paired.txt','chunked-audio',metadata={'awaitingAudioUpload':True})['task']['id']
        result=self.imports.upload(owner,task,'paired.txt',b'Original audio text.','text/plain')
        self.assertTrue(result['awaitingAudioUpload'])
        self.assertIn('完整配套音频',result['step'])
        body=b'a'*CHUNK_BYTES+b'b'*CHUNK_BYTES+b'the end'
        parts=[body[i:i+CHUNK_BYTES] for i in range(0,len(body),CHUNK_BYTES)]
        hashes=[hashlib.sha256(p).hexdigest() for p in parts]
        return owner,task,body,parts,hashes,self.imports.audio_upload()

    def test_out_of_order_resume_checks_bytes_then_registers_complete_audio_once(self):
        owner,task,body,parts,hashes,upload=self.pending()
        for index in [2,0]:upload.put(owner,task,'paired.mp3',len(body),index,hashes[index],parts[index])
        with self.assertRaises(SaaSError) as pending:upload.finish(owner,task,'paired.mp3',len(body),hashes)
        self.assertEqual(pending.exception.code,'companion_audio_pending')
        with self.assertRaises(SaaSError):self.imports.submit_complete(owner,task)
        resumed=CompanionAudioUpload(self.imports)
        self.assertEqual(set(resumed.status(owner,task)['received']),{'0','2'})
        resumed.put(owner,task,'paired.mp3',len(body),0,hashes[0],parts[0])
        resumed.put(owner,task,'paired.mp3',len(body),1,hashes[1],parts[1])
        with patch.object(self.imports,'audio_duration',return_value=4.2):resumed.finish(owner,task,'paired.mp3',len(body),hashes)
        self.assertTrue(resumed.finish(owner,task,'paired.mp3',len(body),hashes)['idempotent'])
        state=resumed.status(owner,task)
        self.assertTrue(state['finalized']);self.assertFalse(state['task']['awaitingAudioUpload'])
        self.assertFalse(resumed._directory(owner,task).exists())
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT byte_size,sha256 FROM asset_variants WHERE asset_id=%s AND variant_name='audio' AND deleted_at IS NULL",(state['task']['sourceAssetId'],))
                rows=self.accounts._many(cursor)
        self.assertEqual(rows,[{'byte_size':len(body),'sha256':hashlib.sha256(body).hexdigest()}])

    def test_foreign_user_and_wrong_official_scope_cannot_read_write_or_finalize(self):
        owner,task,body,parts,hashes,upload=self.pending()
        for actor,service in [(str(self.other['id']),upload),(owner,CompanionAudioUpload(type(self.imports)(self.accounts,self.memberships,self.media,official=True)))]:
            for action in [lambda:service.status(actor,task),lambda:service.put(actor,task,'paired.mp3',len(body),0,hashes[0],parts[0]),lambda:service.finish(actor,task,'paired.mp3',len(body),hashes)]:
                with self.assertRaises(SaaSError):action()
        self.assertFalse(upload._directory(owner,task).exists())

    def test_short_corrupt_and_conflicting_parts_never_register_partial_audio(self):
        owner,task,body,parts,hashes,upload=self.pending()
        for data,digest in [(parts[0][:-1],hashes[0]),(parts[0],hashes[1])]:
            with self.assertRaises(SaaSError):upload.put(owner,task,'paired.mp3',len(body),0,digest,data)
        upload.put(owner,task,'paired.mp3',len(body),0,hashes[0],parts[0])
        with self.assertRaises(SaaSError):upload.put(owner,task,'paired.mp3',len(body),0,hashes[1],parts[1])
        with self.assertRaises(SaaSError):upload.finish(owner,task,'paired.mp3',len(body),hashes)
        self.assertTrue(upload.status(owner,task)['task']['awaitingAudioUpload'])

    def test_lost_or_corrupt_staged_parts_are_requested_again(self):
        owner,task,body,parts,hashes,upload=self.pending()
        for index in [0,1]:upload.put(owner,task,'paired.mp3',len(body),index,hashes[index],parts[index])
        (upload._directory(owner,task)/'0.part').unlink()
        (upload._directory(owner,task)/'1.part').write_bytes(b'corrupted')
        self.assertEqual(upload.status(owner,task)['received'],{})
        upload.put(owner,task,'paired.mp3',len(body),0,hashes[0],parts[0])
        self.assertEqual(set(upload.status(owner,task)['received']),{'0'})

    def test_cancel_discards_parts_and_prevents_late_upload(self):
        owner,task,body,parts,hashes,upload=self.pending()
        upload.put(owner,task,'paired.mp3',len(body),0,hashes[0],parts[0])
        self.imports.cancel(owner,task)
        self.assertFalse(upload._directory(owner,task).exists())
        with self.assertRaises(SaaSError):upload.put(owner,task,'paired.mp3',len(body),1,hashes[1],parts[1])

    def test_filename_and_total_size_changes_are_rejected(self):
        owner,task,body,parts,hashes,upload=self.pending()
        with self.assertRaises(SaaSError):upload.put(owner,task,'other.mp3',len(body),0,hashes[0],parts[0])
        upload.put(owner,task,'paired.mp3',len(body),0,hashes[0],parts[0])
        with self.assertRaises(SaaSError):upload.put(owner,task,'paired.mp3',len(body)+1,0,hashes[0],parts[0])


if __name__=='__main__':unittest.main()
