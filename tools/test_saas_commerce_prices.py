"""Exact sale amounts must never be reconstructed from rounded discounts."""
import unittest

from saas_auth import SaaSError
from saas_commerce import CommerceService


class CommercePriceTests(unittest.TestCase):
    def test_exact_sale_price_wins_over_client_discount(self):
        self.assertEqual(CommerceService._prices({"originalAmountCents": 4900, "amountCents": 1900, "discountPercent": 99}), (4900, 1900, 39))
        self.assertEqual(CommerceService._prices({"originalAmountCents": 4999, "amountCents": 1999}), (4999, 1999, 40))

    def test_zero_equal_and_rounding_boundaries(self):
        for original, sale, discount in [(0, 0, 100), (100, 100, 100), (2000, 790, 40), (10000, 1, 0), (10000, 9999, 100)]:
            with self.subTest(original=original, sale=sale):
                self.assertEqual(CommerceService._prices({"originalAmountCents": original, "amountCents": sale}), (original, sale, discount))

    def test_legacy_clients_remain_compatible(self):
        self.assertEqual(CommerceService._prices({"amountCents": 10900}), (10900, 10900, 100))
        self.assertEqual(CommerceService._prices({"originalAmountCents": 3167, "discountPercent": 60}), (3167, 1900, 60))

    def test_invalid_prices_are_rejected(self):
        for payload in [{}, {"amountCents": True}, {"amountCents": 1.5}, {"amountCents": "1.5"}, {"amountCents": float("nan")}, {"amountCents": -1}, {"amountCents": 2147483648}, {"originalAmountCents": 100, "amountCents": 101}, {"originalAmountCents": 0, "amountCents": 1}, {"originalAmountCents": 100, "amountCents": None}]:
            with self.subTest(payload=payload), self.assertRaises(SaaSError):
                CommerceService._prices(payload)


if __name__ == '__main__':
    unittest.main()
