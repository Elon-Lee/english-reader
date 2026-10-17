#!/usr/bin/env python3
"""Real PostgreSQL acceptance tests for plans, manual orders, and quotas."""
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
from urllib.parse import urlsplit

from saas_auth import SaaSError, SaaSService, new_id, token_hash, utcnow
from saas_membership import MembershipService


TEST_URL = os.environ.get("SHIYUE_SAAS_TEST_DATABASE_URL", "")


def assert_safe_database(url: str) -> None:
    if not urlsplit(url).path.rsplit("/", 1)[-1].endswith("_test"):
        raise RuntimeError("SHIYUE_SAAS_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用数据库。")


class PhaseTwoPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert_safe_database(TEST_URL)
        cls.environment = {
            "DATABASE_URL": TEST_URL,
            "SHIYUE_SAAS_ENABLED": "1",
            "SESSION_SECRET": "test-only-session-secret-that-is-at-least-32-characters",
            "BOOTSTRAP_ADMIN_EMAIL": "admin@local.test",
            "BOOTSTRAP_ADMIN_PASSWORD": "phase2 admin password",
        }
        cls.accounts = SaaSService(TEST_URL, cls.environment)
        cls.accounts.migrate()
        cls.memberships = MembershipService(cls.accounts)

    def setUp(self):
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """TRUNCATE TABLE membership_audit, usage_ledger, quota_reservations, usage_periods, subscriptions,
                    manual_orders, assets, content_sentence_grammar, content_learning_daily, content_word_annotations,
                    content_vocabulary, content_books, invitation_uses, invitations, password_reset_tokens,
                    email_verifications, user_sessions, devices, user_roles, users, roles RESTART IDENTITY CASCADE"""
                )
        self.admin = self.accounts.bootstrap_admin()
        assert self.admin
        invite = self.accounts.create_invitation("PHASE2-TEST", max_uses=30, created_by=str(self.admin["id"]))
        self.user = self.accounts.register("member@local.test", "member password for phase two", invite["code"])["user"]
        self.verify(str(self.user["id"]))

    def verify(self, user_id: str) -> None:
        raw = "verify-" + new_id()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO email_verifications(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",
                    (new_id(), user_id, token_hash(raw), utcnow() + timedelta(days=1)),
                )
        self.accounts.verify_email(raw)

    def test_default_plan_and_period_are_immutable_snapshot(self):
        membership = self.memberships.membership(str(self.user["id"]), include_usage=True)
        self.assertEqual(membership["plan"]["id"], "free-v2")
        self.assertEqual(membership["plan"]["quotas"]["ai_context_generations"], 50)
        self.assertEqual(len(membership["usage"]), 11)
        self.assertEqual(next(item for item in membership["usage"] if item["feature"] == "storage_bytes")["limit"], 1024**3)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT limits_json->>'ai_context_generations' FROM usage_periods WHERE user_id=%s", (self.user["id"],))
                self.assertEqual(cursor.fetchone()[0], "50")

    def test_concurrent_reservation_cannot_overspend_and_duplicate_is_idempotent(self):
        user_id = str(self.user["id"])

        def reserve(index: int):
            try:
                result = self.memberships.reserve(user_id, "ai_context_generations", f"parallel-{index}")
                return result["reservation"]
            except SaaSError as exc:
                return exc

        with ThreadPoolExecutor(max_workers=25) as workers:
            results = list(workers.map(reserve, range(25)))
        reservations = [item for item in results if isinstance(item, dict)]
        errors = [item for item in results if isinstance(item, SaaSError)]
        self.assertEqual(len(reservations), 25)
        self.assertEqual(len(errors), 0)
        self.assertTrue(all(item.code == "quota_exceeded" for item in errors))
        self.assertTrue(all(item.details["limit"] == 50 and item.details["used"] == 0 for item in errors))
        first = reservations[0]
        repeated = self.memberships.reserve(user_id, "ai_context_generations", first["idempotencyKey"])
        self.assertTrue(repeated["idempotent"])
        self.assertEqual(repeated["reservation"]["id"], first["id"])
        self.memberships.settle(user_id, first["id"])
        self.memberships.settle(user_id, first["id"])
        usage = self.memberships.usage(user_id)
        context = next(item for item in usage["usage"] if item["feature"] == "ai_context_generations")
        self.assertEqual(context["used"], 1)
        self.assertEqual(context["reserved"], 24)

    def test_free_ai_limits_are_daily_and_paid_ai_is_unlimited(self):
        user_id = str(self.user["id"])
        for index in range(50):
            self.memberships.reserve(user_id, "ai_context_generations", f"daily-context-{index}")
        with self.assertRaises(SaaSError) as exceeded:
            self.memberships.reserve(user_id, "ai_context_generations", "daily-context-50")
        self.assertEqual(exceeded.exception.code, "quota_exceeded")
        self.assertEqual(exceeded.exception.details["limit"], 50)
        self.assertTrue(str(exceeded.exception.details["resetAt"]).endswith("+08:00"))
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM usage_periods WHERE user_id=%s AND period_key LIKE 'ai-day:%%'", (user_id,))
                self.assertEqual(cursor.fetchone()[0], 1)
        self.memberships.create_manual_order(str(self.admin["id"]), user_id, "advanced-v1", utcnow(), utcnow() + timedelta(days=30), "paid AI unlimited", 1900)
        paid = self.memberships.membership(user_id, include_usage=True)
        context = next(item for item in paid["usage"] if item["feature"] == "ai_context_generations")
        grammar = next(item for item in paid["usage"] if item["feature"] == "ai_grammar_generations")
        self.assertTrue(context["unlimited"])
        self.assertTrue(grammar["unlimited"])
        for index in range(60):
            result = self.memberships.reserve(user_id, "ai_context_generations", f"paid-context-{index}")["reservation"]
            self.assertEqual(result["state"], "settled")

    def test_release_returns_reserved_quota_and_credit_is_atomic(self):
        user_id = str(self.user["id"])
        reservation = self.memberships.reserve(user_id, "ai_context_generations", "cancelled-context")["reservation"]
        self.memberships.release(user_id, reservation["id"])
        again = self.memberships.reserve(user_id, "ai_context_generations", "second-context")["reservation"]
        self.assertEqual(again["state"], "reserved")
        before = self.memberships.credit(user_id, "ai_grammar_generations", 5, "support-credit-1", str(self.admin["id"]), "support")
        duplicate = self.memberships.credit(user_id, "ai_grammar_generations", 5, "support-credit-1", str(self.admin["id"]), "support")
        self.assertEqual(before["available"], 25)
        self.assertEqual(duplicate["available"], 25)

    def test_manual_order_updates_membership_and_suspend_reverts_to_free(self):
        user_id = str(self.user["id"])
        start, end = utcnow() - timedelta(minutes=1), utcnow() + timedelta(days=30)
        created = self.memberships.create_manual_order(str(self.admin["id"]), user_id, "advanced-v1", start, end, "local manual opening", 3900)
        self.assertEqual(created["order"]["planVersion"], "advanced-v1")
        self.assertEqual(created["membership"]["plan"]["id"], "advanced-v1")
        self.assertEqual(created["membership"]["plan"]["quotas"]["youtube_imports"], 5)
        orders = self.memberships.orders(user_id)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["amountCents"], 3900)
        suspended = self.memberships.update_subscription(str(self.admin["id"]), created["subscription"]["id"], "suspend", note="manual pause")
        self.assertEqual(suspended["subscription"]["status"], "suspended")
        self.assertEqual(suspended["membership"]["plan"]["id"], "free-v2")
        activated = self.memberships.update_subscription(str(self.admin["id"]), created["subscription"]["id"], "activate")
        self.assertEqual(activated["membership"]["plan"]["id"], "advanced-v1")
        extended = self.memberships.update_subscription(str(self.admin["id"]), created["subscription"]["id"], "extend", utcnow() + timedelta(days=60))
        self.assertGreater(extended["subscription"]["endsAt"], created["subscription"]["endsAt"])

    def test_paid_plan_device_limit_is_read_from_immutable_plan_version(self):
        user_id=str(self.user["id"])
        self.memberships.create_manual_order(str(self.admin["id"]),user_id,"advanced-v1",utcnow()-timedelta(minutes=1),utcnow()+timedelta(days=30))
        self.accounts.login("member@local.test","member password for phase two","advanced-device-000001","Phase2 test")
        self.accounts.login("member@local.test","member password for phase two","advanced-device-000002","Phase2 test")
        with self.assertRaises(SaaSError) as limited:
            self.accounts.login("member@local.test","member password for phase two","advanced-device-000003","Phase2 test")
        self.assertEqual(limited.exception.code,"device_limit_exceeded")
        self.assertEqual(limited.exception.details["limit"],2)

    def test_expired_subscription_is_marked_expired_and_falls_back_to_free(self):
        user_id=str(self.user["id"])
        created=self.memberships.create_manual_order(str(self.admin["id"]),user_id,"pro-v1",utcnow()-timedelta(days=40),utcnow()-timedelta(days=1),"expired acceptance")
        membership=self.memberships.membership(user_id)
        self.assertEqual(membership["plan"]["id"],"free-v2")
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT status FROM subscriptions WHERE id=%s",(created["subscription"]["id"],))
                self.assertEqual(cursor.fetchone()[0],"expired")

    def test_http_membership_and_admin_manual_order_endpoints(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        environment = {**os.environ, **self.environment, "READER_HOST": "127.0.0.1", "READER_PORT": str(port)}
        server_path = os.path.join(os.path.dirname(__file__), "reader_server.py")
        process = subprocess.Popen([sys.executable, server_path], cwd=os.path.dirname(__file__), env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        connections: list[http.client.HTTPConnection] = []
        try:
            deadline = time.time() + 10
            while time.time() < deadline:
                try:
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1); connections.append(connection)
                    connection.request("GET", "/api/health")
                    response = connection.getresponse(); response.read(); connection.close(); connections.remove(connection)
                    if response.status == 200: break
                except OSError: time.sleep(.1)
            else: self.fail("SaaS membership test server did not start: " + (process.stderr.read() if process.stderr else ""))
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5); connections.append(connection)
            connection.request("POST", "/api/auth/login", json.dumps({"email":"admin@local.test","password":"phase2 admin password"}), {"Content-Type":"application/json","X-Device-Id":"phase2-admin-device-1"})
            response = connection.getresponse(); self.assertEqual(response.status, 200); headers=response.getheaders(); response.read(); connection.close(); connections.remove(connection)
            cookie_values=[value.split(";",1)[0] for name,value in headers if name.lower()=="set-cookie"]
            cookies="; ".join(cookie_values);csrf=next(value.split("=",1)[1] for value in cookie_values if value.startswith("shiyue_csrf="))
            start,end=utcnow()-timedelta(minutes=1),utcnow()+timedelta(days=30)
            payload={"userId":self.user["id"],"planVersion":"pro-v1","startsAt":start.isoformat(),"endsAt":end.isoformat(),"amountCents":7900,"note":"HTTP manual opening"}
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection)
            connection.request("POST","/api/admin/manual-orders",json.dumps(payload),{"Content-Type":"application/json","Cookie":cookies,"X-CSRF-Token":csrf})
            response=connection.getresponse();created=json.loads(response.read());self.assertEqual(response.status,201);self.assertEqual(created["membership"]["plan"]["id"],"pro-v1");connection.close();connections.remove(connection)
            login=self.accounts.login("member@local.test","member password for phase two","phase2-member-device-1","Phase2 test")
            connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5);connections.append(connection)
            connection.request("GET","/api/membership/usage",headers={"Cookie":f"shiyue_session={login['sessionToken']}"})
            response=connection.getresponse();membership=json.loads(response.read());self.assertEqual(response.status,200);self.assertEqual(membership["plan"]["id"],"pro-v1");self.assertEqual(next(row for row in membership["usage"] if row["feature"]=="youtube_imports")["limit"],20);connection.close();connections.remove(connection)
        finally:
            for connection in connections: connection.close()
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill()
            if process.stderr: process.stderr.close()


if __name__ == "__main__":
    unittest.main()
