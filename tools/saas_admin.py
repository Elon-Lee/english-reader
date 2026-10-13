#!/usr/bin/env python3
"""Auditable operations service for SaaS Phase 5."""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime
from typing import Any

from saas_auth import SaaSError, SaaSService, new_id, utcnow
from saas_membership import FEATURES, MembershipService, as_json, parse_time, timestamp


class AdminService:
    def __init__(self, accounts: SaaSService, memberships: MembershipService):
        self.accounts, self.memberships = accounts, memberships

    def _audit(self, cursor: Any, actor_id: str, action: str, target_user_id: str | None = None, reason: str = "", payload: dict[str, Any] | None = None) -> None:
        cursor.execute(
            """INSERT INTO admin_audit_logs(id,actor_id,target_user_id,action,reason,payload_json)
            VALUES(%s,%s,%s,%s,%s,%s::jsonb)""",
            (new_id(), actor_id, target_user_id, action, str(reason or "")[:1000], json.dumps(payload or {})),
        )

    def record_action(self, actor_id: str, action: str, target_user_id: str | None = None, reason: str = "", payload: dict[str, Any] | None = None) -> None:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                self._audit(cursor, actor_id, action, target_user_id, reason, payload)

    def dashboard(self) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total,COUNT(*) FILTER (WHERE status='active') AS active,COUNT(*) FILTER (WHERE status='suspended') AS suspended,COUNT(*) FILTER (WHERE email_verified_at IS NOT NULL) AS verified FROM users")
                users=self.accounts._one(cursor) or {}
                cursor.execute("SELECT plan_version,COUNT(*) AS total FROM users GROUP BY plan_version ORDER BY plan_version")
                plans=[{"planVersion":r["plan_version"],"users":int(r["total"])} for r in self.accounts._many(cursor)]
                cursor.execute("SELECT COUNT(*) AS total FROM subscriptions WHERE status IN ('active','grace_period') AND starts_at<=NOW() AND ends_at>NOW()")
                active_subscriptions=int((self.accounts._one(cursor)or{"total":0})["total"])
                cursor.execute("SELECT COUNT(*) AS total FROM invitations WHERE status='active' AND (expires_at IS NULL OR expires_at>NOW()) AND used_count<max_uses AND verification_email_count<3")
                invitations=int((self.accounts._one(cursor)or{"total":0})["total"])
                cursor.execute("SELECT COUNT(*) AS total,COUNT(*) FILTER (WHERE publication_status='published') AS published FROM catalog_books")
                catalog=self.accounts._one(cursor)or{}
                cursor.execute("SELECT COALESCE(SUM(storage_bytes),0) AS bytes FROM assets WHERE status='active'")
                storage=int((self.accounts._one(cursor)or{"bytes":0})["bytes"])
                cursor.execute("SELECT COUNT(*) AS total FROM member_invites WHERE status IN ('registered','effective_learning','paid')")
                referrals=int((self.accounts._one(cursor)or{"total":0})["total"])
                return {"users":{"total":int(users.get("total",0)),"active":int(users.get("active",0)),"suspended":int(users.get("suspended",0)),"verified":int(users.get("verified",0))},"plans":plans,"activeSubscriptions":active_subscriptions,"activeInvitations":invitations,"catalog":{"total":int(catalog.get("total",0)),"published":int(catalog.get("published",0))},"storageBytes":storage,"referrals":referrals,"imports":{"available":False,"notice":"多租户导入任务将在私人工作区迁移后接入。"}}

    def users(self, query: str = "", limit: int = 100) -> dict[str, Any]:
        limit=max(1,min(200,int(limit)))
        terms=[];values=[]
        if query.strip():terms.append("(u.email ILIKE %s OR u.display_name ILIKE %s OR u.id=%s)");values += [f"%{query.strip()}%",f"%{query.strip()}%",query.strip()]
        where=("WHERE "+" AND ".join(terms)) if terms else ""
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"""SELECT u.id,u.email,u.display_name,u.status,u.plan_version,u.email_verified_at,u.created_at,u.last_login_at,
                COUNT(d.id) FILTER (WHERE d.revoked_at IS NULL) AS devices FROM users u LEFT JOIN devices d ON d.user_id=u.id
                {where} GROUP BY u.id ORDER BY u.created_at DESC LIMIT %s""",(*values,limit))
                return {"users":[{"id":r["id"],"email":r["email"],"displayName":r["display_name"],"status":r["status"],"planVersion":r["plan_version"],"emailVerified":bool(r["email_verified_at"]),"createdAt":timestamp(r["created_at"]),"lastLoginAt":timestamp(r["last_login_at"]),"devices":int(r["devices"])} for r in self.accounts._many(cursor)]}

    def user_detail(self, user_id: str) -> dict[str, Any]:
        users=self.users(user_id,1)["users"]
        if not users or users[0]["id"]!=user_id:raise SaaSError("user_not_found","用户不存在。",404)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,label,user_agent,first_seen_at,last_seen_at,revoked_at FROM devices WHERE user_id=%s ORDER BY last_seen_at DESC",(user_id,));devices=[{"id":r["id"],"label":r["label"],"userAgent":r["user_agent"],"firstSeenAt":timestamp(r["first_seen_at"]),"lastSeenAt":timestamp(r["last_seen_at"]),"revoked":bool(r["revoked_at"])} for r in self.accounts._many(cursor)]
                cursor.execute("SELECT id,plan_version_id,status,starts_at,ends_at,note FROM subscriptions WHERE user_id=%s ORDER BY created_at DESC LIMIT 20",(user_id,));subscriptions=[{"id":r["id"],"planVersion":r["plan_version_id"],"status":r["status"],"startsAt":timestamp(r["starts_at"]),"endsAt":timestamp(r["ends_at"]),"note":r["note"]} for r in self.accounts._many(cursor)]
                cursor.execute("SELECT feature,COALESCE(SUM(quantity),0) AS total FROM usage_ledger WHERE user_id=%s GROUP BY feature ORDER BY feature",(user_id,));usage=[{"feature":r["feature"],"netUsage":int(r["total"])} for r in self.accounts._many(cursor)]
                cursor.execute("SELECT COALESCE(SUM(points),0) AS balance FROM reward_ledger WHERE user_id=%s",(user_id,));growth=int((self.accounts._one(cursor)or{"balance":0})["balance"])
                cursor.execute("SELECT id,plan_version_id,status,starts_at,ends_at,amount_cents,currency,note,created_at FROM manual_orders WHERE user_id=%s ORDER BY created_at DESC LIMIT 20",(user_id,));orders=[{"id":r["id"],"planVersion":r["plan_version_id"],"status":r["status"],"startsAt":timestamp(r["starts_at"]),"endsAt":timestamp(r["ends_at"]),"amountCents":int(r["amount_cents"]),"currency":r["currency"],"note":r["note"],"createdAt":timestamp(r["created_at"])} for r in self.accounts._many(cursor)]
                return {"user":users[0],"devices":devices,"subscriptions":subscriptions,"orders":orders,"usage":usage,"growthBalance":growth}

    def set_user_status(self, actor_id: str, user_id: str, status: str, reason: str) -> dict[str, Any]:
        if status not in {"active","suspended"}:raise SaaSError("invalid_user_status","仅支持启用或封禁账号。",400)
        if actor_id==user_id and status!="active":raise SaaSError("invalid_user_status","不能封禁当前管理员账号。",400)
        if not str(reason or "").strip():raise SaaSError("audit_reason_required","封禁或恢复账号需要填写操作原因。",400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE id=%s FOR UPDATE",(user_id,))
                if not cursor.fetchone():raise SaaSError("user_not_found","用户不存在。",404)
                cursor.execute("UPDATE users SET status=%s,updated_at=NOW() WHERE id=%s",(status,user_id))
                if status=="suspended":cursor.execute("UPDATE user_sessions SET revoked_at=NOW() WHERE user_id=%s AND revoked_at IS NULL",(user_id,))
                self._audit(cursor,actor_id,"user_status",user_id,reason,{"status":status})
                return {"userId":user_id,"status":status}

    def revoke_device(self, actor_id: str, user_id: str, device_id: str, reason: str) -> dict[str, Any]:
        if not str(reason or "").strip(): raise SaaSError("audit_reason_required", "撤销设备需要填写操作原因。", 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE id=%s", (user_id,))
                if not cursor.fetchone(): raise SaaSError("user_not_found", "用户不存在。", 404)
                cursor.execute("SELECT id,revoked_at FROM devices WHERE id=%s AND user_id=%s FOR UPDATE", (device_id, user_id))
                device = self.accounts._one(cursor)
                if not device: raise SaaSError("device_not_found", "设备不存在或不属于该用户。", 404)
                if device["revoked_at"]:
                    return {"userId": user_id, "deviceId": device_id, "status": "revoked", "idempotent": True}
                cursor.execute("UPDATE devices SET revoked_at=NOW() WHERE id=%s", (device_id,))
                cursor.execute("UPDATE user_sessions SET revoked_at=NOW() WHERE user_id=%s AND device_id=%s AND revoked_at IS NULL", (user_id, device_id))
                self._audit(cursor, actor_id, "device_revoked", user_id, reason, {"deviceId": device_id})
                return {"userId": user_id, "deviceId": device_id, "status": "revoked", "idempotent": False}

    def invitations(self, limit: int = 100, query: str = "", offset: int = 0) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                term=str(query or "").strip();where="WHERE (i.code ILIKE %s OR i.note ILIKE %s OR i.channel ILIKE %s)" if term else "";values=[f"%{term}%"]*3 if term else []
                cursor.execute(f"SELECT COUNT(*) AS total FROM invitations i {where}",values);total=int((self.accounts._one(cursor)or{"total":0})["total"])
                cursor.execute("""SELECT i.*,u.email AS creator_email FROM invitations i LEFT JOIN users u ON u.id=i.created_by
                """+where+" ORDER BY i.created_at DESC LIMIT %s OFFSET %s",(*values,max(1,min(200,int(limit))),max(0,int(offset))))
                return {"invitations":[{"id":r["id"],"code":r["code"],"channel":r["channel"],"status":r["status"],"maxUses":int(r["max_uses"]),"usedCount":int(r["used_count"]),"verificationEmailCount":int(r["verification_email_count"]),"verificationEmailLimit":3,"expiresAt":timestamp(r["expires_at"]),"note":r["note"],"createdBy":r["creator_email"],"createdAt":timestamp(r["created_at"])} for r in self.accounts._many(cursor)],"total":total,"limit":max(1,min(200,int(limit))),"offset":max(0,int(offset))}

    def create_invitation(self, actor_id: str, code: str, max_uses: int, expires_at: Any = None, note: str = "", channel: str = "") -> dict[str, Any]:
        expiry=parse_time(expires_at,"expiresAt") if expires_at else None
        normalized=str(code or "").strip();candidate=normalized or f"SHIYUE-{secrets.token_hex(5).upper()}"
        invitation=self.accounts.create_invitation(candidate,int(max_uses),expiry,actor_id,note,channel)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:self._audit(cursor,actor_id,"invitation_created",None,note,{"invitationId":invitation["id"],"code":invitation["code"],"channel":channel})
        return {"id":invitation["id"],"code":invitation["code"],"channel":invitation["channel"],"maxUses":int(invitation["max_uses"]),"expiresAt":timestamp(invitation["expires_at"])}

    def create_invitations(self,actor_id:str,code:str,max_uses:Any,count:Any=1,expires_at:Any=None,note:str="",channel:str="")->dict[str,Any]:
        try:quantity=max(1,min(100,int(count)))
        except (TypeError,ValueError) as exc:raise SaaSError("invalid_invitation","生成数量无效。",400) from exc
        if str(code or "").strip() and quantity>1:raise SaaSError("invalid_invitation","指定邀请码时只能生成一个；批量生成请留空邀请码。",400)
        try:uses=int(max_uses)
        except (TypeError,ValueError) as exc:raise SaaSError("invalid_invitation","邀请码使用次数无效。",400) from exc
        if uses<1 or uses>1_000_000:raise SaaSError("invalid_invitation","邀请码使用次数无效。",400)
        expiry=parse_time(expires_at,"expiresAt") if expires_at else None
        normalized=re.sub(r"\s+","",str(code or "").upper());batch_id="invite-batch-"+new_id();items=[]
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO invitation_batches(id,requested_count,max_uses,expires_at,created_by,note,channel)
                VALUES(%s,%s,%s,%s,%s,%s,%s)""",(batch_id,quantity,uses,expiry,actor_id,str(note or "")[:1000],str(channel or "")[:100]))
                for index in range(quantity):
                    candidate=normalized if index==0 and normalized else f"SHIYUE-{secrets.token_hex(5).upper()}"
                    if not re.fullmatch(r"[A-Z0-9_-]{4,64}",candidate):raise SaaSError("invalid_invitation","邀请码需为 4～64 位的大写字母、数字、下划线或连字符。")
                    invitation_id=new_id();cursor.execute("""INSERT INTO invitations(id,code,max_uses,expires_at,created_by,note,channel,batch_id)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",(invitation_id,candidate,uses,expiry,actor_id,str(note or "")[:1000],str(channel or "")[:100],batch_id))
                    items.append({"id":invitation_id,"code":candidate,"maxUses":uses,"usedCount":0,"status":"active","deletable":True})
                self._audit(cursor,actor_id,"invitation_batch_created",None,note,{"batchId":batch_id,"count":quantity,"maxUses":uses,"channel":channel})
        result={"batch":{"id":batch_id,"count":quantity,"unusedCount":quantity,"usedCount":0,"maxUses":uses,"expiresAt":timestamp(expiry),"note":str(note or "")[:1000],"channel":str(channel or "")[:100],"createdAt":timestamp(utcnow())},"invitations":items,"count":quantity}
        if quantity==1:result.update({"id":items[0]["id"],"code":items[0]["code"],"channel":str(channel or "")[:100],"maxUses":uses,"expiresAt":timestamp(expiry)})
        return result

    def invitation_batches(self,limit:Any=50,query:str="",offset:Any=0)->dict[str,Any]:
        size=max(1,min(200,int(limit)));start=max(0,int(offset));term=str(query or "").strip();values=[]
        where=""
        if term:
            where="WHERE (b.note ILIKE %s OR b.channel ILIKE %s OR EXISTS(SELECT 1 FROM invitations ix WHERE ix.batch_id=b.id AND ix.code ILIKE %s))"
            values=[f"%{term}%"]*3
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) AS total FROM invitation_batches b {where}",values);total=int((self.accounts._one(cursor)or{"total":0})["total"])
                cursor.execute(f"""SELECT b.*,u.email AS creator_email,COUNT(i.id) AS actual_count,
                COUNT(i.id) FILTER(WHERE i.used_count=0) AS unused_count,COUNT(i.id) FILTER(WHERE i.used_count>0) AS used_count,
                COALESCE(SUM(i.used_count),0) AS registrations
                FROM invitation_batches b LEFT JOIN invitations i ON i.batch_id=b.id LEFT JOIN users u ON u.id=b.created_by
                {where} GROUP BY b.id,u.email ORDER BY b.created_at DESC LIMIT %s OFFSET %s""",(*values,size,start))
                batches=[]
                for row in self.accounts._many(cursor):
                    expired=bool(row["expires_at"] and row["expires_at"]<=datetime.now().astimezone())
                    actual=int(row["actual_count"]);unused=int(row["unused_count"]);used=int(row["used_count"])
                    status="expired" if expired else "empty" if actual==0 else "unused" if used==0 else "partial" if unused>0 else "used"
                    batches.append({"id":row["id"],"count":actual,"requestedCount":int(row["requested_count"]),"unusedCount":unused,"usedCount":used,"registrations":int(row["registrations"]),"maxUses":int(row["max_uses"]),"expiresAt":timestamp(row["expires_at"]),"note":row["note"],"channel":row["channel"],"createdBy":row["creator_email"],"createdAt":timestamp(row["created_at"]),"status":status})
                return {"batches":batches,"total":total,"limit":size,"offset":start}

    def invitation_batch_detail(self,batch_id:str)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT b.*,u.email AS creator_email FROM invitation_batches b LEFT JOIN users u ON u.id=b.created_by WHERE b.id=%s",(batch_id,));batch=self.accounts._one(cursor)
                if not batch:raise SaaSError("invitation_batch_not_found","邀请码批次不存在。",404)
                cursor.execute("""SELECT i.*,NOT EXISTS(SELECT 1 FROM invitation_uses iu WHERE iu.invitation_id=i.id)
                AND NOT EXISTS(SELECT 1 FROM member_invites mi WHERE mi.invitation_id=i.id) AS deletable
                FROM invitations i WHERE i.batch_id=%s ORDER BY i.created_at,i.code""",(batch_id,));codes=[]
                for row in self.accounts._many(cursor):
                    cursor.execute("SELECT email,used_at FROM invitation_uses WHERE invitation_id=%s ORDER BY used_at",(row["id"],));uses=[{"email":item["email"],"usedAt":timestamp(item["used_at"])} for item in self.accounts._many(cursor)]
                    codes.append({"id":row["id"],"code":row["code"],"status":row["status"],"maxUses":int(row["max_uses"]),"usedCount":int(row["used_count"]),"verificationEmailCount":int(row["verification_email_count"]),"deletable":bool(row["deletable"] and int(row["used_count"])==0),"uses":uses})
                return {"batch":{"id":batch["id"],"requestedCount":int(batch["requested_count"]),"maxUses":int(batch["max_uses"]),"expiresAt":timestamp(batch["expires_at"]),"note":batch["note"],"channel":batch["channel"],"createdBy":batch["creator_email"],"createdAt":timestamp(batch["created_at"])},"invitations":codes}

    def delete_unused_invitations(self,actor_id:str,batch_id:str,invitation_ids:Any)->dict[str,Any]:
        ids=[str(item).strip() for item in (invitation_ids or []) if str(item).strip()]
        if not ids:raise SaaSError("invitation_selection_required","请选择要删除的未使用邀请码。",400)
        if len(ids)>100:raise SaaSError("invalid_invitation_selection","单次最多删除 100 个邀请码。",400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT i.id,i.code,i.used_count,EXISTS(SELECT 1 FROM invitation_uses iu WHERE iu.invitation_id=i.id) AS has_uses,
                EXISTS(SELECT 1 FROM member_invites mi WHERE mi.invitation_id=i.id) AS has_referral
                FROM invitations i WHERE i.batch_id=%s AND i.id=ANY(%s) FOR UPDATE""",(batch_id,ids));rows=self.accounts._many(cursor)
                if len(rows)!=len(set(ids)):raise SaaSError("invalid_invitation_selection","部分邀请码不存在或不属于该批次。",400)
                blocked=[row["code"] for row in rows if int(row["used_count"])>0 or row["has_uses"] or row["has_referral"]]
                if blocked:raise SaaSError("invitation_in_use","已使用或关联邀请奖励的邀请码不能删除。",409,{"codes":blocked})
                cursor.execute("DELETE FROM invitations WHERE batch_id=%s AND id=ANY(%s)",(batch_id,ids));deleted=cursor.rowcount
                cursor.execute("SELECT COUNT(*) AS total FROM invitations WHERE batch_id=%s",(batch_id,));remaining=int((self.accounts._one(cursor)or{"total":0})["total"])
                if remaining==0:cursor.execute("DELETE FROM invitation_batches WHERE id=%s",(batch_id,))
                self._audit(cursor,actor_id,"unused_invitations_deleted",None,"批量删除未使用邀请码",{"batchId":batch_id,"invitationIds":ids,"deleted":deleted})
                return {"batchId":batch_id,"deleted":int(deleted),"remaining":remaining,"batchDeleted":remaining==0}

    def adjust_quota(self, actor_id: str, user_id: str, feature: str, quantity: Any, reason: str, idempotency_key: str) -> dict[str, Any]:
        if not str(reason or "").strip():raise SaaSError("audit_reason_required","调整额度需要填写原因。",400)
        try: amount=int(quantity)
        except (TypeError,ValueError) as exc:raise SaaSError("invalid_quantity","额度调整数量无效。",400) from exc
        summary=self.memberships.adjust(user_id,feature,amount,idempotency_key,actor_id,reason)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:self._audit(cursor,actor_id,"quota_adjustment",user_id,reason,{"feature":feature,"quantity":amount,"idempotencyKey":idempotency_key})
        return summary

    def grant_invite_allowance(self, actor_id: str, user_id: str, quantity: Any, reason: str, expires_at: Any = None) -> dict[str, Any]:
        try: amount=int(quantity)
        except (TypeError,ValueError) as exc:raise SaaSError("invalid_quantity","邀请码额度数量无效。",400) from exc
        if amount<1:raise SaaSError("invalid_quantity","邀请码额度必须大于零。",400)
        if not str(reason or "").strip():raise SaaSError("audit_reason_required","发放邀请码额度需要填写原因。",400)
        expiry=parse_time(expires_at,"expiresAt") if expires_at else None
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE id=%s FOR UPDATE",(user_id,))
                if not cursor.fetchone():raise SaaSError("user_not_found","用户不存在。",404)
                allowance_id=new_id();cursor.execute("INSERT INTO member_invite_allowances(id,user_id,quantity_remaining,source,note,expires_at,created_by) VALUES(%s,%s,%s,'admin',%s,%s,%s)",(allowance_id,user_id,amount,reason[:1000],expiry,actor_id))
                self._audit(cursor,actor_id,"invite_allowance_granted",user_id,reason,{"allowanceId":allowance_id,"quantity":amount,"expiresAt":timestamp(expiry)})
                return {"id":allowance_id,"userId":user_id,"quantity":amount,"expiresAt":timestamp(expiry)}

    def plan_versions(self) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pv.*,p.slug AS plan_slug FROM plan_versions pv JOIN plans p ON p.id=pv.plan_id ORDER BY pv.rank,pv.created_at")
                return {"planVersions":[{"id":r["id"],"planSlug":r["plan_slug"],"name":r["display_name"],"rank":int(r["rank"]),"periodDays":int(r["period_days"]),"quotas":as_json(r["quotas_json"]),"pricing":as_json(r["pricing_json"]),"active":bool(r["active"]),"createdAt":timestamp(r["created_at"])} for r in self.accounts._many(cursor)]}

    def create_plan_version(self, actor_id: str, version_id: str, plan_slug: str, display_name: str, rank: Any, period_days: Any, quotas: Any, pricing: Any) -> dict[str, Any]:
        version_id=str(version_id or "").strip();plan_slug=str(plan_slug or "").strip();display_name=str(display_name or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9-]{2,63}",version_id):raise SaaSError("invalid_plan_version","套餐版本 ID 无效。",400)
        if not display_name:raise SaaSError("invalid_plan_version","套餐显示名称不能为空。",400)
        if not isinstance(quotas,dict):raise SaaSError("invalid_plan_version","套餐额度必须是对象。",400)
        try: rank_value,days=int(rank),int(period_days)
        except (TypeError,ValueError) as exc:raise SaaSError("invalid_plan_version","套餐等级或账期无效。",400) from exc
        if rank_value<0 or days<1:raise SaaSError("invalid_plan_version","套餐等级或账期无效。",400)
        normalized={}
        for feature in FEATURES:
            try: value=int(quotas[feature])
            except (KeyError,TypeError,ValueError) as exc:raise SaaSError("invalid_plan_version",f"缺少或无效额度：{feature}",400) from exc
            if value<0:raise SaaSError("invalid_plan_version",f"额度不能为负数：{feature}",400)
            normalized[feature]=value
        if not isinstance(pricing,dict):pricing={}
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM plans WHERE slug=%s FOR UPDATE",(plan_slug,));plan=self.accounts._one(cursor)
                if not plan:raise SaaSError("unknown_plan","套餐不存在。",404)
                cursor.execute("INSERT INTO plan_versions(id,plan_id,display_name,rank,period_days,quotas_json,pricing_json) VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)",(version_id,plan["id"],display_name,rank_value,days,json.dumps(normalized),json.dumps(pricing)))
                self._audit(cursor,actor_id,"plan_version_created",None,"",{"versionId":version_id,"planSlug":plan_slug})
                return {"id":version_id,"planSlug":plan_slug,"name":display_name,"rank":rank_value,"periodDays":days,"quotas":normalized,"pricing":pricing}

    def audit(self, limit: int = 100, query: str = "", action: str = "") -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                terms, values = [], []
                if str(query or "").strip():
                    terms.append("(a.action ILIKE %s OR a.reason ILIKE %s OR actor.email ILIKE %s OR target.email ILIKE %s)")
                    values.extend([f"%{str(query).strip()}%"] * 4)
                if str(action or "").strip():
                    terms.append("a.action=%s"); values.append(str(action).strip())
                where = f"WHERE {' AND '.join(terms)}" if terms else ""
                cursor.execute(f"""SELECT a.*,actor.email AS actor_email,target.email AS target_email FROM admin_audit_logs a
                LEFT JOIN users actor ON actor.id=a.actor_id LEFT JOIN users target ON target.id=a.target_user_id
                {where} ORDER BY a.created_at DESC LIMIT %s""",(*values,max(1,min(300,int(limit)))))
                return {"items":[{"id":r["id"],"action":r["action"],"actor":r["actor_email"],"target":r["target_email"],"reason":r["reason"],"payload":as_json(r["payload_json"]),"createdAt":timestamp(r["created_at"])} for r in self.accounts._many(cursor)]}

    def platform_config(self) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT value_json,updated_at FROM platform_settings WHERE key='ai.dioco'");row=self.accounts._one(cursor);value=as_json(row["value_json"]) if row else {}
                token=str(value.get("token","")or"")
                return {"dioco":{"configured":bool(token),"emailConfigured":bool(value.get("email")),"email":str(value.get("email","")or""),"upstream":str(value.get("upstream","")or"https://api-cdn-plus.dioco.io"),"tokenMask":("••••"+token[-4:]) if token else "","source":"database","updatedAt":timestamp(row.get("updated_at")) if row else None}}

    def update_platform_config(self,actor_id:str,item:dict[str,Any])->dict[str,Any]:
        email=str(item.get("email","")or"").strip();upstream=str(item.get("upstream","")or"https://api-cdn-plus.dioco.io").strip().rstrip("/");token=str(item.get("token","")or"").strip();clear=bool(item.get("clearToken",False))
        if email and ("@" not in email or len(email)>320):raise SaaSError("invalid_platform_config","AI 服务邮箱无效。",400)
        if not upstream.startswith(("https://","http://")):raise SaaSError("invalid_platform_config","AI 服务地址必须是 HTTP 或 HTTPS 地址。",400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT value_json FROM platform_settings WHERE key='ai.dioco' FOR UPDATE");row=self.accounts._one(cursor);current=as_json(row["value_json"]) if row else {}
                next_value={"email":email,"upstream":upstream,"token":"" if clear else token or str(current.get("token","")or"")}
                cursor.execute("""INSERT INTO platform_settings(key,value_json,updated_by) VALUES('ai.dioco',%s::jsonb,%s)
                ON CONFLICT(key) DO UPDATE SET value_json=EXCLUDED.value_json,updated_by=EXCLUDED.updated_by,updated_at=NOW()""",(json.dumps(next_value),actor_id))
                self._audit(cursor,actor_id,"platform_ai_config_updated",None,"",{"emailConfigured":bool(email),"tokenConfigured":bool(next_value["token"]),"upstream":upstream})
        return self.platform_config()

    def export_summary(self) -> dict[str, Any]:
        dashboard=self.dashboard();users=self.users(limit=200)["users"]
        return {"generatedAt":timestamp(datetime.now().astimezone()),"dashboard":dashboard,"users":[{"email":u["email"],"status":u["status"],"planVersion":u["planVersion"],"devices":u["devices"],"createdAt":u["createdAt"]} for u in users]}
