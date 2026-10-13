#!/usr/bin/env python3
"""Transactional plan, subscription, and quota services for SaaS Phase 2."""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from saas_auth import SaaSError, SaaSConfigurationError, SaaSService, new_id, utcnow


FEATURES = (
    "official_library_capacity",
    "official_unlocks",
    "ai_context_generations",
    "ai_grammar_generations",
    "mp3_imports",
    "video_imports",
    "youtube_imports",
    "storage_bytes",
    "devices",
)

FEATURE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "official_library_capacity": {"name": "官方书架容量", "unit": "本", "default": 30, "minimum": 0, "control": "加入官方书架时校验当前容量"},
    "official_unlocks": {"name": "学习材料使用额度", "unit": "次/30天", "default": 12, "minimum": 0, "control": "解锁公版及授权学习材料时预占并结算"},
    "ai_context_generations": {"name": "词汇语境分析", "unit": "次/30天", "default": 300, "minimum": 0, "control": "生成词汇语境前预占额度，失败自动释放"},
    "ai_grammar_generations": {"name": "句法分析", "unit": "次/30天", "default": 100, "minimum": 0, "control": "生成句法分析前预占额度，失败自动释放"},
    "mp3_imports": {"name": "MP3 学习导入", "unit": "次/30天", "default": 5, "minimum": 0, "control": "创建 MP3 导入任务时预占额度"},
    "video_imports": {"name": "视频学习导入", "unit": "次/30天", "default": 3, "minimum": 0, "control": "创建视频导入任务时预占额度"},
    "youtube_imports": {"name": "在线视频学习导入", "unit": "次/30天", "default": 5, "minimum": 0, "control": "创建在线视频导入任务时预占额度"},
    "storage_bytes": {"name": "私人学习空间", "unit": "GB", "default": 20, "minimum": 0, "storage": True, "control": "上传原文件和生成媒体变体时按字节结算"},
    "devices": {"name": "登录设备", "unit": "台", "default": 2, "minimum": 1, "required": True, "control": "新设备登录时校验活跃设备数量"},
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
        rank = {"free-v1": "advanced-v1", "advanced-v1": "pro-v1"}
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
            plan = self._plan(cursor, "free-v1")
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
        limits = as_json(context["period"]["limits_json"])
        limit = int(limits.get(feature, 0))
        net_used, reserved = self._usage_numbers(cursor, context["period"]["id"], feature)
        used, credits = max(0, net_used), max(0, -net_used)
        return {
            "feature": feature,
            "limit": limit,
            "used": used,
            "credits": credits,
            "reserved": reserved,
            "available": max(0, limit - net_used - reserved),
        }

    def _public_context(self, cursor: Any, context: dict[str, Any], include_usage: bool = False) -> dict[str, Any]:
        plan, period, subscription = context["plan"], context["period"], context["subscription"]
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
        }
        if include_usage:
            result["usage"] = [self._feature_summary(cursor, context, feature) for feature in FEATURES]
        return result

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
                cursor.execute(
                    "SELECT * FROM quota_reservations WHERE user_id=%s AND feature=%s AND idempotency_key=%s FOR UPDATE",
                    (user_id, feature, key),
                )
                existing = self.accounts._one(cursor)
                if existing:
                    return {"reservation": self._reservation(existing), "membership": self._public_context(cursor, context, True), "idempotent": True}
                summary = self._feature_summary(cursor, context, feature)
                if quantity > summary["available"]:
                    plan_id = context["plan"]["id"]
                    raise SaaSError(
                        "quota_exceeded", "当前套餐的该项额度已用完。", 409,
                        {"feature": feature, "plan": plan_id, "used": summary["used"], "limit": summary["limit"],
                         "resetAt": timestamp(context["period"]["ends_at"]), "recommendedPlan": self._recommended_plan(plan_id)},
                    )
                reservation = {
                    "id": new_id(), "user_id": user_id, "usage_period_id": context["period"]["id"], "feature": feature,
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
                cursor.execute(
                    """INSERT INTO usage_ledger(id,user_id,usage_period_id,feature,quantity,reason,idempotency_key,metadata_json)
                    VALUES(%s,%s,%s,%s,%s,'credit',%s,%s::jsonb) ON CONFLICT DO NOTHING""",
                    (new_id(), user_id, context["period"]["id"], feature, -quantity, key, json.dumps({"note": note[:1000], "actorId": actor_id})),
                )
                self._audit(cursor, user_id, actor_id, "quota_credit", {"feature": feature, "quantity": quantity, "key": key})
                return self._feature_summary(cursor, context, feature)

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
                # Usage ledger stores consumption as positive and credits as
                # negative, so a positive user-facing grant maps to -quantity.
                ledger_quantity = -quantity
                cursor.execute(
                    """INSERT INTO usage_ledger(id,user_id,usage_period_id,feature,quantity,reason,idempotency_key,metadata_json)
                    VALUES(%s,%s,%s,%s,%s,'adjustment',%s,%s::jsonb) ON CONFLICT DO NOTHING""",
                    (new_id(), user_id, context["period"]["id"], feature, ledger_quantity, key, json.dumps({"note": note[:1000], "actorId": actor_id, "adjustment": quantity})),
                )
                self._audit(cursor, user_id, actor_id, "quota_adjustment", {"feature": feature, "quantity": quantity, "key": key, "note": note[:1000]})
                return self._feature_summary(cursor, context, feature)

    def create_manual_order(self, actor_id: str, user_id: str, plan_version: str, starts_at: Any, ends_at: Any, note: str = "", amount_cents: int = 0) -> dict[str, Any]:
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
                return {"order": self._order({"id": order_id, "user_id": user_id, "plan_version_id": plan_version, "status": "completed", "starts_at": start, "ends_at": end, "amount_cents": amount_cents, "currency": "CNY", "note": note, "created_at": utcnow()}),
                        "subscription": {"id": subscription_id, "status": "active", "startsAt": timestamp(start), "endsAt": timestamp(end)},
                        "membership": self._public_context(cursor, context, True)}

    def update_subscription(self, actor_id: str, subscription_id: str, action: str, ends_at: Any | None = None, note: str = "") -> dict[str, Any]:
        if action not in {"suspend", "activate", "extend"}:
            raise SaaSError("invalid_subscription_action", "不支持的订阅操作。", 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM subscriptions WHERE id=%s FOR UPDATE", (subscription_id,))
                subscription = self.accounts._one(cursor)
                if not subscription:
                    raise SaaSError("subscription_not_found", "订阅不存在。", 404)
                if action == "extend":
                    if ends_at is None:
                        raise SaaSError("invalid_subscription", "延期需要新的结束时间。", 400)
                    new_end = parse_time(ends_at, "endsAt")
                    if new_end <= subscription["ends_at"]:
                        raise SaaSError("invalid_subscription", "新的结束时间必须晚于原结束时间。", 400)
                    cursor.execute("UPDATE subscriptions SET ends_at=%s,note=%s,updated_at=NOW() WHERE id=%s", (new_end, str(note or "")[:1000], subscription_id))
                else:
                    state = "suspended" if action == "suspend" else "active"
                    cursor.execute("UPDATE subscriptions SET status=%s,note=%s,updated_at=NOW() WHERE id=%s", (state, str(note or "")[:1000], subscription_id))
                context = self._context(cursor, subscription["user_id"])
                self._audit(cursor, subscription["user_id"], actor_id, f"subscription_{action}", {"subscriptionId": subscription_id, "note": note[:1000]})
                cursor.execute("SELECT * FROM subscriptions WHERE id=%s", (subscription_id,))
                updated = self.accounts._one(cursor) or subscription
                return {"subscription": {"id": updated["id"], "status": updated["status"], "startsAt": timestamp(updated["starts_at"]), "endsAt": timestamp(updated["ends_at"])}, "membership": self._public_context(cursor, context, True)}

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
                    ORDER BY created_at DESC""",
                    (user_id, user_id),
                )
                return [self._order(row) for row in self.accounts._many(cursor)]

    def _audit(self, cursor: Any, user_id: str, actor_id: str | None, action: str, payload: dict[str, Any]) -> None:
        cursor.execute(
            "INSERT INTO membership_audit(id,user_id,actor_id,action,payload_json) VALUES(%s,%s,%s,%s,%s::jsonb)",
            (new_id(), user_id, actor_id, action, json.dumps(payload)),
        )

    @staticmethod
    def _reservation(row: dict[str, Any]) -> dict[str, Any]:
        return {"id": row["id"], "feature": row["feature"], "quantity": int(row["quantity"]), "state": row["state"], "idempotencyKey": row["idempotency_key"]}

    @staticmethod
    def _order(row: dict[str, Any]) -> dict[str, Any]:
        return {"id": row["id"], "planVersion": row["plan_version_id"], "status": row["status"], "startsAt": timestamp(row["starts_at"]), "endsAt": timestamp(row["ends_at"]), "amountCents": int(row["amount_cents"]), "currency": row["currency"], "note": row["note"], "provider": row.get("provider", "manual"), "createdAt": timestamp(row.get("created_at"))}
