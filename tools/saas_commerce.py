#!/usr/bin/env python3
"""Public product catalog and immutable product-version administration."""
from __future__ import annotations

import json
import re
from typing import Any

from saas_auth import SaaSError, SaaSService, new_id
from saas_membership import FEATURE_DEFINITIONS, FEATURES, as_json, timestamp


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

    @staticmethod
    def _configured_benefits(value: Any) -> list[dict[str, str]]:
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
        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "") or "").strip()[:80]
            text = str(item.get("text", "") or name).strip()[:160]
            if name and text:
                result.append({"id": str(item.get("id", "") or ""), "name": name, "text": text})
        return result[:12]

    @staticmethod
    def _display_limits(value: Any) -> dict[str, int]:
        quotas = as_json(value)
        result: dict[str, int] = {}
        for key in FEATURES:
            amount = int(quotas.get(key, 0) or 0)
            result[key] = amount // (1024**3) if FEATURE_DEFINITIONS[key].get("storage") else amount
        return result

    @staticmethod
    def _benefit_text(feature: str, stored_value: int) -> str:
        definition = FEATURE_DEFINITIONS[feature]
        shown = stored_value // (1024**3) if definition.get("storage") else stored_value
        return f"{definition['name']} {shown} {definition['unit']}"

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
            "featureLimits": cls._display_limits(row.get("limits_json")),
            "configuredBenefits": cls._configured_benefits(row.get("configured_benefits_json")),
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
                    """SELECT cp.slug,cp.family_slug,cp.display_order,cp.active AS product_active,cpv.*,pv.quotas_json AS limits_json
                    FROM commerce_products cp JOIN commerce_product_versions cpv ON cpv.product_id=cp.id
                    JOIN plan_versions pv ON pv.id=cpv.plan_version_id
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
                    """SELECT cp.slug,cp.family_slug,cp.display_order,cp.active AS product_active,cpv.*,pv.quotas_json AS limits_json
                    FROM commerce_products cp LEFT JOIN commerce_product_versions cpv ON cpv.product_id=cp.id
                    LEFT JOIN plan_versions pv ON pv.id=cpv.plan_version_id
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

    def entitlement_catalog(self) -> dict[str, Any]:
        built_in = []
        for key in FEATURES:
            definition = FEATURE_DEFINITIONS[key]
            built_in.append({"key": key, "type": "built_in", "name": definition["name"], "unit": definition["unit"], "defaultLimit": int(definition["default"]), "minimum": int(definition["minimum"]), "required": bool(definition.get("required")), "control": definition["control"], "enforced": True})
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM commerce_configured_benefits ORDER BY active DESC,created_at,display_name")
                configured = [{"id": row["id"], "code": row["code"], "type": "configured", "name": row["display_name"], "description": row["description"], "defaultText": row["default_text"], "active": bool(row["active"]), "createdAt": timestamp(row["created_at"])} for row in self.accounts._many(cursor)]
        return {"builtIn": built_in, "configured": configured}

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
                cursor.execute("SELECT id FROM plans WHERE slug=%s AND active=TRUE", (family,))
                if not cursor.fetchone():
                    raise SaaSError("unknown_plan", "商品系列必须对应现有会员等级。", 400)
                cursor.execute("INSERT INTO commerce_products(id,slug,family_slug,display_order) VALUES(%s,%s,%s,%s)", (product_id, slug, family, order))
                self._audit(cursor, actor_id, "commerce_product_created", {"productId": product_id, "slug": slug})
        return {"id": product_id, "slug": slug, "family": family, "displayOrder": order, "active": True, "versions": []}

    def create_version(self, actor_id: str, product_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        product_id = str(product_id or "").strip()
        name = str(payload.get("name", "") or "").strip()[:80]
        short_name = str(payload.get("shortName", "") or name).strip()[:40]
        tagline = str(payload.get("tagline", "") or "").strip()[:160]
        description = str(payload.get("description", "") or "").strip()[:1000]
        incoming_limits = payload.get("featureLimits")
        configured_ids = [str(item).strip() for item in (payload.get("configuredBenefitIds") or []) if str(item).strip()]
        if not name or not short_name or not tagline or not description:
            raise SaaSError("invalid_product_version", "名称、短名称、卖点和商品说明均不能为空。")
        if not isinstance(incoming_limits, dict):
            raise SaaSError("invalid_product_version", "请勾选真实产品功能并配置使用限制。")
        unknown = sorted(set(incoming_limits) - set(FEATURES))
        if unknown:
            raise SaaSError("invalid_product_version", "包含未知的内置权益：" + ", ".join(unknown))
        normalized: dict[str, int] = {}
        for feature in FEATURES:
            definition = FEATURE_DEFINITIONS[feature]
            raw = incoming_limits.get(feature, 0)
            try:
                amount = int(raw)
            except (TypeError, ValueError) as exc:
                raise SaaSError("invalid_product_version", f"{definition['name']} 的限制无效。") from exc
            minimum = int(definition["minimum"])
            if amount < minimum or amount > 10**12:
                raise SaaSError("invalid_product_version", f"{definition['name']} 的限制超出允许范围。")
            normalized[feature] = amount * (1024**3) if definition.get("storage") else amount
        if normalized["devices"] < 1:
            raise SaaSError("invalid_product_version", "登录设备是必选的内置权益，限制不能低于 1。")
        if sum(1 for value in normalized.values() if value > 0) < 3:
            raise SaaSError("invalid_product_version", "至少启用 3 项真实受控功能。")
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
                cursor.execute("SELECT id,slug,family_slug FROM commerce_products WHERE id=%s FOR UPDATE", (product_id,))
                product = self.accounts._one(cursor)
                if not product:
                    raise SaaSError("product_not_found", "商品不存在。", 404)
                cursor.execute("SELECT id FROM plans WHERE slug=%s AND active=TRUE FOR UPDATE", (product["family_slug"],))
                plan = self.accounts._one(cursor)
                if not plan:
                    raise SaaSError("unknown_plan", "商品系列对应的会员等级不存在。", 400)
                configured: list[dict[str, str]] = []
                if configured_ids:
                    cursor.execute("SELECT id,display_name,default_text FROM commerce_configured_benefits WHERE id=ANY(%s) AND active=TRUE ORDER BY created_at", (configured_ids,))
                    configured = [{"id": row["id"], "name": row["display_name"], "text": row["default_text"]} for row in self.accounts._many(cursor)]
                    if len(configured) != len(set(configured_ids)):
                        raise SaaSError("invalid_product_version", "包含不存在或已停用的配置权益。")
                cursor.execute("SELECT COALESCE(MAX(version_number),0)+1 AS next_version FROM commerce_product_versions WHERE product_id=%s", (product_id,))
                version_number = int((self.accounts._one(cursor) or {"next_version": 1})["next_version"])
                version_id = f"{product['slug']}-v{version_number}"
                plan_version = f"commerce-{product['slug']}-v{version_number}"
                cursor.execute("SELECT COALESCE(MAX(rank),0) AS rank FROM plan_versions WHERE plan_id=%s", (plan["id"],))
                rank = max(1, int((self.accounts._one(cursor) or {"rank": 1})["rank"]))
                pricing = {"currency": "CNY", "amount_cents": amount_cents, "duration_days": duration_days, "commerce_product_version": version_id}
                cursor.execute("""INSERT INTO plan_versions(id,plan_id,display_name,rank,period_days,quotas_json,pricing_json,active)
                VALUES(%s,%s,%s,%s,30,%s::jsonb,%s::jsonb,FALSE)""", (plan_version, plan["id"], name, rank, json.dumps(normalized), json.dumps(pricing)))
                benefits = [self._benefit_text(feature, normalized[feature]) for feature in FEATURES if normalized[feature] > 0] + [item["text"] for item in configured]
                cursor.execute(
                    """INSERT INTO commerce_product_versions(
                    id,product_id,version_number,plan_version_id,display_name,short_name,tagline,description,
                    duration_days,amount_cents,currency,benefits_json,configured_benefits_json,featured,created_by)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'CNY',%s::jsonb,%s::jsonb,%s,%s)""",
                    (version_id, product_id, version_number, plan_version, name, short_name, tagline, description, duration_days, amount_cents, json.dumps(benefits), json.dumps(configured), featured, actor_id),
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
                cursor.execute("UPDATE plan_versions SET active=TRUE WHERE id=%s", (version["plan_version_id"],))
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

    def create_configured_benefit(self, actor_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        code = str(payload.get("code", "") or "").strip().lower()
        name = str(payload.get("name", "") or "").strip()[:80]
        description = str(payload.get("description", "") or "").strip()[:500]
        default_text = str(payload.get("defaultText", "") or name).strip()[:160]
        if not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", code) or not name or not default_text:
            raise SaaSError("invalid_configured_benefit", "配置权益的标识、名称或展示文案无效。")
        benefit_id = "benefit-" + new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO commerce_configured_benefits(id,code,display_name,description,default_text,created_by) VALUES(%s,%s,%s,%s,%s,%s)", (benefit_id, code, name, description, default_text, actor_id))
                self._audit(cursor, actor_id, "commerce_configured_benefit_created", {"benefitId": benefit_id, "code": code})
        return {"id": benefit_id, "code": code, "name": name, "description": description, "defaultText": default_text, "active": True}

    def update_configured_benefit(self, actor_id: str, benefit_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        benefit_id = str(benefit_id or "").strip()
        name = str(payload.get("name", "") or "").strip()[:80]
        description = str(payload.get("description", "") or "").strip()[:500]
        default_text = str(payload.get("defaultText", "") or name).strip()[:160]
        active = bool(payload.get("active", True))
        if not name or not default_text:
            raise SaaSError("invalid_configured_benefit", "配置权益名称和展示文案不能为空。")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE commerce_configured_benefits SET display_name=%s,description=%s,default_text=%s,active=%s,updated_at=NOW() WHERE id=%s RETURNING code", (name, description, default_text, active, benefit_id))
                row = self.accounts._one(cursor)
                if not row:
                    raise SaaSError("configured_benefit_not_found", "配置权益不存在。", 404)
                self._audit(cursor, actor_id, "commerce_configured_benefit_updated", {"benefitId": benefit_id, "active": active})
        return {"id": benefit_id, "code": row["code"], "name": name, "description": description, "defaultText": default_text, "active": active}

