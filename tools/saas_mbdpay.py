#!/usr/bin/env python3
"""Mianbaoduo Pay one-time checkout and verified order provisioning."""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from saas_auth import SaaSError, SaaSConfigurationError, SaaSService, new_id, utcnow
from saas_membership import MembershipService, as_json, timestamp


class MbdPayService:
    ALIPAY_URL = "https://newapi.mbd.pub/release/alipay/pay"
    SEARCH_URL = "https://newapi.mbd.pub/release/main/search_order"

    def __init__(self, accounts: SaaSService, memberships: MembershipService):
        self.accounts = accounts
        self.memberships = memberships
        self.app_id = str(accounts.environment.get("MBDPAY_APP_ID", "") or "").strip()
        self.app_key = str(accounts.environment.get("MBDPAY_APP_KEY", "") or "").strip()
        self.base_url = str(accounts.environment.get("APP_BASE_URL", "") or "").strip().rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.app_key and self.base_url.startswith(("http://", "https://")))

    def _require_configured(self) -> None:
        if not self.configured:
            raise SaaSConfigurationError("面包多 Pay 尚未配置。")

    def _sign(self, payload: dict[str, Any]) -> str:
        parts = [f"{key}={payload[key]}" for key in sorted(payload) if key != "sign" and payload[key] not in (None, "")]
        return hashlib.md5(("&".join(parts) + "&key=" + self.app_key).encode("utf-8")).hexdigest()

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_configured()
        signed = {**payload, "app_id": self.app_id}
        signed["sign"] = self._sign(signed)
        request = Request(url, data=json.dumps(signed, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), method="POST", headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urlopen(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise SaaSError("mbdpay_api_error", "面包多 Pay 暂时无法处理请求。", 502) from exc
        except (URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SaaSError("mbdpay_unavailable", "暂时无法连接面包多 Pay，请稍后重试。", 502) from exc
        if not isinstance(result, dict):
            raise SaaSError("mbdpay_invalid_response", "面包多 Pay 返回了无法识别的数据。", 502)
        if result.get("error"):
            raise SaaSError("mbdpay_rejected", str(result["error"])[:300], 502)
        return result

    def _product_row(self, cursor: Any, slug: str) -> dict[str, Any]:
        cursor.execute(
            """SELECT cp.slug,cp.active AS product_active,cpv.*,pv.quotas_json
            FROM commerce_products cp JOIN commerce_product_versions cpv ON cpv.product_id=cp.id
            JOIN plan_versions pv ON pv.id=cpv.plan_version_id
            WHERE cp.slug=%s AND cp.active=TRUE AND cpv.status='published'""",
            (slug,),
        )
        row = self.accounts._one(cursor)
        if not row:
            raise SaaSError("product_not_found", "商品不存在或已停止销售。", 404)
        return row

    def create_order(self, user_id: str, slug: str, idempotency_key: str) -> dict[str, Any]:
        self._require_configured()
        key = str(idempotency_key or "").strip()
        if len(key) < 16 or len(key) > 128:
            raise SaaSError("invalid_idempotency_key", "支付请求标识无效。")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                product = self._product_row(cursor, str(slug or "").strip())
                cursor.execute("SELECT id,email,status,email_verified_at FROM users WHERE id=%s FOR UPDATE", (user_id,))
                user = self.accounts._one(cursor)
                if not user or user["status"] != "active" or not user["email_verified_at"]:
                    raise SaaSError("account_unavailable", "账号不可用于付款。", 403)
                cursor.execute("SELECT * FROM payment_orders WHERE user_id=%s AND idempotency_key=%s FOR UPDATE", (user_id, key))
                existing = self.accounts._one(cursor)
                if existing:
                    if existing["product_version_id"] != product["id"]:
                        raise SaaSError("idempotency_conflict", "支付请求标识已用于其他商品。", 409)
                    return self._public_order(existing)
                cursor.execute(
                    """SELECT s.plan_version_id,s.ends_at FROM subscriptions s
                    WHERE s.user_id=%s AND s.status IN ('active','grace_period') AND s.starts_at<=NOW() AND s.ends_at>NOW()
                    ORDER BY s.ends_at DESC LIMIT 1 FOR UPDATE""",
                    (user_id,),
                )
                active = self.accounts._one(cursor)
                if active and active["plan_version_id"] != product["plan_version_id"]:
                    raise SaaSError("plan_change_support_required", "当前会员仍在有效期内，跨等级升级请联系客服核算权益。", 409, {"support": "289614546"})
                order_id = new_id()
                product_snapshot = {"name": product["display_name"], "shortName": product["short_name"], "durationDays": int(product["duration_days"]), "amountCents": int(product["amount_cents"]), "currency": product["currency"], "version": int(product["version_number"]), "slug": product["slug"]}
                entitlement_snapshot = {"planVersion": product["plan_version_id"], "quotas": as_json(product["quotas_json"]), "benefits": product["benefits_json"]}
                cursor.execute(
                    """INSERT INTO payment_orders(id,user_id,plan_version_id,provider,status,amount_cents,currency,idempotency_key,
                    external_transaction_id,product_version_id,duration_days,product_snapshot_json,entitlement_snapshot_json)
                    VALUES(%s,%s,%s,'mbdpay','pending',%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)""",
                    (order_id, user_id, product["plan_version_id"], int(product["amount_cents"]), product["currency"], key, order_id, product["id"], int(product["duration_days"]), json.dumps(product_snapshot), json.dumps(entitlement_snapshot)),
                )
        return_url = f"{self.base_url}/purchase/{product['slug']}?order={order_id}"
        try:
            checkout = self._post(self.ALIPAY_URL, {"url": return_url, "callback_url": return_url, "description": product["display_name"], "amount_total": int(product["amount_cents"]), "out_trade_no": order_id})
            payment_html = str(checkout.get("body", "") or "")
            if "<form" not in payment_html:
                raise SaaSError("mbdpay_invalid_response", "面包多 Pay 未返回有效支付页面。", 502)
        except Exception as exc:
            with self.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE payment_orders SET status='failed',error_code=%s,error_message=%s,updated_at=NOW() WHERE id=%s", (getattr(exc, "code", "mbdpay_unavailable"), str(exc)[:1000], order_id))
            raise
        return {"orderId": order_id, "status": "pending", "paymentMethod": "alipay", "paymentHtml": payment_html, "returnUrl": return_url}

    def order(self, user_id: str, order_id: str) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM payment_orders WHERE id=%s AND user_id=%s", (str(order_id or "").strip(), user_id))
                row = self.accounts._one(cursor)
        if not row:
            raise SaaSError("payment_order_not_found", "订单不存在。", 404)
        return self._public_order(row)

    @staticmethod
    def _public_order(row: dict[str, Any]) -> dict[str, Any]:
        snapshot = as_json(row.get("product_snapshot_json"))
        return {"id": row["id"], "status": row["status"], "provider": row["provider"], "productVersionId": row.get("product_version_id"), "product": snapshot, "amountCents": int(row["amount_cents"]), "currency": row["currency"], "startsAt": timestamp(row.get("starts_at")), "endsAt": timestamp(row.get("ends_at")), "createdAt": timestamp(row.get("created_at")), "error": row.get("error_message") or ""}

    def _verified_remote_order(self, order_id: str) -> dict[str, Any]:
        return self._post(self.SEARCH_URL, {"out_trade_no": order_id})

    def handle_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        event_type = str(payload.get("type", "") or "").strip()
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        order_id = str(data.get("out_trade_no", "") or "").strip()
        if not event_type or not order_id:
            raise SaaSError("invalid_mbdpay_event", "面包多通知缺少必要字段。")
        charge_id = str(data.get("charge_id", "") or "")
        event_id = f"{event_type}:{order_id}:{charge_id or hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()[:16]}"
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT status FROM payment_provider_events WHERE provider='mbdpay' AND event_id=%s FOR UPDATE", (event_id,))
                existing = self.accounts._one(cursor)
                if existing and existing["status"] in {"processed", "ignored"}:
                    return {"status": "duplicate"}
                if not existing:
                    cursor.execute("INSERT INTO payment_provider_events(provider,event_id,event_type) VALUES('mbdpay',%s,%s)", (event_id, event_type))
                if event_type != "charge_succeeded":
                    cursor.execute("UPDATE payment_provider_events SET status='ignored',processed_at=NOW(),error_message=%s WHERE provider='mbdpay' AND event_id=%s", (str(data.get("complaint_detail", "") or "")[:1000], event_id))
                    return {"status": "ignored"}
        remote = self._verified_remote_order(order_id)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM payment_orders WHERE id=%s AND provider='mbdpay' FOR UPDATE", (order_id,))
                order = self.accounts._one(cursor)
                if not order:
                    raise SaaSError("payment_order_not_found", "支付通知无法关联本地订单。", 404)
                if order["status"] == "paid":
                    cursor.execute("UPDATE payment_provider_events SET status='processed',processed_at=NOW() WHERE provider='mbdpay' AND event_id=%s", (event_id,))
                    return {"status": "duplicate"}
                if int(remote.get("state", 0)) not in {1, 2} or int(remote.get("amount", -1)) != int(order["amount_cents"]):
                    cursor.execute("UPDATE payment_provider_events SET status='failed',processed_at=NOW(),error_message='remote order mismatch' WHERE provider='mbdpay' AND event_id=%s", (event_id,))
                    raise SaaSError("payment_verification_failed", "支付订单核验失败。", 409)
                now = utcnow()
                cursor.execute(
                    """SELECT * FROM subscriptions WHERE user_id=%s AND plan_version_id=%s
                    AND status IN ('active','grace_period') AND ends_at>NOW() ORDER BY ends_at DESC LIMIT 1 FOR UPDATE""",
                    (order["user_id"], order["plan_version_id"]),
                )
                current = self.accounts._one(cursor)
                if current:
                    starts_at = current["starts_at"]
                    ends_at = current["ends_at"] + timedelta(days=int(order["duration_days"]))
                    subscription_id = current["id"]
                    cursor.execute("UPDATE subscriptions SET ends_at=%s,updated_at=NOW(),note='面包多 Pay 固定期限续费' WHERE id=%s", (ends_at, subscription_id))
                else:
                    starts_at, ends_at = now, now + timedelta(days=int(order["duration_days"]))
                    subscription_id = new_id()
                    cursor.execute("UPDATE subscriptions SET status='expired',updated_at=NOW() WHERE user_id=%s AND status IN ('active','grace_period')", (order["user_id"],))
                    cursor.execute("INSERT INTO subscriptions(id,user_id,plan_version_id,status,starts_at,ends_at,note) VALUES(%s,%s,%s,'active',%s,%s,'面包多 Pay 固定期限购买')", (subscription_id, order["user_id"], order["plan_version_id"], starts_at, ends_at))
                cursor.execute("UPDATE payment_orders SET status='paid',external_transaction_id=%s,starts_at=%s,ends_at=%s,error_code=NULL,error_message='',updated_at=NOW() WHERE id=%s", (str(remote.get("charge_id") or charge_id or order_id), starts_at, ends_at, order_id))
                self.memberships._audit(cursor, order["user_id"], order["user_id"], "mbdpay_payment_completed", {"orderId": order_id, "subscriptionId": subscription_id, "productVersionId": order.get("product_version_id")})
                cursor.execute("UPDATE payment_provider_events SET status='processed',processed_at=NOW() WHERE provider='mbdpay' AND event_id=%s", (event_id,))
        return {"status": "processed"}

