#!/usr/bin/env python3
"""One-time CloudCat redemption codes for immutable membership products."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import timedelta
from typing import Any

from saas_auth import SaaSError, SaaSService, new_id, utcnow
from saas_membership import MembershipService, as_json, timestamp


CODE_PATTERN = re.compile(r"^SY-[A-F0-9]{32}$")


class RedemptionService:
    def __init__(self, accounts: SaaSService, memberships: MembershipService):
        self.accounts = accounts
        self.memberships = memberships

    @staticmethod
    def _normalized_code(value: Any) -> str:
        code = str(value or "").strip().upper()
        if not CODE_PATTERN.fullmatch(code):
            raise SaaSError("invalid_redemption_code", "兑换码无效或已使用。", 400)
        return code

    @staticmethod
    def _hash(code: str) -> str:
        return hashlib.sha256(code.encode("ascii")).hexdigest()

    def batches(self, limit: Any = 100) -> dict[str, Any]:
        try:
            size = max(1, min(200, int(limit)))
        except (TypeError, ValueError):
            size = 100
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT b.id,b.product_version_id,b.requested_count,b.note,b.created_at,
                    cpv.display_name,cpv.amount_cents,cpv.duration_days,
                    COUNT(c.id) AS generated_count,
                    COUNT(c.id) FILTER (WHERE c.status='redeemed') AS redeemed_count,
                    COUNT(c.id) FILTER (WHERE c.status='active') AS active_count,
                    COUNT(c.id) FILTER (WHERE c.status='revoked') AS revoked_count
                    FROM commerce_redemption_batches b
                    JOIN commerce_product_versions cpv ON cpv.id=b.product_version_id
                    LEFT JOIN commerce_redemption_codes c ON c.batch_id=b.id
                    GROUP BY b.id,cpv.display_name,cpv.amount_cents,cpv.duration_days
                    ORDER BY b.created_at DESC LIMIT %s""",
                    (size,),
                )
                return {"batches": [{
                    "id": row["id"], "productVersionId": row["product_version_id"], "productName": row["display_name"],
                    "amountCents": int(row["amount_cents"]), "durationDays": int(row["duration_days"]),
                    "requestedCount": int(row["requested_count"]), "generatedCount": int(row["generated_count"]),
                    "redeemedCount": int(row["redeemed_count"]), "activeCount": int(row["active_count"]),
                    "revokedCount": int(row["revoked_count"]), "note": row["note"], "createdAt": timestamp(row["created_at"]),
                } for row in self.accounts._many(cursor)]}

    def generate(self, actor_id: str, product_version_id: Any, count: Any, note: Any = "") -> dict[str, Any]:
        version_id = str(product_version_id or "").strip()
        try:
            quantity = int(count)
        except (TypeError, ValueError) as exc:
            raise SaaSError("invalid_redemption_batch", "兑换码数量无效。", 400) from exc
        if quantity < 1 or quantity > 5000:
            raise SaaSError("invalid_redemption_batch", "单批兑换码数量必须在 1 到 5000 之间。", 400)
        batch_id = "redeem-batch-" + new_id()
        codes = ["SY-" + secrets.token_hex(16).upper() for _ in range(quantity)]
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,display_name,status,amount_cents FROM commerce_product_versions WHERE id=%s FOR UPDATE", (version_id,))
                version = self.accounts._one(cursor)
                if not version or version["status"] != "published" or int(version["amount_cents"]) <= 0:
                    raise SaaSError("redemption_product_unavailable", "只能为已发布的付费套餐生成兑换码。", 409)
                cursor.execute("""INSERT INTO commerce_redemption_batches(id,product_version_id,requested_count,note,created_by)
                    VALUES(%s,%s,%s,%s,%s)""", (batch_id, version_id, quantity, str(note or "").strip()[:500], actor_id))
                cursor.executemany(
                    """INSERT INTO commerce_redemption_codes(id,batch_id,product_version_id,code_hash,code_prefix)
                    VALUES(%s,%s,%s,%s,%s)""",
                    [(new_id(), batch_id, version_id, self._hash(code), code[:7]) for code in codes],
                )
                cursor.execute("""INSERT INTO admin_audit_logs(id,actor_id,action,reason,payload_json)
                    VALUES(%s,%s,'redemption_batch_created','生成云猫兑换库存',%s::jsonb)""",
                    (new_id(), actor_id, json.dumps({"batchId": batch_id, "productVersionId": version_id, "count": quantity})))
        # Plaintext is returned only once and is never stored or logged.
        return {"batchId": batch_id, "productVersionId": version_id, "productName": version["display_name"], "count": quantity, "codes": codes}

    def revoke(self, actor_id: str, value: Any, reason: Any) -> dict[str, Any]:
        code = self._normalized_code(value)
        note = str(reason or "").strip()[:500]
        if not note:
            raise SaaSError("audit_reason_required", "作废兑换码需要填写原因。", 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM commerce_redemption_codes WHERE code_hash=%s FOR UPDATE", (self._hash(code),))
                record = self.accounts._one(cursor)
                if not record:
                    raise SaaSError("redemption_code_not_found", "兑换码不存在。", 404)
                if record["status"] == "redeemed":
                    raise SaaSError("redemption_code_used", "兑换码已兑换，不能直接作废；请按退款流程处理会员权益。", 409)
                if record["status"] == "revoked":
                    return {"status": "revoked", "idempotent": True}
                cursor.execute("UPDATE commerce_redemption_codes SET status='revoked' WHERE id=%s", (record["id"],))
                cursor.execute("""INSERT INTO admin_audit_logs(id,actor_id,action,reason,payload_json)
                    VALUES(%s,%s,'redemption_code_revoked',%s,%s::jsonb)""",
                    (new_id(), actor_id, note, json.dumps({"batchId": record["batch_id"], "codePrefix": record["code_prefix"]})))
                return {"status": "revoked", "idempotent": False}

    def redeem(self, user_id: str, value: Any, idempotency_key: Any = None) -> dict[str, Any]:
        code = self._normalized_code(value)
        code_hash = self._hash(code)
        now = utcnow()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                key = str(idempotency_key or "").strip()[:255] or None
                if key:
                    cursor.execute("SELECT * FROM membership_change_orders WHERE user_id=%s AND idempotency_key=%s", (user_id, key))
                    prior = self.accounts._one(cursor)
                    if prior:
                        return {"status": "redeemed", "idempotent": True, "changeOrder": self.memberships._change_order(prior)}
                context = self.memberships._context(cursor, user_id)
                cursor.execute(
                    """SELECT c.*,cpv.display_name,cpv.short_name,cpv.duration_days,cpv.amount_cents,cpv.plan_version_id,
                    pv.rank,pv.quotas_json FROM commerce_redemption_codes c
                    JOIN commerce_product_versions cpv ON cpv.id=c.product_version_id
                    JOIN plan_versions pv ON pv.id=cpv.plan_version_id
                    WHERE c.code_hash=%s FOR UPDATE OF c""",
                    (code_hash,),
                )
                record = self.accounts._one(cursor)
                if not record:
                    raise SaaSError("invalid_redemption_code", "兑换码无效或已使用。", 400)
                if record["status"] == "redeemed":
                    if record["redeemed_by"] == user_id:
                        cursor.execute("SELECT starts_at,ends_at FROM subscriptions WHERE id=%s", (record["subscription_id"],))
                        subscription = self.accounts._one(cursor) or {}
                        return {"status": "redeemed", "idempotent": True, "planName": record["display_name"], "startsAt": timestamp(subscription.get("starts_at")), "endsAt": timestamp(subscription.get("ends_at")), "membership": self.memberships._public_context(cursor, context, True)}
                    raise SaaSError("invalid_redemption_code", "兑换码无效或已使用。", 400)
                if record["status"] != "active":
                    raise SaaSError("invalid_redemption_code", "兑换码无效或已使用。", 400)
                details = self.memberships._change_details(cursor, user_id, record["plan_version_id"], now)
                starts_at, ends_at = details["startsAt"], details["endsAt"]
                carry_days = details["carryDays"]
                carry_seconds = details["carrySeconds"]
                change_type = details["changeType"]
                change_order_id = new_id()
                subscription_id = new_id()
                existing_subscription_id = details["currentSubscriptionId"]
                if change_type == "upgrade":
                    cursor.execute("""UPDATE subscriptions SET status='expired',updated_at=NOW(),note='升级兑换后剩余期限折算并结转'
                        WHERE user_id=%s AND status IN ('active','grace_period') AND ends_at>NOW()""", (user_id,))
                if change_type == "renewal" and existing_subscription_id:
                    cursor.execute("""UPDATE subscriptions SET starts_at=LEAST(starts_at,NOW()),ends_at=%s,updated_at=NOW(),note='同级续费直接延长有效期'
                        WHERE id=%s""", (ends_at, existing_subscription_id))
                    subscription_id = existing_subscription_id
                    cursor.execute("""UPDATE subscriptions SET status='expired',updated_at=NOW(),note='同级续费并入当前有效期'
                        WHERE user_id=%s AND id<>%s AND starts_at>NOW() AND status IN ('active','grace_period')""", (user_id, existing_subscription_id))
                    cursor.execute("""UPDATE membership_change_orders SET status='cancelled',updated_at=NOW()
                        WHERE user_id=%s AND status='scheduled'""", (user_id,))
                else:
                    cursor.execute("""INSERT INTO subscriptions(id,user_id,plan_version_id,status,starts_at,ends_at,note)
                        VALUES(%s,%s,%s,'active',%s,%s,'云猫寄售兑换')""",
                        (subscription_id, user_id, record["plan_version_id"], starts_at, ends_at))
                order_status = "applied"
                cursor.execute("""INSERT INTO membership_change_orders(
                    id,user_id,source,source_code_id,from_plan_version_id,to_plan_version_id,
                    current_subscription_id,created_subscription_id,change_type,status,effective_at,
                    carry_days,carry_seconds,amount_cents,note)
                    VALUES(%s,%s,'cloudcat',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'云猫寄售兑换')""",
                    (change_order_id, user_id, record["id"], context["plan"]["id"], record["plan_version_id"],
                     details["currentSubscriptionId"], subscription_id, change_type, order_status, starts_at,
                    int(carry_seconds // 86400), carry_seconds, int(record["amount_cents"])))
                if key:
                    cursor.execute("UPDATE membership_change_orders SET idempotency_key=%s WHERE id=%s", (key, change_order_id))
                cursor.execute("""UPDATE commerce_redemption_codes SET status='redeemed',redeemed_by=%s,redeemed_at=NOW(),subscription_id=%s
                    WHERE id=%s AND status='active'""", (user_id, subscription_id, record["id"]))
                self.memberships._audit(cursor, user_id, user_id, "commerce_code_redeemed", {"batchId": record["batch_id"], "planVersionId": record["plan_version_id"], "subscriptionId": subscription_id})
                self.memberships._membership_event(cursor, user_id, change_order_id, f"{change_type}_" + ("scheduled" if order_status == "scheduled" else "applied"), {"fromPlanVersion": context["plan"]["id"], "toPlanVersion": record["plan_version_id"], "carryDays": carry_days, "carrySeconds": carry_seconds}, user_id)
                if change_type in {"first_purchase", "upgrade"}:
                    cursor.execute("UPDATE users SET plan_version=%s,updated_at=NOW() WHERE id=%s", (record["plan_version_id"], user_id))
                context = self.memberships._context(cursor, user_id)
                return {"status": "redeemed", "idempotent": False, "changeOrder": {"id": change_order_id, "changeType": change_type, "status": order_status, "effectiveAt": timestamp(starts_at), "carryDays": carry_days}, "planName": record["display_name"], "startsAt": timestamp(starts_at), "endsAt": timestamp(ends_at), "membership": self.memberships._public_context(cursor, context, True)}
