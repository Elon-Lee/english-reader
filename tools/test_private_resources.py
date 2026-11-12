"""Private access and resource policy regressions without a running database."""
from datetime import datetime, timezone
import unittest
from unittest.mock import Mock

from saas_auth import SaaSError, SaaSService, device_limit
from saas_resources import ResourceService, can_watch_hd_video


class PrivateResourceTests(unittest.TestCase):
    def test_registration_requires_invitation_before_database_access(self):
        service = SaaSService(database_url="")
        service.transaction = Mock(side_effect=AssertionError("must not open database"))
        with self.assertRaises(SaaSError) as error:
            service.register("reader@example.com", "a-long-password-123", "")
        self.assertEqual(error.exception.code, "invitation_required")
        service.transaction.assert_not_called()

    def test_device_limit_is_uniform(self):
        self.assertEqual(device_limit(), 5)

    def test_resource_configuration_is_uniform_and_validated(self):
        account = SaaSService(environment={"RESOURCE_STORAGE_BYTES": "4096", "RESOURCE_DEVICES": "50"})
        resources = ResourceService(account)
        self.assertEqual(resources.limits["storage_bytes"], 4096)
        self.assertEqual(resources.limits["devices"], 5)
        with self.assertRaises(RuntimeError):
            ResourceService(SaaSService(environment={"RESOURCE_STORAGE_BYTES": "-1"}))

    def test_hd_access_uses_account_policy_and_valid_paid_subscription(self):
        cursor = Mock()
        cursor.fetchone.return_value = (True,)
        self.assertTrue(can_watch_hd_video(cursor, "authenticated-reader"))
        sql, parameters = cursor.execute.call_args.args
        self.assertIn("account_resource_policy='private'", sql)
        self.assertIn('s.ends_at>NOW()', sql)
        self.assertEqual(parameters, ('authenticated-reader',))
        cursor.fetchone.return_value = (False,)
        self.assertFalse(can_watch_hd_video(cursor, 'commercial-free-reader'))

    def test_resource_context_is_independent_of_historical_tiers(self):
        accounts = Mock()
        service = ResourceService(accounts)
        now = datetime(2026, 11, 9, tzinfo=timezone.utc)
        for previous_tier in ("free-v2", "pro-v1"):
            cursor = Mock()
            accounts._one.side_effect = [
                {"id": "reader", "created_at": now, "status": "active", "plan_version": previous_tier, "account_resource_policy": "private"},
                None,
                {"id": "period", "limits_json": service.limits, "starts_at": now, "ends_at": now},
            ]
            context = service._context(cursor, "reader")
            self.assertNotIn("plan", context)
            self.assertNotIn("subscription", context)
            sql = " ".join(str(call.args[0]) for call in cursor.execute.call_args_list)
            self.assertIn("FROM subscriptions", sql)
            self.assertNotIn("UPDATE users SET plan_version", sql)
            self.assertEqual(context["period"]["limits_json"]["storage_bytes"], 20 * 1024**3)
            self.assertEqual(context["period"]["limits_json"]["ai_context_generations"], 50)


if __name__ == "__main__":
    unittest.main()
