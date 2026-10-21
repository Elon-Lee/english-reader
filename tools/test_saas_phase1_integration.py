#!/usr/bin/env python3
"""Real PostgreSQL acceptance tests for SaaS Phase 1.

Run only against a disposable database whose name ends in ``_test``.  The
script truncates every SaaS table between tests and reads (never alters) the
current SQLite library when validating the legacy import.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch

from saas_auth import ROOT, SaaSError, SaaSService, new_id, token_hash, utcnow


TEST_URL = os.environ.get("SHIYUE_SAAS_TEST_DATABASE_URL", "")
SQLITE_PATH = ROOT / ".local/library.sqlite3"


def assert_safe_database(url: str) -> None:
    database = urlsplit(url).path.rsplit("/", 1)[-1]
    if not url or not database.endswith("_test"):
        raise RuntimeError("SHIYUE_SAAS_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用数据库。")


class PhaseOnePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert_safe_database(TEST_URL)
        cls.environment = {
            "DATABASE_URL": TEST_URL,
            "SHIYUE_SAAS_ENABLED": "1",
            "SESSION_SECRET": "test-only-session-secret-that-is-at-least-32-characters",
            "APP_BASE_URL": "http://127.0.0.1",
            "BOOTSTRAP_ADMIN_EMAIL": "admin@local.test",
            "BOOTSTRAP_ADMIN_PASSWORD": "phase1 admin password",
        }
        cls.service = SaaSService(TEST_URL, cls.environment)
        cls.service.migrate()

    def setUp(self):
        with self.service.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """TRUNCATE TABLE content_sentence_grammar, content_learning_daily, content_word_annotations,
                    content_vocabulary, content_books, invitation_uses, invitations, password_reset_tokens,
                    email_verifications, user_sessions, devices, user_roles, users, roles RESTART IDENTITY CASCADE"""
                )
        self.admin = self.service.bootstrap_admin()
        assert self.admin

    def invitation(self, code: str, max_uses: int = 1):
        return self.service.create_invitation(code, max_uses=max_uses, created_by=str(self.admin["id"]))

    def verify(self, user_id: str) -> None:
        raw = "verify-" + new_id()
        with self.service.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO email_verifications(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",
                    (new_id(), user_id, token_hash(raw), utcnow().replace(year=utcnow().year + 1)),
                )
        self.service.verify_email(raw)

    def test_invitation_max_use_is_concurrency_safe(self):
        self.invitation("ONE-ONLY", 1)

        def register(index: int):
            try:
                self.service.register(f"parallel{index}@local.test", "valid password for testing", "ONE-ONLY")
                return "ok"
            except SaaSError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes = list(workers.map(register, range(2)))
        self.assertEqual(outcomes.count("ok"), 1)
        self.assertEqual(outcomes.count("invitation_exhausted"), 1)
        with self.service.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT used_count FROM invitations WHERE code='ONE-ONLY'")
                self.assertEqual(cursor.fetchone()[0], 1)

    def test_missing_disabled_and_expired_invitations_are_rejected(self):
        with self.assertRaises(SaaSError) as missing:
            self.service.register("missing@local.test", "valid password for testing", "NO-SUCH-CODE")
        self.assertEqual(missing.exception.code, "invalid_invitation")
        invitation = self.invitation("DISABLED")
        with self.service.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE invitations SET status='disabled' WHERE id=%s", (invitation["id"],))
        with self.assertRaises(SaaSError) as disabled:
            self.service.register("disabled@local.test", "valid password for testing", "DISABLED")
        self.assertEqual(disabled.exception.code, "invalid_invitation")
        self.service.create_invitation("EXPIRED", created_by=str(self.admin["id"]), expires_at=utcnow() - timedelta(seconds=1))
        with self.assertRaises(SaaSError) as expired:
            self.service.register("expired@local.test", "valid password for testing", "EXPIRED")
        self.assertEqual(expired.exception.code, "invalid_invitation")

    def test_invitation_can_send_at_most_three_verification_emails(self):
        self.invitation("MAIL-LIMIT", 10)
        with patch.object(self.service, "_send_verification", return_value=True):
            for index in range(3):
                result = self.service.register(f"mail-limit-{index}@local.test", "valid password for testing", "MAIL-LIMIT")
                self.assertTrue(result["emailDelivery"])
            with self.assertRaises(SaaSError) as limited:
                self.service.register("mail-limit-3@local.test", "valid password for testing", "MAIL-LIMIT")
        self.assertEqual(limited.exception.code, "invitation_email_limit")
        with self.service.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT used_count,verification_email_count FROM invitations WHERE code='MAIL-LIMIT'")
                self.assertEqual(cursor.fetchone(), (3, 3))

    def test_verification_csrf_device_limit_and_logout(self):
        self.invitation("FLOW-ONLY")
        result = self.service.register("reader@local.test", "valid password for testing", "FLOW-ONLY")
        user_id = str(result["user"]["id"])
        with self.assertRaises(SaaSError) as unverified:
            self.service.login("reader@local.test", "valid password for testing", "device-flow-00000001", "Phase1 test")
        self.assertEqual(unverified.exception.code, "email_unverified")
        self.verify(user_id)
        login = self.service.login("reader@local.test", "valid password for testing", "device-flow-00000001", "Phase1 test")
        session = self.service.authenticate(login["sessionToken"])
        self.assertIsNotNone(session)
        self.assertTrue(session["email_verified_at"])
        self.service.assert_csrf(session, login["csrfToken"])
        rotated, recovered = self.service.recover_csrf(str(session["session_id"]), login["sessionToken"])
        self.assertIsNone(self.service.authenticate(login["sessionToken"]))
        self.service.assert_csrf(self.service.authenticate(rotated), recovered)
        with self.assertRaises(SaaSError) as csrf_error:
            self.service.assert_csrf(self.service.authenticate(rotated), "wrong")
        self.assertEqual(csrf_error.exception.code, "csrf_failed")
        with self.assertRaises(SaaSError) as device_error:
            self.service.login("reader@local.test", "valid password for testing", "device-flow-00000002", "Phase1 test")
        self.assertEqual(device_error.exception.code, "device_limit_exceeded")
        devices = self.service.devices(user_id)
        self.assertEqual(len(devices), 1)
        self.assertFalse(devices[0]["current"])
        self.assertTrue(self.service.devices(user_id, str(session["device_id"]))[0]["current"])
        self.service.logout(session)
        self.assertIsNone(self.service.authenticate(login["sessionToken"]))

    def test_password_reset_changes_password_and_revokes_sessions(self):
        self.invitation("RESET-ONLY")
        registered = self.service.register("reset@local.test", "valid password for testing", "RESET-ONLY")
        user_id = str(registered["user"]["id"])
        self.verify(user_id)
        login = self.service.login("reset@local.test", "valid password for testing", "device-reset-0000001", "Phase1 test")
        raw = "reset-" + new_id()
        with self.service.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO password_reset_tokens(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",
                    (new_id(), user_id, token_hash(raw), utcnow() + timedelta(hours=1)),
                )
        self.service.reset_password(raw, "replacement password for test")
        self.assertIsNone(self.service.authenticate(login["sessionToken"]))
        with self.assertRaises(SaaSError):
            self.service.login("reset@local.test", "valid password for testing", "device-reset-0000001", "Phase1 test")
        fresh = self.service.login("reset@local.test", "replacement password for test", "device-reset-0000001", "Phase1 test")
        self.assertIsNotNone(self.service.authenticate(fresh["sessionToken"]))

    def test_password_reset_email_limit_clears_after_success(self):
        self.invitation("RESET-LIMIT")
        registered = self.service.register("reset-limit@local.test", "valid password for testing", "RESET-LIMIT")
        self.verify(str(registered["user"]["id"]))
        tokens = []

        def capture(_email, raw_token):
            tokens.append(raw_token)
            return True

        with patch.object(self.service, "_send_password_reset", side_effect=capture):
            self.assertTrue(self.service.forgot_password("reset-limit@local.test"))
            self.assertTrue(self.service.forgot_password("reset-limit@local.test"))
            self.assertTrue(self.service.forgot_password("reset-limit@local.test"))
            self.assertFalse(self.service.forgot_password("reset-limit@local.test"))
            self.assertEqual(len(tokens), 3)
            self.service.reset_password(tokens[-1], "replacement password for reset limit")
            self.assertTrue(self.service.forgot_password("reset-limit@local.test"))
            self.assertEqual(len(tokens), 4)

    def test_operational_admin_password_reset_revokes_current_sessions(self):
        before = self.service.login("admin@local.test", "phase1 admin password", "device-admin-00000001", "Phase1 test")
        self.service.reset_admin_password("admin@local.test", "replacement administrator password")
        self.assertIsNone(self.service.authenticate(before["sessionToken"]))
        with self.assertRaises(SaaSError):
            self.service.login("admin@local.test", "phase1 admin password", "device-admin-00000001", "Phase1 test")
        self.assertIsNotNone(self.service.login("admin@local.test", "replacement administrator password", "device-admin-00000001", "Phase1 test"))

    def test_legacy_sqlite_import_preserves_counts_and_admin_ownership(self):
        imported = self.service.import_legacy_sqlite(SQLITE_PATH, str(self.admin["id"]))
        self.assertEqual(imported["books"], 39)
        with self.service.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*),COUNT(*) FILTER (WHERE owner_id=%s),COUNT(*) FILTER (WHERE visibility='private') FROM content_books", (self.admin["id"],))
                self.assertEqual(cursor.fetchone(), (39, 39, 39))
                cursor.execute("SELECT COUNT(*) FROM content_sentence_grammar")
                self.assertEqual(cursor.fetchone()[0], imported["grammar"])
                cursor.execute("SELECT COUNT(*) FROM content_vocabulary")
                self.assertEqual(cursor.fetchone()[0], imported["vocabulary"])

    def test_server_authenticates_without_exposing_other_users_content(self):
        self.invitation("HTTP-ONLY")
        result = self.service.register("http-reader@local.test", "valid password for testing", "HTTP-ONLY")
        self.verify(str(result["user"]["id"]))
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        environment = {**os.environ, **self.environment, "READER_HOST": "127.0.0.1", "READER_PORT": str(port)}
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "tools/reader_server.py")], cwd=ROOT, env=environment,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        connection = None
        try:
            deadline = time.time() + 10
            while time.time() < deadline:
                try:
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                    connection.request("GET", "/api/health")
                    health_response = connection.getresponse()
                    health_response.read()
                    connection.close()
                    connection = None
                    if health_response.status == 200:
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                stderr = process.stderr.read() if process.stderr else ""
                self.fail("SaaS test server did not start: " + stderr)
            for auth_path in ("/verify-email?token=test", "/reset-password?token=test"):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                connection.request("GET", auth_path)
                response = connection.getresponse()
                body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertIn('id="root"', body)
                connection.close()
                connection = None
            payload = json.dumps({"email": "http-reader@local.test", "password": "valid password for testing"})
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("POST", "/api/auth/login", payload, {"Content-Type": "application/json", "X-Device-Id": "device-http-00000001"})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            cookies = "; ".join(header.split(";", 1)[0] for name, header in response.getheaders() if name.lower() == "set-cookie")
            response.read()
            connection.close()
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("GET", "/api/library", headers={"Cookie": cookies})
            response = connection.getresponse()
            body = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(body, {"items": []})
            connection.close()
            connection = None
            session_cookie = next(value for value in cookies.split("; ") if value.startswith("shiyue_session="))
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("GET", "/api/auth/me", headers={"Cookie": session_cookie})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            recovered_cookies = [value.split(";", 1)[0] for name, value in response.getheaders() if name.lower() == "set-cookie"]
            rotated_cookie = next(value for value in recovered_cookies if value.startswith("shiyue_session="))
            csrf_cookie = next(value for value in recovered_cookies if value.startswith("shiyue_csrf="))
            response.read()
            connection.close()
            self.assertIsNone(self.service.authenticate(session_cookie.split("=", 1)[1]))
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("POST", "/api/auth/logout", "{}", {"Content-Type": "application/json", "Cookie": f"{rotated_cookie}; {csrf_cookie}", "X-CSRF-Token": csrf_cookie.split("=", 1)[1]})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            connection.close()
            connection = None
        finally:
            if connection:
                connection.close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            if process.stderr:
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
