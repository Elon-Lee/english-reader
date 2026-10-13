#!/usr/bin/env python3
"""Paddle checkout, webhook verification, and subscription provisioning."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from saas_auth import SaaSError, SaaSConfigurationError, SaaSService, new_id, utcnow
from saas_membership import MembershipService, as_json, parse_time, timestamp


PRICE_ENV = {
    ("advanced-v1", "month"): "PADDLE_PRICE_ADVANCED_MONTHLY",
    ("advanced-v1", "year"): "PADDLE_PRICE_ADVANCED_ANNUAL",
    ("pro-v1", "month"): "PADDLE_PRICE_PRO_MONTHLY",
    ("pro-v1", "year"): "PADDLE_PRICE_PRO_ANNUAL",
}
SUPPORTED_EVENTS = {
    "transaction.completed",
    "subscription.created",
    "subscription.activated",
    "subscription.updated",
    "subscription.past_due",
    "subscription.paused",
    "subscription.resumed",
    "subscription.canceled",
}


def _event_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class PaddleBillingService:
    def __init__(self, accounts: SaaSService, memberships: MembershipService):
        self.accounts = accounts
        self.memberships = memberships
        environment = accounts.environment
        self.environment = str(environment.get("PADDLE_ENVIRONMENT", "sandbox") or "sandbox").strip().lower()
        if self.environment not in {"sandbox", "production"}:
            self.environment = "sandbox"
        self.api_key = str(environment.get("PADDLE_API_KEY", "") or "").strip()
        self.client_token = str(environment.get("PADDLE_CLIENT_TOKEN", "") or "").strip()
        self.webhook_secret = str(environment.get("PADDLE_WEBHOOK_SECRET", "") or "").strip()
        self.webhook_tolerance = max(5, int(environment.get("PADDLE_WEBHOOK_TOLERANCE_SECONDS", "300") or 300))
        self.grace_days = max(0, min(30, int(environment.get("PADDLE_GRACE_DAYS", "3") or 3)))
        self.price_map = self._price_map(environment)

    @staticmethod
    def _price_map(environment: dict[str, str]) -> dict[tuple[str, str], str]:
        result = {key: str(environment.get(name, "") or "").strip() for key, name in PRICE_ENV.items()}
        raw = str(environment.get("PADDLE_PRICE_MAP_JSON", "") or "").strip()
        if raw:
            try:
                configured = json.loads(raw)
                for plan_version, intervals in configured.items():
                    if isinstance(intervals, dict):
                        for interval in ("month", "year"):
                            price_id = str(intervals.get(interval, "") or "").strip()
                            if price_id:
                                result[(str(plan_version), interval)] = price_id
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise SaaSConfigurationError("PADDLE_PRICE_MAP_JSON 不是有效的套餐价格映射。") from exc
        return {key: value for key, value in result.items() if value}

    @property
    def api_base(self) -> str:
        return "https://sandbox-api.paddle.com" if self.environment == "sandbox" else "https://api.paddle.com"

    def public_config(self) -> dict[str, Any]:
        available: dict[str, list[str]] = {}
        for plan_version, interval in self.price_map:
            available.setdefault(plan_version, []).append(interval)
        checkout_ready = bool(self.api_key and self.client_token and self.price_map)
        return {
            "provider": "paddle",
            "environment": self.environment,
            "checkoutConfigured": checkout_ready,
            "webhookConfigured": bool(self.webhook_secret),
            "configured": bool(checkout_ready and self.webhook_secret),
            "clientToken": self.client_token if checkout_ready else "",
            "availableIntervals": {key: sorted(value) for key, value in available.items()},
        }

    def _require_checkout(self) -> None:
        if not self.api_key or not self.client_token:
            raise SaaSConfigurationError("Paddle API Key 或客户端 Token 尚未配置。")

    def _api(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._require_checkout()
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = Request(
            self.api_base + path,
            data=body,
            method=method,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=20) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                error = json.loads(exc.read().decode("utf-8"))
                detail = error.get("error", {}).get("detail") or error.get("error", {}).get("code")
            except (ValueError, AttributeError):
                detail = None
            raise SaaSError("paddle_api_error", str(detail or "Paddle 暂时无法处理请求。"), 502) from exc
        except (URLError, TimeoutError, ValueError) as exc:
            raise SaaSError("paddle_unavailable", "暂时无法连接 Paddle，请稍后重试。", 502) from exc
        data = decoded.get("data") if isinstance(decoded, dict) else None
        if not isinstance(data, dict):
            raise SaaSError("paddle_invalid_response", "Paddle 返回了无法识别的数据。", 502)
        return data

    def create_checkout(self, user_id: str, plan_version: str, billing_interval: str, idempotency_key: str) -> dict[str, Any]:
        self._require_checkout()
        plan_version = str(plan_version or "").strip()
        billing_interval = str(billing_interval or "").strip().lower()
        key = str(idempotency_key or "").strip()
        if billing_interval not in {"month", "year"}:
            raise SaaSError("invalid_billing_interval", "请选择月付或年付。")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key):
            raise SaaSError("invalid_idempotency_key", "支付请求标识无效。")
        price_id = self.price_map.get((plan_version, billing_interval))
        if not price_id:
            raise SaaSError("paddle_price_unavailable", "该套餐的 Paddle 价格尚未配置。", 503)

        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                plan = self.memberships._plan(cursor, plan_version)
                if int(plan["rank"]) <= 0:
                    raise SaaSError("invalid_paid_plan", "免费套餐不需要付款。")
                cursor.execute("SELECT id,email,status,email_verified_at FROM users WHERE id=%s FOR UPDATE", (user_id,))
                user = self.accounts._one(cursor)
                if not user or user["status"] != "active" or not user["email_verified_at"]:
                    raise SaaSError("account_unavailable", "账号不可用于付款。", 403)
                cursor.execute(
                    """SELECT external_id FROM external_subscriptions
                    WHERE user_id=%s AND status IN ('active','trialing','past_due','paused')
                    ORDER BY updated_at DESC LIMIT 1""",
                    (user_id,),
                )
                active = self.accounts._one(cursor)
                if active:
                    raise SaaSError("subscription_already_managed", "你已有 Paddle 订阅，请使用订阅管理入口。", 409)
                cursor.execute("SELECT * FROM payment_orders WHERE user_id=%s AND idempotency_key=%s FOR UPDATE", (user_id, key))
                existing = self.accounts._one(cursor)
                if existing:
                    if existing["plan_version_id"] != plan_version or existing["billing_interval"] != billing_interval:
                        raise SaaSError("idempotency_conflict", "支付请求标识已用于其他套餐。", 409)
                    if existing["external_transaction_id"]:
                        return self._checkout_result(existing, str(user["email"]))
                    raise SaaSError("checkout_retry_required", "上一次支付创建未完成，请刷新后重新发起。", 409)
                pricing = as_json(plan["pricing_json"])
                amount = int(pricing.get("monthly_cents" if billing_interval == "month" else "annual_cents", 0) or 0)
                if amount <= 0:
                    raise SaaSError("invalid_plan_price", "套餐价格未配置。")
                order_id = new_id()
                cursor.execute(
                    """INSERT INTO payment_orders(id,user_id,plan_version_id,provider,billing_interval,amount_cents,idempotency_key)
                    VALUES(%s,%s,%s,'paddle',%s,%s,%s)""",
                    (order_id, user_id, plan_version, billing_interval, amount, key),
                )

        try:
            transaction = self._api(
                "POST",
                "/transactions",
                {
                    "items": [{"price_id": price_id, "quantity": 1}],
                    "collection_mode": "automatic",
                    "custom_data": {
                        "local_order_id": order_id,
                        "user_id": user_id,
                        "plan_version_id": plan_version,
                        "billing_interval": billing_interval,
                    },
                },
            )
            transaction_id = str(transaction.get("id", ""))
            if not transaction_id.startswith("txn_"):
                raise SaaSError("paddle_invalid_response", "Paddle 未返回有效交易编号。", 502)
        except (SaaSError, SaaSConfigurationError) as exc:
            with self.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE payment_orders SET status='failed',error_code=%s,error_message=%s,updated_at=NOW() WHERE id=%s",
                        (getattr(exc, "code", "paddle_unavailable"), str(exc)[:1000], order_id),
                    )
            raise

        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE payment_orders SET external_transaction_id=%s,updated_at=NOW() WHERE id=%s", (transaction_id, order_id))
                cursor.execute("SELECT * FROM payment_orders WHERE id=%s", (order_id,))
                order = self.accounts._one(cursor)
        return self._checkout_result(order or {"id": order_id, "external_transaction_id": transaction_id}, str(user["email"]))

    def _checkout_result(self, order: dict[str, Any], email: str) -> dict[str, Any]:
        return {
            "orderId": order["id"],
            "transactionId": order["external_transaction_id"],
            "environment": self.environment,
            "clientToken": self.client_token,
            "customerEmail": email,
        }

    def management_links(self, user_id: str) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT external_id,status FROM external_subscriptions
                    WHERE user_id=%s AND status IN ('active','trialing','past_due','paused')
                    ORDER BY updated_at DESC LIMIT 1""",
                    (user_id,),
                )
                subscription = self.accounts._one(cursor)
        if not subscription:
            raise SaaSError("external_subscription_not_found", "当前没有可管理的 Paddle 订阅。", 404)
        data = self._api("GET", f"/subscriptions/{subscription['external_id']}")
        urls = data.get("management_urls") if isinstance(data.get("management_urls"), dict) else {}
        return {
            "status": data.get("status") or subscription["status"],
            "cancelUrl": urls.get("cancel"),
            "updatePaymentMethodUrl": urls.get("update_payment_method"),
        }

    def verify_signature(self, raw_body: bytes, signature_header: str, current_time: int | None = None) -> None:
        if not self.webhook_secret:
            raise SaaSConfigurationError("PADDLE_WEBHOOK_SECRET 尚未配置。")
        parts: dict[str, list[str]] = {}
        for item in str(signature_header or "").split(";"):
            key, separator, value = item.strip().partition("=")
            if separator and key and value:
                parts.setdefault(key, []).append(value)
        timestamp_values, signatures = parts.get("ts", []), parts.get("h1", [])
        if not timestamp_values or not signatures:
            raise SaaSError("invalid_paddle_signature", "Paddle webhook 签名格式无效。", 401)
        try:
            signed_at = int(timestamp_values[0])
        except ValueError as exc:
            raise SaaSError("invalid_paddle_signature", "Paddle webhook 时间戳无效。", 401) from exc
        now = int(time.time() if current_time is None else current_time)
        if abs(now - signed_at) > self.webhook_tolerance:
            raise SaaSError("stale_paddle_webhook", "Paddle webhook 已超过验签时间窗口。", 401)
        signed_payload = str(signed_at).encode("ascii") + b":" + raw_body
        expected = hmac.new(self.webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
            raise SaaSError("invalid_paddle_signature", "Paddle webhook 签名校验失败。", 401)

    def handle_webhook(self, raw_body: bytes, signature_header: str) -> dict[str, Any]:
        self.verify_signature(raw_body, signature_header)
        try:
            event = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SaaSError("invalid_paddle_event", "Paddle webhook 不是有效 JSON。") from exc
        event_id = str(event.get("event_id", "") or "").strip()
        event_type = str(event.get("event_type", "") or "").strip()
        data = event.get("data")
        if not event_id or not event_type or not isinstance(data, dict):
            raise SaaSError("invalid_paddle_event", "Paddle webhook 缺少必要字段。")
        occurred_at = _event_time(event.get("occurred_at"))

        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT status FROM payment_provider_events WHERE provider='paddle' AND event_id=%s FOR UPDATE", (event_id,))
                existing = self.accounts._one(cursor)
                if existing and existing["status"] in {"processed", "ignored"}:
                    return {"status": "duplicate", "eventId": event_id}
                if existing:
                    cursor.execute("UPDATE payment_provider_events SET status='processing',error_message='' WHERE provider='paddle' AND event_id=%s", (event_id,))
                else:
                    cursor.execute(
                        """INSERT INTO payment_provider_events(provider,event_id,event_type,occurred_at)
                        VALUES('paddle',%s,%s,%s)""",
                        (event_id, event_type, occurred_at),
                    )
                if event_type not in SUPPORTED_EVENTS:
                    cursor.execute(
                        "UPDATE payment_provider_events SET status='ignored',processed_at=NOW() WHERE provider='paddle' AND event_id=%s",
                        (event_id,),
                    )
                    return {"status": "ignored", "eventId": event_id}
                try:
                    if event_type == "transaction.completed":
                        self._complete_transaction(cursor, data)
                    else:
                        self._sync_subscription(cursor, data)
                except Exception as exc:
                    cursor.execute(
                        """UPDATE payment_provider_events SET status='failed',error_message=%s,processed_at=NOW()
                        WHERE provider='paddle' AND event_id=%s""",
                        (str(exc)[:1000], event_id),
                    )
                    raise
                cursor.execute(
                    "UPDATE payment_provider_events SET status='processed',processed_at=NOW() WHERE provider='paddle' AND event_id=%s",
                    (event_id,),
                )
        return {"status": "processed", "eventId": event_id}

    def _context_from_data(self, cursor: Any, data: dict[str, Any]) -> tuple[dict[str, Any] | None, str, str, str]:
        custom = data.get("custom_data") if isinstance(data.get("custom_data"), dict) else {}
        order = None
        order_id = str(custom.get("local_order_id", "") or "").strip()
        if order_id:
            cursor.execute("SELECT * FROM payment_orders WHERE id=%s FOR UPDATE", (order_id,))
            order = self.accounts._one(cursor)
        transaction_id = str(data.get("id", "") or "") if str(data.get("id", "")).startswith("txn_") else str(data.get("transaction_id", "") or "")
        if not order and transaction_id:
            cursor.execute("SELECT * FROM payment_orders WHERE provider='paddle' AND external_transaction_id=%s FOR UPDATE", (transaction_id,))
            order = self.accounts._one(cursor)
        user_id = str((order or {}).get("user_id") or custom.get("user_id") or "").strip()
        plan_version = str((order or {}).get("plan_version_id") or custom.get("plan_version_id") or "").strip()
        interval = str((order or {}).get("billing_interval") or custom.get("billing_interval") or "").strip()
        if not user_id or not plan_version or interval not in {"month", "year"}:
            raise SaaSError("paddle_event_unmatched", "Paddle 事件无法关联本地用户或套餐。", 409)
        cursor.execute("SELECT 1 FROM users WHERE id=%s", (user_id,))
        if not cursor.fetchone():
            raise SaaSError("paddle_event_unmatched", "Paddle 事件关联的用户不存在。", 409)
        self.memberships._plan(cursor, plan_version)
        return order, user_id, plan_version, interval

    @staticmethod
    def _period(data: dict[str, Any], field: str) -> tuple[datetime | None, datetime | None]:
        period = data.get(field) if isinstance(data.get(field), dict) else {}
        start = _event_time(period.get("starts_at"))
        end = _event_time(period.get("ends_at"))
        return start, end

    def _upsert_entitlement(
        self,
        cursor: Any,
        user_id: str,
        plan_version: str,
        external_id: str | None,
        interval: str,
        provider_status: str,
        starts_at: datetime | None,
        ends_at: datetime | None,
        customer_id: str | None = None,
        cancel_at_period_end: bool = False,
    ) -> str | None:
        if not starts_at:
            starts_at = utcnow()
        if not ends_at or ends_at <= starts_at:
            ends_at = starts_at + timedelta(days=365 if interval == "year" else 30)
        local_status = {
            "active": "active",
            "trialing": "active",
            "past_due": "grace_period",
            "paused": "suspended",
            "canceled": "expired",
        }.get(provider_status, "active")
        if local_status == "grace_period":
            ends_at = max(ends_at, utcnow() + timedelta(days=self.grace_days))
        local_id = None
        if external_id:
            cursor.execute("SELECT local_subscription_id FROM external_subscriptions WHERE provider='paddle' AND external_id=%s FOR UPDATE", (external_id,))
            row = self.accounts._one(cursor)
            local_id = str(row["local_subscription_id"]) if row and row.get("local_subscription_id") else None
        if local_id:
            cursor.execute(
                """UPDATE subscriptions SET plan_version_id=%s,status=%s,starts_at=%s,ends_at=%s,note=%s,updated_at=NOW()
                WHERE id=%s""",
                (plan_version, local_status, starts_at, ends_at, "Paddle subscription", local_id),
            )
        elif local_status in {"active", "grace_period", "suspended"}:
            local_id = new_id()
            cursor.execute(
                """INSERT INTO subscriptions(id,user_id,plan_version_id,status,starts_at,ends_at,note)
                VALUES(%s,%s,%s,%s,%s,%s,'Paddle subscription')""",
                (local_id, user_id, plan_version, local_status, starts_at, ends_at),
            )
        if local_status in {"active", "grace_period"} and local_id:
            cursor.execute(
                """UPDATE subscriptions SET status='expired',updated_at=NOW()
                WHERE user_id=%s AND id<>%s AND status IN ('active','grace_period')""",
                (user_id, local_id),
            )
        if external_id:
            cursor.execute(
                """INSERT INTO external_subscriptions(provider,external_id,user_id,plan_version_id,local_subscription_id,customer_id,status,billing_interval,current_period_start,current_period_end,cancel_at_period_end)
                VALUES('paddle',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(provider,external_id) DO UPDATE SET user_id=EXCLUDED.user_id,plan_version_id=EXCLUDED.plan_version_id,
                local_subscription_id=COALESCE(EXCLUDED.local_subscription_id,external_subscriptions.local_subscription_id),customer_id=COALESCE(EXCLUDED.customer_id,external_subscriptions.customer_id),
                status=EXCLUDED.status,billing_interval=EXCLUDED.billing_interval,current_period_start=EXCLUDED.current_period_start,
                current_period_end=EXCLUDED.current_period_end,cancel_at_period_end=EXCLUDED.cancel_at_period_end,updated_at=NOW()""",
                (external_id, user_id, plan_version, local_id, customer_id, provider_status, interval, starts_at, ends_at, cancel_at_period_end),
            )
        return local_id

    def _complete_transaction(self, cursor: Any, data: dict[str, Any]) -> None:
        order, user_id, plan_version, interval = self._context_from_data(cursor, data)
        transaction_id = str(data.get("id", "") or "")
        external_subscription_id = str(data.get("subscription_id", "") or "").strip() or None
        starts_at, ends_at = self._period(data, "billing_period")
        totals = data.get("details", {}).get("totals", {}) if isinstance(data.get("details"), dict) else {}
        total = totals.get("total")
        currency = str(data.get("currency_code", "CNY") or "CNY")[:3].upper()
        local_id = self._upsert_entitlement(cursor, user_id, plan_version, external_subscription_id, interval, "active", starts_at, ends_at, str(data.get("customer_id", "") or "") or None)
        if order:
            cursor.execute(
                """UPDATE payment_orders SET status='paid',external_transaction_id=%s,external_subscription_id=%s,
                amount_cents=COALESCE(%s,amount_cents),currency=%s,starts_at=%s,ends_at=%s,error_code=NULL,error_message='',updated_at=NOW()
                WHERE id=%s""",
                (transaction_id, external_subscription_id, int(total) if str(total or "").isdigit() else None, currency, starts_at, ends_at, order["id"]),
            )
        self.memberships._audit(cursor, user_id, user_id, "paddle_payment_completed", {"orderId": (order or {}).get("id"), "transactionId": transaction_id, "subscriptionId": external_subscription_id, "localSubscriptionId": local_id, "plan": plan_version})

    def _sync_subscription(self, cursor: Any, data: dict[str, Any]) -> None:
        order, user_id, plan_version, interval = self._context_from_data(cursor, data)
        external_id = str(data.get("id", "") or "").strip()
        if not external_id.startswith("sub_"):
            raise SaaSError("invalid_paddle_subscription", "Paddle 订阅编号无效。", 409)
        provider_status = str(data.get("status", "active") or "active").strip()
        starts_at, ends_at = self._period(data, "current_billing_period")
        scheduled = data.get("scheduled_change") if isinstance(data.get("scheduled_change"), dict) else {}
        cancel_at_period_end = scheduled.get("action") == "cancel"
        self._upsert_entitlement(cursor, user_id, plan_version, external_id, interval, provider_status, starts_at, ends_at, str(data.get("customer_id", "") or "") or None, cancel_at_period_end)
        if order:
            cursor.execute("UPDATE payment_orders SET external_subscription_id=%s,updated_at=NOW() WHERE id=%s", (external_id, order["id"]))

