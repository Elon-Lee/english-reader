#!/usr/bin/env python3
"""PostgreSQL acceptance tests for immutable public commerce products."""
from __future__ import annotations

import os
import unittest
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from saas_auth import SaaSError, SaaSService, new_id, token_hash, utcnow
from saas_commerce import CommerceService
from saas_mbdpay import MbdPayService
from saas_membership import MembershipService


TEST_URL = os.environ.get("SHIYUE_SAAS_TEST_DATABASE_URL", "")


class CommercePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not urlsplit(TEST_URL).path.rsplit("/", 1)[-1].endswith("_test"):
            raise RuntimeError("SHIYUE_SAAS_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用数据库。")
        cls.environment = {
            "DATABASE_URL": TEST_URL,
            "SHIYUE_SAAS_ENABLED": "1",
            "SESSION_SECRET": "test-only-session-secret-that-is-at-least-32-characters",
            "BOOTSTRAP_ADMIN_EMAIL": "commerce-admin@local.test",
            "BOOTSTRAP_ADMIN_PASSWORD": "commerce admin password",
            "APP_BASE_URL": "https://example.test",
            "MBDPAY_APP_ID": "test-app-id",
            "MBDPAY_APP_KEY": "test-app-key",
        }
        cls.accounts = SaaSService(TEST_URL, cls.environment)
        cls.accounts.migrate()
        cls.commerce = CommerceService(cls.accounts)
        cls.memberships = MembershipService(cls.accounts)
        cls.mbdpay = MbdPayService(cls.accounts, cls.memberships)

    def setUp(self):
        self.admin = self.accounts.bootstrap_admin()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                migrations = Path(__file__).with_name("saas_migrations")
                cursor.execute((migrations / "0020_restore_public_commerce_seed.sql").read_text(encoding="utf-8"))
                cursor.execute((migrations / "0021_annual_products_monthly_allowances.sql").read_text(encoding="utf-8"))
                cursor.execute((migrations / "0023_commerce_entitlement_catalog.sql").read_text(encoding="utf-8"))
                cursor.execute("DELETE FROM external_subscriptions WHERE user_id IN (SELECT id FROM users WHERE email='commerce-cycle@local.test')")
                cursor.execute("DELETE FROM payment_orders WHERE user_id IN (SELECT id FROM users WHERE email='commerce-cycle@local.test')")
                cursor.execute("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email='commerce-cycle@local.test')")
                cursor.execute("DELETE FROM manual_orders WHERE user_id IN (SELECT id FROM users WHERE email='commerce-cycle@local.test')")
                cursor.execute("DELETE FROM users WHERE email='commerce-cycle@local.test'")
                cursor.execute("DELETE FROM invitations WHERE code='COMMERCE-CYCLE-TEST'")
                cursor.execute("DELETE FROM commerce_product_versions WHERE product_id IN (SELECT id FROM commerce_products WHERE slug='commerce-test-90')")
                cursor.execute("DELETE FROM plan_versions WHERE id LIKE 'commerce-commerce-test-90-v%'")
                cursor.execute("DELETE FROM commerce_products WHERE slug='commerce-test-90'")
                cursor.execute("DELETE FROM commerce_configured_benefits WHERE code='commerce-test-support'")

    def create_verified_user(self):
        invite = self.accounts.create_invitation("COMMERCE-CYCLE-TEST", max_uses=1, created_by=str(self.admin["id"]))
        user = self.accounts.register("commerce-cycle@local.test", "commerce cycle password", invite["code"])["user"]
        raw = "verify-" + new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO email_verifications(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)", (new_id(), user["id"], token_hash(raw), utcnow() + timedelta(days=1)))
        self.accounts.verify_email(raw)
        return user

    def test_new_version_retires_previous_without_rewriting_it(self):
        product = self.commerce.create_product(str(self.admin["id"]), "commerce-test-90", "advanced", 999)
        configured = self.commerce.create_configured_benefit(str(self.admin["id"]), {"code": "commerce-test-support", "name": "测试客服权益", "description": "仅展示，不参与额度控制", "defaultText": "测试客服支持"})
        limits = {"official_library_capacity": 20, "official_unlocks": 8, "ai_context_generations": 120, "ai_grammar_generations": 60, "mp3_imports": 3, "video_imports": 2, "youtube_imports": 2, "storage_bytes": 10, "devices": 2}
        first = self.commerce.create_version(str(self.admin["id"]), product["id"], {
            "name": "测试会员 90 天", "shortName": "测试 90 天", "tagline": "第一版卖点", "description": "第一版商品说明",
            "durationDays": 90, "amountCents": 9900, "featureLimits": limits, "configuredBenefitIds": [configured["id"]],
        })
        self.commerce.publish_version(str(self.admin["id"]), first["id"])
        second = self.commerce.create_version(str(self.admin["id"]), product["id"], {
            "name": "测试会员 90 天新版", "shortName": "测试 90 天", "tagline": "第二版卖点", "description": "第二版商品说明",
            "durationDays": 90, "amountCents": 10900, "featureLimits": {**limits, "ai_context_generations": 240}, "configuredBenefitIds": [configured["id"]], "featured": True,
        })
        self.commerce.publish_version(str(self.admin["id"]), second["id"])
        public = self.commerce.product("commerce-test-90")["product"]
        self.assertEqual(public["id"], second["id"])
        self.assertEqual(public["amountCents"], 10900)
        admin = next(item for item in self.commerce.admin_catalog()["products"] if item["id"] == product["id"])
        self.assertEqual([item["status"] for item in admin["versions"]], ["published", "retired"])
        self.assertEqual(admin["versions"][1]["amountCents"], 9900)
        self.assertEqual(admin["versions"][0]["featureLimits"]["ai_context_generations"], 240)
        self.assertEqual(admin["versions"][0]["configuredBenefits"][0]["text"], "测试客服支持")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT quotas_json->>'ai_context_generations',quotas_json->>'storage_bytes',quotas_json->>'devices',active FROM plan_versions WHERE id=%s", (admin["versions"][0]["planVersion"],))
                self.assertEqual(cursor.fetchone(), ("240", str(10 * 1024**3), "2", True))

    def test_entitlement_catalog_only_exposes_enforced_features(self):
        catalog = self.commerce.entitlement_catalog()
        self.assertEqual({item["key"] for item in catalog["builtIn"]}, {"official_library_capacity", "official_unlocks", "ai_context_generations", "ai_grammar_generations", "mp3_imports", "video_imports", "youtube_imports", "storage_bytes", "devices"})
        self.assertTrue(all(item["enforced"] and item["control"] for item in catalog["builtIn"]))
        self.assertIn("support-7x8", {item["code"] for item in catalog["configured"]})

    def test_published_feature_limits_control_runtime_usage(self):
        product = self.commerce.create_product(str(self.admin["id"]), "commerce-test-90", "advanced", 999)
        limits = {"official_library_capacity": 3, "official_unlocks": 1, "ai_context_generations": 2, "ai_grammar_generations": 1, "mp3_imports": 0, "video_imports": 0, "youtube_imports": 0, "storage_bytes": 2, "devices": 1}
        version = self.commerce.create_version(str(self.admin["id"]), product["id"], {"name": "运行时限制测试", "shortName": "限制测试", "tagline": "验证真实额度控制", "description": "用于验证新套餐的功能限制会进入运行时额度系统。", "durationDays": 30, "amountCents": 100, "featureLimits": limits, "configuredBenefitIds": []})
        self.commerce.publish_version(str(self.admin["id"]), version["id"])
        plan_version = self.commerce.product("commerce-test-90")["product"]["planVersion"]
        user = self.create_verified_user()
        self.memberships.create_manual_order(str(self.admin["id"]), str(user["id"]), plan_version, utcnow() - timedelta(minutes=1), utcnow() + timedelta(days=30), amount_cents=100)
        self.memberships.reserve(str(user["id"]), "ai_context_generations", "runtime-limit-1")
        self.memberships.reserve(str(user["id"]), "ai_context_generations", "runtime-limit-2")
        with self.assertRaises(SaaSError) as exceeded:
            self.memberships.reserve(str(user["id"]), "ai_context_generations", "runtime-limit-3")
        self.assertEqual(exceeded.exception.code, "quota_exceeded")
        self.assertEqual(exceeded.exception.details["limit"], 2)

    def test_seeded_catalog_has_fixed_term_products(self):
        products = self.commerce.public_catalog()["products"]
        self.assertGreaterEqual(len(products), 4)
        self.assertTrue(all(item["durationDays"] in {30, 365} or item["slug"] == "commerce-test-90" for item in products))
        self.assertFalse(self.commerce.public_catalog()["payment"]["automaticRenewal"])

    def test_long_term_subscription_resets_usage_every_plan_period(self):
        user = self.create_verified_user()
        start = utcnow() - timedelta(days=31)
        self.memberships.create_manual_order(str(self.admin["id"]), str(user["id"]), "advanced-v1", start, start + timedelta(days=365), amount_cents=29900)
        membership = self.memberships.membership(str(user["id"]), include_usage=True)
        period_start = membership["period"]["startsAt"]
        self.assertTrue(period_start.startswith((start + timedelta(days=30)).date().isoformat()))
        self.assertEqual(next(item for item in membership["usage"] if item["feature"] == "ai_context_generations")["limit"], 300)

    def test_mbdpay_order_is_verified_before_entitlement_and_is_idempotent(self):
        user = self.create_verified_user()
        self.mbdpay._post = lambda url, payload: {"body": "<form id='pay'></form><script>document.forms.pay.submit()</script>"}
        created = self.mbdpay.create_order(str(user["id"]), "advanced-30", "commerce-payment-idempotency")
        self.assertEqual(created["status"], "pending")
        self.mbdpay._verified_remote_order = lambda order_id: {"order_id": order_id, "charge_id": "charge-test-1", "amount": "3900", "state": "1", "payway": "2"}
        event = {"type": "charge_succeeded", "data": {"out_trade_no": created["orderId"], "amount": 3900, "charge_id": "charge-test-1", "payway": 2}}
        self.assertEqual(self.mbdpay.handle_webhook(event)["status"], "processed")
        self.assertEqual(self.mbdpay.handle_webhook(event)["status"], "duplicate")
        order = self.mbdpay.order(str(user["id"]), created["orderId"])
        self.assertEqual(order["status"], "paid")
        self.assertEqual(order["productVersionId"], "advanced-30-v1")
        self.assertEqual(self.memberships.membership(str(user["id"]))["plan"]["id"], "advanced-v1")


if __name__ == "__main__":
    unittest.main()
