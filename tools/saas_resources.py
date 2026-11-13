#!/usr/bin/env python3
"""Uniform resource protection for invitation-only reading accounts."""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from saas_auth import SaaSError, SaaSConfigurationError, SaaSService, new_id, utcnow

DEFAULT_LIMITS = {
    "video_library_capacity": 100,
    "audio_library_capacity": 200,
    "ai_context_generations": 50,
    "ai_grammar_generations": 20,
    "storage_bytes": 20 * 1024**3,
    "devices": 5,
}
FEATURES = tuple(DEFAULT_LIMITS)
AI_FEATURES = {"ai_context_generations", "ai_grammar_generations"}
PRIVATE_STORAGE_CAPS = {'advanced': 1024**3, 'pro': 5 * 1024**3}
SHANGHAI = ZoneInfo("Asia/Shanghai")


def can_watch_hd_video(cursor: Any, user_id: str) -> bool:
    """Account entitlement is shared by both entry points."""
    cursor.execute("""SELECT EXISTS(SELECT 1 FROM users u WHERE u.id=%s AND
        (u.account_resource_policy='private' OR EXISTS(SELECT 1 FROM subscriptions s
          JOIN plan_versions pv ON pv.id=s.plan_version_id JOIN plans p ON p.id=pv.plan_id
          WHERE s.user_id=u.id AND s.status IN ('active','grace_period')
            AND s.starts_at<=NOW() AND s.ends_at>NOW() AND p.slug<>'free')))""", (user_id,))
    return bool(cursor.fetchone()[0])


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
            raise SaaSError("invalid_time", f"{field} 必须是带时区的 ISO-8601 时间。") from exc
    if result.tzinfo is None:
        raise SaaSError("invalid_time", f"{field} 必须包含时区。")
    return result.astimezone(timezone.utc)


