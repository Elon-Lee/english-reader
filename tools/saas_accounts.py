#!/usr/bin/env python3
"""Privacy export and delayed account deletion lifecycle."""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from saas_auth import SaaSError, SaaSService, hash_password, new_id, utcnow
from saas_membership import as_json, timestamp


DELETION_GRACE_DAYS = 30


class AccountLifecycleService:
    def __init__(self, accounts: SaaSService):
        self.accounts=accounts

    def export(self,user_id:str)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,email,display_name,timezone,plan_version,email_verified_at,created_at,last_login_at FROM users WHERE id=%s",(user_id,));user=self.accounts._one(cursor)
                if not user:raise SaaSError("user_not_found","用户不存在。",404)
                cursor.execute("SELECT id,label,user_agent,first_seen_at,last_seen_at,revoked_at FROM devices WHERE user_id=%s",(user_id,));devices=[{"id":r["id"],"label":r["label"],"userAgent":r["user_agent"],"firstSeenAt":timestamp(r["first_seen_at"]),"lastSeenAt":timestamp(r["last_seen_at"]),"revoked":bool(r["revoked_at"])} for r in self.accounts._many(cursor)]
                cursor.execute("SELECT plan_version_id,status,starts_at,ends_at,note FROM subscriptions WHERE user_id=%s ORDER BY created_at",(user_id,));subscriptions=[{"planVersion":r["plan_version_id"],"status":r["status"],"startsAt":timestamp(r["starts_at"]),"endsAt":timestamp(r["ends_at"]),"note":r["note"]} for r in self.accounts._many(cursor)]
                cursor.execute("SELECT feature,quantity,reason,created_at FROM usage_ledger WHERE user_id=%s ORDER BY created_at",(user_id,));usage=[{"feature":r["feature"],"quantity":int(r["quantity"]),"reason":r["reason"],"createdAt":timestamp(r["created_at"])} for r in self.accounts._many(cursor)]
                cursor.execute("SELECT event_type,points,reward_day,created_at FROM reward_ledger WHERE user_id=%s ORDER BY created_at",(user_id,));rewards=[{"eventType":r["event_type"],"points":int(r["points"]),"day":r["reward_day"].isoformat() if r["reward_day"] else None,"createdAt":timestamp(r["created_at"])} for r in self.accounts._many(cursor)]
                cursor.execute("SELECT checkin_day,kind,streak_count FROM checkins WHERE user_id=%s ORDER BY checkin_day",(user_id,));checkins=[{"day":r["checkin_day"].isoformat(),"kind":r["kind"],"streak":int(r["streak_count"])} for r in self.accounts._many(cursor)]
                cursor.execute("""SELECT cb.id,cb.title,cb.english_title,ul.shelf_state,ul.added_at FROM user_library ul
                JOIN catalog_books cb ON cb.id=ul.catalog_book_id WHERE ul.user_id=%s""",(user_id,));library=[{"id":r["id"],"title":r["title"],"englishTitle":r["english_title"],"shelfState":r["shelf_state"],"addedAt":timestamp(r["added_at"])} for r in self.accounts._many(cursor)]
                cursor.execute("SELECT id,scope,kind,content_type,original_bytes,generated_bytes,storage_path,status,created_at FROM media_assets WHERE owner_id=%s",(user_id,));assets=[{"id":r["id"],"scope":r["scope"],"kind":r["kind"],"contentType":r["content_type"],"originalBytes":int(r["original_bytes"]),"generatedBytes":int(r["generated_bytes"]),"storagePath":r["storage_path"],"status":r["status"],"createdAt":timestamp(r["created_at"])} for r in self.accounts._many(cursor)]
                cursor.execute("SELECT id,title,english_title,series,level,source_type,status,visibility,created_at,updated_at FROM content_books WHERE owner_id=%s ORDER BY created_at",(user_id,));private_books=[{"id":r["id"],"title":r["title"],"englishTitle":r["english_title"],"series":r["series"],"level":r["level"],"sourceType":r["source_type"],"status":r["status"],"visibility":r["visibility"],"createdAt":timestamp(r["created_at"]),"updatedAt":timestamp(r["updated_at"])} for r in self.accounts._many(cursor)]
                cursor.execute("SELECT legacy_id,book_id,sentence_id,word_index,payload FROM content_vocabulary WHERE owner_id=%s ORDER BY legacy_id",(user_id,));vocabulary=[{"id":int(r["legacy_id"]),"bookId":r["book_id"],"sentenceId":r["sentence_id"],"wordIndex":int(r["word_index"]),"payload":as_json(r["payload"])} for r in self.accounts._many(cursor)]
                cursor.execute("SELECT book_id,sentence_id,word_index,payload FROM content_word_annotations WHERE owner_id=%s ORDER BY book_id,sentence_id,word_index",(user_id,));annotations=[{"bookId":r["book_id"],"sentenceId":r["sentence_id"],"wordIndex":int(r["word_index"]),"payload":as_json(r["payload"])} for r in self.accounts._many(cursor)]
                cursor.execute("SELECT day,payload FROM content_learning_daily WHERE owner_id=%s ORDER BY day",(user_id,));learning_days=[{"day":r["day"].isoformat(),"payload":as_json(r["payload"])} for r in self.accounts._many(cursor)]
                cursor.execute("SELECT content_book_id,result_type,content_key,payload,provider,created_at,updated_at FROM workspace_ai_results WHERE owner_id=%s ORDER BY created_at",(user_id,));ai_results=[{"bookId":r["content_book_id"],"type":r["result_type"],"contentKey":r["content_key"],"payload":as_json(r["payload"]),"provider":r["provider"],"createdAt":timestamp(r["created_at"]),"updatedAt":timestamp(r["updated_at"])} for r in self.accounts._many(cursor)]
                return {"exportedAt":timestamp(utcnow()),"account":{"id":user["id"],"email":user["email"],"displayName":user["display_name"],"timezone":user["timezone"],"planVersion":user["plan_version"],"emailVerified":bool(user["email_verified_at"]),"createdAt":timestamp(user["created_at"]),"lastLoginAt":timestamp(user["last_login_at"])},"devices":devices,"subscriptions":subscriptions,"usage":usage,"rewards":rewards,"checkins":checkins,"officialLibrary":library,"privateBooks":private_books,"vocabulary":vocabulary,"annotations":annotations,"learningDays":learning_days,"aiResults":ai_results,"assets":assets}

    def deletion_status(self,user_id:str)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT status,requested_at,scheduled_for,reason FROM account_deletion_requests WHERE user_id=%s",(user_id,));request=self.accounts._one(cursor)
                if not request:return {"status":"none"}
                return {"status":request["status"],"requestedAt":timestamp(request["requested_at"]),"scheduledFor":timestamp(request["scheduled_for"]),"reason":request["reason"]}

    def request_deletion(self,user_id:str,reason:str="")->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,status FROM users WHERE id=%s FOR UPDATE",(user_id,));user=self.accounts._one(cursor)
                if not user:raise SaaSError("user_not_found","用户不存在。",404)
                if user["status"]=="deleted":raise SaaSError("account_deleted","账号已删除。",409)
                schedule=utcnow()+timedelta(days=DELETION_GRACE_DAYS)
                cursor.execute("SELECT * FROM account_deletion_requests WHERE user_id=%s FOR UPDATE",(user_id,));existing=self.accounts._one(cursor)
                if existing and existing["status"]=="requested":return {"status":"requested","scheduledFor":timestamp(existing["scheduled_for"]),"idempotent":True}
                if existing:cursor.execute("UPDATE account_deletion_requests SET status='requested',requested_at=NOW(),scheduled_for=%s,cancelled_at=NULL,completed_at=NULL,reason=%s WHERE id=%s",(schedule,str(reason or "")[:1000],existing["id"]))
                else:cursor.execute("INSERT INTO account_deletion_requests(id,user_id,status,scheduled_for,reason) VALUES(%s,%s,'requested',%s,%s)",(new_id(),user_id,schedule,str(reason or "")[:1000]))
                # Keep the identity active during the grace period so the user
                # can sign in and cancel the request.  Existing sessions are
                # revoked, requiring a deliberate fresh login to continue.
                cursor.execute("UPDATE users SET updated_at=NOW() WHERE id=%s",(user_id,));cursor.execute("UPDATE user_sessions SET revoked_at=NOW() WHERE user_id=%s AND revoked_at IS NULL",(user_id,))
                return {"status":"requested","scheduledFor":timestamp(schedule),"idempotent":False}

    def cancel_deletion(self,user_id:str)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM account_deletion_requests WHERE user_id=%s FOR UPDATE",(user_id,));request=self.accounts._one(cursor)
                if not request or request["status"]!="requested":raise SaaSError("deletion_not_pending","当前没有可取消的注销请求。",409)
                cursor.execute("UPDATE account_deletion_requests SET status='cancelled',cancelled_at=NOW() WHERE id=%s",(request["id"],));cursor.execute("UPDATE users SET status='active',updated_at=NOW() WHERE id=%s",(user_id,))
                return {"status":"cancelled"}

    def cleanup_due_deletions(self)->dict[str,Any]:
        completed=[]
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM account_deletion_requests WHERE status='requested' AND scheduled_for<=NOW() FOR UPDATE SKIP LOCKED")
                for request in self.accounts._many(cursor):
                    user_id=request["user_id"]
                    cursor.execute("UPDATE user_sessions SET revoked_at=NOW() WHERE user_id=%s AND revoked_at IS NULL",(user_id,))
                    cursor.execute("UPDATE devices SET revoked_at=NOW() WHERE user_id=%s AND revoked_at IS NULL",(user_id,))
                    cursor.execute("UPDATE media_assets SET status='deleted',deleted_at=NOW() WHERE owner_id=%s AND scope='private' AND status='active'",(user_id,))
                    cursor.execute("UPDATE content_books SET visibility='blocked' WHERE owner_id=%s AND visibility='private'",(user_id,))
                    cursor.execute("DELETE FROM workspace_ai_results WHERE owner_id=%s",(user_id,))
                    cursor.execute("UPDATE users SET status='deleted',email=%s,display_name='',password_hash=%s,email_verified_at=NULL,updated_at=NOW() WHERE id=%s",(f"deleted-{user_id}@invalid.local",hash_password(new_id()+new_id()),user_id))
                    cursor.execute("UPDATE account_deletion_requests SET status='completed',completed_at=NOW() WHERE id=%s",(request["id"],));completed.append(user_id)
        return {"completedUserIds":completed}
