"""Captcha receipts cannot be replayed or moved between accounts/actions/browsers."""
import threading
import unittest
from unittest.mock import Mock

from saas_auth import SaaSError
from saas_captcha import CaptchaService


class MemoryRedis:
    def __init__(self):
        self.values = {}
        self.lock = threading.Lock()

    def set(self, key, value, ex=None, nx=False):
        with self.lock:
            if nx and key in self.values:
                return False
            self.values[key] = value
            return True

    def get(self, key):
        return self.values.get(key)

    def eval(self, script, count, key, expected):
        with self.lock:
            if self.values.get(key) != expected:
                return 0
            del self.values[key]
            return 1

    def ping(self):
        return True


class CaptchaTests(unittest.TestCase):
    def setUp(self):
        self.redis = MemoryRedis()
        self.service = CaptchaService(Mock(), self.redis, {"SHIYUE_CAPTCHA_SECRET": "test-only-internal-secret-at-least-32"})
        self.service.config = Mock(return_value={"captchaEnabled": True, "captchaType": "ROTATE"})
        self.service._provider = Mock(side_effect=self.provider)

    def provider(self, path, payload=None):
        if path.startswith("/gen"):
            return {"code": 200, "data": {"id": "challenge-1", "type": "ROTATE"}}
        return {"code": 200, "success": True, "data": {"id": "challenge-1"}}

    def receipt(self):
        context = self.service.prepare("login", "a@example.test", "browser-one")["context"]
        self.service.generate(context, "browser-one")
        return self.service.check({"id": "challenge-1", "data": {}}, "browser-one")["data"]["captchaToken"]

    def test_receipt_is_required_and_one_use(self):
        with self.assertRaises(SaaSError):
            self.service.require("login", "a@example.test", "", "browser-one")
        token = self.receipt()
        self.service.require("login", "a@example.test", token, "browser-one")
        with self.assertRaises(SaaSError):
            self.service.require("login", "a@example.test", token, "browser-one")

    def test_binding_cannot_be_changed(self):
        token = self.receipt()
        for scene, email, browser in [("register", "a@example.test", "browser-one"), ("login", "b@example.test", "browser-one"), ("login", "a@example.test", "browser-two")]:
            with self.assertRaises(SaaSError):
                self.service.require(scene, email, token, browser)
        self.service.require("login", "A@example.test", token, "browser-one")

    def test_challenge_cannot_be_checked_twice(self):
        self.receipt()
        with self.assertRaises(SaaSError):
            self.service.check({"id": "challenge-1", "data": {}}, "browser-one")

    def test_disabled_preserves_existing_auth(self):
        self.service.config.return_value = {"captchaEnabled": False}
        self.service.require("login", "a@example.test", "", "")

    def test_provider_failure_never_creates_receipt(self):
        context = self.service.prepare("login", "a@example.test", "browser-one")["context"]
        self.service.generate(context, "browser-one")
        self.service._provider.return_value = None
        self.service._provider.side_effect = lambda *args: {"code": 200, "success": False}
        with self.assertRaises(SaaSError):
            self.service.check({"id": "challenge-1", "data": {}}, "browser-one")

    def test_cache_outage_fails_closed(self):
        self.service.redis = None
        with self.assertRaises(SaaSError) as error:
            self.service.require("login", "a@example.test", "fake", "browser-one")
        self.assertEqual(error.exception.status, 503)

    def test_enabling_requires_authenticated_rotation_generation(self):
        self.service._provider.side_effect = None
        self.service._provider.return_value = {"status": "ok"}
        with self.assertRaises(SaaSError) as error:
            self.service.update_config("test-admin", {"captchaEnabled": True})
        self.assertEqual(error.exception.status, 503)


if __name__ == "__main__":
    unittest.main()
