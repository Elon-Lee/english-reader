#!/usr/bin/env python3
"""Unit checks for the Alipay RSA2 envelope and activation gate."""
from __future__ import annotations

import base64
from datetime import timedelta
import io
import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from saas_auth import SaaSError, SaaSConfigurationError, utcnow
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

    def test_domestic_or_insecure_callback_cannot_enable_international_payment(self):
        for notify in ('https://cn.example.test/api/payments/alipay/notify', 'http://intl.example.test/api/payments/alipay/notify'):
            service = AlipayService(None, MembershipService(None), {
                **self.service.environment, 'INTL_APP_BASE_URL': 'https://intl.example.test', 'ALIPAY_NOTIFY_URL': notify,
            })
            self.assertFalse(service.readiness()['configured'])
        valid = AlipayService(None, MembershipService(None), {
            **self.service.environment, 'INTL_APP_BASE_URL': 'https://intl.example.test',
            'ALIPAY_NOTIFY_URL': 'https://intl.example.test/api/payments/alipay/notify',
        })
        self.assertTrue(valid.readiness()['configured'])

    def test_refund_requires_provider_success_and_exact_full_amount(self):
        self.assertTrue(AlipayService._refund_confirmed({"refund_status": "REFUND_SUCCESS", "refund_amount": "19.00"}, 1900))
        self.assertFalse(AlipayService._refund_confirmed({"refund_status": "REFUND_PROCESSING", "refund_amount": "19.00"}, 1900))
        self.assertFalse(AlipayService._refund_confirmed({"refund_status": "REFUND_SUCCESS", "refund_amount": "18.99"}, 1900))
        self.assertFalse(AlipayService._refund_confirmed({"refund_status": "REFUND_SUCCESS", "refund_amount": "invalid"}, 1900))

    def page_service(self, **overrides):
        return AlipayService(None, MembershipService(None), {
            **self.service.environment, 'ALIPAY_PAYMENT_PRODUCT': 'page_pay',
            'INTL_APP_BASE_URL': 'https://intl.example.test',
            'ALIPAY_NOTIFY_URL': 'https://intl.example.test/api/payments/alipay/notify', **overrides,
        })

    def test_page_pay_readiness_and_signed_checkout_use_trusted_order(self):
        service = self.page_service()
        self.assertTrue(service.readiness()['configured'])
        order = {'id': 'ali_fixture', 'amount_cents': 1900, 'created_at': utcnow(),
                 'product_snapshot_json': {'name': '进阶月卡', 'paymentProduct': 'page_pay'}}
        value = service._checkout_details(order)
        self.assertEqual(value['paymentMode'], 'page_pay')
        self.assertNotIn('qrCode', value)
        url = urlsplit(value['checkoutUrl'])
        self.assertEqual((url.scheme, url.netloc, url.path), ('https', 'openapi.alipay.com', '/gateway.do'))
        params = {key: values[0] for key, values in parse_qs(url.query).items()}
        self.assertEqual(params['method'], 'alipay.trade.page.pay')
        self.assertEqual(params['notify_url'], service.environment['ALIPAY_NOTIFY_URL'])
        self.assertEqual(params['return_url'], 'https://intl.example.test/app?screen=membership')
        content = json.loads(params['biz_content'])
        self.assertEqual(content['product_code'], 'FAST_INSTANT_TRADE_PAY')
        self.assertEqual(content['total_amount'], '19.00')
        self.assertEqual(content['out_trade_no'], 'ali_fixture')
        self.assertEqual(content['subject'], '进阶月卡')
        unsigned = {key: value for key, value in params.items() if key != 'sign'}
        self.public.verify(base64.b64decode(params['sign']), service._canonical(unsigned).encode(), padding.PKCS1v15(), hashes.SHA256())

    def test_page_pay_requires_international_https_origin(self):
        service = self.page_service(INTL_APP_BASE_URL='', ALIPAY_NOTIFY_URL='https://other.example.test/notify')
        self.assertFalse(service.readiness()['configured'])

    def test_expired_order_does_not_issue_new_checkout(self):
        order = {'id': 'ali_expired', 'amount_cents': 1900, 'created_at': utcnow() - timedelta(minutes=16),
                 'product_snapshot_json': {'name': '月卡', 'paymentProduct': 'page_pay'}}
        self.assertNotIn('checkoutUrl', self.page_service()._checkout_details(order))

    def signed_response(self, content):
        signature = base64.b64encode(self.private.sign(content.encode(), padding.PKCS1v15(), hashes.SHA256())).decode()
        return ('{"alipay_trade_query_response":' + content + ',"sign":' + json.dumps(signature) + '}').encode()

    def test_gateway_verifies_original_json_node_instead_of_form_canonicalization(self):
        content = '{ "code":"10000", "trade_status":"WAIT_BUYER_PAY", "out_trade_no":"ali_test", "note":"中文\\\"内容" }'
        with patch('saas_payments.urllib.request.urlopen', return_value=io.BytesIO(self.signed_response(content))):
            result = self.service._request('alipay.trade.query', {'out_trade_no': 'ali_test'})
        self.assertEqual(result['trade_status'], 'WAIT_BUYER_PAY')

    def test_gateway_rejects_tampered_and_unsigned_responses(self):
        valid = self.signed_response('{"code":"10000","trade_status":"WAIT_BUYER_PAY"}')
        for body in [valid.replace(b'WAIT_BUYER_PAY', b'TRADE_SUCCESS'), b'{"alipay_trade_query_response":{"code":"10000"}}']:
            with self.subTest(body=body[:60]), patch('saas_payments.urllib.request.urlopen', return_value=io.BytesIO(body)):
                with self.assertRaises(SaaSError):
                    self.service._request('alipay.trade.query', {})

    def test_trade_not_exist_is_pending_only_for_trade_query(self):
        content = '{"code":"40004","sub_code":"ACQ.TRADE_NOT_EXIST","sub_msg":"交易不存在"}'
        with patch('saas_payments.urllib.request.urlopen', return_value=io.BytesIO(self.signed_response(content))):
            self.assertEqual(self.service._request('alipay.trade.query', {})['trade_status'], 'WAIT_BUYER_PAY')
        denied = '{"code":"40004","sub_code":"ACQ.ACCESS_FORBIDDEN","sub_msg":"无权限"}'
        with patch('saas_payments.urllib.request.urlopen', return_value=io.BytesIO(self.signed_response(denied))):
            with self.assertRaises(SaaSError):
                self.service._request('alipay.trade.query', {})

    def test_raw_response_node_ignores_nested_text_and_rejects_duplicate_nodes(self):
        node = '{"code":"10000","note":"alipay_trade_query_response\\\":{},\\\"sign\\\":fake"}'
        raw = '{"metadata":{"alipay_trade_query_response":{}},"alipay_trade_query_response":' + node + ',"sign":"fake"}'
        self.assertEqual(self.service._response_node(raw, 'alipay_trade_query_response'), node)
        with self.assertRaises(ValueError):
            self.service._response_node('{"alipay_trade_query_response":{},"alipay_trade_query_response":{}}', 'alipay_trade_query_response')


if __name__ == "__main__":
    unittest.main()
