#!/usr/bin/env python3
"""Real PostgreSQL races for library access and membership writes; test DB only."""
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import test_saas_phase3_integration as fixtures
from saas_auth import SaaSError, new_id, utcnow
from saas_admin import AdminService
from saas_commerce import CommerceService
from saas_ai import WorkspaceAIService as AIService
from saas_imports import WorkspaceImportService
from saas_media import MediaService
from saas_mbdpay import MbdPayService
from saas_redemptions import RedemptionService
from saas_rewards import RewardService, MONTHLY_GROWTH_CAP, local_day
from saas_workspace import WorkspaceService


class EntitlementConcurrencyTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.PhaseThreePostgresTests.setUpClass.__func__)
    setUp = fixtures.PhaseThreePostgresTests.setUp
    verify = fixtures.PhaseThreePostgresTests.verify
    source = fixtures.PhaseThreePostgresTests.source
    publish = fixtures.PhaseThreePostgresTests.publish

    def race(self, fn, count=12):
        barrier = threading.Barrier(count)
        def run(index):
            barrier.wait(timeout=10)
            try:
                return fn(index)
            except SaaSError as exc:
                return exc
        with ThreadPoolExecutor(max_workers=count) as workers:
            return list(workers.map(run, range(count)))

    def limits(self, **limits):
        self.memberships.usage(str(self.alice['id']))
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE usage_periods SET limits_json=limits_json || %s::jsonb WHERE user_id=%s", (json.dumps(limits), self.alice['id']))

    def scalar(self, query, values=()):
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, values)
                return cursor.fetchone()[0]

    def test_library_duplicate_add_remove_and_legacy_access(self):
        user = str(self.alice['id']); book = self.publish(101)
        results = self.race(lambda _: self.catalog.add_or_unlock(user, book, False))
        self.assertTrue(all(isinstance(row, dict) for row in results))
        self.assertEqual(len(self.catalog.library(user)['items']), 1)
        self.assertEqual(len(self.catalog.reader(user, book)['book']['sentences']), 3)
        # An existing old unlock must never grant access after shelf removal.
        self.scalar("INSERT INTO official_book_unlocks(id,user_id,catalog_book_id,usage_period_id) SELECT %s,%s,%s,id FROM usage_periods WHERE user_id=%s LIMIT 1 RETURNING id", (new_id(), user, book, user))
        self.assertTrue(all(isinstance(row, dict) for row in self.race(lambda _: self.catalog.remove(user, book))))
        detail = self.catalog.detail(book, user)['book']
        self.assertFalse(detail['inLibrary']); self.assertFalse(detail['unlocked'])
        with self.assertRaises(SaaSError): self.catalog.reader(user, book)
        with self.assertRaises(SaaSError): WorkspaceService(self.accounts).save_progress(user, book, 's101-0')
        with self.assertRaises(SaaSError): AIService(self.accounts, self.memberships).context(user, book, 's101-0', 0, 'Sample')
        with self.assertRaises(SaaSError): RewardService(self.accounts, self.memberships).complete_book(user, book)
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'official.mp3').write_bytes(b'original audio')
            media = MediaService(self.accounts, self.memberships, Path(root))
            asset = media.register(str(self.admin['id']), str(self.admin['id']), 'official', 'official.mp3', 'audio', 'audio/mpeg', book)
            with self.assertRaises(SaaSError): media.stream(user, asset['id'])
            self.catalog.add_or_unlock(user, book, False)
            self.assertTrue(media.stream(user, asset['id'])['path'].is_file())

    def test_audio_video_limits_mix_private_official_readd_and_concurrency(self):
        user = str(self.alice['id'])
        self.limits(video_library_capacity=2, audio_library_capacity=2)
        for offset, kind in enumerate(('audio', 'video')):
            with self.subTest(kind=kind):
                private = self.source(200 + offset)
                with self.accounts.transaction() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("UPDATE content_books SET owner_id=%s,source_type=%s WHERE id=%s", (user, kind, private))
                books = [self.publish(210 + offset * 20 + i) for i in range(12)]
                with self.accounts.transaction() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("UPDATE catalog_books SET resource_type=%s WHERE id=ANY(%s)", (kind, books))
                results = self.race(lambda i: self.catalog.add_or_unlock(user, books[i], False))
                successes = [r for r in results if isinstance(r, dict)]
                self.assertEqual(len(successes), 1)
                self.assertEqual([r.code for r in results if isinstance(r, SaaSError)], ['media_capacity_exceeded'] * 11)
                chosen = successes[0]['bookId']
                self.catalog.remove(user, chosen)
                other = next(b for b in books if b != chosen)
                self.catalog.add_or_unlock(user, other, False)
                with self.assertRaises(SaaSError): self.catalog.add_or_unlock(user, chosen, True)
                with self.assertRaises(SaaSError): self.catalog.reader(user, chosen)
                capacity = self.memberships.usage(user)['mediaCapacity'][kind]
                self.assertEqual((capacity['used'], capacity['limit']), (2, 2))

    def test_quota_settlement_release_race_and_credit_adjustment(self):
        user = str(self.alice['id']); feature = 'ai_context_generations'
        reservation = self.memberships.reserve(user, feature, 'race-reserve')['reservation']
        results = self.race(lambda i: self.memberships.settle(user, reservation['id']) if i % 2 else self.memberships.release(user, reservation['id']))
        self.assertTrue(any(isinstance(r, dict) for r in results))
        state = self.scalar('SELECT state FROM quota_reservations WHERE id=%s', (reservation['id'],))
        count = self.scalar('SELECT COUNT(*) FROM usage_ledger WHERE reservation_id=%s', (reservation['id'],))
        self.assertEqual(count, int(state == 'settled'))
        self.race(lambda _: self.memberships.credit(user, feature, 3, 'same-credit'))
        self.race(lambda _: AdminService(self.accounts, self.memberships).adjust_quota(str(self.admin['id']), user, feature, 2, 'concurrency', 'same-adjust'))
        self.assertEqual(self.scalar("SELECT SUM(quantity) FROM usage_ledger WHERE user_id=%s AND idempotency_key IN ('same-credit','same-adjust')", (user,)), -5)
        with self.assertRaises(SaaSError): self.memberships.settle(str(self.bob['id']), reservation['id'])

    def test_manual_order_and_invite_allowance_idempotency(self):
        actor = str(self.admin['id']); user = str(self.alice['id'])
        start = utcnow() - timedelta(minutes=1); end = start + timedelta(days=30)
        results = self.race(lambda _: self.memberships.create_manual_order(actor, user, 'advanced-v1', start, end, idempotency_key='manual-repeat'))
        self.assertTrue(all(isinstance(r, dict) for r in results))
        self.assertEqual(len({r['order']['id'] for r in results}), 1)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM subscriptions WHERE user_id=%s', (user,)), 1)
        with self.assertRaises(SaaSError) as conflict:
            self.memberships.create_manual_order(actor, user, 'pro-v1', start, end, idempotency_key='manual-repeat')
        self.assertEqual(conflict.exception.code, 'idempotency_conflict')
        admin = AdminService(self.accounts, self.memberships)
        grants = self.race(lambda _: admin.grant_invite_allowance(actor, user, 2, 'same campaign', idempotency_key='invite-repeat'))
        self.assertEqual(len({r['id'] for r in grants}), 1)
        self.assertEqual(self.scalar('SELECT SUM(quantity_remaining) FROM member_invite_allowances WHERE user_id=%s', (user,)), 2)
        rewards = RewardService(self.accounts, self.memberships)
        invites = self.race(lambda _: rewards.issue_invite(user, 'same-member-invite'))
        self.assertEqual(len({r['id'] for r in invites}), 1)
        invites = self.race(lambda i: rewards.issue_invite(user, f'new-member-invite-{i}'))
        self.assertEqual(sum(isinstance(r, dict) for r in invites), 1)
        self.assertEqual(self.scalar('SELECT SUM(quantity_remaining) FROM member_invite_allowances WHERE user_id=%s', (user,)), 0)
        extensions = self.race(lambda _: self.memberships.update_subscription(actor, results[0]['subscription']['id'], 'extend', end + timedelta(days=1), idempotency_key='same-extension'))
        self.assertTrue(all(isinstance(r, dict) for r in extensions))
        self.assertEqual(self.scalar('SELECT ends_at FROM subscriptions WHERE id=%s', (results[0]['subscription']['id'],)), end + timedelta(days=1))

    def test_rewards_duplicate_events_and_concurrent_spending(self):
        user = str(self.alice['id']); rewards = RewardService(self.accounts, self.memberships)
        self.race(lambda _: rewards.checkin(user))
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM checkins WHERE user_id=%s', (user,)), 1)
        self.race(lambda _: rewards.activity(user, 60, 1, 0, 'same-activity'))
        self.assertEqual(self.scalar('SELECT SUM(reading_seconds) FROM reward_activity_events WHERE user_id=%s', (user,)), 60)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO reward_ledger(id,user_id,month_key,reward_day,event_type,event_key,points) VALUES(%s,%s,'2026-10',CURRENT_DATE,'test','funds',20)", (new_id(), user))
        rows = self.race(lambda _: rewards.redeem(user, 'ai_context_10', 'same-redemption'))
        self.assertEqual(sum(not r['idempotent'] for r in rows), 1)
        # Distinct requests compete for the actual remaining balance.
        self.race(lambda i: rewards.redeem(user, 'ai_context_10', f'unique-{i}'))
        self.assertGreaterEqual(rewards.status(user)['balance'], 0)

    def test_parallel_growth_awards_respect_monthly_cap(self):
        user = str(self.alice['id']); rewards = RewardService(self.accounts, self.memberships)
        def award(index):
            with self.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    return rewards._award(cursor, user, 'parallel_referral', str(index), MONTHLY_GROWTH_CAP, local_day('Asia/Shanghai'))
        rows = self.race(award)
        self.assertEqual(sum(rows), MONTHLY_GROWTH_CAP)
        self.assertEqual(rewards.status(user)['balance'], MONTHLY_GROWTH_CAP)

    def test_cloudcat_same_key_different_codes_and_single_code_multiple_users(self):
        redemptions = RedemptionService(self.accounts, self.memberships)
        commerce = CommerceService(self.accounts); actor = str(self.admin['id'])
        product = commerce.create_product(actor, 'race-' + new_id(), 'advanced')
        version = commerce.create_version(actor, product['id'], {
            'name': 'Concurrency month card', 'shortName': 'Month', 'durationDays': 30,
            'tagline': 'Concurrency validation', 'description': 'Isolated test membership.',
            'amountCents': 1900, 'featureLimits': {'video_library_capacity': 20, 'audio_library_capacity': 50, 'storage_bytes': 5},
            'configuredBenefitIds': [],
        })
        commerce.publish_version(actor, version['id'])
        batch = redemptions.generate(actor, version['id'], 3, 'test concurrency')
        codes = batch['codes']; user = str(self.alice['id'])
        results = self.race(lambda i: redemptions.redeem(user, codes[i % 2], 'same-operation'))
        self.assertTrue(all(isinstance(r, dict) for r in results))
        self.assertEqual(len({r['changeOrder']['id'] for r in results}), 1)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM commerce_redemption_codes WHERE redeemed_by=%s', (user,)), 1)
        users = (user, str(self.bob['id']))
        results = self.race(lambda i: redemptions.redeem(users[i % 2], codes[2]))
        winners = {r['changeOrder']['id'] for r in results if isinstance(r, dict)}
        self.assertEqual(len(winners), 1)

    def test_import_create_complete_and_cancel_concurrency(self):
        user = str(self.alice['id'])
        with tempfile.TemporaryDirectory() as root:
            media = MediaService(self.accounts, self.memberships, Path(root))
            imports = WorkspaceImportService(self.accounts, self.memberships, media)
            rows = self.race(lambda _: imports.create(user, 'text', 'same import', 'same.txt', 'same-import'))
            self.assertEqual(len({r['task']['id'] for r in rows}), 1)
            task = rows[0]['task']['id']
            uploaded = self.race(lambda _: imports.upload(user, task, 'same.txt', b'A real sentence.', 'text/plain'))
            self.assertTrue(all(isinstance(r, dict) for r in uploaded))
            self.assertEqual(len({r['sourceAssetId'] for r in uploaded}), 1)
            started = threading.Event(); proceed = threading.Event()
            original = imports._document_text
            def extract(*args):
                started.set(); self.assertTrue(proceed.wait(10)); return original(*args)
            with patch.object(imports, '_document_text', side_effect=extract) as processor:
                with ThreadPoolExecutor(max_workers=1) as worker:
                    future = worker.submit(imports.complete, user, task)
                    self.assertTrue(started.wait(10))
                    repeats = self.race(lambda _: imports.complete(user, task))
                    self.assertTrue(all(r['idempotent'] for r in repeats))
                    proceed.set(); self.assertEqual(future.result(timeout=10)['task']['status'], 'complete')
                self.assertEqual(processor.call_count, 1)
            self.assertEqual(self.scalar('SELECT COUNT(*) FROM content_books WHERE owner_id=%s', (user,)), 1)
            cancelled = imports.create(user, 'mp3', 'cancel', 'cancel.mp3', 'cancel-import')['task']['id']
            results = self.race(lambda _: imports.cancel(user, cancelled))
            self.assertTrue(all(isinstance(r, dict) for r in results))

    def test_storage_limit_and_ai_generation_concurrency(self):
        user = str(self.alice['id']); self.limits(storage_bytes=10)
        with tempfile.TemporaryDirectory() as root:
            media = MediaService(self.accounts, self.memberships, Path(root))
            for i in range(12): Path(root, f'{i}.bin').write_bytes(b'123456')
            rows = self.race(lambda i: media.register(user, user, 'private', f'{i}.bin'))
            self.assertEqual(sum(isinstance(r, dict) for r in rows), 1)
            self.assertEqual(self.scalar('SELECT SUM(charged_bytes) FROM asset_usage WHERE user_id=%s', (user,)), 6)
        book = self.publish(900); self.catalog.add_or_unlock(user, book, False)
        calls = []
        def generator(*args): calls.append(1); return {'text': 'Real test explanation'}
        ai = AIService(self.accounts, self.memberships, generator)
        rows = self.race(lambda _: ai.context(user, book, 's900-0', 0, 'Sample'))
        self.assertTrue(all(isinstance(r, dict) for r in rows))
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM usage_ledger WHERE user_id=%s AND feature='ai_context_generations' AND reason='consumption'", (user,)), 1)

    def test_private_import_and_official_add_share_last_audio_slot(self):
        user = str(self.alice['id']); self.limits(audio_library_capacity=1)
        official = self.publish(950)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE catalog_books SET resource_type='audio' WHERE id=%s", (official,))
        with tempfile.TemporaryDirectory() as root:
            media = MediaService(self.accounts, self.memberships, Path(root))
            imports = WorkspaceImportService(self.accounts, self.memberships, media)
            task = imports.create(user, 'mp3', 'Last slot', 'last.mp3', 'last-audio')['task']['id']
            imports.upload(user, task, 'last.mp3', b'original test audio', 'audio/mpeg')
            def extracted(source, task_id, title):
                return {'id': f'private-{task_id}', 'sentences': [{'id': 's1', 'text': 'A sentence.'}]}, {'extractor': 'test'}
            with patch.object(imports, '_audio_book', side_effect=extracted):
                rows = self.race(lambda i: imports.complete(user, task) if i == 0 else self.catalog.add_or_unlock(user, official, False), count=2)
            self.assertEqual(sum(isinstance(r, dict) for r in rows), 1)
            self.assertEqual(self.memberships.usage(user)['mediaCapacity']['audio']['used'], 1)
            if isinstance(rows[0], SaaSError):
                self.assertEqual(rows[0].code, 'media_capacity_exceeded')
                self.assertEqual(self.scalar("SELECT COUNT(*) FROM media_assets WHERE owner_id=%s AND status='active'", (user,)), 1)

    def test_cancel_during_upload_does_not_restore_task_or_keep_storage(self):
        user = str(self.alice['id'])
        with tempfile.TemporaryDirectory() as root:
            media = MediaService(self.accounts, self.memberships, Path(root))
            imports = WorkspaceImportService(self.accounts, self.memberships, media)
            task = imports.create(user, 'text', 'Cancelled upload', 'cancel.txt', 'upload-cancel')['task']['id']
            register = media.register
            def register_then_cancel(*args, **kwargs):
                asset = register(*args, **kwargs)
                imports.cancel(user, task)
                return asset
            with patch.object(media, 'register', side_effect=register_then_cancel):
                with self.assertRaises(SaaSError): imports.upload(user, task, 'cancel.txt', b'A cancelled upload.')
            self.assertEqual(self.scalar('SELECT status FROM workspace_import_tasks WHERE id=%s', (task,)), 'cancelled')
            self.assertEqual(self.scalar("SELECT COUNT(*) FROM media_assets WHERE owner_id=%s AND status='active'", (user,)), 0)

    def test_legacy_payment_callbacks_repeat_and_renew_without_lost_days(self):
        user = str(self.alice['id']); orders = [new_id() for _ in range(4)]
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                for order in orders:
                    cursor.execute("""INSERT INTO payment_orders(id,user_id,plan_version_id,provider,amount_cents,idempotency_key,duration_days)
                        VALUES(%s,%s,'advanced-v1','mbdpay',1900,%s,30)""", (order, user, order))
        service = MbdPayService(self.accounts, self.memberships)
        with patch.object(service, '_verified_remote_order', return_value={'state': 1, 'amount': 1900}):
            rows = self.race(lambda i: service.handle_webhook({'type': 'charge_succeeded', 'data': {'out_trade_no': orders[i % 4]}}))
        self.assertTrue(all(isinstance(r, dict) for r in rows))
        self.assertEqual(sum(r['status'] == 'processed' for r in rows), 4)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM subscriptions WHERE user_id=%s', (user,)), 1)
        self.assertGreater(self.scalar('SELECT MAX(ends_at) FROM subscriptions WHERE user_id=%s', (user,)), utcnow() + timedelta(days=119))

    def test_commerce_concurrent_versions_and_single_published_version(self):
        actor = str(self.admin['id']); commerce = CommerceService(self.accounts)
        product = commerce.create_product(actor, 'parallel-product-' + new_id(), 'advanced')
        def create(index):
            return commerce.create_version(actor, product['id'], {
                'name': f'Parallel version {index}', 'shortName': 'Parallel', 'durationDays': 30,
                'tagline': 'Concurrency', 'description': 'Test immutable entitlement versions.',
                'amountCents': 1900, 'featureLimits': {'video_library_capacity': 20, 'audio_library_capacity': 50, 'storage_bytes': 5}, 'configuredBenefitIds': [],
            })
        versions = self.race(create, count=4)
        self.assertTrue(all(isinstance(row, dict) for row in versions))
        self.assertEqual(self.scalar('SELECT COUNT(DISTINCT version_number) FROM commerce_product_versions WHERE product_id=%s', (product['id'],)), 4)
        published = self.race(lambda i: commerce.publish_version(actor, versions[i]['id']), count=4)
        self.assertTrue(all(isinstance(row, dict) for row in published))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM commerce_product_versions WHERE product_id=%s AND status='published'", (product['id'],)), 1)
        current = self.scalar("SELECT id FROM commerce_product_versions WHERE product_id=%s AND status='published'", (product['id'],))
        repeated = self.race(lambda _: commerce.publish_version(actor, current))
        self.assertTrue(all(row['idempotent'] for row in repeated))


if __name__ == '__main__':
    unittest.main()
