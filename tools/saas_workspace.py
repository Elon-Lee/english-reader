#!/usr/bin/env python3
"""Owner-isolated private books, vocabulary, annotations, and study activity."""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from saas_auth import SaaSError, SaaSService, new_id, utcnow
from saas_membership import as_json, timestamp
from saas_rewards import local_day


class WorkspaceService:
    def __init__(self, accounts: SaaSService):
        self.accounts=accounts

    def _user(self,cursor:Any,user_id:str)->dict[str,Any]:
        cursor.execute("SELECT id,timezone,status FROM users WHERE id=%s FOR UPDATE",(user_id,));user=self.accounts._one(cursor)
        if not user or user["status"]!="active":raise SaaSError("account_unavailable","账号不可用。",403)
        return user

    def _book(self,cursor:Any,user_id:str,book_id:str,lock:bool=False)->dict[str,Any]:
        cursor.execute(f"SELECT * FROM content_books WHERE id=%s AND owner_id=%s AND visibility IN ('private','draft') {'FOR UPDATE' if lock else ''}",(book_id,user_id));book=self.accounts._one(cursor)
        if not book:raise SaaSError("workspace_book_not_found","私人读物不存在或你无权访问。",404)
        return book

    def _learning_book(self,cursor:Any,user_id:str,book_id:str,lock:bool=False)->tuple[str,str]:
        cursor.execute(f"SELECT id FROM content_books WHERE id=%s AND owner_id=%s AND visibility IN ('private','draft') {'FOR UPDATE' if lock else ''}",(book_id,user_id));private=self.accounts._one(cursor)
        if private:return str(private["id"]),str(private["id"])
        cursor.execute("""SELECT cb.id AS catalog_id,cb.source_content_book_id FROM catalog_books cb
        JOIN official_book_unlocks ou ON ou.catalog_book_id=cb.id AND ou.user_id=%s
        WHERE cb.id=%s AND cb.publication_status='published' AND cb.rights_status IN ('public_domain','licensed')""",(user_id,book_id));official=self.accounts._one(cursor)
        if official:return str(official["source_content_book_id"]),str(official["catalog_id"])
        raise SaaSError("learning_book_not_found","读物不存在、尚未解锁或你无权访问。",404)

    def _asset_summaries(self,cursor:Any,book_id:str)->list[dict[str,Any]]:
        cursor.execute("SELECT id,kind,content_type,original_bytes,generated_bytes FROM media_assets WHERE content_book_id=%s AND scope='private' AND status='active' ORDER BY created_at",(book_id,))
        assets=[]
        for row in self.accounts._many(cursor):
            cursor.execute("SELECT variant_name,content_type,byte_size FROM asset_variants WHERE asset_id=%s AND deleted_at IS NULL ORDER BY variant_name",(row["id"],))
            variants=[{"name":variant["variant_name"],"contentType":variant["content_type"],"bytes":int(variant["byte_size"]),"url":f"/api/media/{row['id']}?variant={variant['variant_name']}"} for variant in self.accounts._many(cursor)]
            assets.append({"id":row["id"],"kind":row["kind"],"contentType":row["content_type"],"bytes":int(row["original_bytes"])+int(row["generated_bytes"]),"url":f"/api/media/{row['id']}","variants":variants})
        return assets

    def list_books(self,user_id:str)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                self._user(cursor,user_id)
                cursor.execute("""SELECT cb.*,wp.last_sentence_id,wp.reading_seconds,wp.completed_at FROM content_books cb
                LEFT JOIN workspace_progress wp ON wp.content_book_id=cb.id AND wp.user_id=%s
                WHERE cb.owner_id=%s AND cb.visibility IN ('private','draft') ORDER BY cb.updated_at DESC""",(user_id,user_id))
                books=[]
                for row in self.accounts._many(cursor):
                    data=as_json(row["data_json"]);sentences=data.get("sentences",[]) if isinstance(data.get("sentences",[]),list) else []
                    books.append({"id":row["id"],"title":row["title"],"englishTitle":row["english_title"],"series":row["series"],"level":row["level"],"resourceType":row["source_type"],"sentenceCount":len(sentences),"duration":float(row["duration"]),"updatedAt":timestamp(row["updated_at"]),"progress":{"lastSentenceId":row["last_sentence_id"] or "","readingSeconds":int(row["reading_seconds"] or 0),"completedAt":timestamp(row["completed_at"])},"mediaCount":len(self._asset_summaries(cursor,row["id"]) )})
                return {"books":books}

    def delete_book(self,user_id:str,book_id:str,confirm_title:str="")->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                book=self._book(cursor,user_id,book_id,True)
                title=str(book.get("title","") or "")
                if confirm_title and confirm_title != title:
                    raise SaaSError("book_title_mismatch","确认标题与读物标题不一致。",400)
                cursor.execute("SELECT id FROM catalog_books WHERE source_content_book_id=%s",(book_id,))
                if cursor.fetchone():
                    raise SaaSError("book_is_catalog_source","该读物已作为官方书城内容发布，不能从私人工作区删除。",409)
                cursor.execute("UPDATE media_assets SET status='deleted',deleted_at=NOW() WHERE owner_id=%s AND content_book_id=%s AND status='active'",(user_id,book_id))
                cursor.execute("DELETE FROM content_books WHERE id=%s AND owner_id=%s",(book_id,user_id))
                return {"status":"deleted","bookId":book_id,"title":title}

    def reader(self,user_id:str,book_id:str)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                book=self._book(cursor,user_id,book_id);data=as_json(book["data_json"]);sentences=[]
                for item in data.get("sentences",[]) if isinstance(data.get("sentences",[]),list) else []:
                    if not isinstance(item,dict):continue
                    text=str(item.get("text","")).strip()
                    if text:sentences.append({"id":str(item.get("id",len(sentences))),"text":text,"translation":str(item.get("translation","")).strip(),"start":item.get("start"),"end":item.get("end"),"page":item.get("page"),"section":item.get("section"),"words":item.get("words",[]) if isinstance(item.get("words",[]),list) else []})
                cursor.execute("SELECT last_sentence_id,reading_seconds,completed_at FROM workspace_progress WHERE user_id=%s AND content_book_id=%s",(user_id,book_id));progress=self.accounts._one(cursor)or{}
                return {"book":{"id":book["id"],"title":book["title"],"englishTitle":book["english_title"],"series":book["series"],"level":book["level"],"resourceType":book["source_type"],"duration":float(book["duration"]),"sentences":sentences,"mediaAssets":self._asset_summaries(cursor,book_id),"progress":{"lastSentenceId":progress.get("last_sentence_id","") or "","readingSeconds":int(progress.get("reading_seconds",0)or 0),"completedAt":timestamp(progress.get("completed_at"))}}}

    def vocabulary(self,user_id:str,book_id:str="")->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                self._user(cursor,user_id);values=[user_id,user_id,user_id,user_id];where="""WHERE cv.owner_id=%s AND
                ((cb.owner_id=%s AND cb.visibility IN ('private','draft')) OR
                (ou.user_id=%s AND catalog.publication_status='published' AND catalog.rights_status IN ('public_domain','licensed')))"""
                public_book_id="COALESCE(catalog.id,cv.book_id)"
                if book_id:
                    storage_id,public_id=self._learning_book(cursor,user_id,book_id);where+=" AND cv.book_id=%s";values=[public_id,*values,storage_id];public_book_id="%s"
                cursor.execute(f"""SELECT cv.legacy_id,{public_book_id} AS public_book_id,cv.sentence_id,cv.word_index,cv.payload FROM content_vocabulary cv
                JOIN content_books cb ON cb.id=cv.book_id LEFT JOIN catalog_books catalog ON catalog.source_content_book_id=cv.book_id
                LEFT JOIN official_book_unlocks ou ON ou.catalog_book_id=catalog.id AND ou.user_id=%s {where} ORDER BY cv.legacy_id DESC""",values)
                return {"items":[{"id":int(row["legacy_id"]),"bookId":row["public_book_id"],"sentenceId":row["sentence_id"],"wordIndex":int(row["word_index"]),"payload":as_json(row["payload"])} for row in self.accounts._many(cursor)]}

    def annotations(self,user_id:str,book_id:str="")->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                self._user(cursor,user_id);values=[user_id,user_id];where="WHERE wa.owner_id=%s AND cb.owner_id=%s AND cb.visibility IN ('private','draft')"
                if book_id:
                    self._book(cursor,user_id,book_id);where+=" AND wa.book_id=%s";values.append(book_id)
                cursor.execute(f"SELECT wa.book_id,wa.sentence_id,wa.word_index,wa.payload FROM content_word_annotations wa JOIN content_books cb ON cb.id=wa.book_id {where} ORDER BY wa.book_id,wa.sentence_id,wa.word_index",values)
                return {"items":[{"bookId":row["book_id"],"sentenceId":row["sentence_id"],"wordIndex":int(row["word_index"]),"payload":as_json(row["payload"])} for row in self.accounts._many(cursor)]}

    def save_vocabulary(self,user_id:str,book_id:str,sentence_id:str,word_index:Any,payload:Any)->dict[str,Any]:
        if not isinstance(payload,dict):raise SaaSError("invalid_vocabulary","生词数据无效。",400)
        try:index=int(word_index)
        except (ValueError,TypeError) as exc:raise SaaSError("invalid_vocabulary","单词索引无效。",400) from exc
        if index<0:raise SaaSError("invalid_vocabulary","单词索引无效。",400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                storage_book_id,public_book_id=self._learning_book(cursor,user_id,book_id,True)
                cursor.execute("""INSERT INTO content_vocabulary(owner_id,book_id,sentence_id,word_index,payload)
                VALUES(%s,%s,%s,%s,%s::jsonb) ON CONFLICT (owner_id,book_id,sentence_id,word_index) DO UPDATE SET payload=EXCLUDED.payload
                RETURNING legacy_id""",(user_id,storage_book_id,str(sentence_id),index,json.dumps(payload)))
                row=self.accounts._one(cursor);return {"id":int(row["legacy_id"]),"bookId":public_book_id,"sentenceId":str(sentence_id),"wordIndex":index,"payload":payload}

    def annotate(self,user_id:str,book_id:str,sentence_id:str,word_index:Any,payload:Any)->dict[str,Any]:
        if not isinstance(payload,dict):raise SaaSError("invalid_annotation","标注数据无效。",400)
        try:index=int(word_index)
        except (ValueError,TypeError) as exc:raise SaaSError("invalid_annotation","单词索引无效。",400) from exc
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                self._book(cursor,user_id,book_id,True)
                cursor.execute("""INSERT INTO content_word_annotations(owner_id,book_id,sentence_id,word_index,payload)
                VALUES(%s,%s,%s,%s,%s::jsonb) ON CONFLICT (owner_id,book_id,sentence_id,word_index) DO UPDATE SET payload=EXCLUDED.payload""",(user_id,book_id,str(sentence_id),index,json.dumps(payload)))
                return {"bookId":book_id,"sentenceId":str(sentence_id),"wordIndex":index,"payload":payload}

    def learning_days(self,user_id:str,limit:Any=365)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                self._user(cursor,user_id);cursor.execute("SELECT day,payload FROM content_learning_daily WHERE owner_id=%s ORDER BY day DESC LIMIT %s",(user_id,max(1,min(730,int(limit)))))
                return {"days":[{"day":row["day"].isoformat(),"payload":as_json(row["payload"])} for row in self.accounts._many(cursor)]}

    def activity(self,user_id:str,book_id:str,reading_seconds:Any,sentences:Any,last_sentence_id:str,idempotency_key:str,lookups:Any=0,reviews:Any=0,shadow_attempts:Any=0,sessions:Any=0)->dict[str,Any]:
        try:
            seconds=max(0,min(86400,int(float(reading_seconds or 0))));sentence_count=max(0,min(10000,int(sentences or 0)))
            lookup_count=max(0,min(10000,int(lookups or 0)));review_count=max(0,min(10000,int(reviews or 0)))
            shadow_count=max(0,min(10000,int(shadow_attempts or 0)));session_count=max(0,min(10000,int(sessions or 0)))
        except (ValueError,TypeError) as exc:raise SaaSError("invalid_activity","学习活动数据无效。",400) from exc
        key=str(idempotency_key or "").strip()
        if not key:raise SaaSError("invalid_idempotency_key","操作标识无效。",400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                user=self._user(cursor,user_id);self._book(cursor,user_id,book_id,True);day=local_day(user["timezone"])
                cursor.execute("INSERT INTO workspace_activity_events(id,user_id,idempotency_key,content_book_id,activity_day,reading_seconds,sentences) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (user_id,idempotency_key) DO NOTHING RETURNING id",(new_id(),user_id,key,book_id,day,seconds,sentence_count))
                if not cursor.fetchone():return {"idempotent":True}
                cursor.execute("SELECT payload FROM content_learning_daily WHERE owner_id=%s AND day=%s FOR UPDATE",(user_id,day));existing=self.accounts._one(cursor);payload=as_json(existing["payload"]) if existing else {"day":day.isoformat()}
                payload["reading_seconds"]=float(payload.get("reading_seconds",0)or 0)+seconds;payload["sentences"]=int(payload.get("sentences",0)or 0)+sentence_count
                payload["lookups"]=int(payload.get("lookups",0)or 0)+lookup_count;payload["reviews"]=int(payload.get("reviews",0)or 0)+review_count
                payload["shadow_attempts"]=int(payload.get("shadow_attempts",0)or 0)+shadow_count;payload["sessions"]=int(payload.get("sessions",0)or 0)+session_count;payload["updated_at"]=timestamp(utcnow())
                cursor.execute("INSERT INTO content_learning_daily(owner_id,day,payload) VALUES(%s,%s,%s::jsonb) ON CONFLICT (owner_id,day) DO UPDATE SET payload=EXCLUDED.payload",(user_id,day,json.dumps(payload)))
                cursor.execute("""INSERT INTO workspace_progress(user_id,content_book_id,last_sentence_id,reading_seconds,updated_at)
                VALUES(%s,%s,%s,%s,NOW()) ON CONFLICT (user_id,content_book_id) DO UPDATE SET last_sentence_id=EXCLUDED.last_sentence_id,reading_seconds=workspace_progress.reading_seconds+EXCLUDED.reading_seconds,updated_at=NOW()""",(user_id,book_id,str(last_sentence_id or ""),seconds))
                return {"idempotent":False,"day":day.isoformat(),"readingSeconds":seconds,"sentences":sentence_count,"lookups":lookup_count,"reviews":review_count,"shadowAttempts":shadow_count,"sessions":session_count}
