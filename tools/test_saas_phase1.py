#!/usr/bin/env python3
"""Fast dependency-free checks for Phase 1 before a PostgreSQL test DB exists."""
from __future__ import annotations

import unittest

from saas_auth import MIGRATIONS_DIR, device_limit, hash_password, normalize_email, verify_password


class PhaseOneContractTests(unittest.TestCase):
    def test_scrypt_is_salted_and_verifiable(self):
        password = "correct horse battery staple"
        first, second = hash_password(password), hash_password(password)
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password(password, first))
        self.assertFalse(verify_password("not the password", first))

    def test_email_and_device_plan_normalization(self):
        self.assertEqual(normalize_email("  Reader@Example.COM "), "reader@example.com")
        self.assertEqual([device_limit(value) for value in ("free-v1", "advanced-v1", "pro-v1")], [1, 2, 5])

    def test_initial_migration_has_required_tables_and_constraints(self):
        sql = (MIGRATIONS_DIR / "0001_accounts.sql").read_text(encoding="utf-8")
        for table in (
            "users", "user_sessions", "email_verifications", "password_reset_tokens",
            "invitations", "invitation_uses", "devices", "roles", "content_books",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table} ", sql)
        for fragment in (
            "token_hash TEXT NOT NULL UNIQUE", "UNIQUE (invitation_id, email)",
            "REFERENCES users(id)", "visibility TEXT NOT NULL DEFAULT 'private'",
        ):
            self.assertIn(fragment, sql)


if __name__ == "__main__":
    unittest.main()
