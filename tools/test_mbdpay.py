#!/usr/bin/env python3
import hashlib
import unittest

from saas_auth import SaaSService
from saas_mbdpay import MbdPayService
from saas_membership import MembershipService


class MbdPayTests(unittest.TestCase):
    def test_documented_md5_signature_order(self):
        environment = {"MBDPAY_APP_ID": "12345", "MBDPAY_APP_KEY": "xxxxxxxxxxx", "APP_BASE_URL": "https://example.test"}
        accounts = SaaSService(environment=environment)
        service = MbdPayService(accounts, MembershipService(accounts))
        payload = {"app_id": "12345", "amount_total": 1, "out_trade_no": "123123123123"}
        expected = hashlib.md5(b"amount_total=1&app_id=12345&out_trade_no=123123123123&key=xxxxxxxxxxx").hexdigest()
        self.assertEqual(service._sign(payload), expected)
        self.assertTrue(service.configured)


if __name__ == "__main__":
    unittest.main()
