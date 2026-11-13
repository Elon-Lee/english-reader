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
from saas_auth import SaaSError, new_id
from saas_imports import WorkspaceImportService
from saas_media import MediaService
from saas_workspace import WorkspaceService
from saas_commerce import CommerceService


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
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.media = MediaService(cls.accounts, cls.resources, Path(cls.temp.name) / 'media')
        cls.imports = WorkspaceImportService(cls.accounts, cls.resources, cls.media)
        cls.official_imports = WorkspaceImportService(cls.accounts, cls.resources, cls.media, official=True)
        cls.workspace = WorkspaceService(cls.accounts)
        import reader_server
        cls.backend_module = reader_server
        for key, value in {'SAAS': cls.accounts, 'RESOURCES': cls.resources, 'MEMBERSHIPS': cls.memberships,
                           'WORKSPACE_IMPORTS': cls.imports, 'OFFICIAL_IMPORTS': cls.official_imports,
                           'WORKSPACE': cls.workspace, 'MEDIA': cls.media, 'COMMERCE': CommerceService(cls.accounts),
                           'CAPTCHA': Mock(config=lambda: {'captchaEnabled': False}),
                           'DEPLOYMENT_MODE': 'remote'}.items():
            cls.stack.enter_context(patch.object(reader_server, key, value))
        cls.backend = cls.start_server(reader_server.Handler)
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
                migrations = Path(__file__).with_name('saas_migrations')
                for name in ('0020_restore_public_commerce_seed.sql', '0026_cloudcat_monthly_products.sql', '0028_publish_default_plan_cards.sql'):
                    cursor.execute((migrations / name).read_text())
                cursor.execute("""INSERT INTO commerce_product_versions(id,product_id,version_number,plan_version_id,
                    display_name,short_name,tagline,description,duration_days,amount_cents,benefits_json,status)
                    VALUES('free-plan-v1','product-free',1,'free-v2','免费版','免费','原免费方案','原1GB空间',30,0,
                    '["私人学习空间最多 1 GB","音频、视频及在线视频导入，不按导入次数收费"]','published')""")
                cursor.execute("UPDATE commerce_product_versions SET purchase_url='https://checkout.example.test/'||id WHERE amount_cents>0 AND status='published'")
                cursor.execute((migrations / '0046_private_import_entitlements.sql').read_text())
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

    def grant(self, family):
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM subscriptions WHERE user_id=%s', (self.user['id'],))
                cursor.execute("""INSERT INTO subscriptions(id,user_id,plan_version_id,status,starts_at,ends_at)
                    VALUES(%s,%s,%s,'active',NOW()-INTERVAL '1 day',NOW()+INTERVAL '30 days')""",
                    (new_id(), self.user['id'], 'commerce-' + family + '-30-v2'))

    def test_domestic_private_import_denied_and_official_admin_import_retained(self):
        self.login('cn')
        for path in ['/api/workspace/imports', '/api/workspace/imports/task/upload',
                     '/api/workspace/imports/task/upload-audio-chunk', '/api/workspace/imports/task/complete']:
            self.assertEqual(self.request('cn', path, 'POST', {}, headers={
                'X-Shiyue-Site': 'intl', 'X-Shiyue-Site-Token': self.environment['INTL_GATEWAY_TOKEN'],
            })[0], 404, path)
        self.assertEqual(self.request('cn', '/api/workspace/imports')[0], 404)
        status, body = self.request('cn', '/api/admin/content-imports', 'POST', {
            'kind': 'text', 'filename': 'official.txt', 'idempotencyKey': new_id(),
        })
        self.assertEqual(status, 201, body)
        task = body['task']['id']
        self.official_imports.upload(self.user['id'], task, 'official.txt', b'An official reading passage.')
        self.assertEqual(self.official_imports.complete(self.user['id'], task)['task']['status'], 'complete')
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM user_roles WHERE user_id=%s', (self.user['id'],))
        self.assertEqual(self.request('cn', '/api/admin/content-imports', 'POST', {})[0], 403)

    def test_international_free_import_rejected_before_reading_upload(self):
        self.login('intl')
        resources = self.request('intl', '/api/resources')[1]
        self.assertEqual(resources['limits']['storage_bytes'], 0)
        self.assertFalse(resources['privateImport']['allowed'])
        for path in ['/api/workspace/imports', '/api/workspace/imports/task/upload',
                     '/api/workspace/imports/task/upload-audio', '/api/workspace/imports/task/upload-audio-chunk',
                     '/api/workspace/imports/task/complete-audio-upload', '/api/workspace/imports/task/complete',
                     '/api/workspace/imports/task/retry']:
            status, body = self.request('intl', path, 'POST', {})
            self.assertEqual(status, 403, (path, body))
            self.assertEqual(body['code'], 'private_import_upgrade_required')
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT COUNT(*) FROM workspace_import_tasks')
                self.assertEqual(cursor.fetchone()[0], 0)

    def test_paid_caps_expiry_cleanup_and_existing_reading(self):
        self.login('intl')
        for family, gb in [('advanced', 1), ('pro', 5)]:
            self.grant(family)
            resources = self.request('intl', '/api/resources')[1]
            self.assertTrue(resources['privateImport']['allowed'])
            self.assertEqual(resources['limits']['storage_bytes'], gb * 1024**3)
            self.assertEqual(self.media.ensure_private_capacity(self.user['id'], gb * 1024**3)['limit'], gb * 1024**3)
            with self.assertRaises(SaaSError):
                self.media.ensure_private_capacity(self.user['id'], gb * 1024**3 + 1)
        task = self.imports.create(self.user['id'], 'text', 'Existing book', 'book.txt', new_id())['task']['id']
        self.imports.upload(self.user['id'], task, 'book.txt', b'Existing content remains readable.')
        completed = self.imports.complete(self.user['id'], task)
        pending = self.imports.create(self.user['id'], 'text', 'Pending', 'pending.txt', new_id())['task']['id']
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE subscriptions SET starts_at=NOW()-INTERVAL '2 days',ends_at=NOW()-INTERVAL '1 day' WHERE user_id=%s", (self.user['id'],))
        self.assertFalse(self.resources.usage(self.user['id'])['privateImport']['allowed'])
        self.assertEqual(self.request('intl', '/api/workspace/imports/'+pending+'/retry', 'POST', {})[0], 403)
        self.assertEqual(self.request('intl', '/api/workspace/imports/'+pending+'/cancel', 'POST', {})[0], 200)
        self.assertEqual(self.request('intl', '/api/workspace/books/'+completed['task']['outputBookId']+'/reader')[0], 200)

    def test_new_product_versions_match_caps_and_keep_original_snapshots(self):
        products = CommerceService(self.accounts).public_catalog()['products']
        self.assertEqual(len(products), 3)
        for product in products:
            self.assertEqual(product['featureLimits']['storage_bytes'], {'free': 0, 'advanced': 1, 'pro': 5}[product['family']])
            self.assertTrue(product['id'].endswith('-imports-v1'))
            if product['family'] == 'free':
                self.assertNotIn('音频、视频及在线视频导入，不按导入次数收费', ' '.join(product['benefits']))
                self.assertIn('不支持', ' '.join(product['benefits']))
            else:
                self.assertEqual(product['purchaseUrl'], 'https://checkout.example.test/'+product['id'].removesuffix('-imports-v1'))
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT quotas_json->>'storage_bytes' FROM plan_versions WHERE id='commerce-pro-30-v2'")
                self.assertEqual(int(cursor.fetchone()[0]), 20 * 1024**3)
                cursor.execute("SELECT status FROM commerce_product_versions WHERE id='pro-30-v2'")
                self.assertEqual(cursor.fetchone()[0], 'retired')
        self.assertEqual(self.accounts.migrate(), [])
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(Path(__file__).with_name('saas_migrations').joinpath('0046_private_import_entitlements.sql').read_text())
        self.assertEqual(CommerceService(self.accounts).public_catalog()['products'], products)

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
