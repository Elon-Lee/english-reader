#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import json
import unittest

from saas_auth import SaaSError, SaaSService
from saas_billing import PaddleBillingService
from saas_membership import MembershipService


class PaddleBillingTests(unittest.TestCase):
    def setUp(self):
        self.environment = {
            "PADDLE_ENVIRONMENT": "sandbox",
            "PADDLE_API_KEY": "pdl_sdbx_apikey_test",
            "PADDLE_CLIENT_TOKEN": "test_client_token",
            "PADDLE_WEBHOOK_SECRET": "pdl_ntfset_test_secret",
            "PADDLE_PRICE_ADVANCED_MONTHLY": "pri_advanced_month",
            "PADDLE_PRICE_ADVANCED_ANNUAL": "pri_advanced_year",
            "PADDLE_PRICE_PRO_MONTHLY": "pri_pro_month",
            "PADDLE_PRICE_PRO_ANNUAL": "pri_pro_year",
            "PADDLE_WEBHOOK_TOLERANCE_SECONDS": "300",
        }
        accounts = SaaSService(environment=self.environment)
        self.billing = PaddleBillingService(accounts, MembershipService(accounts))

    def signature(self, body: bytes, timestamp: int) -> str:
        payload = str(timestamp).encode("ascii") + b":" + body
        digest = hmac.new(self.environment["PADDLE_WEBHOOK_SECRET"].encode(), payload, hashlib.sha256).hexdigest()
        return f"ts={timestamp};h1={digest}"

    def test_public_config_exposes_only_browser_safe_values(self):
        config = self.billing.public_config()
        self.assertTrue(config["configured"])
        self.assertEqual(config["environment"], "sandbox")
        self.assertEqual(config["clientToken"], "test_client_token")
        self.assertNotIn("apiKey", config)
        self.assertNotIn("webhookSecret", config)
        self.assertEqual(config["availableIntervals"]["advanced-v1"], ["month", "year"])

    def test_valid_signature_accepts_exact_raw_body(self):
        body = json.dumps({"event_id": "evt_test", "event_type": "transaction.completed"}, separators=(",", ":")).encode()
        self.billing.verify_signature(body, self.signature(body, 1_000_000), current_time=1_000_100)
        with self.assertRaises(SaaSError) as invalid:
            self.billing.verify_signature(body + b"\n", self.signature(body, 1_000_000), current_time=1_000_100)
        self.assertEqual(invalid.exception.code, "invalid_paddle_signature")

    def test_stale_signature_is_rejected(self):
        body = b"{}"
        with self.assertRaises(SaaSError) as stale:
            self.billing.verify_signature(body, self.signature(body, 1_000_000), current_time=1_000_301)
        self.assertEqual(stale.exception.code, "stale_paddle_webhook")


if __name__ == "__main__":
    unittest.main()
