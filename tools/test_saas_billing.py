"""Checkout links must remain on the configured international entry."""
import unittest
from types import SimpleNamespace

from saas_auth import SaaSConfigurationError
from saas_billing import PaddleBillingService


class PaddleCheckoutSiteTests(unittest.TestCase):
    def service(self, **environment):
        return PaddleBillingService(SimpleNamespace(environment={
            'PADDLE_API_KEY': 'test-key', 'PADDLE_CLIENT_TOKEN': 'test-public-client-token',
            'PADDLE_WEBHOOK_SECRET': 'test-webhook-secret', 'PADDLE_PRICE_ADVANCED_MONTHLY': 'pri_test',
            'APP_BASE_URL': 'https://domestic.example.test', **environment,
        }), None)

    def test_checkout_cannot_fallback_to_domestic_origin(self):
        billing = self.service()
        self.assertFalse(billing.public_config()['checkoutConfigured'])
        with self.assertRaises(SaaSConfigurationError):
            billing._require_checkout()

    def test_checkout_returns_trusted_international_origin(self):
        billing = self.service(INTL_APP_BASE_URL='https://international.example.test')
        self.assertTrue(billing.public_config()['checkoutConfigured'])
        result = billing._checkout_result({'id': 'order-test', 'external_transaction_id': 'txn_test'}, 'test@local.test')
        self.assertEqual(result['returnUrl'], 'https://international.example.test/app?tab=membership')


if __name__ == '__main__':
    unittest.main()