class ResourceService:
    def __init__(self, accounts: SaaSService):
        self.accounts = accounts
        self.limits = dict(DEFAULT_LIMITS)
        environment = getattr(accounts, "environment", {})
        if not isinstance(environment, Mapping):
            environment = {}
        for feature, default in DEFAULT_LIMITS.items():
            if feature == "devices":
                continue
            raw = environment.get("RESOURCE_" + feature.upper(), default)
            try:
                value = int(raw)
            except (ValueError, TypeError) as exc:
                raise SaaSConfigurationError(f"RESOURCE_{feature.upper()} 必须为正整数。") from exc
            if value < 1:
                raise SaaSConfigurationError(f"RESOURCE_{feature.upper()} 必须为正整数。")
            self.limits[feature] = value

    def resolve_limits(self, policy: str, paid_quotas: dict[str, Any] | None = None, free_quotas: dict[str, Any] | None = None, *, paid_family: str = '') -> dict[str, int]:
        limits = dict(self.limits)
        if policy == 'commercial':
            quotas = paid_quotas if paid_quotas is not None else (free_quotas or {})
            for feature in FEATURES:
                if feature not in AI_FEATURES and feature in quotas:
                    limits[feature] = max(0, int(quotas[feature] or 0))
        elif paid_quotas is not None:
            for feature in FEATURES:
                if feature not in AI_FEATURES:
                    limits[feature] = max(limits[feature], int(paid_quotas.get(feature, 0) or 0))
        # Personal-account floors apply to reading resources, never private
        # imports. Old plan versions and redemption codes obey the same cap.
        limits['storage_bytes'] = min(max(0, int((paid_quotas or {}).get('storage_bytes', 0))), PRIVATE_STORAGE_CAPS.get(paid_family, 0))
        return limits

    @staticmethod
    def private_import_access(context: dict[str, Any]) -> dict[str, Any]:
        limit = int(context['limits'].get('storage_bytes', 0))
        allowed = bool(context.get('paid')) and limit > 0
        return {'allowed': allowed, 'storageLimit': limit, 'reason': 'available' if allowed else 'upgrade_required'}

    def assert_private_import(self, context: dict[str, Any]) -> None:
        if not self.private_import_access(context)['allowed']:
            raise SaaSError('private_import_upgrade_required', '免费版不支持导入私人读物，请升级到进阶版或 Pro 版。', 403)

    def _context(self, cursor: Any, user_id: str, lock_user: bool = True) -> dict[str, Any]:
        cursor.execute(f"SELECT id,created_at,status,account_resource_policy FROM users WHERE id=%s {'FOR UPDATE' if lock_user else ''}", (user_id,))
        user = self.accounts._one(cursor)
        if not user or user["status"] != "active":
            raise SaaSError("account_unavailable", "账号不可用。", 403)
        cursor.execute("""SELECT pv.quotas_json,p.slug AS plan_slug FROM subscriptions s
            JOIN plan_versions pv ON pv.id=s.plan_version_id JOIN plans p ON p.id=pv.plan_id
            WHERE s.user_id=%s AND s.status IN ('active','grace_period') AND s.starts_at<=NOW()
              AND s.ends_at>NOW() AND p.slug<>'free'
            ORDER BY pv.rank DESC,s.ends_at DESC,s.created_at DESC LIMIT 1""", (user_id,))
        paid = self.accounts._one(cursor)
        free = None
        if user['account_resource_policy'] == 'commercial' and not paid:
            cursor.execute("SELECT quotas_json FROM plan_versions WHERE id='free-v2'")
            free = self.accounts._one(cursor)
        limits = self.resolve_limits(user['account_resource_policy'], as_json(paid['quotas_json']) if paid else None, as_json(free['quotas_json']) if free else None, paid_family=paid['plan_slug'] if paid else '')
        local_now = utcnow().astimezone(SHANGHAI)
        start = datetime.combine(local_now.date(), datetime.min.time(), tzinfo=SHANGHAI)
        period_key = f"resource-day:{local_now.date().isoformat()}"
        cursor.execute("""INSERT INTO usage_periods(id,user_id,period_key,starts_at,ends_at,limits_json)
            VALUES(%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT(user_id,period_key) DO UPDATE SET limits_json=EXCLUDED.limits_json""",
            (new_id(), user_id, period_key, start.astimezone(timezone.utc),
             (start + timedelta(days=1)).astimezone(timezone.utc), json.dumps(limits)))
        cursor.execute("SELECT * FROM usage_periods WHERE user_id=%s AND period_key=%s FOR UPDATE", (user_id, period_key))
        period = self.accounts._one(cursor)
        if not period:
            raise RuntimeError("resource period creation failed")
        return {"user": user, "period": period, "paid": bool(paid), "limits": limits,
                "canWatchHdVideo": user['account_resource_policy'] == 'private' or bool(paid)}

    def _quota_context(self, cursor: Any, context: dict[str, Any], feature: str) -> dict[str, Any]:
        return context

    def _public_context(self, cursor: Any, context: dict[str, Any], include_usage: bool = False) -> dict[str, Any]:
        period = context["period"]
        limits = as_json(period['limits_json'])
        result = {"limits": limits, "privateImport": self.private_import_access(context), "canWatchHdVideo": context.get('canWatchHdVideo', True),
                  "period": {"startsAt": timestamp(period["starts_at"]), "endsAt": timestamp(period["ends_at"])},
                  "mediaCapacity": self._media_capacity(cursor, context["user"]["id"], limits)}
        if include_usage:
            result["usage"] = [self._feature_summary(cursor, context, feature) for feature in FEATURES]
        return result

    def usage(self, user_id: str) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                return self._public_context(cursor, self._context(cursor, user_id), True)

    def _feature(self, feature: str) -> str:
        value = str(feature or "").strip()
        if value not in FEATURES:
            raise SaaSError("invalid_feature", "未知资源项目。", 400)
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
        context = self._quota_context(cursor, context, feature)
        limits = as_json(context["period"]["limits_json"])
        limit = int(limits.get(feature, 0))
        if feature in AI_FEATURES and context.get('paid'):
            net_used, reserved = self._usage_numbers(cursor, context['period']['id'], feature)
            return {'feature': feature, 'limit': None, 'used': max(0, net_used), 'credits': max(0, -net_used),
                    'reserved': reserved, 'available': None, 'unlimited': True, 'resetAt': None}
        if feature in {"video_library_capacity", "audio_library_capacity"}:
            media_type = "video" if feature.startswith("video_") else "audio"
            used = self._media_library_count(cursor, str(context["user"]["id"]), media_type)
            return {"feature": feature, "limit": limit, "used": used, "credits": 0, "reserved": 0, "available": max(0, limit - used)}
        if feature == "storage_bytes":
            cursor.execute("SELECT COALESCE(SUM(original_bytes+generated_bytes),0) AS total FROM media_assets WHERE owner_id=%s AND scope='private' AND status='active'", (context["user"]["id"],))
            used = int((self.accounts._one(cursor) or {"total": 0})["total"])
            return {"feature": feature, "limit": limit, "used": used, "available": max(0, limit-used)}
        if feature == "devices":
            cursor.execute("SELECT COUNT(*) AS total FROM devices WHERE user_id=%s AND revoked_at IS NULL", (context["user"]["id"],))
            used = int((self.accounts._one(cursor) or {"total": 0})["total"])
            return {"feature": feature, "limit": limit, "used": used, "available": max(0, limit-used)}
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


    def _media_library_count(self, cursor: Any, user_id: str, media_type: str) -> int:
        resource_types = ["video", "youtube"] if media_type == "video" else ["audio"]
        cursor.execute(
            """SELECT
              (SELECT COUNT(*) FROM user_library ul JOIN catalog_books cb ON cb.id=ul.catalog_book_id
               WHERE ul.user_id=%s AND cb.resource_type=ANY(%s)) +
              (SELECT COUNT(*) FROM content_books WHERE owner_id=%s AND visibility IN ('private','draft')
               AND NOT EXISTS (SELECT 1 FROM catalog_books official WHERE official.source_content_book_id=content_books.id)
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
            raise SaaSError("media_capacity_exceeded", f"最多收藏 {limit} 个{'视频' if kind == 'video' else '音频'}（公版与私人内容合计），请先移除不再使用的内容。", 409, {"feature": feature, "used": used, "limit": limit})
        return {"used": used, "limit": limit, "available": max(0, limit - used)}


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
                    return {"reservation": self._reservation(existing), "resources": self._public_context(cursor, context, True), "idempotent": True}
                quota_context = self._quota_context(cursor, context, feature)
                summary = self._feature_summary(cursor, quota_context, feature)
                if not summary.get('unlimited') and quantity > summary["available"]:
                    raise SaaSError("quota_exceeded", "今日该项使用次数已用完，请在次日恢复后重试。", 409,
                        {"feature": feature, "used": summary["used"], "limit": summary["limit"],
                         "resetAt": timestamp(context["period"]["ends_at"])})
                reservation = {
                    "id": new_id(), "user_id": user_id, "usage_period_id": quota_context["period"]["id"], "feature": feature,
                    "idempotency_key": key, "quantity": quantity, "state": "reserved", "metadata_json": payload,
                }
                cursor.execute(
                    """INSERT INTO quota_reservations(id,user_id,usage_period_id,feature,idempotency_key,quantity,state,metadata_json)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                    (reservation["id"], user_id, reservation["usage_period_id"], feature, key, quantity, "reserved", json.dumps(payload)),
                )
                return {"reservation": self._reservation(reservation), "resources": self._public_context(cursor, context, True), "idempotent": False}


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


    def _audit(self, cursor: Any, user_id: str, actor_id: str | None, action: str, payload: dict[str, Any]) -> None:
        cursor.execute(
            "INSERT INTO resource_audit(id,user_id,actor_id,action,payload_json) VALUES(%s,%s,%s,%s,%s::jsonb)",
            (new_id(), user_id, actor_id, action, json.dumps(payload)),
        )


    @staticmethod
    def _reservation(row: dict[str, Any]) -> dict[str, Any]:
        return {"id": row["id"], "feature": row["feature"], "quantity": int(row["quantity"]), "state": row["state"], "idempotencyKey": row["idempotency_key"]}
