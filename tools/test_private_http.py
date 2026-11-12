"""Exercise the real request dispatchers without external services or user data."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, unquote, urlsplit
from http.server import SimpleHTTPRequestHandler

from saas_auth import SaaSError, SaaSConfigurationError


class PrivateHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("reader_server.py").read_text()
        tree = ast.parse(source)
        handler = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Handler")
        cls.namespace = {
            "SimpleHTTPRequestHandler": SimpleHTTPRequestHandler,
            "SAAS": SimpleNamespace(enabled=True), "urlsplit": urlsplit,
            "parse_qs": parse_qs, "unquote": unquote,
            "SaaSError": SaaSError, "SaaSConfigurationError": SaaSConfigurationError,
        }
        for name in ("COMMERCE", "PAYMENTS", "BILLING", "MEMBERSHIPS", "REDEMPTIONS", "ADMIN", "JOURNEY"):
            cls.namespace[name] = Mock()
        exec(compile(ast.Module(body=[handler], type_ignores=[]), "reader_server.py", "exec"), cls.namespace)
        cls.handler_type = cls.namespace["Handler"]

    def request(self, method, path):
        handler = self.handler_type.__new__(self.handler_type)
        handler.path = path
        handler.headers = {}
        handler.client_address = ("127.0.0.1", 12345)
        handler.reply = Mock()
        handler.send_error = Mock()
        handler.rate_limit = Mock(return_value=True)
        handler.require_saas_user = Mock(return_value=True)
        handler.require_csrf = Mock(return_value=True)
        handler.admin_required = Mock(return_value=True)
        handler.json_body = Mock(return_value={})
        handler._saas_session = {"id": "test-admin", "is_admin": True}
        getattr(handler, "do_" + method)()
        return handler

    def assert_not_found(self, handler):
        if handler.reply.called:
            self.assertEqual(handler.reply.call_args.args[1:], (404,))
        else:
            handler.send_error.assert_called_once_with(404)

    def test_removed_services_have_no_get_routes(self):
        for path in (
            "/api/membership", "/api/membership/usage", "/api/membership/orders",
            "/api/membership/plans", "/api/membership/change-preview?targetPlan=pro-v1",
            "/api/commerce/products", "/api/commerce/products/old", "/api/commerce/orders/old",
            "/api/billing/config", "/api/payments/alipay/orders/old",
            "/api/admin/plan-versions", "/api/admin/commerce/products",
            "/api/admin/commerce/entitlements", "/api/admin/commerce/redemption-batches",
            "/api/admin/payment-config", "/api/admin/payment-orders",
            "/api/admin/commerce/redemption-records", "/api/public/stats",
        ):
            with self.subTest(path=path):
                self.assert_not_found(self.request("GET", path))

    def test_removed_services_have_no_write_routes(self):
        for path in (
            "/api/membership/redeem", "/api/membership/requests", "/api/membership/change-orders",
            "/api/commerce/orders", "/api/commerce/webhooks/mbdpay", "/api/billing/checkout",
            "/api/billing/manage", "/api/billing/webhooks/paddle", "/api/payments/alipay/notify",
            "/api/payments/alipay/orders", "/api/payments/alipay/orders/old/simulate-paid",
            "/api/admin/payment-config", "/api/admin/payment-orders/old/refund",
            "/api/admin/manual-orders", "/api/admin/subscriptions", "/api/admin/plan-versions",
            "/api/admin/commerce/products", "/api/admin/commerce/redemption-batches",
            "/api/admin/commerce/redemption-codes/revoke", "/api/member-invites",
        ):
            with self.subTest(path=path):
                self.assert_not_found(self.request("POST", path))

    def test_removed_subscription_delete_does_not_execute(self):
        self.assert_not_found(self.request("DELETE", "/api/membership/change-orders/old"))

    def test_catalog_requires_verified_session_before_disclosing_content(self):
        handler = self.handler_type.__new__(self.handler_type)
        handler.path = "/api/catalog"
        handler.require_saas_user = Mock(return_value=False)
        handler.catalog_get = Mock()
        handler.do_GET()
        handler.require_saas_user.assert_called_once_with(verified=True)
        handler.catalog_get.assert_not_called()

    def deployment_request(self, method, session, csrf_valid=True, mode="local", address="127.0.0.1"):
        self.namespace.update(DEPLOYMENT_MODE=mode, RUNTIME_MODE="saas", deployment_manager=Mock())
        auth = SimpleNamespace(enabled=True, authenticate=Mock(return_value=session), assert_csrf=Mock())
        if not csrf_valid:
            auth.assert_csrf.side_effect = SaaSError("csrf_failed", "invalid csrf", 403)
        self.namespace["SAAS"] = auth
        self.addCleanup(self.namespace.update, SAAS=SimpleNamespace(enabled=True))
        handler = self.handler_type.__new__(self.handler_type)
        handler.path = "/api/deployment/config"
        handler.headers = {}
        handler.client_address = (address, 12345)
        handler.cookie_value = Mock(return_value="test-cookie")
        handler.reply = Mock()
        handler.rate_limit = Mock(return_value=True)
        handler.json_body = Mock(return_value={"name": "test"})
        getattr(handler, "do_" + method)()
        return handler, self.namespace["deployment_manager"]

    def test_deployment_authenticates_before_requiring_admin(self):
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                handler, manager = self.deployment_request(method, None)
                self.assertEqual(handler.reply.call_args.args[1], 401)
                manager.list_targets.assert_not_called()
                manager.save_target.assert_not_called()

    def test_deployment_admin_get_and_post_remain_available_locally(self):
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                handler, manager = self.deployment_request(method, {"id": "admin", "is_admin": True})
                self.assertEqual(handler._saas_session["id"], "admin")
                if method == "GET":
                    manager.list_targets.assert_called_once_with()
                else:
                    manager.save_target.assert_called_once_with({"name": "test"}, "")

    def test_deployment_rejects_nonadmin_remote_mode_and_nonloopback(self):
        for method in ("GET", "POST"):
            for session, mode, address in (
                ({"id": "user", "is_admin": False}, "local", "127.0.0.1"),
                ({"id": "admin", "is_admin": True}, "remote", "127.0.0.1"),
                ({"id": "admin", "is_admin": True}, "local", "192.0.2.1"),
            ):
                with self.subTest(method=method, mode=mode, address=address, session=session):
                    handler, manager = self.deployment_request(method, session, mode=mode, address=address)
                    self.assertEqual(handler.reply.call_args.args[1], 403)
                    manager.list_targets.assert_not_called()
                    manager.save_target.assert_not_called()

    def test_deployment_write_requires_csrf(self):
        handler, manager = self.deployment_request("POST", {"id": "admin", "is_admin": True}, csrf_valid=False)
        self.assertEqual(handler.reply.call_args.args[1], 403)
        manager.save_target.assert_not_called()


if __name__ == "__main__":
    unittest.main()
