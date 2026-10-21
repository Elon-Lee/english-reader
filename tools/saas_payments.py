#!/usr/bin/env python3
"""Alipay one-time checkout and auditable commerce administration."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from decimal import Decimal, InvalidOperation
import urllib.parse
import urllib.request
from datetime import timedelta
from typing import Any

from saas_auth import SaaSError, SaaSConfigurationError, SaaSService, new_id, utcnow
from saas_membership import MembershipService, as_json, timestamp


ALIPAY_GATEWAY = "https://openapi.alipay.com/gateway.do"


class AlipayService:
    def __init__(self, accounts: SaaSService, memberships: MembershipService, environment: dict[str, str] | None = None):
        self.accounts = accounts
        self.memberships = memberships
        self.environment = dict(environment or os.environ)

    def _credentials(self) -> dict[str, str]:
        return {
            "app_id": self.environment.get("ALIPAY_APP_ID", "").strip(),
            "private_key": self.environment.get("ALIPAY_PRIVATE_KEY", "").replace("\\n", "\n").strip(),
            "alipay_public_key": self.environment.get("ALIPAY_PUBLIC_KEY", "").replace("\\n", "\n").strip(),
            "notify_url": self.environment.get("ALIPAY_NOTIFY_URL", "").strip(),
            "product": self.environment.get("ALIPAY_PAYMENT_PRODUCT", "").strip(),
            "approved": self.environment.get("ALIPAY_PAYMENT_PRODUCT_APPROVED", "").strip(),
        }

    def _test_mode(self) -> bool:
        return self.environment.get("ALIPAY_TEST_MODE", "").strip() == "1" and self.environment.get("SHIYUE_DEPLOYMENT_MODE", "remote").strip() == "local"

    def _crypto(self) -> tuple[Any, Any, Any]:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError as exc:
            raise SaaSConfigurationError("支付宝 RSA2 组件未安装，请部署依赖后再配置支付。") from exc
        return hashes, serialization, padding

    def _keys(self) -> tuple[Any, Any, dict[str, str]]:
        values = self._credentials()
        if not all(values.values()):
            raise SaaSConfigurationError("支付宝获批产品标识、应用参数、RSA2 密钥和异步通知地址尚未完整配置。")
        if values["product"] != "face_to_face" or values["approved"] != "1":
            raise SaaSConfigurationError("当前实现只支持已获批的支付宝当面付扫码产品。")
        hashes, serialization, padding = self._crypto()
        try:
            private_key = serialization.load_pem_private_key(values["private_key"].encode(), password=None)
            public_pem = "-----BEGIN PUBLIC KEY-----\n" + values["alipay_public_key"] + "\n-----END PUBLIC KEY-----\n"
            public_key = serialization.load_pem_public_key(public_pem.encode())
        except (ValueError, TypeError) as exc:
            raise SaaSConfigurationError("支付宝 RSA2 密钥格式无效。") from exc
        return private_key, public_key, values

    def readiness(self) -> dict[str, Any]:
        values = self._credentials()
        test_mode = self._test_mode()
        ready = test_mode or (all(values.values()) and values["product"] == "face_to_face" and values["approved"] == "1")
        if ready and not test_mode:
            try:self._keys()
            except (SaaSError, SaaSConfigurationError):ready = False
        return {"configured": ready, "appIdConfigured": bool(values["app_id"]),
                "privateKeyConfigured": bool(values["private_key"]),
                "alipayPublicKeyConfigured": bool(values["alipay_public_key"]),
                "notifyUrlConfigured": bool(values["notify_url"]),
                "approvedProduct": values["product"] if values["approved"] == "1" else "",
                "testMode": test_mode, "enabled": False}

    def _settings(self, cursor: Any | None = None) -> dict[str, Any]:
        if cursor:
            cursor.execute("SELECT value_json FROM platform_settings WHERE key='commerce.payment_methods'")
            row = self.accounts._one(cursor)
        else:
            with self.accounts.transaction() as connection:
                with connection.cursor() as current:
                    current.execute("SELECT value_json FROM platform_settings WHERE key='commerce.payment_methods'")
                    row = self.accounts._one(current)
        stored = as_json(row["value_json"]) if row else {}
        readiness = self.readiness()
        return {
            "cloudcatEnabled": bool(stored.get("cloudcatEnabled", True)),
            "redemptionEnabled": bool(stored.get("redemptionEnabled", True)),
            "alipayEnabled": bool(stored.get("alipayEnabled", False)) and readiness["configured"],
            "alipayReady": readiness["configured"],
            "alipayRequirements": readiness,
        }

    def public_config(self) -> dict[str, Any]:
        settings = self._settings()
        methods = []
        if settings["alipayEnabled"]:
            methods.append("alipay")
        if settings["cloudcatEnabled"]:
            methods.append("cloudcat")
        return {"methods": methods, "redemptionEnabled": settings["redemptionEnabled"],
                "automaticRenewal": False}

    def admin_config(self) -> dict[str, Any]:
        return {"payment": self._settings()}

    def update_config(self, actor_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        readiness = self.readiness()
        alipay_enabled = bool(payload.get("alipayEnabled"))
        if alipay_enabled and not readiness["configured"]:
            raise SaaSError("alipay_not_configured", "支付宝支付产品与服务端参数尚未配置完整，暂不能启用。", 409)
        value = {"alipayEnabled": alipay_enabled,
                 "cloudcatEnabled": bool(payload.get("cloudcatEnabled", False)),
                 "redemptionEnabled": bool(payload.get("redemptionEnabled", False))}
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO platform_settings(key,value_json,updated_by)
                    VALUES('commerce.payment_methods',%s::jsonb,%s)
                    ON CONFLICT(key) DO UPDATE SET value_json=EXCLUDED.value_json,updated_by=EXCLUDED.updated_by,updated_at=NOW()""",
                    (json.dumps(value), actor_id))
                cursor.execute("""INSERT INTO admin_audit_logs(id,actor_id,action,reason,payload_json)
                    VALUES(%s,%s,'payment_methods_updated','',%s::jsonb)""",
                    (new_id(), actor_id, json.dumps(value)))
        return self.admin_config()

    @staticmethod
    def _canonical(values: dict[str, Any]) -> str:
        return "&".join(f"{key}={str(values[key])}" for key in sorted(values) if values[key] is not None and values[key] != "")

    def _sign(self, values: dict[str, Any], private_key: Any) -> str:
        hashes, _, padding = self._crypto()
        signature = private_key.sign(self._canonical(values).encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(signature).decode("ascii")

    def _verify(self, values: dict[str, Any], public_key: Any) -> None:
        signature = str(values.get("sign", "") or "")
        if not signature:
            raise SaaSError("invalid_alipay_signature", "支付宝签名缺失。", 401)
        hashes, _, padding = self._crypto()
        try:
            public_key.verify(base64.b64decode(signature), self._canonical({key: value for key, value in values.items() if key not in {"sign", "sign_type"}}).encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        except Exception as exc:
            raise SaaSError("invalid_alipay_signature", "支付宝签名校验失败。", 401) from exc

    def _request(self, method: str, biz_content: dict[str, Any]) -> dict[str, Any]:
        if self._test_mode():
            raise SaaSConfigurationError("本地支付宝模拟模式禁止访问支付宝网关。")
        private_key, public_key, credentials = self._keys()
        params = {"app_id": credentials["app_id"], "method": method, "format": "JSON", "charset": "utf-8",
                  "sign_type": "RSA2", "timestamp": utcnow().strftime("%Y-%m-%d %H:%M:%S"), "version": "1.0",
                  "biz_content": json.dumps(biz_content, ensure_ascii=False, separators=(",", ":"))}
        if method == "alipay.trade.precreate":
            params["notify_url"] = credentials["notify_url"]
        params["sign"] = self._sign(params, private_key)
        body = urllib.parse.urlencode(params).encode("utf-8")
        request = urllib.request.Request(ALIPAY_GATEWAY, data=body, headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read(1_000_000).decode("utf-8"))
        except Exception as exc:
            raise SaaSError("alipay_unavailable", "支付宝暂时无法响应，请稍后查询订单状态。", 503) from exc
        result = payload.get(method.replace(".", "_") + "_response")
        if not isinstance(result, dict):
            raise SaaSError("alipay_invalid_response", "支付宝返回数据无效。", 502)
        if not payload.get("sign"):
            raise SaaSError("alipay_invalid_signature", "支付宝接口响应缺少签名。", 502)
        self._verify({**result, "sign": payload["sign"]}, public_key)
        if result.get("code") != "10000":
            raise SaaSError("alipay_request_failed", str(result.get("sub_msg") or result.get("msg") or "支付宝处理失败。")[:300], 502)
        return result

    def _create_provider_order(self, order: dict[str, Any], product: dict[str, Any]) -> dict[str, Any]:
        result = self._request("alipay.trade.precreate", {
            "out_trade_no": order["id"], "total_amount": f"{int(order['amount_cents']) / 100:.2f}",
            "subject": str(product["display_name"])[:128], "body": str(product.get("description") or product["display_name"])[:256],
            "timeout_express": "15m",
        })
        if not result.get("qr_code"):
            raise SaaSError("alipay_invalid_response", "支付宝没有返回付款二维码。", 502)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE payment_orders SET external_transaction_id=%s,updated_at=NOW() WHERE id=%s AND status='pending'",
                               (str(result.get("trade_no") or "") or None, order["id"]))
                cursor.execute("UPDATE payment_orders SET payment_code_url=%s WHERE id=%s", (str(result["qr_code"]), order["id"]))
        return {"orderId": order["id"], "status": "pending", "qrCode": result["qr_code"], "expiresAt": timestamp(utcnow() + timedelta(minutes=15))}

    def simulate_paid(self, user_id: str, order_id: str) -> dict[str, Any]:
        if not self._test_mode():
            raise SaaSError("payment_test_mode_disabled", "本地支付模拟模式未启用。", 404)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM payment_orders WHERE id=%s AND user_id=%s AND provider='alipay' FOR UPDATE", (order_id, user_id))
                order = self.accounts._one(cursor)
        if not order:
            raise SaaSError("payment_order_not_found", "支付订单不存在。", 404)
        if not as_json(order.get("product_snapshot_json")).get("testMode"):
            raise SaaSError("payment_test_mode_disabled", "该订单不是本地模拟订单。", 409)
        if order["status"] == "paid":
            return self._public_order(order)
        if order["status"] != "pending":
            raise SaaSError("payment_order_not_payable", "该订单已不能模拟付款。", 409)
        self._complete_paid({"out_trade_no": order_id, "trade_status": "TRADE_SUCCESS",
            "total_amount": f"{int(order['amount_cents']) / 100:.2f}",
            "app_id": self._credentials()["app_id"] or "local-test", "trade_no": "local-test-" + order_id})
        return self.order_status(user_id, order_id)

    def create_order(self, user_id: str, product_version_id: Any, idempotency_key: Any) -> dict[str, Any]:
        key = str(idempotency_key or "").strip()
        version_id = str(product_version_id or "").strip()
        if not 16 <= len(key) <= 128 or not all(char.isalnum() or char in "_-" for char in key):
            raise SaaSError("invalid_idempotency_key", "支付请求标识无效。", 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE id=%s AND status='active' AND email_verified_at IS NOT NULL FOR UPDATE", (user_id,))
                if not cursor.fetchone():
                    raise SaaSError("account_unavailable", "请先验证邮箱后再付款。", 403)
                settings = self._settings(cursor)
                if not settings["alipayEnabled"]:
                    raise SaaSError("alipay_unavailable", "支付宝暂未开放，请选择其他支付方式。", 503)
                cursor.execute("SELECT * FROM payment_orders WHERE user_id=%s AND idempotency_key=%s FOR UPDATE", (user_id, "alipay:" + key))
                existing = self.accounts._one(cursor)
                if existing:
                    if existing["product_version_id"] != version_id:
                        raise SaaSError("idempotency_conflict", "支付请求标识已用于其他套餐。", 409)
                    if existing["status"] == "pending":
                        cursor.execute("SELECT display_name,description FROM commerce_product_versions WHERE id=%s", (version_id,))
                        product = self.accounts._one(cursor)
                        order = existing
                    else:
                        return self._public_order(existing)
                else:
                    cursor.execute("""SELECT cpv.*,pv.id AS target_plan_id FROM commerce_product_versions cpv
                        JOIN plan_versions pv ON pv.id=cpv.plan_version_id WHERE cpv.id=%s AND cpv.status='published'""", (version_id,))
                    product = self.accounts._one(cursor)
                    if not product or int(product["amount_cents"]) <= 0:
                        raise SaaSError("payment_product_unavailable", "该套餐当前不可购买。", 409)
                    context = self.memberships._context(cursor, user_id)
                    if context["user"].get("status") != "active":
                        raise SaaSError("account_unavailable", "请先验证邮箱后再付款。", 403)
                    change = self.memberships._change_details(cursor, user_id, product["target_plan_id"])
                    order_id = "ali_" + new_id()
                    test_mode = self._test_mode()
                    cursor.execute("""INSERT INTO payment_orders(id,user_id,plan_version_id,provider,status,amount_cents,currency,
                        idempotency_key,product_version_id,duration_days,product_snapshot_json,entitlement_snapshot_json)
                        VALUES(%s,%s,%s,'alipay','pending',%s,'CNY',%s,%s,%s,%s::jsonb,%s::jsonb)""",
                        (order_id, user_id, product["target_plan_id"], int(product["amount_cents"]), "alipay:" + key,
                         version_id, int(product["duration_days"]), json.dumps({"name": product["display_name"], "shortName": product["short_name"], "amountCents": int(product["amount_cents"]), "durationDays": int(product["duration_days"]), "currency": product["currency"], "testMode": test_mode}),
                         json.dumps(as_json(product["limits_json"]) if product.get("limits_json") else {})))
                    cursor.execute("SELECT * FROM payment_orders WHERE id=%s", (order_id,))
                    order = self.accounts._one(cursor)
        if self._test_mode() and as_json(order.get("product_snapshot_json")).get("testMode"):
            return {**self._public_order(order), "testMode": True}
        if not order.get("payment_code_url"):
            return self._create_provider_order(order, product)
        return {**self._public_order(order), "qrCode": order["payment_code_url"], "expiresAt": timestamp(order["created_at"] + timedelta(minutes=15))}

    @staticmethod
    def _public_order(row: dict[str, Any]) -> dict[str, Any]:
        return {"orderId": row["id"], "status": row["status"], "amountCents": int(row["amount_cents"]),
                "currency": row["currency"], "createdAt": timestamp(row["created_at"]), "startsAt": timestamp(row.get("starts_at")),
                "endsAt": timestamp(row.get("ends_at")), "refundedAt": timestamp(row.get("refunded_at")),
                "testMode": bool(as_json(row.get("product_snapshot_json")).get("testMode"))}

    def order_status(self, user_id: str, order_id: str) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM payment_orders WHERE id=%s AND user_id=%s AND provider='alipay'", (order_id, user_id))
                order = self.accounts._one(cursor)
        if not order:
            raise SaaSError("payment_order_not_found", "支付订单不存在。", 404)
        if order["status"] == "pending" and not as_json(order.get("product_snapshot_json")).get("testMode"):
            result = self._request("alipay.trade.query", {"out_trade_no": order["id"]})
            if result.get("trade_status") == "TRADE_SUCCESS":
                self._complete_paid(result)
                with self.accounts.transaction() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT * FROM payment_orders WHERE id=%s AND user_id=%s", (order_id, user_id))
                        order = self.accounts._one(cursor) or order
            elif result.get("trade_status") == "TRADE_CLOSED":
                with self.accounts.transaction() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("UPDATE payment_orders SET status='cancelled',updated_at=NOW() WHERE id=%s AND status='pending'", (order_id,))
                        cursor.execute("SELECT * FROM payment_orders WHERE id=%s AND user_id=%s", (order_id, user_id))
                        order = self.accounts._one(cursor) or order
        status = self._public_order(order)
        if order["status"] == "pending" and order.get("payment_code_url"):
            status["qrCode"] = order["payment_code_url"]
            status["expiresAt"] = timestamp(order["created_at"] + timedelta(minutes=15))
        return status

    def admin_order_detail(self, order_id: str) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT o.*,u.email,cpv.display_name FROM payment_orders o
                    JOIN users u ON u.id=o.user_id LEFT JOIN commerce_product_versions cpv ON cpv.id=o.product_version_id
                    WHERE o.id=%s AND o.provider='alipay'""", (order_id,))
                row = self.accounts._one(cursor)
        if not row:
            raise SaaSError("payment_order_not_found", "支付宝订单不存在。", 404)
        result = self._admin_order(row)
        result["productSnapshot"] = as_json(row["product_snapshot_json"])
        result["entitlementSnapshot"] = as_json(row["entitlement_snapshot_json"])
        result["refundCompletedAt"] = timestamp(row.get("refunded_at"))
        result["updatedAt"] = timestamp(row.get("updated_at"))
        return result

    def notify(self, form: dict[str, Any]) -> str:
        private_key, public_key, credentials = self._keys()
        self._verify(form, public_key)
        if str(form.get("app_id", "")) != credentials["app_id"]:
            raise SaaSError("alipay_wrong_app", "支付宝通知应用号不匹配。", 400)
        if str(form.get("trade_status", "")) not in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
            return "success"
        result = self._request("alipay.trade.query", {"out_trade_no": str(form.get("out_trade_no", ""))})
        self._complete_paid(result)
        return "success"

    def _complete_paid(self, trade: dict[str, Any]) -> None:
        order_id = str(trade.get("out_trade_no", "") or "")
        if trade.get("trade_status") not in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
            raise SaaSError("alipay_trade_unpaid", "支付宝订单尚未支付。", 409)
        try:
            amount_decimal = Decimal(str(trade.get("total_amount", "0"))) * 100
            amount = int(amount_decimal)
            if amount_decimal != amount:
                raise InvalidOperation
        except (TypeError, ValueError, InvalidOperation) as exc:
            raise SaaSError("alipay_invalid_amount", "支付宝订单金额无效。", 409) from exc
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM payment_orders WHERE id=%s AND provider='alipay' FOR UPDATE", (order_id,))
                order = self.accounts._one(cursor)
                test_order = bool(order and self._test_mode() and as_json(order.get("product_snapshot_json")).get("testMode"))
                expected_app_id = self._credentials()["app_id"] or ("local-test" if test_order else "")
                if not order or int(order["amount_cents"]) != amount or str(trade.get("app_id", expected_app_id)) != expected_app_id:
                    raise SaaSError("alipay_order_mismatch", "支付宝付款与拾页订单不匹配。", 409)
                if order["status"] == "paid":
                    return
                if order["status"] != "pending":
                    raise SaaSError("alipay_order_not_payable", "拾页订单已不能支付。", 409)
                user_id = order["user_id"]
                cursor.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (user_id,))
                if not cursor.fetchone():
                    raise SaaSError("alipay_user_missing", "订单账号不存在。", 409)
                change = self.memberships._change_details(cursor, user_id, order["plan_version_id"])
                subscription_id = change["currentSubscriptionId"]
                if change["changeType"] == "upgrade" and subscription_id:
                    cursor.execute("UPDATE subscriptions SET status='expired',updated_at=NOW(),note='支付宝升级后折算结转' WHERE user_id=%s AND status IN ('active','grace_period') AND ends_at>NOW()", (user_id,))
                    subscription_id = None
                if change["changeType"] == "renewal" and subscription_id:
                    cursor.execute("UPDATE subscriptions SET ends_at=%s,updated_at=NOW(),note='支付宝同级续费' WHERE id=%s", (change["endsAt"], subscription_id))
                else:
                    subscription_id = new_id()
                    cursor.execute("INSERT INTO subscriptions(id,user_id,plan_version_id,status,starts_at,ends_at,note) VALUES(%s,%s,%s,'active',%s,%s,'支付宝一次性付款')",
                                   (subscription_id, user_id, order["plan_version_id"], change["startsAt"], change["endsAt"]))
                change_id = new_id()
                cursor.execute("""INSERT INTO membership_change_orders(id,user_id,source,from_plan_version_id,to_plan_version_id,
                    current_subscription_id,created_subscription_id,change_type,status,effective_at,carry_days,carry_seconds,amount_cents,note)
                    VALUES(%s,%s,'alipay',%s,%s,%s,%s,%s,'applied',%s,%s,%s,%s,'支付宝一次性付款')""",
                    (change_id, user_id, change["currentPlanId"], order["plan_version_id"], change["currentSubscriptionId"], subscription_id,
                     change["changeType"], change["effectiveAt"], int(change["carrySeconds"] // 86400), int(change["carrySeconds"]), amount))
                self.memberships._membership_event(cursor, user_id, change_id, change["changeType"] + "_applied", {"source": "alipay", "orderId": order_id, "carrySeconds": int(change["carrySeconds"])}, user_id)
                if change["changeType"] in {"first_purchase", "upgrade"}:
                    cursor.execute("UPDATE users SET plan_version=%s,updated_at=NOW() WHERE id=%s", (order["plan_version_id"], user_id))
                cursor.execute("""UPDATE payment_orders SET status='paid',external_transaction_id=%s,starts_at=%s,ends_at=%s,
                    membership_change_order_id=%s,updated_at=NOW() WHERE id=%s""",
                    (str(trade.get("trade_no", "")) or None, change["startsAt"], change["endsAt"], change_id, order_id))
                cursor.execute("""INSERT INTO admin_audit_logs(id,actor_id,target_user_id,action,payload_json)
                    VALUES(%s,%s,%s,'alipay_payment_completed',%s::jsonb)""",
                    (new_id(), user_id, user_id, json.dumps({"orderId": order_id, "tradeNo": trade.get("trade_no"), "amountCents": amount})))

    def list_orders(self, query: str = "", status: str = "", limit: Any = 20, offset: Any = 0) -> dict[str, Any]:
        size = max(1, min(100, int(limit or 20))); start = max(0, int(offset or 0))
        terms = ["o.provider='alipay'"]; values: list[Any] = []
        if status in {"pending", "paid", "failed", "cancelled", "refunding", "refunded"}:
            terms.append("o.status=%s"); values.append(status)
        if query.strip():
            terms.append("(o.id ILIKE %s OR o.external_transaction_id ILIKE %s OR u.email ILIKE %s OR cpv.display_name ILIKE %s)")
            needle = "%" + query.strip()[:120] + "%"; values.extend([needle] * 4)
        where = "WHERE " + " AND ".join(terms)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) AS total FROM payment_orders o JOIN users u ON u.id=o.user_id LEFT JOIN commerce_product_versions cpv ON cpv.id=o.product_version_id {where}", values)
                total = int(self.accounts._one(cursor)["total"])
                cursor.execute(f"""SELECT o.*,u.email,cpv.display_name FROM payment_orders o JOIN users u ON u.id=o.user_id
                    LEFT JOIN commerce_product_versions cpv ON cpv.id=o.product_version_id {where}
                    ORDER BY o.created_at DESC LIMIT %s OFFSET %s""", (*values, size, start))
                rows = self.accounts._many(cursor)
        return {"orders": [self._admin_order(row) for row in rows], "total": total, "limit": size, "offset": start}

    @staticmethod
    def _admin_order(row: dict[str, Any]) -> dict[str, Any]:
        value = AlipayService._public_order(row)
        value.update({"userId": row["user_id"], "email": row["email"], "productName": row.get("display_name") or as_json(row["product_snapshot_json"]).get("name"),
                      "tradeNo": row.get("external_transaction_id"), "refundAmountCents": int(row.get("refund_amount_cents", 0)),
                      "refundReason": row.get("refund_reason", ""), "refundRequestedAt": timestamp(row.get("refund_requested_at")),
                      "membershipChangeOrderId": row.get("membership_change_order_id")})
        return value

    def refund(self, actor_id: str, order_id: str, reason: str) -> dict[str, Any]:
        note = str(reason or "").strip()[:500]
        if not note:
            raise SaaSError("refund_reason_required", "退款必须填写原因。", 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM payment_orders WHERE id=%s AND provider='alipay' FOR UPDATE", (order_id,))
                order = self.accounts._one(cursor)
                if not order:
                    raise SaaSError("payment_order_not_found", "支付宝订单不存在。", 404)
                if order["status"] == "refunded":
                    return {"id": order_id, "status": "refunded", "idempotent": True}
                if order["status"] == "refunding":
                    return {"id": order_id, "status": "refunding", "idempotent": True, "message": "退款已提交，正在等待支付宝确认。"}
                if order["status"] != "paid" or not order.get("membership_change_order_id"):
                    raise SaaSError("payment_not_refundable", "只有已开通且未退款的支付宝订单可以申请全额退款。", 409)
                cursor.execute("SELECT change_type FROM membership_change_orders WHERE id=%s", (order["membership_change_order_id"],))
                change = self.accounts._one(cursor)
                if not change or change["change_type"] != "first_purchase":
                    raise SaaSError("payment_refund_needs_review", "续费或升级涉及已有权益期限，暂不能自动退款，请先人工核对。", 409)
                cursor.execute("""SELECT EXISTS(SELECT 1 FROM membership_change_orders m
                    WHERE m.user_id=%s AND m.id<>%s
                    AND m.created_at>(SELECT own.created_at FROM membership_change_orders own WHERE own.id=%s)
                    AND m.status IN ('applied','scheduled')) AS later_change""",
                    (order["user_id"], order["membership_change_order_id"], order["membership_change_order_id"]))
                if self.accounts._one(cursor)["later_change"]:
                    raise SaaSError("payment_refund_has_later_changes", "该订单之后已有会员变更，暂不能自动退款。", 409)
                cursor.execute("UPDATE payment_orders SET status='refunding',refund_reason=%s,refund_requested_at=NOW(),updated_at=NOW() WHERE id=%s", (note, order_id))
        try:
            if as_json(order.get("product_snapshot_json")).get("testMode") and self._test_mode():
                result = {"fund_change": "Y", "refund_fee": f"{int(order['amount_cents']) / 100:.2f}", "trade_no": "local-test-refund-" + order_id}
            else:
                result = self._request("alipay.trade.refund", {"out_trade_no": order_id,
                    "refund_amount": f"{int(order['amount_cents']) / 100:.2f}", "refund_reason": note,
                    "out_request_no": "refund_" + hashlib.sha256(order_id.encode()).hexdigest()[:48]})
        except Exception:
            with self.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE payment_orders SET status='paid',updated_at=NOW() WHERE id=%s AND status='refunding'", (order_id,))
            raise
        try:
            settled_cents = int(Decimal(str(result.get("refund_fee", "0"))) * 100)
        except (TypeError, ValueError, InvalidOperation):
            settled_cents = 0
        if result.get("fund_change") != "Y" or settled_cents != int(order["amount_cents"]):
            return {"id": order_id, "status": "refunding", "refundAmountCents": int(order["amount_cents"]),
                    "message": "支付宝已受理退款，资金状态尚未确认；会员权益保持有效。"}
        return self._finalize_refund(actor_id, order, result)

    def sync_refund(self, actor_id: str, order_id: str) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM payment_orders WHERE id=%s AND provider='alipay'", (order_id,))
                order = self.accounts._one(cursor)
        if not order:
            raise SaaSError("payment_order_not_found", "支付宝订单不存在。", 404)
        if order["status"] == "refunded":
            return {"id": order_id, "status": "refunded", "idempotent": True}
        if order["status"] != "refunding":
            raise SaaSError("payment_not_refunding", "该订单没有待确认的支付宝退款。", 409)
        request_no = "refund_" + hashlib.sha256(order_id.encode()).hexdigest()[:48]
        result = self._request("alipay.trade.fastpay.refund.query", {"out_trade_no": order_id, "out_request_no": request_no})
        if not self._refund_confirmed(result, int(order["amount_cents"])):
            return {"id": order_id, "status": "refunding", "message": "支付宝尚未确认全额退款；会员权益保持有效。"}
        return self._finalize_refund(actor_id, order, result)

    @staticmethod
    def _refund_confirmed(result: dict[str, Any], expected_cents: int) -> bool:
        try:
            settled_cents = int(Decimal(str(result.get("refund_amount") or result.get("refund_fee") or "0")) * 100)
        except (TypeError, ValueError, InvalidOperation):
            return False
        return result.get("refund_status") == "REFUND_SUCCESS" and settled_cents == expected_cents

    def _finalize_refund(self, actor_id: str, order: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        order_id = str(order["id"])
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM payment_orders WHERE id=%s FOR UPDATE", (order_id,))
                current = self.accounts._one(cursor)
                if current["status"] == "refunded":
                    return {"id": order_id, "status": "refunded", "idempotent": True}
                if current["status"] != "refunding":
                    raise SaaSError("payment_not_refunding", "支付宝订单退款状态已变化，请刷新后重试。", 409)
                cursor.execute("""UPDATE payment_orders SET status='refunded',refund_amount_cents=amount_cents,refunded_at=NOW(),updated_at=NOW()
                    WHERE id=%s AND status='refunding'""", (order_id,))
                cursor.execute("""UPDATE membership_change_orders SET status='refunded',updated_at=NOW()
                    WHERE id=%s AND status='applied'""", (current["membership_change_order_id"],))
                cursor.execute("SELECT created_subscription_id,user_id FROM membership_change_orders WHERE id=%s", (current["membership_change_order_id"],))
                change = self.accounts._one(cursor)
                if change and change.get("created_subscription_id"):
                    cursor.execute("""UPDATE subscriptions SET status='expired',ends_at=LEAST(ends_at,NOW()),updated_at=NOW(),note='支付宝退款'
                        WHERE id=%s AND user_id=%s AND ends_at>NOW()""", (change["created_subscription_id"], change["user_id"]))
                    cursor.execute("SELECT plan_version_id FROM subscriptions WHERE user_id=%s AND status IN ('active','grace_period') AND starts_at<=NOW() AND ends_at>NOW() ORDER BY ends_at DESC LIMIT 1", (change["user_id"],))
                    active = self.accounts._one(cursor)
                    if active:
                        cursor.execute("UPDATE users SET plan_version=%s,updated_at=NOW() WHERE id=%s", (active["plan_version_id"], change["user_id"]))
                cursor.execute("""INSERT INTO admin_audit_logs(id,actor_id,target_user_id,action,reason,payload_json)
                    VALUES(%s,%s,%s,'alipay_refund_completed',%s,%s::jsonb)""",
                    (new_id(), actor_id, current["user_id"], current.get("refund_reason", ""), json.dumps({"orderId": order_id, "refundAmountCents": int(current["amount_cents"]), "providerRefundId": result.get("trade_no")})))
        return {"id": order_id, "status": "refunded", "refundAmountCents": int(order["amount_cents"]), "idempotent": False}
