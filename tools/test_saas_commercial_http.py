"""Commercial dispatch keeps domestic isolation and original auth gates."""
import unittest
import http.client
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch

from saas_sites import current_site, site_context
from test_private_http import PrivateHTTPTests


class CommercialHTTPTests(PrivateHTTPTests):
    def test_price_dispatch_and_domestic_isolation(self):
        service = self.namespace['COMMERCE']
        service.reset_mock()
        path = '/api/admin/commerce/products/product-test/price'
        self.assert_not_found(self.request('POST', path))
        service.update_price.assert_not_called()
        with site_context('intl'):
            handler = self.request('POST', path)
        handler.admin_required.assert_called_once()
        service.update_price.assert_called_once_with('test-admin', 'product-test', {})

    def test_price_write_checks_csrf_and_admin(self):
        for gate in ['require_csrf', 'admin_required']:
            handler = self.handler_type.__new__(self.handler_type)
            handler.path = '/api/admin/commerce/products/test/price'
            handler.rate_limit = Mock(return_value=True)
            handler.require_saas_user = Mock(return_value=True)
            handler.require_csrf = Mock(return_value=True)
            handler.admin_required = Mock(return_value=True)
            setattr(handler, gate, Mock(return_value=False))
            handler.reply = Mock()
            self.namespace['COMMERCE'].reset_mock()
            with site_context('intl'):
                handler.do_POST()
            self.namespace['COMMERCE'].update_price.assert_not_called()

    def test_gateway_identity_is_applied_before_dispatch_and_reset_on_keepalive(self):
        parent = self.handler_type

        class Probe(parent):
            __init__ = BaseHTTPRequestHandler.__init__
            end_headers = BaseHTTPRequestHandler.end_headers

            def log_message(self, *args):
                pass

            def do_GET(self):
                self.reply({'site': current_site()})

            def reply(self, value, status=200):
                body = json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        environment = {'CN_GATEWAY_TOKEN': 'test-cn-secret', 'INTL_GATEWAY_TOKEN': 'test-intl-secret',
                       'CN_APP_BASE_URL': 'https://cn.example.test', 'INTL_APP_BASE_URL': 'https://intl.example.test'}
        with patch.dict(os.environ, environment):
            server = ThreadingHTTPServer(('127.0.0.1', 0), Probe)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            client = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=5)
            try:
                headers = {'X-Shiyue-Site': 'intl', 'X-Shiyue-Site-Token': 'test-intl-secret',
                           'X-Shiyue-Original-Host': 'intl.example.test'}
                client.request('GET', '/api/test', headers=headers)
                response = client.getresponse()
                self.assertEqual((response.status, json.loads(response.read())['site']), (200, 'intl'))
                # Probe on the same HTTP connection must not inherit the intl context.
                client.request('GET', '/api/health')
                response = client.getresponse()
                self.assertEqual((response.status, json.loads(response.read())['site']), (200, 'cn'))
                client.request('GET', '/api/test', headers={**headers, 'X-Shiyue-Site-Token': 'forged'})
                response = client.getresponse()
                self.assertEqual(response.status, 403)
                self.assertEqual(json.loads(response.read())['code'], 'invalid_site')
            finally:
                client.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_international_membership_dispatches_to_real_service(self):
        service = self.namespace['MEMBERSHIPS']
        service.reset_mock()
        with site_context('intl'):
            self.request('GET', '/api/membership/usage')
        service.usage.assert_called_once_with('test-admin')

    def test_checkout_stops_before_service_when_csrf_fails(self):
        handler = self.handler_type.__new__(self.handler_type)
        handler.path = '/api/payments/alipay/orders'
        handler.rate_limit = Mock(return_value=True)
        handler.require_saas_user = Mock(return_value=True)
        handler.require_csrf = Mock(return_value=False)
        handler.reply = Mock()
        payments = self.namespace['PAYMENTS']
        payments.reset_mock()
        with site_context('intl'):
            handler.do_POST()
        handler.require_saas_user.assert_called_once_with(verified=True)
        handler.require_csrf.assert_called_once_with()
        payments.create_order.assert_not_called()


if __name__ == '__main__':
    unittest.main()
