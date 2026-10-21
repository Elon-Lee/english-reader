#!/usr/bin/env python3
"""PostgreSQL acceptance tests for immutable public commerce products."""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from saas_auth import SaaSError, SaaSService, new_id, token_hash, utcnow
from saas_commerce import CommerceService
from saas_catalog import CatalogService
from saas_mbdpay import MbdPayService
from saas_membership import MembershipService
from saas_redemptions import RedemptionService


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
        cls.catalog = CatalogService(cls.accounts, cls.memberships)
        cls.mbdpay = MbdPayService(cls.accounts, cls.memberships)
        cls.redemptions = RedemptionService(cls.accounts, cls.memberships)

    def setUp(self):
        self.admin = self.accounts.bootstrap_admin()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                migrations = Path(__file__).with_name("saas_migrations")
                cursor.execute((migrations / "0020_restore_public_commerce_seed.sql").read_text(encoding="utf-8"))
                cursor.execute((migrations / "0021_annual_products_monthly_allowances.sql").read_text(encoding="utf-8"))
                cursor.execute((migrations / "0023_commerce_entitlement_catalog.sql").read_text(encoding="utf-8"))
                cursor.execute((migrations / "0026_cloudcat_monthly_products.sql").read_text(encoding="utf-8"))
                cursor.execute((migrations / "0028_publish_default_plan_cards.sql").read_text(encoding="utf-8"))
                cursor.execute("UPDATE commerce_product_versions SET status='published',published_at=COALESCE(published_at,NOW()) WHERE id IN ('advanced-30-v2','pro-30-v2')")
                cursor.execute("UPDATE plan_versions SET active=TRUE WHERE id IN ('commerce-advanced-30-v2','commerce-pro-30-v2')")
                cursor.execute("UPDATE commerce_product_versions SET status='published',published_at=COALESCE(published_at,NOW()) WHERE id='free-plan-v1'")
                cursor.execute("""UPDATE commerce_product_versions SET original_amount_cents=3167,discount_percent=60,
                    benefits_json='["私人学习空间最多 5 GB","最多收藏 20 个视频（公版 + 私人）","最多收藏 50 个音频（公版 + 私人）","免费包含：公版及授权学习材料不限次使用","免费包含：公版书架收藏不限量","免费包含：词汇语境分析 300 次/30天","免费包含：句法分析 100 次/30天","免费包含：音频、视频及在线视频导入，不按导入次数收费","免费包含：最多同时登录 2 台设备"]'::jsonb
                    WHERE id='advanced-30-v2'""")
                cursor.execute("""UPDATE commerce_product_versions SET original_amount_cents=8167,discount_percent=60,
                    benefits_json='["私人学习空间最多 20 GB","最多收藏 100 个视频（公版 + 私人）","最多收藏 200 个音频（公版 + 私人）","免费包含：公版及授权学习材料不限次使用","免费包含：公版书架收藏不限量","免费包含：词汇语境分析 300 次/30天","免费包含：句法分析 100 次/30天","免费包含：音频、视频及在线视频导入，不按导入次数收费","免费包含：最多同时登录 2 台设备"]'::jsonb
                    WHERE id='pro-30-v2'""")
                cursor.execute("""INSERT INTO commerce_products(id,slug,family_slug,display_order)
                    VALUES('product-free','free','free',0) ON CONFLICT(id) DO NOTHING""")
                cursor.execute("""INSERT INTO commerce_product_versions(
                    id,product_id,version_number,plan_version_id,display_name,short_name,tagline,description,duration_days,
                    amount_cents,original_amount_cents,discount_percent,currency,benefits_json,featured,status,published_at)
                    VALUES('free-plan-v1','product-free',1,'free-v2','免费版','免费','从自己的材料开始学习','永久免费使用基础学习空间。',
                    30,0,0,100,'CNY','["永久免费","私人学习空间最多 1 GB","最多收藏 2 个视频","最多收藏 5 个音频"]'::jsonb,
                    TRUE,'published',NOW()) ON CONFLICT(id) DO NOTHING""")
                cursor.execute("DELETE FROM external_subscriptions WHERE user_id IN (SELECT id FROM users WHERE email='commerce-cycle@local.test')")
                cursor.execute("DELETE FROM payment_orders WHERE user_id IN (SELECT id FROM users WHERE email='commerce-cycle@local.test')")
                cursor.execute("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email='commerce-cycle@local.test')")
                cursor.execute("DELETE FROM manual_orders WHERE user_id IN (SELECT id FROM users WHERE email='commerce-cycle@local.test')")
                cursor.execute("DELETE FROM users WHERE email='commerce-cycle@local.test'")
                cursor.execute("DELETE FROM invitations WHERE code='COMMERCE-CYCLE-TEST'")
                cursor.execute("DELETE FROM commerce_product_versions WHERE product_id IN (SELECT id FROM commerce_products WHERE slug='commerce-test-90')")
                cursor.execute("DELETE FROM commerce_product_versions WHERE product_id IN (SELECT id FROM commerce_products WHERE slug IN ('commerce-delete-draft','commerce-delete-published'))")
                cursor.execute("DELETE FROM plan_versions WHERE id LIKE 'commerce-commerce-delete-%'")
                cursor.execute("DELETE FROM commerce_products WHERE slug IN ('commerce-delete-empty','commerce-delete-draft','commerce-delete-published')")
                cursor.execute("DELETE FROM usage_periods WHERE plan_version_id LIKE 'commerce-commerce-test-90-v%'")
                cursor.execute("DELETE FROM subscriptions WHERE plan_version_id LIKE 'commerce-commerce-test-90-v%'")
                cursor.execute("DELETE FROM manual_orders WHERE plan_version_id LIKE 'commerce-commerce-test-90-v%'")
                cursor.execute("DELETE FROM payment_orders WHERE plan_version_id LIKE 'commerce-commerce-test-90-v%'")
                cursor.execute("DELETE FROM plan_versions WHERE id LIKE 'commerce-commerce-test-90-v%'")
                cursor.execute("DELETE FROM commerce_products WHERE slug='commerce-test-90'")
                cursor.execute("DELETE FROM commerce_configured_benefits WHERE code='commerce-test-support'")

    def create_verified_user(self):
        suffix = new_id()[:12].upper()
        email = f"commerce-cycle-{suffix.lower()}@local.test"
        invite = self.accounts.create_invitation("COMMERCE-CYCLE-" + suffix, max_uses=1, created_by=str(self.admin["id"]))
        user = self.accounts.register(email, "commerce cycle password", invite["code"])["user"]
        raw = "verify-" + new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO email_verifications(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)", (new_id(), user["id"], token_hash(raw), utcnow() + timedelta(days=1)))
        self.accounts.verify_email(raw)
        return user

    def test_new_version_retires_previous_without_rewriting_it(self):
        product = self.commerce.create_product(str(self.admin["id"]), "commerce-test-90", "advanced", 999)
        configured = self.commerce.create_configured_benefit(str(self.admin["id"]), {"code": "commerce-test-support", "name": "测试客服权益", "description": "仅展示，不参与额度控制", "defaultText": "测试客服支持"})
        limits = {"video_library_capacity": 20, "audio_library_capacity": 50, "storage_bytes": 10, "devices": 2}
        first = self.commerce.create_version(str(self.admin["id"]), product["id"], {
            "name": "测试会员 90 天", "shortName": "测试 90 天", "tagline": "第一版卖点", "description": "第一版商品说明",
            "durationDays": 90, "amountCents": 9900, "purchaseUrl": "https://catfk.com/shop/TEST1234", "featureLimits": limits, "configuredBenefitIds": [configured["id"]],
        })
        self.commerce.publish_version(str(self.admin["id"]), first["id"])
        second = self.commerce.create_version(str(self.admin["id"]), product["id"], {
            "name": "测试会员 90 天新版", "shortName": "测试 90 天", "tagline": "第二版卖点", "description": "第二版商品说明",
            "durationDays": 90, "amountCents": 10900, "purchaseUrl": "https://catfk.com/shop/TEST1234", "featureLimits": limits, "configuredBenefitIds": [configured["id"]], "featured": True,
        })
        self.commerce.publish_version(str(self.admin["id"]), second["id"])
        public = self.commerce.product("commerce-test-90")["product"]
        self.assertEqual(public["id"], second["id"])
        self.assertEqual(public["amountCents"], 10900)
        admin = next(item for item in self.commerce.admin_catalog()["products"] if item["id"] == product["id"])
        self.assertEqual([item["status"] for item in admin["versions"]], ["published", "retired"])
        self.assertEqual(admin["versions"][1]["amountCents"], 9900)
        self.assertEqual(admin["versions"][0]["purchaseUrl"], "https://catfk.com/shop/TEST1234")
        self.assertEqual(admin["versions"][0]["configuredBenefits"][0]["text"], "测试客服支持")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT quotas_json->>'video_library_capacity',quotas_json->>'storage_bytes',quotas_json->>'devices',active FROM plan_versions WHERE id=%s", (admin["versions"][0]["planVersion"],))
                self.assertEqual(cursor.fetchone(), ("20", str(10 * 1024**3), "2", True))

    def test_only_unlisted_unused_draft_package_can_be_deleted(self):
        actor=str(self.admin["id"])
        empty=self.commerce.create_product(actor,"commerce-delete-empty","advanced",999)
        listed=next(item for item in self.commerce.admin_catalog()["products"] if item["slug"]=="commerce-delete-empty")
        self.assertEqual(listed["id"],empty["id"])
        self.assertEqual(listed["versions"],[])
        self.assertTrue(self.commerce.delete_unlisted_product(actor,listed["id"])["deleted"])

        draft=self.commerce.create_product(actor,"commerce-delete-draft","advanced",998)
        version=self.commerce.create_version(actor,draft["id"],{"name":"待配置草稿","shortName":"草稿","tagline":"测试未上架删除","description":"仅供隔离测试。","durationDays":30,"amountCents":100,"featureLimits":{"video_library_capacity":2,"audio_library_capacity":5,"storage_bytes":1},"configuredBenefitIds":[]})
        deleted=self.commerce.delete_unlisted_product(actor,draft["id"])
        self.assertTrue(deleted["deleted"])
        self.assertNotIn(draft["id"],[item["id"] for item in self.commerce.admin_catalog()["products"]])
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:cursor.execute("SELECT COUNT(*) FROM plan_versions WHERE id=%s",("commerce-"+version["id"],));self.assertEqual(cursor.fetchone()[0],0)

        published=self.commerce.create_product(actor,"commerce-delete-published","advanced",997)
        published_version=self.commerce.create_version(actor,published["id"],{"name":"已发布套餐","shortName":"已发布","tagline":"测试删除保护","description":"仅供隔离测试。","durationDays":30,"amountCents":100,"purchaseUrl":"https://catfk.com/shop/TEST1234","featureLimits":{"video_library_capacity":2,"audio_library_capacity":5,"storage_bytes":1},"configuredBenefitIds":[]})
        self.commerce.publish_version(actor,published_version["id"])
        with self.assertRaises(SaaSError) as blocked:self.commerce.delete_unlisted_product(actor,published["id"])
        self.assertEqual(blocked.exception.code,"product_not_unlisted")

    def test_entitlement_catalog_only_exposes_enforced_features(self):
        catalog = self.commerce.entitlement_catalog()
        self.assertEqual({item["key"] for item in catalog["builtIn"]}, {"video_library_capacity", "audio_library_capacity", "storage_bytes"})
        self.assertTrue(all(item["enforced"] and item["control"] for item in catalog["builtIn"]))
        self.assertIn("support-7x8", {item["code"] for item in catalog["configured"]})

    def test_published_feature_limits_control_runtime_usage(self):
        product = self.commerce.create_product(str(self.admin["id"]), "commerce-test-90", "advanced", 999)
        limits = {"video_library_capacity": 3, "audio_library_capacity": 5, "storage_bytes": 2}
        version = self.commerce.create_version(str(self.admin["id"]), product["id"], {"name": "运行时限制测试", "shortName": "限制测试", "tagline": "验证真实额度控制", "description": "用于验证新套餐的功能限制会进入运行时额度系统。", "durationDays": 30, "amountCents": 100, "purchaseUrl": "https://catfk.com/shop/TEST1234", "featureLimits": limits, "configuredBenefitIds": []})
        self.commerce.publish_version(str(self.admin["id"]), version["id"])
        plan_version = self.commerce.product("commerce-test-90")["product"]["planVersion"]
        user = self.create_verified_user()
        self.memberships.create_manual_order(str(self.admin["id"]), str(user["id"]), plan_version, utcnow() - timedelta(minutes=1), utcnow() + timedelta(days=30), amount_cents=100)
        summary = self.memberships.membership(str(user["id"]), include_usage=True)
        self.assertEqual(next(item for item in summary["usage"] if item["feature"] == "video_library_capacity")["limit"], 3)
        self.assertEqual(next(item for item in summary["usage"] if item["feature"] == "audio_library_capacity")["limit"], 5)

    def test_seeded_catalog_has_fixed_term_products(self):
        products = [item for item in self.commerce.public_catalog()["products"] if item["slug"] in {"free", "advanced-30", "pro-30"}]
        by_family = {item["family"]: item for item in products}
        self.assertEqual(by_family["free"]["videoQuality"], "low")
        self.assertIn("流畅版", by_family["free"]["benefits"][0])
        for family in ("advanced", "pro"):
            self.assertEqual(by_family[family]["videoQuality"], "high")
            self.assertIn("高清", by_family[family]["benefits"][0])
        self.assertEqual({item["slug"] for item in products}, {"free", "advanced-30", "pro-30"})
        paid = {item["slug"]: item for item in products if item["family"] != "free"}
        self.assertEqual(paid["advanced-30"]["amountCents"], 1900)
        self.assertEqual(paid["advanced-30"]["originalAmountCents"], 3167)
        self.assertEqual(paid["advanced-30"]["discountPercent"], 60)
        self.assertIn("免费包含：公版及授权学习材料不限次使用", paid["pro-30"]["benefits"])
        self.assertFalse(self.commerce.public_catalog()["payment"]["automaticRenewal"])

    def test_long_term_subscription_resets_usage_every_plan_period(self):
        user = self.create_verified_user()
        start = utcnow() - timedelta(days=31)
        self.memberships.create_manual_order(str(self.admin["id"]), str(user["id"]), "advanced-v1", start, start + timedelta(days=365), amount_cents=29900)
        membership = self.memberships.membership(str(user["id"]), include_usage=True)
        period_start = membership["period"]["startsAt"]
        self.assertLess(abs((datetime.fromisoformat(period_start) - (start + timedelta(days=30))).total_seconds()), 1)
        self.assertTrue(next(item for item in membership["usage"] if item["feature"] == "ai_context_generations")["unlimited"])

    def test_cloudcat_code_is_single_use_and_opens_membership(self):
        slug = "cloudcat-redemption-" + new_id()[:8]
        product = self.commerce.create_product(str(self.admin["id"]), slug, "advanced", 999)
        version = self.commerce.create_version(str(self.admin["id"]), product["id"], {
            "name": "兑换测试月卡", "shortName": "兑换测试", "tagline": "一次性兑换测试", "description": "测试兑换码核销。",
            "durationDays": 30, "amountCents": 1900, "purchaseUrl": "https://catfk.com/shop/TEST1234",
            "featureLimits": {"video_library_capacity": 20, "audio_library_capacity": 50, "storage_bytes": 5}, "configuredBenefitIds": [],
        })
        self.commerce.publish_version(str(self.admin["id"]), version["id"])
        batch = self.redemptions.generate(str(self.admin["id"]), version["id"], 2, "test stock")
        user = self.create_verified_user()
        redeemed = self.redemptions.redeem(str(user["id"]), batch["codes"][0])
        self.assertFalse(redeemed["idempotent"])
        self.assertEqual(redeemed["planName"], "兑换测试月卡")
        order = next(item for item in self.memberships.orders(str(user["id"])) if item["provider"] == "cloudcat")
        self.assertEqual(order["status"], "completed")
        self.assertEqual(order["amountCents"], 1900)
        self.assertEqual(order["planName"], "兑换测试月卡")
        self.assertEqual(self.memberships.orders(str(self.create_verified_user()["id"])), [])
        repeated = self.redemptions.redeem(str(user["id"]), batch["codes"][0])
        self.assertTrue(repeated["idempotent"])
        other = self.create_verified_user()
        with self.assertRaises(SaaSError):
            self.redemptions.redeem(str(other["id"]), batch["codes"][0])
        self.assertEqual(self.redemptions.batches()["batches"][0]["redeemedCount"], 1)

    def test_higher_tier_redemption_carries_remaining_membership_time(self):
        slug = "cloudcat-pro-" + new_id()[:8]
        pro = self.commerce.create_product(str(self.admin["id"]), slug, "pro", 998)
        version = self.commerce.create_version(str(self.admin["id"]), pro["id"], {
            "name": "Pro兑换测试", "shortName": "Pro测试", "tagline": "升级测试", "description": "测试升级兑换。",
            "durationDays": 30, "amountCents": 4900, "purchaseUrl": "https://catfk.com/shop/TEST1234",
            "featureLimits": {"video_library_capacity": 100, "audio_library_capacity": 200, "storage_bytes": 20}, "configuredBenefitIds": [],
        })
        self.commerce.publish_version(str(self.admin["id"]), version["id"])
        user = self.create_verified_user()
        starts = utcnow() - timedelta(days=10)
        ends = utcnow() + timedelta(days=20)
        self.memberships.create_manual_order(str(self.admin["id"]), str(user["id"]), "advanced-v1", starts, ends, "upgrade fixture", 1900)
        batch = self.redemptions.generate(str(self.admin["id"]), version["id"], 1)
        result = self.redemptions.redeem(str(user["id"]), batch["codes"][0])
        plan_version = self.commerce.product(slug)["product"]["planVersion"]
        self.assertEqual(result["membership"]["plan"]["id"], plan_version)
        converted = datetime.fromisoformat(result["endsAt"]) - utcnow()
        self.assertGreaterEqual(converted, timedelta(days=45))
        self.assertLess(converted, timedelta(days=47))

    def test_default_month_cards_upgrade_immediately_and_reject_downgrade(self):
        user_id = str(self.create_verified_user()["id"])
        advanced = self.redemptions.generate(str(self.admin["id"]), "advanced-30-v2", 2)
        pro = self.redemptions.generate(str(self.admin["id"]), "pro-30-v2", 1)
        first = self.redemptions.redeem(user_id, advanced["codes"][0])
        upgraded = self.redemptions.redeem(user_id, pro["codes"][0])
        self.assertEqual(upgraded["membership"]["plan"]["id"], "commerce-pro-30-v2")
        self.assertLessEqual(datetime.fromisoformat(upgraded["startsAt"]), utcnow())
        converted = datetime.fromisoformat(upgraded["endsAt"]) - utcnow()
        self.assertGreater(converted, timedelta(days=41))
        self.assertLess(converted, timedelta(days=43))
        with self.assertRaises(SaaSError) as rejected:
            self.redemptions.redeem(user_id, advanced["codes"][1])
        self.assertEqual(rejected.exception.code, "membership_downgrade_not_allowed")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT status FROM commerce_redemption_codes WHERE code_hash=%s", (self.redemptions._hash(advanced["codes"][1]),))
                self.assertEqual(self.accounts._one(cursor)["status"], "active")

    def test_default_month_card_renewal_extends_current_expiry_immediately(self):
        user_id = str(self.create_verified_user()["id"])
        batch = self.redemptions.generate(str(self.admin["id"]), "advanced-30-v2", 2)
        first = self.redemptions.redeem(user_id, batch["codes"][0])
        renewal = self.redemptions.redeem(user_id, batch["codes"][1])
        self.assertEqual(datetime.fromisoformat(renewal["startsAt"]).date(), utcnow().date())
        self.assertEqual(datetime.fromisoformat(renewal["endsAt"]), datetime.fromisoformat(first["endsAt"]) + timedelta(days=30))
        self.assertEqual(renewal["membership"]["plan"]["id"], "commerce-advanced-30-v2")
        self.assertNotIn("queuedSubscriptions", renewal["membership"])
        self.assertEqual(renewal["changeOrder"]["status"], "applied")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS n FROM subscriptions WHERE user_id=%s AND starts_at>NOW() AND status IN ('active','grace_period')", (user_id,))
                self.assertEqual(self.accounts._one(cursor)["n"], 0)

    def test_upgrade_applies_immediately_without_creating_a_future_subscription(self):
        user_id = str(self.create_verified_user()["id"])
        advanced = self.redemptions.generate(str(self.admin["id"]), "advanced-30-v2", 1)
        self.redemptions.redeem(user_id, advanced["codes"][0])
        pro = self.redemptions.generate(str(self.admin["id"]), "pro-30-v2", 1)
        result = self.redemptions.redeem(user_id, pro["codes"][0])
        self.assertEqual(result["changeOrder"]["changeType"], "upgrade")
        self.assertEqual(result["changeOrder"]["status"], "applied")
        self.assertNotIn("queuedSubscriptions", result["membership"])

    def test_redeem_idempotency_key_returns_same_change_order(self):
        user_id = str(self.create_verified_user()["id"])
        batch = self.redemptions.generate(str(self.admin["id"]), "advanced-30-v2", 1)
        first = self.redemptions.redeem(user_id, batch["codes"][0], "same-request")
        second = self.redemptions.redeem(user_id, batch["codes"][0], "same-request")
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(first["changeOrder"]["id"], second["changeOrder"]["id"])

    def test_video_capacity_combines_private_and_official_library(self):
        user = self.create_verified_user()
        user_id = str(user["id"])
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO content_books(id,owner_id,title,source_type,source_path,data_json,created_at,updated_at)
                    VALUES(%s,%s,'Private video','video','test/private-video','{}'::jsonb,NOW(),NOW())""", (new_id(), user_id))
                catalog_id = new_id()
                cursor.execute("""INSERT INTO catalog_books(id,title,resource_type,rights_status,publication_status,published_at)
                    VALUES(%s,'Official video','video','public_domain','published',NOW())""", (catalog_id,))
        self.catalog.add_or_unlock(user_id, catalog_id, True)
        summary = self.memberships.membership(user_id, include_usage=True)
        video = next(item for item in summary["usage"] if item["feature"] == "video_library_capacity")
        self.assertEqual((video["used"], video["limit"], video["available"]), (2, 2, 0))
        another_id = new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO catalog_books(id,title,resource_type,rights_status,publication_status,published_at)
                    VALUES(%s,'Another official video','video','public_domain','published',NOW())""", (another_id,))
        with self.assertRaises(SaaSError) as exceeded:
            self.catalog.add_or_unlock(user_id, another_id, True)
        self.assertEqual(exceeded.exception.code, "media_capacity_exceeded")


if __name__ == "__main__":
    unittest.main()
