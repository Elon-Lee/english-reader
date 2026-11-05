"""Run only with disposable PostgreSQL (*_test) and isolated Redis database."""
import concurrent.futures
import http.client
import json
import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import urlsplit

import redis
from saas_auth import SaaSError, SaaSService
from saas_captcha import CaptchaService


class CaptchaIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database = os.environ.get("SHIYUE_SAAS_TEST_DATABASE_URL", "")
        redis_url = os.environ.get("SHIYUE_CAPTCHA_TEST_REDIS_URL", "")
        if not urlsplit(database).path.endswith("_test") or not redis_url:
            raise RuntimeError("Provide an isolated *_test PostgreSQL URL and SHIYUE_CAPTCHA_TEST_REDIS_URL")
        cls.environment = {**os.environ, "DATABASE_URL": database, "REDIS_URL": redis_url,
            "SHIYUE_SAAS_ENABLED": "1", "SHIYUE_RUNTIME_MODE": "saas", "SHIYUE_DEPLOYMENT_MODE": "remote",
            "SESSION_SECRET": "test-only-captcha-session-secret-at-least-32-characters",
            "BOOTSTRAP_ADMIN_EMAIL": "captcha-admin@example.test", "BOOTSTRAP_ADMIN_PASSWORD": "test admin password",
            "SHIYUE_CAPTCHA_SECRET": "test-only-captcha-internal-secret-at-least-32", "APP_BASE_URL": "http://127.0.0.1",
            "SMTP_HOST": "", "SMTP_FROM": "", "PYTHONDONTWRITEBYTECODE": "1"}
        cls.accounts = SaaSService(database, cls.environment)
        cls.accounts.migrate()
        cls.admin = cls.accounts.bootstrap_admin()
        cls.redis = redis.Redis.from_url(redis_url, decode_responses=True)
        cls.redis.ping()
        cls.captcha = CaptchaService(cls.accounts, cls.redis, cls.environment)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.environment["READER_PORT"] = str(cls.port)
        cls.environment["READER_HOST"] = "127.0.0.1"
        cls.process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("reader_server.py"))],
            env=cls.environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                status, _, _ = cls.request("GET", "/api/health")
                if status == 200: return
            except OSError: pass
            if cls.process.poll() is not None: raise RuntimeError("HTTP test server exited")
            time.sleep(.1)
        raise RuntimeError("HTTP server startup timed out")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)
        # Delete only the namespace created by this suite, never FLUSHDB.
        for key in cls.redis.scan_iter("shiyue:captcha:*"):
            cls.redis.delete(key)
        cls.redis.close()

    @classmethod
    def request(cls, method, path, payload=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=10)
        conn.request(method, path, json.dumps(payload) if payload is not None else None,
                     {"Content-Type": "application/json", **(headers or {})})
        response = conn.getresponse()
        result = (response.status, json.loads(response.read()), response.getheaders())
        conn.close()
        return result

    def setUp(self):
        with self.accounts.transaction() as connection:
            connection.execute("DELETE FROM platform_settings WHERE key='auth.captcha'")
        self.captcha._provider = Mock(return_value={"code": 200, "data": {"type": "ROTATE", "id": "test-readiness"}})

    def test_disabled_and_enabled_http_guards(self):
        status, config, _ = self.request("GET", "/api/auth/config")
        self.assertEqual((status, config["captchaEnabled"]), (200, False))
        status, _, _ = self.request("POST", "/api/auth/login", {"email": "captcha-admin@example.test", "password": "test admin password", "deviceId": "captcha-http-test-device"})
        self.assertEqual(status, 200)
        self.captcha.update_config(str(self.admin["id"]), {"captchaEnabled": True})
        for path in ("login", "register", "forgot-password", "login/replace-device"):
            status, payload, _ = self.request("POST", "/api/auth/" + path, {"email": "captcha-admin@example.test", "password": "test admin password"})
            self.assertEqual((status, payload["code"]), (400, "captcha_required"), path)

    def test_admin_auth_csrf_and_audit(self):
        self.assertEqual(self.request("GET", "/api/admin/auth-config")[0], 401)
        self.assertEqual(self.request("POST", "/api/admin/auth-config", {"captchaEnabled": True})[0], 401)
        session = self.accounts.login("captcha-admin@example.test", "test admin password", "captcha-settings-device", "test", "127.0.0.1")
        headers = {"Cookie": "shiyue_session=" + session["sessionToken"]}
        self.assertEqual(self.request("POST", "/api/admin/auth-config", {"captchaEnabled": False}, headers)[0], 403)
        headers["X-CSRF-Token"] = session["csrfToken"]
        self.assertEqual(self.request("POST", "/api/admin/auth-config", {"captchaEnabled": False}, headers)[0], 200)
        with self.accounts.transaction() as connection:
            row = connection.execute("SELECT payload_json FROM admin_audit_logs WHERE action='auth_captcha_updated' ORDER BY created_at DESC LIMIT 1").fetchone()
        self.assertEqual(row[0], {"captchaEnabled": False})

    def test_invalid_config_is_not_disabled(self):
        with self.accounts.transaction() as connection:
            connection.execute("INSERT INTO platform_settings(key,value_json) VALUES('auth.captcha','{\"enabled\":\"false\"}')")
        status, result, _ = self.request("GET", "/api/auth/config")
        self.assertEqual((status, result["code"]), (503, "captcha_unavailable"))

    def test_cross_site_generation_rejected(self):
        status, result, _ = self.request("POST", "/api/auth/captcha/gen", {"scene": "login", "email": "a@example.test"}, {"Origin": "https://other.example.test", "Sec-Fetch-Site": "cross-site"})
        self.assertEqual((status, result["code"]), (403, "invalid_origin"))

    @unittest.skipUnless(os.environ.get("SHIYUE_CAPTCHA_LIVE_TEST") == "1", "Requires local Tianai service with test secret")
    def test_live_generation_sets_cookie_and_returns_rotation_images(self):
        self.captcha.update_config(str(self.admin["id"]), {"captchaEnabled": True})
        status, result, headers = self.request("POST", "/api/auth/captcha/gen", {"scene": "login", "email": "a@example.test"}, {"Origin": "http://127.0.0.1"})
        self.assertEqual(status, 200)
        self.assertEqual(result["data"]["type"], "ROTATE")
        self.assertTrue(result["data"]["backgroundImage"].startswith("data:image/"))
        self.assertTrue(result["data"]["templateImage"].startswith("data:image/"))
        cookie = next(value for key, value in headers if key.lower() == "set-cookie")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        # Without the paired anonymous cookie this real challenge cannot be checked.
        status, failure, _ = self.request("POST", "/api/auth/captcha/check", {"id": result["data"]["id"], "data": {}})
        self.assertEqual((status, failure["code"]), (400, "captcha_expired"))

    def test_real_redis_receipt_atomicity_and_expiration(self):
        self.captcha.update_config(str(self.admin["id"]), {"captchaEnabled": True})
        token = "isolated-test-receipt-" + "a" * 32
        browser = "isolated-test-browser-one"
        key = self.captcha._key("receipt", token)
        binding = self.captcha._binding("login", "a@example.test", browser)
        self.redis.set(key, binding, ex=120)
        def consume(_):
            try:
                self.captcha.require("login", "a@example.test", token, browser)
                return True
            except SaaSError: return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(consume, range(8))), 1)
        self.redis.set(key, binding, ex=120)
        self.redis.pexpire(key, 1)
        time.sleep(.02)
        self.assertFalse(consume(None))


if __name__ == "__main__":
    unittest.main()
