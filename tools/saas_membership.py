#!/usr/bin/env python3
"""Transactional plan, subscription, and quota services for SaaS Phase 2."""
from __future__ import annotations

import json
import hashlib
import math
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from saas_auth import SaaSError, SaaSConfigurationError, SaaSService, new_id, utcnow


FEATURES = (
    "official_library_capacity",
    "official_unlocks",
    "video_library_capacity",
    "audio_library_capacity",
    "ai_context_generations",
    "ai_grammar_generations",
    "mp3_imports",
    "video_imports",
    "youtube_imports",
    "storage_bytes",
    "devices",
)

AI_FEATURES = {"ai_context_generations", "ai_grammar_generations"}
DAILY_AI_LIMITS = {"ai_context_generations": 50, "ai_grammar_generations": 20}
SHANGHAI = ZoneInfo("Asia/Shanghai")

FEATURE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "official_library_capacity": {"name": "官方书架容量", "unit": "本", "default": 0, "minimum": 0, "control": "已停止按官方书架总量限制", "sellable": False},
    "official_unlocks": {"name": "学习材料使用额度", "unit": "次/30天", "default": 0, "minimum": 0, "control": "公版及已授权材料不再按次数扣减", "sellable": False},
    "video_library_capacity": {"name": "视频收藏上限", "unit": "个（公版+私人）", "default": 2, "minimum": 0, "control": "加入公版书架或完成私人视频导入时合并校验", "capacity": "video"},
    "audio_library_capacity": {"name": "音频收藏上限", "unit": "个（公版+私人）", "default": 5, "minimum": 0, "control": "加入公版书架或完成私人音频导入时合并校验", "capacity": "audio"},
    "ai_context_generations": {"name": "词汇语境分析", "unit": "次/天（免费版）", "default": 50, "minimum": 0, "control": "免费版按 Asia/Shanghai 自然日限制；收费会员不限次数", "sellable": False},
    "ai_grammar_generations": {"name": "句法分析", "unit": "次/天（免费版）", "default": 20, "minimum": 0, "control": "免费版按 Asia/Shanghai 自然日限制；收费会员不限次数", "sellable": False},
    "mp3_imports": {"name": "MP3 学习导入", "unit": "次/30天", "default": 0, "minimum": 0, "control": "已改为按当前音频收藏容量校验", "sellable": False},
    "video_imports": {"name": "视频学习导入", "unit": "次/30天", "default": 0, "minimum": 0, "control": "已改为按当前视频收藏容量校验", "sellable": False},
    "youtube_imports": {"name": "在线视频学习导入", "unit": "次/30天", "default": 0, "minimum": 0, "control": "已改为按当前视频收藏容量校验", "sellable": False},
    "storage_bytes": {"name": "私人学习空间", "unit": "GB", "default": 20, "minimum": 0, "storage": True, "control": "上传原文件和生成媒体变体时按字节结算"},
    "devices": {"name": "登录设备", "unit": "台", "default": 2, "minimum": 1, "required": True, "control": "新设备登录时校验活跃设备数量", "sellable": False},
}


def as_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            result = json.loads(value)
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def timestamp(value: Any) -> str | None:
    return value.isoformat(timespec="seconds") if isinstance(value, datetime) else None


