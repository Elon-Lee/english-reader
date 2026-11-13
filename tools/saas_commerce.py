#!/usr/bin/env python3
"""Public product catalog and immutable product-version administration."""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

from saas_auth import SaaSError, SaaSService, new_id
from saas_membership import FEATURE_DEFINITIONS, FEATURES, as_json, timestamp


class CommerceService:
    def __init__(self, accounts: SaaSService, payments: Any | None = None):
        self.accounts = accounts
        self.payments = payments

    @staticmethod
    def _prices(payload: dict[str, Any]) -> tuple[int, int, int]:
        def cents(value: Any) -> int:
            if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
                raise SaaSError("invalid_product_price", "价格必须为非负整数分，最多支持两位小数元。")
            amount = int(value)
            if amount > 2147483647:
                raise SaaSError("invalid_product_price", "价格超出允许范围。")
            return amount

        original = cents(payload.get("originalAmountCents", payload.get("amountCents")))
        if "amountCents" in payload:
            sale = cents(payload["amountCents"])
        else:
            # Compatibility for older draft-version clients only.
            discount = cents(payload.get("discountPercent", 100))
            if not 1 <= discount <= 100:
                raise SaaSError("invalid_product_price", "折扣超出允许范围。")
            sale = (original * discount + 50) // 100
        if sale > original:
            raise SaaSError("invalid_product_price", "实际售价不能高于原价。")
        discount = (sale * 200 + original) // (2 * original) if original else 100
        return original, sale, discount

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
                self._audit(cursor,actor_id,"plan_version_created",{"versionId":version_id,"planSlug":plan_slug})
                return {"id":version_id,"planSlug":plan_slug,"name":display_name,"rank":rank_value,"periodDays":days,"quotas":normalized,"pricing":pricing}

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

    @staticmethod
    def _included_benefits(value: Any) -> list[str]:
        quotas = as_json(value)
        context = int(quotas.get("ai_context_generations", 0) or 0)
        grammar = int(quotas.get("ai_grammar_generations", 0) or 0)
        devices = int(quotas.get("devices", 1) or 1)
        return [
            "免费包含：公版及授权学习材料不限次使用",
            "免费包含：公版书架收藏不限量",
            f"免费包含：词汇语境分析 {context} 次/30天",
            f"免费包含：句法分析 {grammar} 次/30天",
            "免费包含：音频、视频及在线视频导入，不按导入次数收费",
            f"免费包含：最多同时登录 {devices} 台设备",
        ]

    @classmethod
    def _version(cls, row: dict[str, Any], include_internal: bool = False) -> dict[str, Any]:
        benefits = cls._benefits(row["benefits_json"])
        if row["family_slug"] == "free":
            benefits = [
                "免费包含：词汇语境分析每天最多 50 次" if "词汇语境分析" in item else
                "免费包含：句法分析每天最多 20 次" if "句法分析" in item else item
                for item in benefits
            ]
        else:
            benefits = [
                "免费包含：词汇语境分析不限次数" if "词汇语境分析" in item else
                "免费包含：句法分析不限次数" if "句法分析" in item else item
                for item in benefits
            ]
        quality_benefit = "视频可观看流畅版；高清需付费会员" if row["family_slug"] == "free" else "视频可在流畅与高清之间切换"
        benefits = [quality_benefit] + [item for item in benefits if item != quality_benefit]
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
            "durationDays": 0 if row["family_slug"] == "free" else int(row["duration_days"]),
            "amountCents": int(row["amount_cents"]),
            "currency": row["currency"],
            "originalAmountCents": int(row.get("original_amount_cents", row["amount_cents"]) or 0),
            "discountPercent": int(row.get("discount_percent", 100)),
            "benefits": benefits,
            "videoQuality": "low" if row["family_slug"] == "free" else "high",
            "featureLimits": cls._display_limits(row.get("limits_json")),
            "purchaseUrl": str(row.get("purchase_url", "") or ""),
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
        payment = self.payments.public_config() if self.payments else {"methods": ["cloudcat"], "redemptionEnabled": True, "automaticRenewal": False}
        for product in products:
            product["paymentMethods"] = [method for method in payment["methods"] if method != "cloudcat" or bool(product.get("purchaseUrl"))]
            product["redemptionEnabled"] = payment["redemptionEnabled"]
        return {
            "products": products,
            "support": {"type": "QQ", "value": "289614546", "response": "1 个工作日内响应"},
            "payment": {**payment, "configured": bool(payment["methods"]),
                "notice": "支付宝付款成功后由 RynEnglish 确认开通；云猫购买后使用兑换码开通。均为单次购买，不自动续费。"},
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
                    """SELECT cp.id AS commerce_product_id,cp.slug,cp.family_slug,cp.display_order,cp.active AS product_active,cpv.*,pv.quotas_json AS limits_json
                    FROM commerce_products cp LEFT JOIN commerce_product_versions cpv ON cpv.product_id=cp.id
                    LEFT JOIN plan_versions pv ON pv.id=cpv.plan_version_id
                    ORDER BY cp.display_order,cpv.version_number DESC"""
                )
                rows = self.accounts._many(cursor)
        products: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = products.setdefault(
                row["commerce_product_id"],
                {"id": row["commerce_product_id"], "slug": row["slug"], "family": row["family_slug"], "displayOrder": int(row["display_order"]), "active": bool(row["product_active"]), "versions": []},
            )
            if row.get("id"):
                item["versions"].append(self._version(row, True))
        return {"products": list(products.values())}

    def entitlement_catalog(self) -> dict[str, Any]:
        built_in = []
        for key in FEATURES:
            definition = FEATURE_DEFINITIONS[key]
            if not definition.get("sellable", True):
                continue
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
            if not definition.get("sellable", True):
                amount = int(definition.get("default", 0))
            else:
                raw = incoming_limits.get(feature, 0)
                try:
                    amount = int(raw)
                except (TypeError, ValueError) as exc:
                    raise SaaSError("invalid_product_version", f"{definition['name']} 的限制无效。") from exc
                minimum = int(definition["minimum"])
                if amount < minimum or amount > 10**12:
                    raise SaaSError("invalid_product_version", f"{definition['name']} 的限制超出允许范围。")
            normalized[feature] = amount * (1024**3) if definition.get("storage") else amount
        if sum(1 for key in ("video_library_capacity", "audio_library_capacity", "storage_bytes") if normalized[key] > 0) < 3:
            raise SaaSError("invalid_product_version", "请配置视频上限、音频上限和私人空间。")
        try:
            duration_days = int(payload.get("durationDays"))
        except (TypeError, ValueError) as exc:
            raise SaaSError("invalid_product_version", "商品期限或价格无效。") from exc
        if duration_days < 1 or duration_days > 3660:
            raise SaaSError("invalid_product_version", "商品期限或价格超出允许范围。")
        original_amount_cents, amount_cents, discount_percent = self._prices(payload)
        featured = bool(payload.get("featured", False))
        purchase_url = str(payload.get("purchaseUrl", "") or "").strip()
        if len(purchase_url) > 1000:
            raise SaaSError("invalid_product_version", "云猫商品链接过长。")
        if purchase_url:
            parsed_url = urlsplit(purchase_url)
            if parsed_url.scheme != "https" or parsed_url.hostname not in {"catfk.com", "www.catfk.com"}:
                raise SaaSError("invalid_product_version", "云猫商品链接必须使用 catfk.com 的 HTTPS 地址。")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,slug,family_slug FROM commerce_products WHERE id=%s FOR UPDATE", (product_id,))
                product = self.accounts._one(cursor)
                if not product:
                    raise SaaSError("product_not_found", "商品不存在。", 404)
                if product["family_slug"] == "free":
                    normalized["ai_context_generations"] = 50
                    normalized["ai_grammar_generations"] = 20
                    normalized["devices"] = 1
                else:
                    normalized["ai_context_generations"] = 300
                    normalized["ai_grammar_generations"] = 100
                    normalized["devices"] = 2
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
                pricing = {"currency": "CNY", "amount_cents": amount_cents, "original_amount_cents": original_amount_cents, "discount_percent": discount_percent, "duration_days": duration_days, "commerce_product_version": version_id}
                cursor.execute("""INSERT INTO plan_versions(id,plan_id,display_name,rank,period_days,quotas_json,pricing_json,active)
                VALUES(%s,%s,%s,%s,30,%s::jsonb,%s::jsonb,FALSE)""", (plan_version, plan["id"], name, rank, json.dumps(normalized), json.dumps(pricing)))
                benefits = [self._benefit_text(feature, normalized[feature]) for feature in FEATURES if FEATURE_DEFINITIONS[feature].get("sellable", True) and normalized[feature] > 0] + self._included_benefits(normalized) + [item["text"] for item in configured]
                benefits = benefits[:12]
                cursor.execute(
                    """INSERT INTO commerce_product_versions(
                    id,product_id,version_number,plan_version_id,display_name,short_name,tagline,description,
                    duration_days,amount_cents,original_amount_cents,discount_percent,currency,benefits_json,configured_benefits_json,featured,created_by,purchase_url)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'CNY',%s::jsonb,%s::jsonb,%s,%s,%s)""",
                    (version_id, product_id, version_number, plan_version, name, short_name, tagline, description, duration_days, amount_cents, original_amount_cents, discount_percent, json.dumps(benefits), json.dumps(configured), featured, actor_id, purchase_url),
                )
                self._audit(cursor, actor_id, "commerce_product_version_created", {"productId": product_id, "versionId": version_id, "version": version_number})
        return {"id": version_id, "productId": product_id, "version": version_number, "status": "draft"}

    def update_price(self, actor_id: str, product_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Atomically publish a price-only copy; existing sale snapshots stay intact."""
        if "originalAmountCents" not in payload or "amountCents" not in payload:
            raise SaaSError("invalid_product_price", "请同时填写原价和实际售价。")
        original, sale, discount = self._prices(payload)
        expected = str(payload.get("expectedVersionId", "") or "").strip()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM commerce_products WHERE id=%s FOR UPDATE", (product_id,))
                product = self.accounts._one(cursor)
                if not product:
                    raise SaaSError("product_not_found", "商品不存在。", 404)
                cursor.execute("SELECT * FROM commerce_product_versions WHERE product_id=%s AND status='published' FOR UPDATE", (product_id,))
                version = self.accounts._one(cursor)
                if not version or not expected or version["id"] != expected:
                    raise SaaSError("product_version_changed", "当前套餐版本已变化，请刷新后重新调整价格。", 409)
                if (product["family_slug"] == "free" and (original or sale)) or (product["family_slug"] != "free" and sale == 0):
                    raise SaaSError("invalid_product_price", "免费版价格须为0，付费套餐售价须大于0。")
                if (version["original_amount_cents"], version["amount_cents"]) == (original, sale):
                    return {"id": version["id"], "status": "published", "idempotent": True}
                cursor.execute("SELECT COALESCE(MAX(version_number),0)+1 AS n FROM commerce_product_versions WHERE product_id=%s", (product_id,))
                number = int(self.accounts._one(cursor)["n"])
                version_id = f"{product['slug']}-v{number}"
                plan_id = "commerce-" + version_id
                pricing = {"amount_cents": sale, "original_amount_cents": original, "discount_percent": discount, "commerce_product_version": version_id}
                cursor.execute("""INSERT INTO plan_versions(id,plan_id,display_name,rank,period_days,quotas_json,pricing_json,active)
                    SELECT %s,plan_id,display_name,rank,period_days,quotas_json,pricing_json || %s::jsonb,TRUE
                    FROM plan_versions WHERE id=%s""", (plan_id, json.dumps(pricing), version["plan_version_id"]))
                cursor.execute("UPDATE commerce_product_versions SET status='retired',retired_at=NOW() WHERE id=%s", (version["id"],))
                cursor.execute("""INSERT INTO commerce_product_versions(
                    id,product_id,version_number,plan_version_id,display_name,short_name,tagline,description,duration_days,
                    amount_cents,original_amount_cents,discount_percent,currency,benefits_json,configured_benefits_json,
                    featured,status,created_by,purchase_url,published_at)
                    SELECT %s,product_id,%s,%s,display_name,short_name,tagline,description,duration_days,
                    %s,%s,%s,currency,benefits_json,configured_benefits_json,featured,'published',%s,purchase_url,NOW()
                    FROM commerce_product_versions WHERE id=%s""", (version_id, number, plan_id, sale, original, discount, actor_id, version["id"]))
                self._audit(cursor, actor_id, "commerce_product_price_updated", {"productId": product_id, "previousVersionId": version["id"], "versionId": version_id, "originalAmountCents": original, "amountCents": sale})
        return {"id": version_id, "status": "published", "idempotent": False}

    def publish_version(self, actor_id: str, version_id: str) -> dict[str, Any]:
        version_id = str(version_id or "").strip()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT product_id FROM commerce_product_versions WHERE id=%s", (version_id,))
                target = self.accounts._one(cursor)
                if not target:
                    raise SaaSError("product_version_not_found", "商品版本不存在。", 404)
                cursor.execute("SELECT id FROM commerce_products WHERE id=%s FOR UPDATE", (target["product_id"],))
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

    def update_draft_purchase_url(self, actor_id: str, version_id: str, purchase_url: Any) -> dict[str, Any]:
        value = str(purchase_url or "").strip()
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.hostname not in {"catfk.com", "www.catfk.com"}:
            raise SaaSError("invalid_purchase_link", "请输入 HTTPS 云猫商品链接。", 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,status FROM commerce_product_versions WHERE id=%s FOR UPDATE", (str(version_id or "").strip(),))
                version = self.accounts._one(cursor)
                if not version:
                    raise SaaSError("product_version_not_found", "商品版本不存在。", 404)
                if version["status"] not in {"draft", "published"}:
                    raise SaaSError("immutable_product_version", "历史版本不可修改。", 409)
                if version["status"] == "published":
                    cursor.execute("SELECT purchase_url FROM commerce_product_versions WHERE id=%s", (version["id"],))
                    current = self.accounts._one(cursor)
                    if str((current or {}).get("purchase_url", "") or "").strip():
                        raise SaaSError("immutable_product_version", "已配置购买链接的版本不可修改。请创建新版本。", 409)
                cursor.execute("UPDATE commerce_product_versions SET purchase_url=%s WHERE id=%s", (value, version["id"]))
                self._audit(cursor, actor_id, "commerce_purchase_link_updated", {"versionId": version["id"], "host": parsed.hostname})
                return {"id": version["id"], "purchaseUrl": value, "status": "draft"}

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

    def delete_unlisted_product(self, actor_id: str, product_id: str) -> dict[str, Any]:
        product_id=str(product_id or "").strip()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,slug,family_slug FROM commerce_products WHERE id=%s FOR UPDATE",(product_id,))
                product=self.accounts._one(cursor)
                if not product:raise SaaSError("product_not_found","套餐不存在。",404)
                if product["family_slug"]=="free":raise SaaSError("product_not_deletable","免费套餐不能删除。",409)
                cursor.execute("SELECT id,plan_version_id,status FROM commerce_product_versions WHERE product_id=%s FOR UPDATE",(product_id,))
                versions=self.accounts._many(cursor)
                if any(row["status"]!="draft" for row in versions):
                    raise SaaSError("product_not_unlisted","只有全部版本均为草稿的未上架套餐可以删除。",409)
                version_ids=[row["id"] for row in versions];plan_ids=[row["plan_version_id"] for row in versions]
                cursor.execute("""SELECT EXISTS(SELECT 1 FROM payment_orders WHERE product_version_id=ANY(%s)) AS has_orders,
                    EXISTS(SELECT 1 FROM commerce_redemption_codes WHERE product_version_id=ANY(%s)) AS has_codes,
                    EXISTS(SELECT 1 FROM commerce_redemption_batches WHERE product_version_id=ANY(%s)) AS has_batches,
                    EXISTS(SELECT 1 FROM subscriptions WHERE plan_version_id=ANY(%s)) AS has_subscriptions,
                    EXISTS(SELECT 1 FROM manual_orders WHERE plan_version_id=ANY(%s)) AS has_manual_orders,
                    EXISTS(SELECT 1 FROM usage_periods WHERE plan_version_id=ANY(%s)) AS has_usage,
                    EXISTS(SELECT 1 FROM membership_change_requests WHERE current_plan_version_id=ANY(%s) OR requested_plan_version_id=ANY(%s)) AS has_change_requests,
                    EXISTS(SELECT 1 FROM membership_change_orders WHERE from_plan_version_id=ANY(%s) OR to_plan_version_id=ANY(%s)) AS has_change_orders,
                    EXISTS(SELECT 1 FROM external_subscriptions WHERE plan_version_id=ANY(%s)) AS has_external_subscriptions""",(version_ids,version_ids,version_ids,plan_ids,plan_ids,plan_ids,plan_ids,plan_ids,plan_ids,plan_ids,plan_ids))
                refs=self.accounts._one(cursor) or {}
                if any(refs.values()):raise SaaSError("product_in_use","套餐已有订单、兑换码或订阅记录，不能删除。",409)
                cursor.execute("DELETE FROM commerce_product_versions WHERE product_id=%s",(product_id,))
                cursor.execute("DELETE FROM plan_versions WHERE id=ANY(%s)",(plan_ids,))
                cursor.execute("DELETE FROM commerce_products WHERE id=%s",(product_id,))
                self._audit(cursor,actor_id,"commerce_unlisted_product_deleted",{"productId":product_id,"slug":product["slug"],"versionIds":version_ids})
                return {"id":product_id,"slug":product["slug"],"deleted":True}

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
