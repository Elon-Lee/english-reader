"""Resumable companion MP3 transport; document/media processing stays unchanged."""
from __future__ import annotations

import hashlib
import json
import mmap
import os
import re
import shutil
from contextlib import contextmanager
from pathlib import Path

from saas_auth import SaaSError
from saas_membership import as_json

CHUNK_BYTES=256*1024
MAX_AUDIO_BYTES=2*1024*1024*1024


class CompanionAudioUpload:
    def __init__(self,imports):
        self.imports=imports
        self.accounts=imports.accounts

    def _directory(self,user_id,task_id):
        key=hashlib.sha256(f'{user_id}:{task_id}:{self.imports.official}'.encode()).hexdigest()
        return self.imports.media.media_root/'.pending-audio'/key

    @contextmanager
    def _lock(self,user_id,task_id):
        connection=self.accounts._connect()
        # Reserve pending bytes consistently across this user's simultaneous tasks.
        key=f'companion-chunks:{user_id}'
        try:
            with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_lock(hashtextextended(%s,0))',(key,))
            yield
        finally:
            try:
                with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))',(key,))
            finally:connection.close()

    def _task(self,user_id,task_id):
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:return self.imports._task(cursor,user_id,task_id)

    @staticmethod
    def _manifest(directory):
        path=directory/'manifest.json'
        return json.loads(path.read_text()) if path.is_file() else None

    @staticmethod
    def _save(directory,value):
        directory.mkdir(parents=True,exist_ok=True)
        temporary=directory/'manifest.tmp'
        temporary.write_text(json.dumps(value))
        os.replace(temporary,directory/'manifest.json')

    def status(self,user_id,task_id):
        with self._lock(user_id,task_id):
            task=self._task(user_id,task_id)
            receipt=as_json(task['metadata_json']).get('audioUploadReceipt')
            directory=self._directory(user_id,task_id)
            state=receipt or self._manifest(directory) or {}
            if state and not receipt:
                valid={key:digest for key,digest in state['received'].items() if (directory/f'{key}.part').is_file() and hashlib.sha256((directory/f'{key}.part').read_bytes()).hexdigest()==digest}
                if valid!=state['received']:
                    state['received']=valid
                    self._save(directory,state)
            return {'chunkSize':CHUNK_BYTES,'filename':state.get('filename',''),'totalBytes':state.get('totalBytes',0),
                    'received':state.get('received',{}),'finalized':bool(receipt),'task':self.imports._public(task)}

    def _validate(self,user_id,task,filename,total):
        if type(total) is not int or not 0<total<=MAX_AUDIO_BYTES:
            raise SaaSError('invalid_audio_upload','MP3 文件为空或超过大小限制。',413)
        if task['status']!='queued' or task['kind'] not in {'text','document'}:
            raise SaaSError('audio_upload_not_allowed','该任务当前不能补传配套音频。',409)
        safe_name=re.sub(r'[^A-Za-z0-9._-]+','-',Path(str(filename)).name).strip('-')
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:source=self.imports._source_path(cursor,user_id,task)
        if Path(safe_name).suffix.lower()!='.mp3' or Path(safe_name).stem.casefold()!=source.stem.casefold():
            raise SaaSError('audio_name_mismatch','请选择与文档同名的完整 MP3。',400)
        return safe_name

    @staticmethod
    def _same_file(state,filename,total):
        if state and (state['filename']!=filename or state['totalBytes']!=total):
            raise SaaSError('audio_source_conflict','已保留其他音频的分段，请选择原来上传的完整 MP3。',409)

    def put(self,user_id,task_id,filename,total,index,digest,data):
        if type(index) is not int or type(total) is not int or not 0<total<=MAX_AUDIO_BYTES or not 0<=index<(total+CHUNK_BYTES-1)//CHUNK_BYTES:
            raise SaaSError('invalid_audio_chunk','音频分段参数无效。',400)
        expected=min(CHUNK_BYTES,total-index*CHUNK_BYTES)
        if len(data)!=expected or not re.fullmatch(r'[0-9a-f]{64}',str(digest)) or hashlib.sha256(data).hexdigest()!=digest:
            raise SaaSError('incomplete_upload','音频分段不完整或校验失败，请重试。',400)
        with self._lock(user_id,task_id):
            task=self._task(user_id,task_id)
            name=self._validate(user_id,task,filename,total)
            if as_json(task['metadata_json']).get('audioUploadReceipt'):
                raise SaaSError('audio_upload_not_allowed','完整配套音频已经上传。',409)
            directory=self._directory(user_id,task_id)
            state=self._manifest(directory)
            self._same_file(state,str(filename),total)
            if state is None:
                if not self.imports.official:
                    pending=0
                    for path in directory.parent.glob('*/manifest.json'):
                        other=json.loads(path.read_text())
                        if other.get('userId')==user_id and not other.get('official'):pending+=other['totalBytes']
                    self.imports.media.ensure_private_capacity(user_id,total+pending)
                state={'filename':str(filename),'totalBytes':total,'received':{},'userId':user_id,'official':self.imports.official}
            key=str(index)
            if key in state['received'] and state['received'][key]!=digest:
                raise SaaSError('audio_source_conflict','音频内容与已上传分段不同，请选择同一份完整 MP3。',409)
            directory.mkdir(parents=True,exist_ok=True)
            part=directory/f'{index}.part'
            temporary=directory/f'{index}.tmp'
            temporary.write_bytes(data)
            os.replace(temporary,part)
            state['received'][key]=digest
            self._save(directory,state)
            count=(total+CHUNK_BYTES-1)//CHUNK_BYTES
            with self.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    current=self.imports._task(cursor,user_id,task_id)
                    if current['status']!='queued':raise SaaSError('import_task_terminal','任务已取消或结束。',409)
                    cursor.execute("UPDATE workspace_import_tasks SET progress=%s,step=%s,updated_at=NOW() WHERE id=%s",(15+int(15*len(state['received'])/count),f"配套音频上传 {len(state['received'])}/{count} 段，未传完不会导入",task_id))
            return {'index':index,'sha256':digest,'receivedCount':len(state['received']),'partCount':count}

    def finish(self,user_id,task_id,filename,total,hashes):
        with self._lock(user_id,task_id):
            task=self._task(user_id,task_id)
            receipt=as_json(task['metadata_json']).get('audioUploadReceipt')
            if receipt:
                self._same_file(receipt,filename,total)
                if not isinstance(hashes,list) or hashes!=[receipt['received'][str(i)] for i in range(len(receipt['received']))]:
                    raise SaaSError('audio_source_conflict','音频内容与已完成上传不同。',409)
                return {'task':self.imports._public(task),'idempotent':True}
            name=self._validate(user_id,task,filename,total)
            directory=self._directory(user_id,task_id)
            state=self._manifest(directory)
            self._same_file(state,str(filename),total)
            count=(total+CHUNK_BYTES-1)//CHUNK_BYTES
            if not state or not isinstance(hashes,list) or len(hashes)!=count or len(state['received'])!=count:
                raise SaaSError('companion_audio_pending','配套音频分段未上传完整，请继续补传。',409)
            merged=directory/'complete.mp3'
            try:
                with merged.open('wb') as output:
                    for index,digest in enumerate(hashes):
                        part=directory/f'{index}.part'
                        data=part.read_bytes() if part.is_file() else b''
                        if state['received'].get(str(index))!=digest or hashlib.sha256(data).hexdigest()!=digest or len(data)!=min(CHUNK_BYTES,total-index*CHUNK_BYTES):
                            state['received'].pop(str(index),None)
                            self._save(directory,state)
                            raise SaaSError('incomplete_upload','音频分段校验失败，请补传对应分段。',400)
                        output.write(data)
                if merged.stat().st_size!=total:raise SaaSError('incomplete_upload','音频尚未上传完整。',400)
                with merged.open('rb') as handle,mmap.mmap(handle.fileno(),0,access=mmap.ACCESS_READ) as audio:
                    digest=hashlib.sha256(audio).hexdigest()
                    self.imports.upload_audio(user_id,task_id,name,audio)
                with self.accounts.transaction() as connection:
                    with connection.cursor() as cursor:
                        current=self.imports._task(cursor,user_id,task_id)
                        cursor.execute("UPDATE workspace_import_tasks SET metadata_json=metadata_json || %s::jsonb,step='完整配套音频已上传，等待处理',updated_at=NOW() WHERE id=%s",(json.dumps({'audioUploadReceipt':{**state,'sha256':digest}}),task_id))
                shutil.rmtree(directory,ignore_errors=True)
                return {'task':self.imports._public(current),'idempotent':False}
            finally:merged.unlink(missing_ok=True)

    def discard(self,user_id,task_id):
        with self._lock(user_id,task_id):shutil.rmtree(self._directory(user_id,task_id),ignore_errors=True)
