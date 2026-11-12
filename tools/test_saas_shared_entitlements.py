"""Shared entitlement rules must never depend on the incoming site."""
import unittest
from types import SimpleNamespace

from saas_resources import DEFAULT_LIMITS, ResourceService


class SharedEntitlementRulesTests(unittest.TestCase):
    def setUp(self):
        self.resources = ResourceService(SimpleNamespace(environment={}))

    def test_private_accounts_keep_existing_capacity_when_a_smaller_plan_is_paid(self):
        limits = self.resources.resolve_limits("private", {"storage_bytes": 5 * 1024**3, "video_library_capacity": 20, "devices": 2})
        self.assertEqual(limits, DEFAULT_LIMITS)

    def test_commercial_free_accounts_use_the_free_plan(self):
        free = {"video_library_capacity": 2, "audio_library_capacity": 5, "storage_bytes": 1024**3, "devices": 2}
        limits = self.resources.resolve_limits("commercial", None, free)
        self.assertEqual(limits["video_library_capacity"], 2)
        self.assertEqual(limits["devices"], 2)
        self.assertEqual(limits["ai_context_generations"], 50)

    def test_paid_capacity_is_the_same_account_policy_on_both_entries(self):
        paid = {**DEFAULT_LIMITS, "video_library_capacity": 400, "devices": 8}
        for policy in ("private", "commercial"):
            self.assertEqual(self.resources.resolve_limits(policy, paid)["video_library_capacity"], 400)
            self.assertEqual(self.resources.resolve_limits(policy, paid)["devices"], 8)


if __name__ == "__main__":
    unittest.main()
