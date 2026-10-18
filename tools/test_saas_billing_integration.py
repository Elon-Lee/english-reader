#!/usr/bin/env python3
"""PostgreSQL acceptance test for Paddle webhook membership provisioning."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import urlsplit

from saas_auth import SaaSService, new_id, token_hash, utcnow
from saas_billing import PaddleBillingService
from saas_membership import MembershipService


TEST_URL = os.environ.get("SHIYUE_SAAS_TEST_DATABASE_URL", "")


class PaddleBillingPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not urlsplit(TEST_URL).path.rsplit("/", 1)[-1].endswith("_test"):
            raise RuntimeError("SHIYUE_SAAS_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用数据库。")
        cls.environment = {
            "DATABASE_URL": TEST_URL,
            "SHIYUE_SAAS_ENABLED": "1",
            "SESSION_SECRET": "test-only-session-secret-that-is-at-least-32-characters",
            "BOOTSTRAP_ADMIN_EMAIL": "billing-admin@local.test",
            "BOOTSTRAP_ADMIN_PASSWORD": "billing admin password",
            "PADDLE_WEBHOOK_SECRET": "pdl_ntfset_billing_test",
        }
        cls.accounts = SaaSService(TEST_URL, cls.environment)
        cls.accounts.migrate()
        cls.memberships = MembershipService(cls.accounts)
        cls.billing = PaddleBillingService(cls.accounts, cls.memberships)

    def setUp(self):
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """TRUNCATE TABLE payment_provider_events,external_subscriptions,payment_orders,membership_change_requests,
                    membership_audit,usage_ledger,quota_reservations,usage_periods,subscriptions,manual_orders,assets,
                    content_sentence_grammar,content_learning_daily,content_word_annotations,content_vocabulary,content_books,
                    invitation_uses,invitations,password_reset_tokens,email_verifications,user_sessions,devices,user_roles,users,roles
                    RESTART IDENTITY CASCADE"""
                )
        admin = self.accounts.bootstrap_admin()
        invitation = self.accounts.create_invitation("PADDLE-BILLING-TEST", max_uses=2, created_by=str(admin["id"]))
        self.user = self.accounts.register("billing-member@local.test", "billing member password", invitation["code"])["user"]
        raw = "verify-" + new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO email_verifications(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",
                    (new_id(), self.user["id"], token_hash(raw), utcnow() + timedelta(days=1)),
                )
        self.accounts.verify_email(raw)

    def test_completed_transaction_activates_membership_once(self):
        order_id = new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO payment_orders(id,user_id,plan_version_id,provider,billing_interval,amount_cents,idempotency_key,external_transaction_id)
                    VALUES(%s,%s,'advanced-v1','paddle','month',3900,%s,'txn_billing_test')""",
                    (order_id, self.user["id"], "billing-test-idempotency"),
                )
        start, end = utcnow(), utcnow() + timedelta(days=30)
        event = {
            "event_id": "evt_billing_test",
            "event_type": "transaction.completed",
            "occurred_at": utcnow().isoformat(),
            "data": {
                "id": "txn_billing_test",
                "subscription_id": "sub_billing_test",
                "customer_id": "ctm_billing_test",
                "currency_code": "CNY",
                "custom_data": {"local_order_id": order_id, "user_id": self.user["id"], "plan_version_id": "advanced-v1", "billing_interval": "month"},
                "billing_period": {"starts_at": start.isoformat(), "ends_at": end.isoformat()},
                "details": {"totals": {"total": "3900"}},
            },
        }
        body = json.dumps(event, separators=(",", ":")).encode()
        timestamp = int(time.time())
        digest = hmac.new(self.environment["PADDLE_WEBHOOK_SECRET"].encode(), str(timestamp).encode() + b":" + body, hashlib.sha256).hexdigest()
        signature = f"ts={timestamp};h1={digest}"
        with ThreadPoolExecutor(max_workers=12) as workers:
            results = list(workers.map(lambda _: self.billing.handle_webhook(body, signature), range(12)))
        self.assertEqual(sum(row["status"] == "processed" for row in results), 1)
        self.assertEqual(sum(row["status"] == "duplicate" for row in results), 11)
        self.assertEqual(self.billing.handle_webhook(body, signature)["status"], "duplicate")
        self.assertEqual(self.memberships.membership(str(self.user["id"]))["plan"]["id"], "advanced-v1")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT status,external_subscription_id FROM payment_orders WHERE id=%s", (order_id,))
                self.assertEqual(cursor.fetchone(), ("paid", "sub_billing_test"))


if __name__ == "__main__":
    unittest.main()
