"""Shared database acceptance for international commerce and domestic reading."""
import unittest
from datetime import timedelta

from saas_auth import SaaSError, new_id, utcnow
from saas_membership import MembershipService
from saas_commerce import CommerceService
from saas_journey import JourneyService
from saas_sites import site_context
from test_saas_phase2_integration import PhaseTwoPostgresTests


class SharedEntitlementPostgresTests(PhaseTwoPostgresTests):
    def setUp(self):
        super().setUp()
        self.accounts.environment['INTL_APP_BASE_URL'] = 'https://intl.example.test'
        self.accounts.environment['CN_APP_BASE_URL'] = 'https://cn.example.test'
        self.memberships = MembershipService(self.accounts)

    def new_international_user(self):
        invitation = self.accounts.create_invitation('INTL-' + new_id(), max_uses=1, created_by=str(self.admin['id']))
        with site_context('intl'):
            user = self.accounts.register('intl-' + new_id() + '@local.test', 'international test password', invitation['code'])['user']
        self.verify(str(user['id']))
        return str(user['id'])

    def grant(self, user_id):
        return self.memberships.create_manual_order(str(self.admin['id']), user_id, 'advanced-v1',
            utcnow() - timedelta(minutes=1), utcnow() + timedelta(days=30), 'shared entitlement test', 1900, new_id())

    def test_both_entries_require_invitation_for_registration(self):
        for site in ('cn', 'intl'):
            with site_context(site), self.assertRaises(SaaSError) as error:
                self.accounts.register(site + '-' + new_id() + '@local.test', 'registration test password', '')
            self.assertEqual(error.exception.code, 'invitation_required')
        user_id = self.new_international_user()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT account_resource_policy,plan_version FROM users WHERE id=%s', (user_id,))
                self.assertEqual(cursor.fetchone(), ('commercial', None))
        self.assertEqual(self.resources.usage(user_id)['limits']['video_library_capacity'], 2)

    def test_paid_entitlements_and_daily_usage_are_shared_across_sites(self):
        user_id = self.new_international_user()
        with site_context('cn'):
            first = self.resources.reserve(user_id, 'ai_context_generations', 'shared-site-operation')
            self.resources.settle(user_id, first['reservation']['id'])
        with site_context('intl'):
            replay = self.resources.reserve(user_id, 'ai_context_generations', 'shared-site-operation')
            self.assertEqual(first['reservation']['id'], replay['reservation']['id'])
            self.grant(user_id)
            international = self.resources.usage(user_id)
            membership = self.memberships.usage(user_id)
        with site_context('cn'):
            domestic = self.resources.usage(user_id)
        self.assertEqual(domestic, international)
        self.assertEqual(membership['mediaCapacity'], domestic['mediaCapacity'])
        self.assertEqual(membership['limits'], domestic['limits'])
        self.assertNotIn('plan', domestic)
        self.assertNotIn('subscription', domestic)
        ai = next(item for item in domestic['usage'] if item['feature'] == 'ai_context_generations')
        self.assertTrue(ai['unlimited'])
        self.assertEqual(ai['used'], 1)

    def test_device_login_enforces_the_same_account_quota_on_both_entries(self):
        user_id = self.new_international_user()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT email FROM users WHERE id=%s', (user_id,))
                email = cursor.fetchone()[0]
        for site in ('cn', 'intl'):
            with site_context(site):
                self.accounts.login(email, 'international test password', 'shared-device-same-0001')
        limit = self.resources.usage(user_id)['limits']['devices']
        for index in range(1, limit):
            self.accounts.login(email, 'international test password', f'shared-device-extra-{index:04d}')
        with site_context('cn'), self.assertRaises(SaaSError) as rejected:
            self.accounts.login(email, 'international test password', 'shared-device-overflow-0001')
        self.assertEqual(rejected.exception.code, 'device_limit_exceeded')
        self.assertEqual(rejected.exception.details['limit'], self.resources.usage(user_id)['limits']['devices'])

    def test_private_account_keeps_capacity_after_paid_subscription_expires(self):
        user_id = str(self.user['id'])
        before = self.resources.usage(user_id)['limits']
        self.grant(user_id)
        self.assertEqual(self.resources.usage(user_id)['limits'], before)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE subscriptions SET ends_at=NOW()-interval '1 second' WHERE user_id=%s", (user_id,))
        self.assertEqual(self.resources.usage(user_id)['limits'], before)

    def test_purchase_guidance_only_exposes_commercial_state_on_international_entry(self):
        user_id = self.new_international_user()
        commerce = CommerceService(self.accounts)
        actor = str(self.admin['id'])
        product = commerce.create_product(actor, 'journey-' + new_id()[:12], 'advanced', 999)
        version = commerce.create_version(actor, product['id'], {
            'name': 'Journey test', 'shortName': 'Test', 'tagline': 'Test guidance', 'description': 'Integration test only.',
            'durationDays': 30, 'amountCents': 1900, 'purchaseUrl': 'https://catfk.com/shop/TEST1234',
            'featureLimits': {'video_library_capacity': 20, 'audio_library_capacity': 50, 'storage_bytes': 5}, 'configuredBenefitIds': [],
        })
        commerce.publish_version(actor, version['id'])
        journey = JourneyService(self.accounts)
        with site_context('intl'):
            state = journey.update(user_id, {'action': 'plan_selected', 'productVersionId': version['id'], 'idempotencyKey': new_id()})
            self.assertEqual(state['pendingPurchase']['phase'], 'selected')
        with site_context('cn'):
            self.assertNotIn('pendingPurchase', journey.state(user_id))
            with self.assertRaises(SaaSError) as rejected:
                journey.update(user_id, {'action': 'clear_purchase'})
            self.assertEqual(rejected.exception.status, 404)
        with site_context('intl'):
            self.assertIsNotNone(journey.state(user_id)['pendingPurchase'])
            self.assertIsNone(journey.update(user_id, {'action': 'clear_purchase'})['pendingPurchase'])


if __name__ == '__main__':
    unittest.main()
