"""Real HTTP gateways and one PostgreSQL account store; only a dedicated _test DB."""
from contextlib import ExitStack
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
import http.client
import importlib.util
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

from saas_auth import SaaSService
from saas_resources import ResourceService
from saas_membership import MembershipService


TEST_URL = os.environ.get('SHIYUE_SAAS_TEST_DATABASE_URL', '')


@unittest.skipUnless(TEST_URL, 'Requires an explicitly configured dedicated _test PostgreSQL database')
class DualEntryHTTPIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not urlsplit(TEST_URL).path.rsplit('/', 1)[-1].endswith('_test'):
            raise RuntimeError('Integration database must end in _test')
        cls.stack = ExitStack()
        cls.addClassCleanup(cls.stack.close)
        cls.environment = {
            'DATABASE_URL': TEST_URL, 'SHIYUE_SAAS_ENABLED': '1', 'SHIYUE_DEPLOYMENT_MODE': 'remote',
            'SESSION_SECRET': secrets.token_urlsafe(48),
            'CN_GATEWAY_TOKEN': secrets.token_urlsafe(32), 'INTL_GATEWAY_TOKEN': secrets.token_urlsafe(32),
            'CN_APP_BASE_URL': 'https://cn.entry.test', 'INTL_APP_BASE_URL': 'https://intl.entry.test',
            'APP_BASE_URL': 'https://cn.entry.test',
        }
        cls.stack.enter_context(patch.dict(os.environ, cls.environment))
        cls.accounts = SaaSService(TEST_URL, cls.environment)
        cls.accounts.migrate()
        cls.resources = ResourceService(cls.accounts)
        cls.memberships = MembershipService(cls.accounts)
        import reader_server
        cls.backend_module = reader_server
        for key, value in {'SAAS': cls.accounts, 'RESOURCES': cls.resources, 'MEMBERSHIPS': cls.memberships,
                           'CAPTCHA': Mock(config=lambda: {'captchaEnabled': False}),
                           'DEPLOYMENT_MODE': 'remote'}.items():
            cls.stack.enter_context(patch.object(reader_server, key, value))
        cls.backend = cls.start_server(reader_server.Handler)
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.gateways = {}
        for site in ('cn', 'intl'):
            spec = importlib.util.spec_from_file_location('test_gateway_' + site, Path(__file__).with_name('saas_frontend_server.py'))
            gateway = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gateway)
            root = (Path(cls.temp.name) / site).resolve()
            root.mkdir()
            (root / 'index.html').write_text('<div id="root">' + site + '</div>')
            gateway.ROOT = root
            gateway.BLOG_ROOT = None
            gateway.BLOG_DOMAIN = ''
            gateway.APP_DOMAIN = site + '.entry.test'
            gateway.FRONTEND_SITE = site
            gateway.SITE_TOKEN = cls.environment[site.upper() + '_GATEWAY_TOKEN']
            gateway.BACKEND = urlsplit('http://127.0.0.1:' + str(cls.backend.server_port))
            cls.gateways[site] = cls.start_server(gateway.FrontendHandler)

    @classmethod
    def start_server(cls, handler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        cls.addClassCleanup(thread.join)
        cls.addClassCleanup(server.server_close)
        cls.addClassCleanup(server.shutdown)
        return server

    def setUp(self):
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('TRUNCATE users CASCADE')
        self.password = 'dual-entry-test-password-only'
        self.user = self.accounts.bootstrap_admin('entry-admin@example.test', self.password)
        self.cookies = {'cn': {}, 'intl': {}}

    def request(self, site, path, method='GET', payload=None, headers=None):
        cookie = self.cookies[site]
        actual = {'Host': site + '.entry.test', 'Content-Type': 'application/json', **(headers or {})}
        if cookie:
            actual['Cookie'] = '; '.join(key + '=' + value for key, value in cookie.items())
            if method != 'GET':
                actual['X-CSRF-Token'] = cookie.get('shiyue_csrf', '')
        connection = http.client.HTTPConnection('127.0.0.1', self.gateways[site].server_port, timeout=15)
        connection.request(method, path, body=json.dumps(payload).encode() if payload is not None else None, headers=actual)
        response = connection.getresponse()
        body = response.read()
        for name, value in response.getheaders():
            if name.lower() == 'set-cookie':
                parsed = SimpleCookie(value)
                cookie.update({key: morsel.value for key, morsel in parsed.items()})
        status = response.status
        connection.close()
        try:
            body = json.loads(body)
        except (ValueError, UnicodeError):
            pass
        return status, body

    def login(self, site):
        status, body = self.request(site, '/api/auth/login', 'POST', {
            'email': 'entry-admin@example.test', 'password': self.password, 'deviceId': 'dual-entry-browser-' + site,
        })
        self.assertEqual(status, 200, body)
        return body['user']['id']

    def test_two_real_gateways_share_account_preferences_and_resource_ledger(self):
        self.assertEqual(self.login('cn'), self.login('intl'))
        self.assertNotEqual(self.cookies['cn']['shiyue_session'], self.cookies['intl']['shiyue_session'])
        self.assertEqual(self.request('cn', '/api/preferences', 'POST', {'eyeComfort': True})[0], 200)
        self.assertTrue(self.request('intl', '/api/preferences')[1]['eyeComfort'])
        reserved = self.resources.reserve(self.user['id'], 'ai_grammar_generations', 'dual-entry-shared-ledger')
        self.resources.settle(self.user['id'], reserved['reservation']['id'])
        cn = self.request('cn', '/api/resources')
        intl = self.request('intl', '/api/resources')
        self.assertEqual(cn[0], 200)
        self.assertEqual(cn, intl)
        self.assertEqual(self.request('cn', '/api/membership/usage')[0], 404)
        self.assertEqual(self.request('intl', '/api/membership/usage')[0], 200)

    def test_browser_cannot_promote_domestic_requests_or_bypass_backend_ingress(self):
        self.assertEqual(self.request('cn', '/api/membership/usage', headers={
            'X-Shiyue-Site': 'intl', 'X-Shiyue-Site-Token': self.environment['INTL_GATEWAY_TOKEN'],
        })[0], 404)
        connection = http.client.HTTPConnection('127.0.0.1', self.backend.server_port, timeout=10)
        connection.request('GET', '/api/auth/config', headers={'X-Shiyue-Site': 'intl'})
        response = connection.getresponse()
        self.assertEqual(response.status, 403)
        response.read()
        connection.close()

    def test_registration_requires_invitation_on_both_entries(self):
        for site in ('cn', 'intl'):
            status, body = self.request(site, '/api/auth/register', 'POST', {
                'email': site + '@example.test', 'password': self.password,
            })
            self.assertEqual(status, 400, body)
            self.assertEqual(body['code'], 'invitation_required')


if __name__ == '__main__':
    unittest.main()