def parse_time(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except ValueError as exc:
            raise SaaSError("invalid_subscription", f"{field} 必须是带时区的 ISO-8601 时间。") from exc
    if result.tzinfo is None:
        raise SaaSError("invalid_subscription", f"{field} 必须包含时区。")
    return result.astimezone(timezone.utc)


class MembershipService:
    def __init__(self, accounts: SaaSService):
        self.accounts = accounts

    @staticmethod
    def _recommended_plan(plan_version: str) -> str | None:
        rank = {"free-v1": "advanced-v1", "free-v2": "advanced-v1", "advanced-v1": "pro-v1"}
        return rank.get(plan_version)

    def _plan(self, cursor: Any, plan_version_id: str) -> dict[str, Any]:
        cursor.execute(
            """SELECT pv.id,pv.display_name,pv.rank,pv.period_days,pv.quotas_json,pv.pricing_json,p.slug
            FROM plan_versions pv JOIN plans p ON p.id=pv.plan_id
            WHERE pv.id=%s AND pv.active=TRUE AND p.active=TRUE""",
            (plan_version_id,),
        )
        found = self.accounts._one(cursor)
        if not found:
            raise SaaSError("unknown_plan", "套餐版本不存在或已下架。", 400)
        found["quotas_json"] = as_json(found["quotas_json"])
        found["pricing_json"] = as_json(found["pricing_json"])
        return found

    def _expire_subscriptions(self, cursor: Any, user_id: str) -> None:
        cursor.execute(
            """UPDATE subscriptions SET status='expired',updated_at=NOW()
            WHERE user_id=%s AND status IN ('active','grace_period') AND ends_at<=NOW()""",
            (user_id,),
        )

    def _context(self, cursor: Any, user_id: str, lock_user: bool = True) -> dict[str, Any]:
        cursor.execute(
            f"SELECT id,created_at,plan_version,status FROM users WHERE id=%s {'FOR UPDATE' if lock_user else ''}",
            (user_id,),
        )
        user = self.accounts._one(cursor)
        if not user or user["status"] != "active":
            raise SaaSError("account_unavailable", "账号不可用。", 403)
        self._expire_subscriptions(cursor, user_id)
        cursor.execute(
            """SELECT s.*,pv.id AS version_id,pv.display_name,pv.rank,pv.period_days,pv.quotas_json,pv.pricing_json,p.slug
            FROM subscriptions s JOIN plan_versions pv ON pv.id=s.plan_version_id JOIN plans p ON p.id=pv.plan_id
            WHERE s.user_id=%s AND s.status IN ('active','grace_period') AND s.starts_at<=NOW() AND s.ends_at>NOW()
            ORDER BY pv.rank DESC,s.ends_at DESC,s.created_at DESC LIMIT 1""",
            (user_id,),
        )
        subscription = self.accounts._one(cursor)
        now = utcnow()
        if subscription:
            plan = dict(subscription)
            plan["id"] = plan.pop("version_id")
            plan["quotas_json"] = as_json(plan["quotas_json"])
            plan["pricing_json"] = as_json(plan["pricing_json"])
            anchor = subscription["starts_at"].astimezone(timezone.utc)
            span = timedelta(days=int(plan["period_days"]))
            cycle = max(0, math.floor((now - anchor).total_seconds() / span.total_seconds()))
            starts_at = anchor + span * cycle
            ends_at = min(subscription["ends_at"], starts_at + span)
            period_key = f"subscription:{subscription['id']}:{cycle}"
            subscription_id = subscription["id"]
        else:
            plan = self._plan(cursor, "free-v2")
            anchor = user["created_at"].astimezone(timezone.utc)
            span = timedelta(days=int(plan["period_days"]))
            cycle = max(0, math.floor((now - anchor).total_seconds() / span.total_seconds()))
            starts_at, ends_at = anchor + span * cycle, anchor + span * (cycle + 1)
            period_key = f"free:{cycle}"
            subscription_id = None
        cursor.execute(
            """INSERT INTO usage_periods(id,user_id,subscription_id,plan_version_id,period_key,starts_at,ends_at,limits_json)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (user_id,period_key) DO NOTHING""",
            (new_id(), user_id, subscription_id, plan["id"], period_key, starts_at, ends_at, json.dumps(plan["quotas_json"])),
        )
        cursor.execute("SELECT * FROM usage_periods WHERE user_id=%s AND period_key=%s FOR UPDATE", (user_id, period_key))
        period = self.accounts._one(cursor)
        if not period:
            raise RuntimeError("usage period creation failed")
        if user["plan_version"] != plan["id"]:
            cursor.execute("UPDATE users SET plan_version=%s,updated_at=NOW() WHERE id=%s", (plan["id"], user_id))
        return {"user": user, "plan": plan, "subscription": subscription, "period": period}

    def _feature(self, feature: str) -> str:
        value = str(feature or "").strip()
        if value not in FEATURES:
            raise SaaSError("invalid_feature", "未知权益项目。", 400)
        return value

    def _usage_numbers(self, cursor: Any, period_id: str, feature: str) -> tuple[int, int]:
        cursor.execute(
            "SELECT COALESCE(SUM(quantity),0) AS total FROM usage_ledger WHERE usage_period_id=%s AND feature=%s",
            (period_id, feature),
        )
        consumed = int((self.accounts._one(cursor) or {"total": 0})["total"])
        cursor.execute(
            """SELECT COALESCE(SUM(quantity),0) AS total FROM quota_reservations
            WHERE usage_period_id=%s AND feature=%s AND state='reserved'""",
            (period_id, feature),
        )
        reserved = int((self.accounts._one(cursor) or {"total": 0})["total"])
        return consumed, max(0, reserved)

    def _feature_summary(self, cursor: Any, context: dict[str, Any], feature: str) -> dict[str, Any]:
        if feature in AI_FEATURES and context["plan"]["slug"] != "free":
            return {"feature": feature, "limit": None, "used": 0, "credits": 0, "reserved": 0, "available": None, "unlimited": True, "resetAt": None}
        context = self._quota_context(cursor, context, feature)
        limits = as_json(context["period"]["limits_json"])
        limit = int(limits.get(feature, 0))
        if feature in {"video_library_capacity", "audio_library_capacity"}:
            media_type = FEATURE_DEFINITIONS[feature]["capacity"]
            used = self._media_library_count(cursor, str(context["user"]["id"]), media_type)
            return {"feature": feature, "limit": limit, "used": used, "credits": 0, "reserved": 0, "available": max(0, limit - used)}
        net_used, reserved = self._usage_numbers(cursor, context["period"]["id"], feature)
        used, credits = max(0, net_used), max(0, -net_used)
        return {
            "feature": feature,
            "limit": limit,
            "used": used,
            "credits": credits,
            "reserved": reserved,
            "available": max(0, limit - net_used - reserved),
            "unlimited": False,
            "resetAt": timestamp(context["period"]["ends_at"]) if feature in AI_FEATURES else None,
        }

    def _quota_context(self, cursor: Any, context: dict[str, Any], feature: str) -> dict[str, Any]:
        if feature not in AI_FEATURES or context["plan"]["slug"] != "free":
            return context
        local_now = utcnow().astimezone(SHANGHAI)
        start_local = datetime.combine(local_now.date(), datetime.min.time(), tzinfo=SHANGHAI)
        end_local = start_local + timedelta(days=1)
        period_key = f"ai-day:{local_now.date().isoformat()}"
        limits = as_json(context["plan"]["quotas_json"])
        limits.update(DAILY_AI_LIMITS)
        cursor.execute(
            """INSERT INTO usage_periods(id,user_id,subscription_id,plan_version_id,period_key,starts_at,ends_at,limits_json)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (user_id,period_key) DO NOTHING""",
            (new_id(), context["user"]["id"], context["subscription"]["id"] if context["subscription"] else None,
             context["plan"]["id"], period_key, start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc), json.dumps(limits)),
        )
        cursor.execute("SELECT * FROM usage_periods WHERE user_id=%s AND period_key=%s FOR UPDATE", (context["user"]["id"], period_key))
        daily_period = self.accounts._one(cursor)
        if not daily_period:
            raise RuntimeError("daily AI usage period creation failed")
        return {**context, "period": daily_period}

    def _public_context(self, cursor: Any, context: dict[str, Any], include_usage: bool = False) -> dict[str, Any]:
        plan, period, subscription = context["plan"], context["period"], context["subscription"]
        cursor.execute(
            """SELECT m.*,from_plan.display_name AS from_name,to_plan.display_name AS to_name
            FROM membership_change_orders m
            LEFT JOIN plan_versions from_plan ON from_plan.id=m.from_plan_version_id
            JOIN plan_versions to_plan ON to_plan.id=m.to_plan_version_id
            WHERE m.user_id=%s ORDER BY m.created_at DESC LIMIT 20""",
            (context["user"]["id"],),
        )
        change_orders = [self._change_order(row) for row in self.accounts._many(cursor)]
        result: dict[str, Any] = {
            "plan": {
                "id": plan["id"], "slug": plan["slug"], "name": plan["display_name"], "rank": int(plan["rank"]),
                "periodDays": int(plan["period_days"]), "quotas": as_json(plan["quotas_json"]), "pricing": as_json(plan["pricing_json"]),
            },
            "period": {"id": period["id"], "startsAt": timestamp(period["starts_at"]), "endsAt": timestamp(period["ends_at"])},
            "subscription": None if not subscription else {
                "id": subscription["id"], "status": subscription["status"], "startsAt": timestamp(subscription["starts_at"]),
                "endsAt": timestamp(subscription["ends_at"]),
            },
            "changeOrders": change_orders,
            "mediaCapacity": self._media_capacity(cursor, str(context["user"]["id"]), as_json(period["limits_json"])),
        }
        if include_usage:
            result["usage"] = [self._feature_summary(cursor, context, feature) for feature in FEATURES]
        return result

    def _change_details(self, cursor: Any, user_id: str, target_plan_id: str, now: datetime | None = None) -> dict[str, Any]:
        """Calculate a membership change without mutating subscriptions."""
        now = now or utcnow()
        context = self._context(cursor, user_id)
        target = self._plan(cursor, target_plan_id)
        current = context["subscription"]
        cursor.execute(
            """SELECT s.id,s.starts_at,s.ends_at,pv.id AS plan_id,pv.display_name,pv.rank
            FROM subscriptions s JOIN plan_versions pv ON pv.id=s.plan_version_id
            WHERE s.user_id=%s AND s.status IN ('active','grace_period') AND s.ends_at>NOW()
            ORDER BY s.ends_at DESC FOR UPDATE OF s""",
            (user_id,),
        )
        existing = self.accounts._many(cursor)
        highest_rank = max((int(row["rank"]) for row in existing), default=int(context["plan"]["rank"]))
        latest_end = max((row["ends_at"] for row in existing), default=now)
        target_rank = int(target["rank"])
        carry_seconds = 0
        if not existing:
            change_type = "first_purchase"
            starts_at = now
            carry_days = 0
        elif target_rank > highest_rank:
            change_type = "upgrade"
            starts_at = now
            remaining_seconds = max(0, int((latest_end - now).total_seconds()))
            source_pricing = as_json(context["plan"]["pricing_json"])
            target_pricing = as_json(target["pricing_json"])
            source_price = int(source_pricing.get("amount_cents") or source_pricing.get("monthly_cents") or 0)
            target_price = int(target_pricing.get("amount_cents") or target_pricing.get("monthly_cents") or 0)
            if source_price <= 0 or target_price <= 0:
                raise SaaSError("upgrade_conversion_unavailable", "当前套餐无法计算升级折算，请联系客服处理。", 409)
            carry_seconds = math.ceil(remaining_seconds * source_price / target_price / 3600) * 3600
            carry_days = carry_seconds / 86400
        elif target_rank < highest_rank:
            raise SaaSError("membership_downgrade_not_allowed", "当前会员不允许使用低等级卡密，兑换失败且卡密未核销。", 409)
        else:
            change_type = "renewal"
            starts_at = now
            carry_days = 0
        ends_at = (latest_end if change_type == "renewal" else starts_at) + timedelta(days=int(target["period_days"]), seconds=carry_seconds)
        return {
            "context": context,
            "target": target,
            "currentSubscriptionId": current["id"] if current else (existing[0]["id"] if existing else None),
            "currentPlanId": context["plan"]["id"],
            "changeType": change_type,
            "startsAt": starts_at,
            "endsAt": ends_at,
            "effectiveAt": starts_at,
            "carryDays": carry_days,
            "carrySeconds": carry_seconds,
        }

    def change_preview(self, user_id: str, target_plan_id: str) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                details = self._change_details(cursor, user_id, str(target_plan_id or "").strip())
                target = details["target"]
                current = details["context"]["plan"]
                return {
                    "currentPlan": {"id": current["id"], "name": current["display_name"], "rank": int(current["rank"])},
                    "targetPlan": {"id": target["id"], "name": target["display_name"], "rank": int(target["rank"])},
                    "changeType": details["changeType"],
                    "effectiveAt": timestamp(details["effectiveAt"]),
                    "renewalMode": "extend_current_expiry" if details["changeType"] == "renewal" else None,
                    "startsAt": timestamp(details["startsAt"]),
                    "endsAt": timestamp(details["endsAt"]),
                    "currentEndsAt": timestamp(details["context"]["subscription"]["ends_at"]) if details["context"]["subscription"] else None,
                    "carryDays": details["carryDays"],
                    "carrySeconds": details["carrySeconds"],
                    "durationDays": int(target["period_days"]),
                }

    def change_orders(self, user_id: str) -> list[dict[str, Any]]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT m.*,from_plan.display_name AS from_name,to_plan.display_name AS to_name
                    FROM membership_change_orders m
                    LEFT JOIN plan_versions from_plan ON from_plan.id=m.from_plan_version_id
                    JOIN plan_versions to_plan ON to_plan.id=m.to_plan_version_id
                    WHERE m.user_id=%s ORDER BY m.created_at DESC LIMIT 50""",
                    (user_id,),
                )
                return [self._change_order(row) for row in self.accounts._many(cursor)]

    def cancel_change_order(self, user_id: str, change_order_id: str) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM membership_change_orders WHERE id=%s AND user_id=%s FOR UPDATE", (change_order_id, user_id))
                order = self.accounts._one(cursor)
                if not order:
                    raise SaaSError("change_order_not_found", "会员变更记录不存在。", 404)
                if order["status"] != "scheduled":
                    raise SaaSError("change_order_not_cancellable", "只有尚未生效的排期变更可以取消。", 409)
                if order["effective_at"] <= utcnow():
                    raise SaaSError("change_order_already_effective", "该变更已经生效，不能取消。", 409)
                if order["created_subscription_id"]:
                    cursor.execute("UPDATE subscriptions SET status='suspended',note='用户取消未来会员排期',updated_at=NOW() WHERE id=%s AND starts_at>NOW()", (order["created_subscription_id"],))
                cursor.execute("UPDATE membership_change_orders SET status='cancelled',updated_at=NOW() WHERE id=%s", (change_order_id,))
                self._membership_event(cursor, user_id, change_order_id, "scheduled_change_cancelled", {"subscriptionId": order["created_subscription_id"]}, user_id)
                return {"changeOrder": self._change_order({**order, "status": "cancelled"})}

    def _media_library_count(self, cursor: Any, user_id: str, media_type: str) -> int:
        resource_types = ["video", "youtube"] if media_type == "video" else ["audio"]
        cursor.execute(
            """SELECT
              (SELECT COUNT(*) FROM user_library ul JOIN catalog_books cb ON cb.id=ul.catalog_book_id
               WHERE ul.user_id=%s AND cb.resource_type=ANY(%s)) +
              (SELECT COUNT(*) FROM content_books WHERE owner_id=%s AND visibility IN ('private','draft')
               AND status='ready' AND source_type=ANY(%s)) AS total""",
            (user_id, resource_types, user_id, resource_types),
        )
        return int((self.accounts._one(cursor) or {"total": 0})["total"])

    def _media_capacity(self, cursor: Any, user_id: str, limits: dict[str, Any]) -> dict[str, dict[str, int]]:
        result = {}
        for kind, feature in (("video", "video_library_capacity"), ("audio", "audio_library_capacity")):
            limit = int(limits.get(feature, 0) or 0)
            used = self._media_library_count(cursor, user_id, kind)
            result[kind] = {"used": used, "limit": limit, "available": max(0, limit - used)}
        return result

    def assert_media_capacity(self, cursor: Any, user_id: str, context: dict[str, Any], kind: str) -> dict[str, int]:
        if kind not in {"video", "audio"}:
            return {"used": 0, "limit": 0, "available": 0}
        feature = f"{kind}_library_capacity"
        limits = as_json(context["period"]["limits_json"])
        limit = int(limits.get(feature, 0) or 0)
        used = self._media_library_count(cursor, user_id, kind)
        if used >= limit:
            raise SaaSError("media_capacity_exceeded", f"当前套餐最多收藏 {limit} 个{ '视频' if kind == 'video' else '音频'}（公版与私人内容合计）。", 409, {"feature": feature, "plan": context["plan"]["id"], "used": used, "limit": limit, "recommendedPlan": self._recommended_plan(context["plan"]["id"])})
        return {"used": used, "limit": limit, "available": max(0, limit - used)}

    def membership(self, user_id: str, include_usage: bool = False) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                return self._public_context(cursor, self._context(cursor, user_id), include_usage)

    def usage(self, user_id: str) -> dict[str, Any]:
        return self.membership(user_id, include_usage=True)

    def plans(self) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT pv.id,pv.display_name,pv.rank,pv.period_days,pv.quotas_json,pv.pricing_json,p.slug
                FROM plan_versions pv JOIN plans p ON p.id=pv.plan_id
                WHERE pv.active=TRUE AND p.active=TRUE ORDER BY pv.rank,pv.created_at DESC""")
                return {"plans":[{"id":row["id"],"slug":row["slug"],"name":row["display_name"],"rank":int(row["rank"]),"periodDays":int(row["period_days"]),"quotas":as_json(row["quotas_json"]),"pricing":as_json(row["pricing_json"])} for row in self.accounts._many(cursor)]}

    def change_requests(self,user_id:str)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT mcr.*,current_plan.display_name AS current_name,requested_plan.display_name AS requested_name
                FROM membership_change_requests mcr JOIN plan_versions current_plan ON current_plan.id=mcr.current_plan_version_id
                JOIN plan_versions requested_plan ON requested_plan.id=mcr.requested_plan_version_id
                WHERE mcr.user_id=%s ORDER BY mcr.created_at DESC LIMIT 20""",(user_id,))
                return {"requests":[{"id":row["id"],"currentPlan":row["current_plan_version_id"],"currentName":row["current_name"],"requestedPlan":row["requested_plan_version_id"],"requestedName":row["requested_name"],"status":row["status"],"note":row["note"],"createdAt":timestamp(row["created_at"]),"updatedAt":timestamp(row["updated_at"])} for row in self.accounts._many(cursor)]}

    def request_change(self,user_id:str,plan_version:str,note:str="")->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                context=self._context(cursor,user_id);requested=self._plan(cursor,str(plan_version or "").strip())
                if requested["id"]==context["plan"]["id"]:raise SaaSError("plan_unchanged","你当前已经在使用该套餐。",409)
                cursor.execute("SELECT id FROM membership_change_requests WHERE user_id=%s AND status='pending' FOR UPDATE",(user_id,));existing=self.accounts._one(cursor)
                if existing:raise SaaSError("membership_change_pending","已有待处理的套餐变更申请。",409)
                request_id=new_id();cursor.execute("""INSERT INTO membership_change_requests(id,user_id,current_plan_version_id,requested_plan_version_id,note)
                VALUES(%s,%s,%s,%s,%s)""",(request_id,user_id,context["plan"]["id"],requested["id"],str(note or "")[:1000]))
                self._audit(cursor,user_id,user_id,"membership_change_requested",{"requestId":request_id,"from":context["plan"]["id"],"to":requested["id"]})
                return {"request":{"id":request_id,"currentPlan":context["plan"]["id"],"requestedPlan":requested["id"],"requestedName":requested["display_name"],"status":"pending","note":str(note or "")[:1000],"createdAt":timestamp(utcnow())}}

    def reserve(self, user_id: str, feature: str, idempotency_key: str, quantity: int = 1, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        feature = self._feature(feature)
        key = str(idempotency_key or "").strip()
        if not key or len(key) > 255:
            raise SaaSError("invalid_idempotency_key", "操作标识无效。", 400)
        try:
            quantity = int(quantity)
        except (TypeError, ValueError) as exc:
            raise SaaSError("invalid_quantity", "额度数量无效。", 400) from exc
        if quantity < 1:
            raise SaaSError("invalid_quantity", "额度数量必须大于零。", 400)
        payload = metadata or {}
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                context = self._context(cursor, user_id)
                quota_context = self._quota_context(cursor, context, feature)
                cursor.execute(
                    "SELECT * FROM quota_reservations WHERE user_id=%s AND feature=%s AND idempotency_key=%s FOR UPDATE",
                    (user_id, feature, key),
                )
                existing = self.accounts._one(cursor)
                if existing:
                    if int(existing["quantity"]) != quantity:
                        raise SaaSError("idempotency_conflict", "同一操作标识不能用于不同的额度数量。", 409)
                    return {"reservation": self._reservation(existing), "membership": self._public_context(cursor, context, True), "idempotent": True}
                if feature in AI_FEATURES and context["plan"]["slug"] != "free":
                    reservation = {
                        "id": new_id(), "user_id": user_id, "usage_period_id": context["period"]["id"], "feature": feature,
                        "idempotency_key": key, "quantity": quantity, "state": "settled", "metadata_json": payload,
                    }
                    cursor.execute(
                        """INSERT INTO quota_reservations(id,user_id,usage_period_id,feature,idempotency_key,quantity,state,metadata_json,settled_at)
                        VALUES(%s,%s,%s,%s,%s,%s,'settled',%s::jsonb,NOW())""",
                        (reservation["id"], user_id, reservation["usage_period_id"], feature, key, quantity, json.dumps(payload)),
                    )
                    return {"reservation": self._reservation(reservation), "membership": self._public_context(cursor, context, True), "idempotent": False}
                quota_context = self._quota_context(cursor, context, feature)
                summary = self._feature_summary(cursor, quota_context, feature)
                if quantity > summary["available"]:
                    plan_id = context["plan"]["id"]
                    raise SaaSError(
                        "quota_exceeded", "当前套餐的该项额度已用完。", 409,
                        {"feature": feature, "plan": plan_id, "used": summary["used"], "limit": summary["limit"],
                         "resetAt": timestamp(context["period"]["ends_at"]), "recommendedPlan": self._recommended_plan(plan_id)},
                    )
                reservation = {
                    "id": new_id(), "user_id": user_id, "usage_period_id": quota_context["period"]["id"], "feature": feature,
                    "idempotency_key": key, "quantity": quantity, "state": "reserved", "metadata_json": payload,
                }
                cursor.execute(
                    """INSERT INTO quota_reservations(id,user_id,usage_period_id,feature,idempotency_key,quantity,state,metadata_json)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                    (reservation["id"], user_id, reservation["usage_period_id"], feature, key, quantity, "reserved", json.dumps(payload)),
                )
                return {"reservation": self._reservation(reservation), "membership": self._public_context(cursor, context, True), "idempotent": False}

    def settle(self, user_id: str, reservation_id: str, reason: str = "consumption") -> dict[str, Any]:
        if reason not in {"consumption", "storage_settlement"}:
            raise SaaSError("invalid_settlement", "额度结算类型无效。", 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM quota_reservations WHERE id=%s AND user_id=%s FOR UPDATE", (reservation_id, user_id))
                reservation = self.accounts._one(cursor)
                if not reservation:
                    raise SaaSError("reservation_not_found", "额度预占不存在。", 404)
                if reservation["state"] == "released":
                    raise SaaSError("reservation_released", "该额度预占已释放。", 409)
                if reservation["state"] == "reserved":
                    cursor.execute("UPDATE quota_reservations SET state='settled',settled_at=NOW() WHERE id=%s", (reservation_id,))
                    cursor.execute(
                        """INSERT INTO usage_ledger(id,user_id,usage_period_id,feature,quantity,reason,reservation_id,idempotency_key,metadata_json)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT (reservation_id) DO NOTHING""",
                        (new_id(), user_id, reservation["usage_period_id"], reservation["feature"], reservation["quantity"], reason,
                         reservation_id, reservation["idempotency_key"], json.dumps(as_json(reservation["metadata_json"]))),
                    )
                cursor.execute("SELECT * FROM quota_reservations WHERE id=%s", (reservation_id,))
                return self._reservation(self.accounts._one(cursor) or reservation)

    def release(self, user_id: str, reservation_id: str) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM quota_reservations WHERE id=%s AND user_id=%s FOR UPDATE", (reservation_id, user_id))
                reservation = self.accounts._one(cursor)
                if not reservation:
                    raise SaaSError("reservation_not_found", "额度预占不存在。", 404)
                if reservation["state"] == "settled":
                    raise SaaSError("reservation_settled", "已结算额度不能释放。", 409)
                if reservation["state"] == "reserved":
                    cursor.execute("UPDATE quota_reservations SET state='released',released_at=NOW() WHERE id=%s", (reservation_id,))
                cursor.execute("SELECT * FROM quota_reservations WHERE id=%s", (reservation_id,))
                return self._reservation(self.accounts._one(cursor) or reservation)

    def consume(self, user_id: str, feature: str, idempotency_key: str, quantity: int = 1, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        reservation = self.reserve(user_id, feature, idempotency_key, quantity, metadata)["reservation"]
        if reservation["state"] == "reserved":
            reservation = self.settle(user_id, reservation["id"])
        return reservation

    def credit(self, user_id: str, feature: str, quantity: int, idempotency_key: str, actor_id: str | None = None, note: str = "") -> dict[str, Any]:
        feature = self._feature(feature)
        if not isinstance(quantity, int) or quantity < 1:
            raise SaaSError("invalid_quantity", "补发额度数量必须大于零。", 400)
        key = str(idempotency_key or "").strip()
        if not key:
            raise SaaSError("invalid_idempotency_key", "操作标识无效。", 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                context = self._context(cursor, user_id)
                quota_context = self._quota_context(cursor, context, feature)
                self._check_ledger_replay(cursor, user_id, feature, key, -quantity, "credit")
                cursor.execute(
                    """INSERT INTO usage_ledger(id,user_id,usage_period_id,feature,quantity,reason,idempotency_key,metadata_json)
                    VALUES(%s,%s,%s,%s,%s,'credit',%s,%s::jsonb) ON CONFLICT DO NOTHING""",
                    (new_id(), user_id, quota_context["period"]["id"], feature, -quantity, key, json.dumps({"note": note[:1000], "actorId": actor_id})),
                )
                self._audit(cursor, user_id, actor_id, "quota_credit", {"feature": feature, "quantity": quantity, "key": key})
                return self._feature_summary(cursor, quota_context, feature)

    def adjust(self, user_id: str, feature: str, quantity: int, idempotency_key: str, actor_id: str | None = None, note: str = "") -> dict[str, Any]:
        """Apply a signed admin adjustment; positive means grant, negative deduct."""
        feature = self._feature(feature)
        if not isinstance(quantity, int) or quantity == 0:
            raise SaaSError("invalid_quantity", "额度调整数量不能为零。", 400)
        key = str(idempotency_key or "").strip()
        if not key: raise SaaSError("invalid_idempotency_key", "操作标识无效。", 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                context = self._context(cursor, user_id)
                quota_context = self._quota_context(cursor, context, feature)
                # Usage ledger stores consumption as positive and credits as
                # negative, so a positive user-facing grant maps to -quantity.
                ledger_quantity = -quantity
                self._check_ledger_replay(cursor, user_id, feature, key, ledger_quantity, "adjustment")
                cursor.execute(
                    """INSERT INTO usage_ledger(id,user_id,usage_period_id,feature,quantity,reason,idempotency_key,metadata_json)
                    VALUES(%s,%s,%s,%s,%s,'adjustment',%s,%s::jsonb) ON CONFLICT DO NOTHING""",
                    (new_id(), user_id, quota_context["period"]["id"], feature, ledger_quantity, key, json.dumps({"note": note[:1000], "actorId": actor_id, "adjustment": quantity})),
                )
                self._audit(cursor, user_id, actor_id, "quota_adjustment", {"feature": feature, "quantity": quantity, "key": key, "note": note[:1000]})
                return self._feature_summary(cursor, quota_context, feature)

    def _check_ledger_replay(self, cursor: Any, user_id: str, feature: str, key: str, quantity: int, reason: str) -> None:
        cursor.execute("SELECT quantity,reason FROM usage_ledger WHERE user_id=%s AND feature=%s AND idempotency_key=%s", (user_id, feature, key))
        prior = self.accounts._one(cursor)
        if prior and (int(prior["quantity"]) != quantity or prior["reason"] != reason):
            raise SaaSError("idempotency_conflict", "同一操作标识不能用于不同的额度请求。", 409)

    def _operation(self, cursor: Any, actor_id: str, user_id: str, operation: str, payload: dict[str, Any], key: Any = None) -> tuple[str, dict[str, Any] | None]:
        """Caller holds the target user lock until the business write and receipt commit."""
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        key = str(key or "").strip() or hashlib.sha256(encoded.encode()).hexdigest()
        if len(key) > 255:
            raise SaaSError("invalid_idempotency_key", "操作标识无效。", 400)
        cursor.execute("SELECT request_json,response_json FROM entitlement_operations WHERE actor_id=%s AND user_id=%s AND operation=%s AND idempotency_key=%s", (actor_id, user_id, operation, key))
        prior = self.accounts._one(cursor)
        if prior and as_json(prior["request_json"]) != payload:
            raise SaaSError("idempotency_conflict", "同一操作标识不能用于不同的请求。", 409)
        return key, as_json(prior["response_json"]) if prior else None

    def _save_operation(self, cursor: Any, actor_id: str, user_id: str, operation: str, key: str, payload: dict[str, Any], result: dict[str, Any]) -> None:
        cursor.execute("INSERT INTO entitlement_operations(actor_id,user_id,operation,idempotency_key,request_json,response_json) VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb)", (actor_id, user_id, operation, key, json.dumps(payload), json.dumps(result)))

    def create_manual_order(self, actor_id: str, user_id: str, plan_version: str, starts_at: Any, ends_at: Any, note: str = "", amount_cents: int = 0, idempotency_key: str | None = None) -> dict[str, Any]:
        start, end = parse_time(starts_at, "startsAt"), parse_time(ends_at, "endsAt")
        if end <= start:
            raise SaaSError("invalid_subscription", "结束时间必须晚于开始时间。", 400)
        try:
            amount_cents = int(amount_cents)
        except (TypeError, ValueError) as exc:
            raise SaaSError("invalid_order", "订单金额无效。", 400) from exc
        if amount_cents < 0:
            raise SaaSError("invalid_order", "订单金额不能为负数。", 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (user_id,))
                if not cursor.fetchone():
                    raise SaaSError("user_not_found", "用户不存在。", 404)
                payload = {"planVersion": plan_version, "startsAt": timestamp(start), "endsAt": timestamp(end), "note": str(note or "")[:1000], "amountCents": amount_cents}
                key, prior = self._operation(cursor, actor_id, user_id, "manual_order", payload, idempotency_key)
                if prior:
                    return {**prior, "idempotent": True}
                self._plan(cursor, plan_version)
                order_id, subscription_id = new_id(), new_id()
                cursor.execute(
                    """INSERT INTO manual_orders(id,user_id,plan_version_id,status,starts_at,ends_at,amount_cents,note,created_by)
                    VALUES(%s,%s,%s,'completed',%s,%s,%s,%s,%s)""",
                    (order_id, user_id, plan_version, start, end, amount_cents, str(note or "")[:1000], actor_id),
                )
                cursor.execute(
                    """INSERT INTO subscriptions(id,user_id,plan_version_id,status,starts_at,ends_at,manual_order_id,note,created_by)
                    VALUES(%s,%s,%s,'active',%s,%s,%s,%s,%s)""",
                    (subscription_id, user_id, plan_version, start, end, order_id, str(note or "")[:1000], actor_id),
                )
                context = self._context(cursor, user_id)
                self._audit(cursor, user_id, actor_id, "manual_subscription_created", {"orderId": order_id, "subscriptionId": subscription_id, "plan": plan_version})
                result = {"order": self._order({"id": order_id, "user_id": user_id, "plan_version_id": plan_version, "status": "completed", "starts_at": start, "ends_at": end, "amount_cents": amount_cents, "currency": "CNY", "note": note, "created_at": utcnow()}),
                        "subscription": {"id": subscription_id, "status": "active", "startsAt": timestamp(start), "endsAt": timestamp(end)},
                        "membership": self._public_context(cursor, context, True), "idempotent": False}
                self._save_operation(cursor, actor_id, user_id, "manual_order", key, payload, result)
                return result

    def update_subscription(self, actor_id: str, subscription_id: str, action: str, ends_at: Any | None = None, note: str = "", idempotency_key: str | None = None) -> dict[str, Any]:
        if action not in {"suspend", "activate", "extend"}:
            raise SaaSError("invalid_subscription_action", "不支持的订阅操作。", 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT user_id FROM subscriptions WHERE id=%s", (subscription_id,))
                owner = self.accounts._one(cursor)
                if not owner:
                    raise SaaSError("subscription_not_found", "订阅不存在。", 404)
                cursor.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (owner["user_id"],))
                cursor.execute("SELECT * FROM subscriptions WHERE id=%s FOR UPDATE", (subscription_id,))
                subscription = self.accounts._one(cursor)
                if not subscription:
                    raise SaaSError("subscription_not_found", "订阅不存在。", 404)
                payload = {"subscriptionId": subscription_id, "action": action, "endsAt": timestamp(parse_time(ends_at, "endsAt")) if ends_at is not None else None, "note": str(note or "")[:1000]}
                if idempotency_key:
                    key, prior = self._operation(cursor, actor_id, subscription["user_id"], "subscription_update", payload, idempotency_key)
                    if prior:return {**prior, "idempotent": True}
                if action == "extend":
                    if ends_at is None:
                        raise SaaSError("invalid_subscription", "延期需要新的结束时间。", 400)
                    new_end = parse_time(ends_at, "endsAt")
                    if new_end < subscription["ends_at"]:
                        raise SaaSError("invalid_subscription", "新的结束时间必须晚于原结束时间。", 400)
                    cursor.execute("UPDATE subscriptions SET ends_at=%s,note=%s,updated_at=NOW() WHERE id=%s", (new_end, str(note or "")[:1000], subscription_id))
                else:
                    state = "suspended" if action == "suspend" else "active"
                    cursor.execute("UPDATE subscriptions SET status=%s,note=%s,updated_at=NOW() WHERE id=%s", (state, str(note or "")[:1000], subscription_id))
                context = self._context(cursor, subscription["user_id"])
                self._audit(cursor, subscription["user_id"], actor_id, f"subscription_{action}", {"subscriptionId": subscription_id, "note": note[:1000]})
                cursor.execute("SELECT * FROM subscriptions WHERE id=%s", (subscription_id,))
                updated = self.accounts._one(cursor) or subscription
                result = {"subscription": {"id": updated["id"], "status": updated["status"], "startsAt": timestamp(updated["starts_at"]), "endsAt": timestamp(updated["ends_at"])}, "membership": self._public_context(cursor, context, True), "idempotent": False}
                if idempotency_key:self._save_operation(cursor, actor_id, subscription["user_id"], "subscription_update", key, payload, result)
                return result

    def orders(self, user_id: str) -> list[dict[str, Any]]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT id,user_id,plan_version_id,status,starts_at,ends_at,amount_cents,currency,note,created_at,'manual' AS provider
                    FROM manual_orders WHERE user_id=%s
                    UNION ALL
                    SELECT id,user_id,plan_version_id,status,starts_at,ends_at,amount_cents,currency,
                    CASE WHEN error_message<>'' THEN error_message ELSE billing_interval END AS note,created_at,provider
                    FROM payment_orders WHERE user_id=%s
                    UNION ALL
                    SELECT rc.id,rc.redeemed_by AS user_id,cpv.plan_version_id,'completed' AS status,
                    s.starts_at,s.ends_at,cpv.amount_cents,'CNY' AS currency,'云猫寄售兑换' AS note,
                    rc.redeemed_at AS created_at,'cloudcat' AS provider
                    FROM commerce_redemption_codes rc
                    JOIN commerce_product_versions cpv ON cpv.id=rc.product_version_id
                    JOIN subscriptions s ON s.id=rc.subscription_id
                    WHERE rc.redeemed_by=%s AND rc.status='redeemed'
                    ORDER BY created_at DESC""",
                    (user_id, user_id, user_id),
                )
                return [self._order(row) for row in self.accounts._many(cursor)]

    def _audit(self, cursor: Any, user_id: str, actor_id: str | None, action: str, payload: dict[str, Any]) -> None:
        cursor.execute(
            "INSERT INTO membership_audit(id,user_id,actor_id,action,payload_json) VALUES(%s,%s,%s,%s,%s::jsonb)",
            (new_id(), user_id, actor_id, action, json.dumps(payload)),
        )

    def _membership_event(self, cursor: Any, user_id: str, change_order_id: str | None, event_type: str, payload: dict[str, Any], actor_id: str | None) -> None:
        cursor.execute(
            """INSERT INTO membership_events(id,user_id,change_order_id,event_type,payload_json,created_by)
            VALUES(%s,%s,%s,%s,%s::jsonb,%s)""",
            (new_id(), user_id, change_order_id, event_type, json.dumps(payload), actor_id),
        )

    @staticmethod
    def _change_order(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"], "source": row["source"], "fromPlanVersion": row["from_plan_version_id"],
            "fromPlanName": row.get("from_name"), "toPlanVersion": row["to_plan_version_id"],
            "toPlanName": row.get("to_name"), "changeType": row["change_type"], "status": row["status"],
            "effectiveAt": timestamp(row["effective_at"]), "carryDays": round(int(row.get("carry_seconds", 0) or 0) / 86400, 2),
            "carrySeconds": int(row.get("carry_seconds", 0) or 0),
            "amountCents": int(row["amount_cents"]), "createdAt": timestamp(row["created_at"]),
            "createdSubscriptionId": row.get("created_subscription_id"),
        }

    @staticmethod
    def _reservation(row: dict[str, Any]) -> dict[str, Any]:
        return {"id": row["id"], "feature": row["feature"], "quantity": int(row["quantity"]), "state": row["state"], "idempotencyKey": row["idempotency_key"]}

    @staticmethod
    def _order(row: dict[str, Any]) -> dict[str, Any]:
        return {"id": row["id"], "planVersion": row["plan_version_id"], "status": row["status"], "startsAt": timestamp(row["starts_at"]), "endsAt": timestamp(row["ends_at"]), "amountCents": int(row["amount_cents"]), "currency": row["currency"], "note": row["note"], "provider": row.get("provider", "manual"), "createdAt": timestamp(row.get("created_at"))}
