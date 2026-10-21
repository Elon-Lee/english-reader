#!/usr/bin/env python3
"""Unit checks for the Alipay RSA2 envelope and activation gate."""
from __future__ import annotations

import base64
import unittest

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from saas_auth import SaaSError, SaaSConfigurationError
from saas_membership import MembershipService
from saas_payments import AlipayService


class AlipaySignatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public = cls.private.public_key()
        private_pem = cls.private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        public_pem = cls.public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        public_body = public_pem.replace("-----BEGIN PUBLIC KEY-----", "").replace("-----END PUBLIC KEY-----", "").replace("\n", "")
        cls.service = AlipayService(None, MembershipService(None), {
            "ALIPAY_APP_ID": "test-app", "ALIPAY_PRIVATE_KEY": private_pem,
            "ALIPAY_PUBLIC_KEY": public_body, "ALIPAY_NOTIFY_URL": "https://example.test/api/payments/alipay/notify",
            "ALIPAY_PAYMENT_PRODUCT": "face_to_face", "ALIPAY_PAYMENT_PRODUCT_APPROVED": "1",
        })

    def test_rsa2_notify_signature_round_trip(self):
        payload = {"app_id": "test-app", "out_trade_no": "ali_test", "trade_status": "TRADE_SUCCESS"}
        signature = self.private.sign(self.service._canonical(payload).encode(), padding.PKCS1v15(), hashes.SHA256())
        self.service._verify({**payload, "sign": base64.b64encode(signature).decode(), "sign_type": "RSA2"}, self.public)

    def test_invalid_signature_is_rejected(self):
        with self.assertRaises(SaaSError) as error:
            self.service._verify({"app_id": "test-app", "sign": "invalid"}, self.public)
        self.assertEqual(error.exception.code, "invalid_alipay_signature")

    def test_product_must_be_explicitly_approved_before_keys_are_used(self):
        environment = {**self.service.environment, "ALIPAY_PAYMENT_PRODUCT_APPROVED": "0"}
        disabled = AlipayService(None, MembershipService(None), environment)
        self.assertFalse(disabled.readiness()["configured"])
        with self.assertRaises(SaaSConfigurationError):
            disabled._keys()

    def test_refund_requires_provider_success_and_exact_full_amount(self):
        self.assertTrue(AlipayService._refund_confirmed({"refund_status": "REFUND_SUCCESS", "refund_amount": "19.00"}, 1900))
        self.assertFalse(AlipayService._refund_confirmed({"refund_status": "REFUND_PROCESSING", "refund_amount": "19.00"}, 1900))
        self.assertFalse(AlipayService._refund_confirmed({"refund_status": "REFUND_SUCCESS", "refund_amount": "18.99"}, 1900))
        self.assertFalse(AlipayService._refund_confirmed({"refund_status": "REFUND_SUCCESS", "refund_amount": "invalid"}, 1900))


if __name__ == "__main__":
    unittest.main()
