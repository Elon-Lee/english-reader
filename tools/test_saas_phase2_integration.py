#!/usr/bin/env python3
"""Real PostgreSQL acceptance tests for uniform resource accounting."""
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
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from saas_auth import SaaSError, SaaSService, new_id, token_hash, utcnow
from saas_resources import ResourceService


TEST_URL = os.environ.get("SHIYUE_SAAS_TEST_DATABASE_URL", "")


def assert_safe_database(url: str) -> None:
    if not urlsplit(url).path.rsplit("/", 1)[-1].endswith("_test"):
        raise RuntimeError("SHIYUE_SAAS_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用数据库。")


class PhaseTwoPostgresTests(unittest.TestCase):
    def test_limits_do_not_read_or_mutate_historical_tier(self):
        user_id = str(self.user["id"])
        for tier in ("free-v2", "pro-v1"):
            with self.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE users SET plan_version=%s WHERE id=%s", (tier, user_id))
            status = self.resources.usage(user_id)
            self.assertNotIn("plan", status)
            self.assertNotIn("subscription", status)
            self.assertEqual(status["limits"]["storage_bytes"], 20 * 1024**3)
            self.assertEqual(status["limits"]["video_library_capacity"], 100)
            self.assertEqual(status["limits"]["audio_library_capacity"], 200)
            self.assertEqual(status["limits"]["ai_context_generations"], 50)
            with self.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT plan_version FROM users WHERE id=%s", (user_id,))
                    self.assertEqual(cursor.fetchone()[0], tier)
                    cursor.execute("SELECT plan_version_id,subscription_id FROM usage_periods WHERE user_id=%s", (user_id,))
                    self.assertTrue(all(row == (None, None) for row in cursor.fetchall()))

    def test_daily_limit_release_idempotency_and_tenant_boundary(self):
        user_id = str(self.user["id"])
        reservations = [self.resources.reserve(user_id, "ai_grammar_generations", f"daily-{i}")["reservation"] for i in range(20)]
        with self.assertRaises(SaaSError) as exhausted:
            self.resources.reserve(user_id, "ai_grammar_generations", "overflow")
        self.assertEqual(exhausted.exception.code, "quota_exceeded")
        self.assertEqual(exhausted.exception.details["limit"], 20)
        self.assertNotIn("recommendedPlan", exhausted.exception.details)
        with self.assertRaises(SaaSError):
            self.resources.settle(str(self.admin["id"]), reservations[0]["id"])
        self.resources.release(user_id, reservations[0]["id"])
        self.resources.reserve(user_id, "ai_grammar_generations", "replacement")
        self.resources.settle(user_id, reservations[1]["id"])
        self.resources.settle(user_id, reservations[1]["id"])
        with self.assertRaises(SaaSError):
            self.resources.release(user_id, reservations[1]["id"])
        status = self.resources.usage(user_id)
        grammar = next(row for row in status["usage"] if row["feature"] == "ai_grammar_generations")
        self.assertEqual((grammar["used"], grammar["reserved"], grammar["available"]), (1, 19, 0))

    def test_invalid_quantity_and_conflict_do_not_consume(self):
        user_id = str(self.user["id"])
        with self.assertRaises(SaaSError):
            self.resources.reserve(user_id, "ai_context_generations", "bad", 0)
        first = self.resources.reserve(user_id, "ai_context_generations", "same", 1)
        with self.assertRaises(SaaSError) as conflict:
            self.resources.reserve(user_id, "ai_context_generations", "same", 2)
        self.assertEqual(conflict.exception.code, "idempotency_conflict")
        replay = self.resources.reserve(user_id, "ai_context_generations", "same", 1)
        self.assertEqual(replay["reservation"]["id"], first["reservation"]["id"])
        context = next(row for row in self.resources.usage(user_id)["usage"] if row["feature"] == "ai_context_generations")
        self.assertEqual(context["reserved"], 1)

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
        cls.resources = ResourceService(cls.accounts)

    def setUp(self):
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """TRUNCATE TABLE resource_audit, usage_ledger, quota_reservations, usage_periods, subscriptions,
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


    def test_concurrent_reservation_cannot_overspend_and_duplicate_is_idempotent(self):
        user_id = str(self.user["id"])

        def reserve(index: int):
            try:
                result = self.resources.reserve(user_id, "ai_context_generations", f"parallel-{index}")
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
        repeated = self.resources.reserve(user_id, "ai_context_generations", first["idempotencyKey"])
        self.assertTrue(repeated["idempotent"])
        self.assertEqual(repeated["reservation"]["id"], first["id"])
        self.resources.settle(user_id, first["id"])
        self.resources.settle(user_id, first["id"])
        usage = self.resources.usage(user_id)
        context = next(item for item in usage["usage"] if item["feature"] == "ai_context_generations")
        self.assertEqual(context["used"], 1)
        self.assertEqual(context["reserved"], 24)


    def test_release_returns_reserved_quota(self):
        user_id = str(self.user["id"])
        reservation = self.resources.reserve(user_id, "ai_context_generations", "cancelled-context")["reservation"]
        self.resources.release(user_id, reservation["id"])
        again = self.resources.reserve(user_id, "ai_context_generations", "second-context")["reservation"]
        self.assertEqual(again["state"], "reserved")
        context = next(row for row in self.resources.usage(user_id)["usage"] if row["feature"] == "ai_context_generations")
        self.assertEqual((context["reserved"], context["available"]), (1, 49))








if __name__ == "__main__":
    unittest.main()
