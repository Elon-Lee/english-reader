#!/usr/bin/env python3
"""PostgreSQL integration checks for Alipay checkout and payment operations."""
from __future__ import annotations

import base64
import os
import unittest
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import json

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from saas_auth import SaaSError, SaaSService, new_id, token_hash, utcnow
from saas_membership import MembershipService
from saas_payments import AlipayService
from saas_redemptions import RedemptionService
from saas_journey import JourneyService
from saas_sites import site_context
from saas_commerce import CommerceService


TEST_URL = os.environ.get("SHIYUE_SAAS_TEST_DATABASE_URL", "")


class AlipayPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not urlsplit(TEST_URL).path.rsplit("/", 1)[-1].endswith("_test"):
            raise RuntimeError("SHIYUE_SAAS_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用数据库。")
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_pem = cls.private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        public_pem = cls.private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        cls.environment = {
            "DATABASE_URL": TEST_URL,
            "SHIYUE_SAAS_ENABLED": "1",
            "SESSION_SECRET": "test-only-session-secret-that-is-at-least-32-characters",
            "BOOTSTRAP_ADMIN_EMAIL": "alipay-admin@local.test",
            "BOOTSTRAP_ADMIN_PASSWORD": "alipay admin password",
            "ALIPAY_APP_ID": "test-alipay-app",
            "ALIPAY_PRIVATE_KEY": cls.private_pem,
            "ALIPAY_PUBLIC_KEY": public_pem.replace("-----BEGIN PUBLIC KEY-----", "").replace("-----END PUBLIC KEY-----", "").replace("\n", ""),
            "ALIPAY_NOTIFY_URL": "https://example.test/api/payments/alipay/notify",
            "ALIPAY_PAYMENT_PRODUCT": "face_to_face",
            "ALIPAY_PAYMENT_PRODUCT_APPROVED": "1",
        }
        cls.accounts = SaaSService(TEST_URL, cls.environment)
        cls.accounts.migrate()
        cls.memberships = MembershipService(cls.accounts)
        cls.admin = cls.accounts.bootstrap_admin()

    def setUp(self):
        self.payments = AlipayService(self.accounts, self.memberships, self.environment)
        self.redemptions = RedemptionService(self.accounts, self.memberships)
        self.user = self._verified_user()
        self.product_version_id = "advanced-30-v2"
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                migrations = Path(__file__).with_name('saas_migrations')
                for name in ('0020_restore_public_commerce_seed.sql', '0026_cloudcat_monthly_products.sql', '0028_publish_default_plan_cards.sql', '0030_default_month_card_tier_rank.sql'):
                    cursor.execute((migrations / name).read_text())
                cursor.execute("UPDATE commerce_product_versions SET status='published',published_at=COALESCE(published_at,NOW()) WHERE id=%s", (self.product_version_id,))
                cursor.execute("UPDATE plan_versions SET active=TRUE WHERE id='commerce-advanced-30-v2'")

    def _verified_user(self):
        suffix = new_id()[:12].upper()
        invitation = self.accounts.create_invitation("ALIPAY-" + suffix, max_uses=1, created_by=str(self.admin["id"]))
        email = f"alipay-{suffix.lower()}@local.test"
        user = self.accounts.register(email, "alipay test password", invitation["code"])["user"]
        raw = "verify-" + new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO email_verifications(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",
                    (new_id(), user["id"], token_hash(raw), utcnow() + timedelta(days=1)))
        self.accounts.verify_email(raw)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,email,email_verified_at FROM users WHERE id=%s", (user["id"],))
                row = self.accounts._one(cursor)
        user.update(row or {})
        return user

    def _enable_alipay(self):
        self.payments.update_config(str(self.admin["id"]), {"alipayEnabled": True, "cloudcatEnabled": True, "redemptionEnabled": True})

    def test_payment_methods_are_dynamic_and_unapproved_alipay_is_rejected(self):
        disabled_env = {**self.environment, "ALIPAY_PAYMENT_PRODUCT_APPROVED": "0"}
        disabled = AlipayService(self.accounts, self.memberships, disabled_env)
        with self.assertRaises(SaaSError) as error:
            disabled.update_config(str(self.admin["id"]), {"alipayEnabled": True, "cloudcatEnabled": False, "redemptionEnabled": False})
        self.assertEqual(error.exception.code, "alipay_not_configured")

        self.payments.update_config(str(self.admin["id"]), {"alipayEnabled": False, "cloudcatEnabled": False, "redemptionEnabled": True})
        self.assertEqual(self.payments.public_config(), {"methods": [], "redemptionEnabled": True, "automaticRenewal": False})
        self._enable_alipay()
        self.assertEqual(self.payments.public_config()["methods"], ["alipay", "cloudcat"])

    def test_price_change_keeps_old_order_and_charges_exact_new_sale(self):
        self._enable_alipay()
        requests = []
        def gateway(method, payload):
            requests.append(payload)
            return {"qr_code": "https://qr.example.test/price-only"}
        self.payments._request = gateway
        commerce = CommerceService(self.accounts)
        product = commerce.create_product(str(self.admin['id']), 'price-' + new_id()[:12], 'advanced', 999)
        version = commerce.create_version(str(self.admin['id']), product['id'], {'name': '调价快照测试', 'shortName': '测试', 'tagline': '隔离测试', 'description': '按实际售价生成支付金额', 'durationDays': 30, 'amountCents': 4900, 'featureLimits': {'video_library_capacity': 20, 'audio_library_capacity': 50, 'storage_bytes': 1}})
        commerce.publish_version(str(self.admin['id']), version['id'])
        old = self.payments.create_order(str(self.user['id']), version['id'], 'old-price-test-' + new_id())
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT * FROM payment_orders WHERE id=%s', (old['orderId'],))
                snapshot = self.accounts._one(cursor)
        changed = commerce.update_price(str(self.admin['id']), product['id'], {'expectedVersionId': version['id'], 'originalAmountCents': 4900, 'amountCents': 1999})
        created = self.payments.create_order(str(self.user['id']), changed['id'], 'new-price-test-' + new_id())
        self.assertEqual(self.payments.admin_order_detail(created['orderId'])['amountCents'], 1999)
        self.assertEqual(requests[-1]['total_amount'], '19.99')
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT * FROM payment_orders WHERE id=%s', (old['orderId'],))
                self.assertEqual(self.accounts._one(cursor), snapshot)

    def test_order_creation_paid_confirmation_admin_listing_and_refund(self):
        self._enable_alipay()
        self.payments._request = lambda method, payload: {"qr_code": "https://qr.example.test/alipay/123", "trade_no": "precreate-" + new_id()}
        created = self.payments.create_order(str(self.user["id"]), self.product_version_id, "integration-key-0001")
        self.assertEqual(created["status"], "pending")
        self.assertEqual(created["qrCode"], "https://qr.example.test/alipay/123")

        restored = self.payments.order_status(str(self.user["id"]), created["orderId"])
        self.assertEqual(restored["qrCode"], created["qrCode"])
        self.assertEqual(restored["status"], "pending")

        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT amount_cents FROM commerce_product_versions WHERE id=%s", (self.product_version_id,))
                amount = cursor.fetchone()[0]
        trade_number = "provider-trade-" + new_id()
        trade = {"out_trade_no": created["orderId"], "trade_status": "TRADE_SUCCESS", "total_amount": f"{amount / 100:.2f}",
                 "app_id": self.environment["ALIPAY_APP_ID"], "trade_no": trade_number}
        self.payments._complete_paid(trade)
        self.payments._complete_paid(trade)
        paid = self.payments.order_status(str(self.user["id"]), created["orderId"])
        self.assertEqual(paid["status"], "paid")
        self.assertIsNotNone(paid["endsAt"])
        with site_context('intl'):
            cleared = JourneyService(self.accounts).update(str(self.user['id']), {'action': 'clear_purchase'})
            self.assertIsNone(cleared['pendingPurchase'])
        admin_order = self.payments.admin_order_detail(created["orderId"])
        self.assertEqual(admin_order["tradeNo"], trade_number)
        self.assertEqual(self.payments.list_orders(status="paid", query=self.user["email"])["total"], 1)

        self.payments._request = lambda method, payload: {"fund_change": "Y", "refund_fee": f"{amount / 100:.2f}", "trade_no": "provider-refund-" + new_id()}
        refunded = self.payments.refund(str(self.admin["id"]), created["orderId"], "integration refund")
        self.assertEqual(refunded["status"], "refunded")
        self.assertEqual(self.payments.admin_order_detail(created["orderId"])["refundAmountCents"], amount)

    def test_redemption_record_admin_query_is_searchable(self):
        batch = self.redemptions.generate(str(self.admin["id"]), self.product_version_id, 2, "payment integration test")
        result = self.redemptions.admin_records(query=batch["batchId"], status="active", limit=10)
        self.assertEqual(result["total"], 2)
        self.assertEqual({record["batchId"] for record in result["records"]}, {batch["batchId"]})
        self.assertTrue(all(record["codePrefix"].startswith("SY-") for record in result["records"]))

    def test_page_pay_creation_recovery_owner_and_confirmation(self):
        environment = {**self.environment, 'ALIPAY_PAYMENT_PRODUCT': 'page_pay',
                       'INTL_APP_BASE_URL': 'https://intl.example.test',
                       'ALIPAY_NOTIFY_URL': 'https://intl.example.test/api/payments/alipay/notify'}
        self.payments = AlipayService(self.accounts, self.memberships, environment)
        self._enable_alipay()
        # Page pay signs a checkout URL; creating a local order must not call precreate.
        self.payments._request = lambda *_: self.fail('page pay creation must not call precreate')
        created = self.payments.create_order(str(self.user['id']), self.product_version_id, 'page-payment-key-001')
        params = parse_qs(urlsplit(created['checkoutUrl']).query)
        self.assertEqual(params['method'], ['alipay.trade.page.pay'])
        self.assertNotIn('qrCode', created)
        self.assertEqual(created['paymentMode'], 'page_pay')
        duplicate = self.payments.create_order(str(self.user['id']), self.product_version_id, 'page-payment-key-001')
        self.assertEqual(created['orderId'], duplicate['orderId'])
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT count(*) FROM payment_orders WHERE user_id=%s AND idempotency_key=%s',
                               (self.user['id'], 'alipay:page-payment-key-001'))
                self.assertEqual(cursor.fetchone()[0], 1)
        with self.assertRaises(SaaSError) as error:
            self.payments.order_status(str(self.admin['id']), created['orderId'])
        self.assertEqual(error.exception.code, 'payment_order_not_found')
        self.payments._request = lambda *_: {'trade_status': 'WAIT_BUYER_PAY'}
        restored = self.payments.order_status(str(self.user['id']), created['orderId'])
        self.assertEqual(restored['status'], 'pending')
        self.assertEqual(restored['paymentMode'], 'page_pay')
        self.assertIn('checkoutUrl', restored)
        amount = json.loads(params['biz_content'][0])['total_amount']
        trade = {'out_trade_no': created['orderId'], 'trade_status': 'TRADE_FINISHED', 'total_amount': amount,
                 'app_id': environment['ALIPAY_APP_ID'], 'trade_no': 'page-test-' + new_id()}
        self.payments._request = lambda *_: {**trade, 'out_trade_no': 'ali_other_order'}
        with self.assertRaises(SaaSError) as mismatch:
            self.payments.order_status(str(self.user['id']), created['orderId'])
        self.assertEqual(mismatch.exception.code, 'alipay_order_mismatch')
        self.payments._request = lambda *_: trade
        confirmed = self.payments.order_status(str(self.user['id']), created['orderId'])
        self.assertEqual(confirmed['status'], 'paid')
        self.assertNotIn('checkoutUrl', confirmed)
        self.assertIsNotNone(confirmed['endsAt'])
        self.assertEqual(self.payments.order_status(str(self.user['id']), created['orderId'])['status'], 'paid')

    def test_expired_page_order_without_provider_trade_can_be_retried(self):
        environment = {**self.environment, 'ALIPAY_PAYMENT_PRODUCT': 'page_pay',
                       'INTL_APP_BASE_URL': 'https://intl.example.test',
                       'ALIPAY_NOTIFY_URL': 'https://intl.example.test/api/payments/alipay/notify'}
        self.payments = AlipayService(self.accounts, self.memberships, environment)
        self._enable_alipay()
        created = self.payments.create_order(str(self.user['id']), self.product_version_id, 'page-expiry-key-001')
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE payment_orders SET created_at=NOW()-INTERVAL '16 minutes' WHERE id=%s", (created['orderId'],))
        self.payments._request = lambda *_: {'trade_status': 'WAIT_BUYER_PAY', 'providerTradeMissing': True}
        expired = self.payments.order_status(str(self.user['id']), created['orderId'])
        self.assertEqual(expired['status'], 'cancelled')
        self.assertNotIn('checkoutUrl', expired)
        retried = self.payments.create_order(str(self.user['id']), self.product_version_id, 'page-expiry-key-002')
        self.assertNotEqual(created['orderId'], retried['orderId'])
        self.assertIn('checkoutUrl', retried)

    def test_local_test_mode_simulates_payment_without_gateway_access(self):
        local_environment = {**self.environment, "SHIYUE_DEPLOYMENT_MODE": "local", "ALIPAY_TEST_MODE": "1",
            "ALIPAY_PAYMENT_PRODUCT_APPROVED": "0", "ALIPAY_APP_ID": ""}
        local_payments = AlipayService(self.accounts, self.memberships, local_environment)
        self.assertTrue(local_payments.readiness()["configured"])
        self.assertTrue(local_payments.readiness()["testMode"])
        with self.assertRaises(SaaSError) as remote_error:
            AlipayService(self.accounts, self.memberships, {**local_environment, "SHIYUE_DEPLOYMENT_MODE": "remote"}).update_config(
                str(self.admin["id"]), {"alipayEnabled": True, "cloudcatEnabled": False, "redemptionEnabled": False})
        self.assertEqual(remote_error.exception.code, "alipay_not_configured")

        local_payments.update_config(str(self.admin["id"]), {"alipayEnabled": True, "cloudcatEnabled": True, "redemptionEnabled": True})
        local_payments._request = lambda method, payload: self.fail("local simulation must never call Alipay gateway")
        created = local_payments.create_order(str(self.user["id"]), self.product_version_id, "local-simulation-key-1")
        self.assertTrue(created["testMode"])
        self.assertNotIn("qrCode", created)
        paid = local_payments.simulate_paid(str(self.user["id"]), created["orderId"])
        self.assertEqual(paid["status"], "paid")
        self.assertTrue(paid["testMode"])
        refunded = local_payments.refund(str(self.admin["id"]), created["orderId"], "local simulation refund")
        self.assertEqual(refunded["status"], "refunded")


if __name__ == "__main__":
    unittest.main()
