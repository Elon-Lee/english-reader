#!/usr/bin/env python3
"""Public product catalog and immutable product-version administration."""
from __future__ import annotations

import json
import re
from typing import Any

from saas_auth import SaaSError, SaaSService, new_id
from saas_membership import as_json, timestamp


class CommerceService:
    def __init__(self, accounts: SaaSService):
        self.accounts = accounts

    @staticmethod
    def _benefits(value: Any) -> list[str]:
        if isinstance(value, list):
            items = value
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
                items = parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                items = []
        else:
            items = []
        return [str(item).strip()[:160] for item in items if str(item).strip()][:12]

    @classmethod
    def _version(cls, row: dict[str, Any], include_internal: bool = False) -> dict[str, Any]:
        result = {
            "id": row["id"],
            "productId": row["product_id"],
            "slug": row["slug"],
            "family": row["family_slug"],
            "version": int(row["version_number"]),
            "planVersion": row["plan_version_id"],
            "name": row["display_name"],
            "shortName": row["short_name"],
            "tagline": row["tagline"],
            "description": row["description"],
            "durationDays": int(row["duration_days"]),
            "amountCents": int(row["amount_cents"]),
            "currency": row["currency"],
            "benefits": cls._benefits(row["benefits_json"]),
            "featured": bool(row["featured"]),
            "status": row["status"],
            "active": bool(row["product_active"]),
            "displayOrder": int(row["display_order"]),
            "publishedAt": timestamp(row.get("published_at")),
        }
        if include_internal:
            result.update({"createdAt": timestamp(row.get("created_at")), "retiredAt": timestamp(row.get("retired_at"))})
        return result

    def public_catalog(self) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT cp.slug,cp.family_slug,cp.display_order,cp.active AS product_active,cpv.*
                    FROM commerce_products cp JOIN commerce_product_versions cpv ON cpv.product_id=cp.id
                    WHERE cp.active=TRUE AND cpv.status='published'
                    ORDER BY cp.display_order,cpv.amount_cents"""
                )
                products = [self._version(row) for row in self.accounts._many(cursor)]
        app_id = str(self.accounts.environment.get("MBDPAY_APP_ID", "")).strip()
        app_key = str(self.accounts.environment.get("MBDPAY_APP_KEY", "")).strip()
        base_url = str(self.accounts.environment.get("APP_BASE_URL", "")).strip()
        return {
            "products": products,
            "support": {"type": "QQ", "value": "289614546", "response": "1 个工作日内响应"},
            "payment": {
                "configured": bool(app_id and app_key and base_url.startswith(("http://", "https://"))),
                "methods": ["alipay"],
                "automaticRenewal": False,
                "notice": "单次购买固定期限权益，不自动续费。",
            },
        }

    def product(self, slug: str) -> dict[str, Any]:
        target = str(slug or "").strip()
        catalog = self.public_catalog()
        product = next((item for item in catalog["products"] if item["slug"] == target), None)
        if not product:
            raise SaaSError("product_not_found", "商品不存在或已停止销售。", 404)
        return {"product": product, "support": catalog["support"], "payment": catalog["payment"]}

    def admin_catalog(self) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT cp.slug,cp.family_slug,cp.display_order,cp.active AS product_active,cpv.*
                    FROM commerce_products cp LEFT JOIN commerce_product_versions cpv ON cpv.product_id=cp.id
                    ORDER BY cp.display_order,cpv.version_number DESC"""
                )
                rows = self.accounts._many(cursor)
        products: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = products.setdefault(
                row["product_id"],
                {"id": row["product_id"], "slug": row["slug"], "family": row["family_slug"], "displayOrder": int(row["display_order"]), "active": bool(row["product_active"]), "versions": []},
            )
            if row.get("id"):
                item["versions"].append(self._version(row, True))
        return {"products": list(products.values())}

    def _audit(self, cursor: Any, actor_id: str, action: str, payload: dict[str, Any]) -> None:
        cursor.execute(
            """INSERT INTO admin_audit_logs(id,actor_id,action,reason,payload_json)
            VALUES(%s,%s,%s,'商品版本管理',%s::jsonb)""",
            (new_id(), actor_id, action, json.dumps(payload)),
        )

    def create_product(self, actor_id: str, slug: str, family: str, display_order: Any = 100) -> dict[str, Any]:
        slug = str(slug or "").strip().lower()
        family = str(family or "").strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", slug):
            raise SaaSError("invalid_product", "商品标识只能使用小写字母、数字和连字符。")
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,31}", family):
            raise SaaSError("invalid_product", "商品系列标识无效。")
        try:
            order = int(display_order)
        except (TypeError, ValueError) as exc:
            raise SaaSError("invalid_product", "商品排序无效。") from exc
        product_id = "product-" + new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO commerce_products(id,slug,family_slug,display_order) VALUES(%s,%s,%s,%s)", (product_id, slug, family, order))
                self._audit(cursor, actor_id, "commerce_product_created", {"productId": product_id, "slug": slug})
        return {"id": product_id, "slug": slug, "family": family, "displayOrder": order, "active": True, "versions": []}

    def create_version(self, actor_id: str, product_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        product_id = str(product_id or "").strip()
        name = str(payload.get("name", "") or "").strip()[:80]
        short_name = str(payload.get("shortName", "") or name).strip()[:40]
        tagline = str(payload.get("tagline", "") or "").strip()[:160]
        description = str(payload.get("description", "") or "").strip()[:1000]
        plan_version = str(payload.get("planVersion", "") or "").strip()
        benefits = self._benefits(payload.get("benefits", []))
        if not name or not short_name or not tagline or not description:
            raise SaaSError("invalid_product_version", "名称、短名称、卖点和商品说明均不能为空。")
        if len(benefits) < 3:
            raise SaaSError("invalid_product_version", "至少填写 3 项明确权益。")
        try:
            duration_days = int(payload.get("durationDays"))
            amount_cents = int(payload.get("amountCents"))
        except (TypeError, ValueError) as exc:
            raise SaaSError("invalid_product_version", "商品期限或价格无效。") from exc
        if duration_days < 1 or duration_days > 3660 or amount_cents < 0:
            raise SaaSError("invalid_product_version", "商品期限或价格超出允许范围。")
        featured = bool(payload.get("featured", False))
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,slug FROM commerce_products WHERE id=%s FOR UPDATE", (product_id,))
                product = self.accounts._one(cursor)
                if not product:
                    raise SaaSError("product_not_found", "商品不存在。", 404)
                cursor.execute("SELECT id FROM plan_versions WHERE id=%s AND active=TRUE", (plan_version,))
                if not cursor.fetchone():
                    raise SaaSError("unknown_plan", "对应会员权益版本不存在或已停用。")
                cursor.execute("SELECT COALESCE(MAX(version_number),0)+1 AS next_version FROM commerce_product_versions WHERE product_id=%s", (product_id,))
                version_number = int((self.accounts._one(cursor) or {"next_version": 1})["next_version"])
                version_id = f"{product['slug']}-v{version_number}"
                cursor.execute(
                    """INSERT INTO commerce_product_versions(
                    id,product_id,version_number,plan_version_id,display_name,short_name,tagline,description,
                    duration_days,amount_cents,currency,benefits_json,featured,created_by)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'CNY',%s::jsonb,%s,%s)""",
                    (version_id, product_id, version_number, plan_version, name, short_name, tagline, description, duration_days, amount_cents, json.dumps(benefits), featured, actor_id),
                )
                self._audit(cursor, actor_id, "commerce_product_version_created", {"productId": product_id, "versionId": version_id, "version": version_number})
        return {"id": version_id, "productId": product_id, "version": version_number, "status": "draft"}

    def publish_version(self, actor_id: str, version_id: str) -> dict[str, Any]:
        version_id = str(version_id or "").strip()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM commerce_product_versions WHERE id=%s FOR UPDATE", (version_id,))
                version = self.accounts._one(cursor)
                if not version:
                    raise SaaSError("product_version_not_found", "商品版本不存在。", 404)
                if version["status"] == "published":
                    return {"id": version_id, "status": "published", "idempotent": True}
                if version["status"] != "draft":
                    raise SaaSError("invalid_product_version", "只有草稿版本可以发布。", 409)
                cursor.execute(
                    """UPDATE commerce_product_versions SET status='retired',retired_at=NOW()
                    WHERE product_id=%s AND status='published'""",
                    (version["product_id"],),
                )
                cursor.execute("UPDATE commerce_product_versions SET status='published',published_at=NOW() WHERE id=%s", (version_id,))
                self._audit(cursor, actor_id, "commerce_product_version_published", {"productId": version["product_id"], "versionId": version_id})
        return {"id": version_id, "status": "published", "idempotent": False}

    def set_product_active(self, actor_id: str, product_id: str, active: bool) -> dict[str, Any]:
        product_id = str(product_id or "").strip()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE commerce_products SET active=%s,updated_at=NOW() WHERE id=%s RETURNING slug", (bool(active), product_id))
                row = self.accounts._one(cursor)
                if not row:
                    raise SaaSError("product_not_found", "商品不存在。", 404)
                self._audit(cursor, actor_id, "commerce_product_status_updated", {"productId": product_id, "active": bool(active)})
        return {"id": product_id, "slug": row["slug"], "active": bool(active)}

