"""Trusted ingress identity and origin selection without production credentials."""
import importlib.util
import unittest
from email.message import Message

from saas_auth import SaaSError, SaaSConfigurationError


class TrustedSiteTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('saas_sites'), 'Trusted site policy is missing')
        import saas_sites
        self.sites = saas_sites
        self.env = {
            'CN_GATEWAY_TOKEN': 'test-cn-token', 'INTL_GATEWAY_TOKEN': 'test-intl-token',
            'CN_APP_BASE_URL': 'https://learn.rynenglish.com',
            'INTL_APP_BASE_URL': 'https://10ye.cc', 'SHIYUE_DEPLOYMENT_MODE': 'remote',
        }

    def headers(self, site='intl', token='test-intl-token', host='10ye.cc'):
        result = Message()
        result['X-Shiyue-Site'] = site
        result['X-Shiyue-Site-Token'] = token
        result['X-Shiyue-Original-Host'] = host
        return result

    def test_valid_ingress_matches_both_token_and_origin(self):
        self.assertEqual(self.sites.request_site(self.headers(), '127.0.0.1', self.env), 'intl')
        self.assertEqual(self.sites.request_site(self.headers('cn', 'test-cn-token', 'learn.rynenglish.com'), '::1', self.env), 'cn')

    def test_forged_header_without_correct_secret_or_loopback_is_rejected(self):
        for headers, peer in [(self.headers(token=''), '127.0.0.1'),
                              (self.headers(token='test-cn-token'), '127.0.0.1'),
                              (self.headers(), '192.0.2.10'),
                              (self.headers(host='learn.rynenglish.com'), '127.0.0.1'),
                              ({}, '127.0.0.1')]:
            with self.subTest(headers=str(headers), peer=peer), self.assertRaises(SaaSError) as exc:
                self.sites.request_site(headers, peer, self.env)
            self.assertEqual(exc.exception.status, 403)

    def test_duplicate_or_malformed_original_host_is_rejected(self):
        for host in ['10ye.cc:443@evil.example', '10ye.cc/path', '10ye.cc\t', '10ye.cc:garbage']:
            with self.subTest(host=host), self.assertRaises(SaaSError):
                self.sites.request_site(self.headers(host=host), '127.0.0.1', self.env)
        headers = self.headers()
        headers['X-Shiyue-Site'] = 'cn'
        with self.assertRaises(SaaSError):
            self.sites.request_site(headers, '127.0.0.1', self.env)

    def test_unconfigured_legacy_environment_cannot_claim_international_site(self):
        self.assertEqual(self.sites.request_site({}, '127.0.0.1', {}), 'cn')
        with self.assertRaises(SaaSError):
            self.sites.request_site(self.headers(), '127.0.0.1', {})

    def test_site_context_resets_after_failure_and_uses_allowlisted_urls(self):
        self.assertEqual(self.sites.current_site(), 'cn')
        with self.assertRaises(ValueError):
            with self.sites.site_context('intl'):
                self.assertEqual(self.sites.app_base_url(self.env), 'https://10ye.cc')
                raise ValueError('test')
        self.assertEqual(self.sites.current_site(), 'cn')
        self.assertEqual(self.sites.app_base_url(self.env), 'https://learn.rynenglish.com')
        with self.sites.site_context('intl'), self.assertRaises(SaaSConfigurationError):
            self.sites.app_base_url({'APP_BASE_URL': 'https://learn.rynenglish.com'})

    def test_invalid_url_configuration_fails_closed(self):
        for value in ['https://name:secret@10ye.cc', 'https://10ye.cc/redirect', 'https://10ye.cc?next=x', 'http://10ye.cc']:
            with self.subTest(value=value), self.sites.site_context('intl'), self.assertRaises(SaaSConfigurationError):
                self.sites.app_base_url({**self.env, 'INTL_APP_BASE_URL': value})

    def test_commerce_classification_has_route_boundaries(self):
        for path in ['/api/membership', '/api/payments/alipay/notify', '/api/admin/commerce/products',
                     '/api/admin/payment-orders/a/refund', '/api/member-invites', '/api/billing/config',
                     '/pricing', '/purchase/pro-30', '/refunds', '/api/public/stats',
                     '/api/%70ayments/alipay/orders']:
            self.assertTrue(self.sites.is_commercial_path(path), path)
        for path in ['/api/resources', '/api/catalog', '/api/admin/users', '/api/memberships-other', '/app', '/about']:
            self.assertFalse(self.sites.is_commercial_path(path), path)


if __name__ == '__main__':
    unittest.main()
