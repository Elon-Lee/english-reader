"""Exercise independent frontend gateways against the same real HTTP backend."""
from contextlib import ExitStack
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import saas_frontend_server as frontend


class EchoBackend(BaseHTTPRequestHandler):
    requests = []

    def do_GET(self):
        self.requests.append(dict(self.headers))
        data = json.dumps(dict(self.headers)).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class SiteGatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        (root / 'index.html').write_text('<div id="root">current app</div>')
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for key, value in {'ROOT': root, 'BLOG_ROOT': None, 'BLOG_DOMAIN': '', 'APP_DOMAIN': '10ye.cc',
                           'FRONTEND_SITE': 'intl', 'SITE_TOKEN': 'trusted-test-token'}.items():
            self.stack.enter_context(patch.object(frontend, key, value, create=True))
        EchoBackend.requests = []
        self.backend = self.start_server(EchoBackend)
        self.stack.enter_context(patch.object(frontend, 'BACKEND', urlsplit(f'http://127.0.0.1:{self.backend.server_port}')))
        self.gateway = self.start_server(frontend.FrontendHandler)

    def start_server(self, handler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def request(self, path, host='10ye.cc', headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.gateway.server_port, timeout=5)
        connection.request('GET', path, headers={'Host': host, **(headers or {})})
        response = connection.getresponse()
        result = response.status, response.read()
        connection.close()
        return result

    def test_standalone_international_entry_rejects_domestic_and_unknown_hosts(self):
        for host in ['rynenglish.com', 'learn.rynenglish.com', 'evil.example']:
            self.assertEqual(self.request('/', host)[0], 421)
        self.assertEqual(self.request('/')[0], 200)

    def test_international_deep_links_serve_entry(self):
        for path in ['/pricing', '/purchase/pro-30', '/refunds']:
            status, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertIn(b'current app', body)

    def test_both_gateways_overwrite_browser_internal_identity(self):
        for site in ['cn', 'intl']:
            with patch.object(frontend, 'FRONTEND_SITE', site, create=True):
                status, body = self.request('/api/resources', headers={
                    'X-Shiyue-Site': 'spoofed', 'X-Shiyue-Site-Token': 'browser-token',
                    'X-Shiyue-Original-Host': 'evil.example', 'X-Shiyue-Client-IP': '192.0.2.1',
                })
                self.assertEqual(status, 200)
                result = {key.lower(): value for key, value in json.loads(body).items()}
                self.assertEqual(result['x-shiyue-site'], site)
                self.assertEqual(result['x-shiyue-site-token'], 'trusted-test-token')
                self.assertEqual(result['x-shiyue-original-host'], '10ye.cc')
                self.assertEqual(result['x-shiyue-client-ip'], '127.0.0.1')

    def test_domestic_commerce_is_rejected_before_api_proxy(self):
        with patch.object(frontend, 'FRONTEND_SITE', 'cn', create=True):
            for path in ['/api/commerce/products', '/api/membership', '/api/payments/alipay/orders',
                         '/api/admin/payment-config', '/api/%70ayments/alipay/orders', '/pricing', '/refunds']:
                self.assertEqual(self.request(path)[0], 404, path)
        self.assertEqual(EchoBackend.requests, [])

    def test_cloudflare_client_identity_takes_precedence_over_browser_xff(self):
        status, body = self.request('/api/resources', headers={
            'CF-Connecting-IP': '198.51.100.20', 'X-Forwarded-For': '192.0.2.9',
        })
        self.assertEqual(status, 200)
        result = {key.lower(): value for key, value in json.loads(body).items()}
        self.assertEqual(result['x-shiyue-client-ip'], '198.51.100.20')


if __name__ == '__main__':
    unittest.main()
