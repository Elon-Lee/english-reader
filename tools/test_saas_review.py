"""Real PostgreSQL coverage for review scheduling, recovery and atomic saves."""
import http.client
import json
import socket
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from saas_auth import SaaSError, new_id, utcnow
from saas_review import ReviewService, due_time, next_interval
from test_saas_phase7_integration import PrivateWorkspaceTests as Fixtures


class ReviewTests(unittest.TestCase):
    setUpClass = classmethod(Fixtures.setUpClass.__func__)
    tearDownClass = classmethod(Fixtures.tearDownClass.__func__)
    verify = Fixtures.verify
    create_private_book = Fixtures.create_private_book

    def setUp(self):
        Fixtures.setUp(self)
        self.uid = str(self.owner['id'])
        self.review = ReviewService(self.workspace)

    def word(self, index=0, **payload):
        return self.workspace.save_vocabulary(self.uid, self.book_id, 's1', index,
            {'word': f'word{index}', 'meaning': '词义', 'context': 'A familiar sentence.', **payload})

    def start(self, **data):
        return self.review.start(self.uid, {'size': 5, 'scope': 'due', 'idempotencyKey': new_id(), **data})['session']

    def answer(self, session, rating='good', **data):
        return self.review.answer(self.uid, {'sessionId': session['id'], 'step': session['step'],
            'attemptKey': new_id(), 'rating': rating, **data})['session']

    def test_queue_empty_and_scope_validation(self):
        with self.assertRaises(SaaSError) as exc: self.start()
        self.assertEqual(exc.exception.code, 'review_queue_empty')
        with self.assertRaises(SaaSError): self.start(size=True)
        with self.assertRaises(SaaSError): self.start(scope='fake')
        self.word(due_at=(utcnow()+timedelta(days=5)).isoformat())
        with self.assertRaises(SaaSError): self.start()
        self.assertEqual(self.start(scope='all')['total'], 1)

    def test_resume_creation_retry_and_completed_creation_retry(self):
        self.word()
        session = self.start(idempotencyKey='same-start')
        self.assertEqual(self.start()['id'], session['id'])
        with self.assertRaises(SaaSError): self.start(idempotencyKey='same-start', size=20)
        self.assertEqual(self.review.state(self.uid)['active']['id'], session['id'])
        done = self.answer(session)
        self.assertEqual(done['status'], 'completed')
        self.assertEqual(self.start(idempotencyKey='same-start')['id'], session['id'])
        self.assertIsNone(self.review.state(self.uid)['active'])

    def test_atomic_answer_and_idempotency_conflict(self):
        self.word()
        session = self.start()
        body = {'sessionId': session['id'], 'step': 0, 'attemptKey': 'stable', 'rating': 'good'}
        first = self.review.answer(self.uid, body)
        second = self.review.answer(self.uid, body)
        self.assertFalse(first['idempotent']); self.assertTrue(second['idempotent'])
        self.assertEqual(self.workspace.learning_days(self.uid)['days'][0]['payload']['reviews'], 1)
        self.assertEqual(self.workspace.vocabulary(self.uid)['items'][0]['payload']['reviews'], 1)
        self.assertEqual(self.review.state(self.uid)['stats']['todayReviewed'], 1)
        with self.assertRaises(SaaSError): self.review.answer(self.uid, {**body, 'rating': 'easy'})
        with self.assertRaises(SaaSError): self.review.answer(self.uid, {**body, 'attemptKey': 'different'})

    def test_failed_save_rolls_back_everything(self):
        self.word()
        session = self.start()
        with patch('saas_review.new_id', side_effect=RuntimeError('forced failure after vocabulary update')):
            with self.assertRaises(RuntimeError): self.answer(session)
        self.assertEqual(self.review.state(self.uid)['active']['step'], 0)
        self.assertNotIn('reviews', self.workspace.vocabulary(self.uid)['items'][0]['payload'])
        self.assertEqual(self.workspace.learning_days(self.uid)['days'], [])

    def test_concurrent_answers_only_advance_once(self):
        self.word(); session = self.start()
        body = {'sessionId': session['id'], 'step': 0, 'attemptKey': 'parallel', 'rating': 'good'}
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.review.answer(self.uid, body), range(4)))
        self.assertEqual(sum(not result['idempotent'] for result in results), 1)
        self.assertEqual(self.workspace.learning_days(self.uid)['days'][0]['payload']['reviews'], 1)

    def test_weak_word_repeats_once_and_does_not_inflate_word_count(self):
        self.word(); session = self.start()
        retry = self.answer(session, 'again')
        self.assertEqual(retry['attemptTotal'], 2); self.assertTrue(retry['current']['repeated'])
        done = self.answer(retry, 'good')
        self.assertEqual(done['status'], 'completed'); self.assertEqual(done['completed'], 1)
        self.assertEqual(done['firstRemembered'], 0); self.assertEqual(done['reinforced'], 1)
        self.assertEqual(done['weakCount'], 0)
        self.assertEqual(self.review.state(self.uid)['stats']['todayReviewed'], 1)
        self.assertEqual(self.workspace.vocabulary(self.uid)['items'][0]['payload']['interval_days'], 1)

    def test_repeated_failure_still_completes(self):
        self.word(); session = self.answer(self.start(), 'hard')
        done = self.answer(session, 'again')
        self.assertEqual(done['status'], 'completed'); self.assertEqual(done['weakCount'], 1)
        self.assertEqual(done['attemptTotal'], 2)

    def test_skip_reinforcement_preserves_weak_result(self):
        self.word(); session = self.answer(self.start(), 'again')
        done = self.answer(session, 'skip')
        self.assertEqual(done['weakCount'], 1)
        self.assertEqual(done['completed'], 1)
        self.assertEqual(done['reinforced'], 0)

    def test_failure_after_daily_write_rolls_back_receipt_and_progress(self):
        self.word(); session = self.start()
        with patch.object(self.review, '_view', side_effect=RuntimeError('forced final response failure')):
            with self.assertRaises(RuntimeError): self.answer(session)
        self.assertEqual(self.review.state(self.uid)['active']['step'], 0)
        self.assertEqual(self.review.state(self.uid)['stats']['todayReviewed'], 0)
        self.assertEqual(self.workspace.learning_days(self.uid)['days'], [])

    def test_hint_is_not_independent_recall(self):
        self.word(); done = self.answer(self.start(), hinted=True)
        self.assertEqual(done['firstRemembered'], 0)
        self.assertEqual(self.workspace.vocabulary(self.uid)['items'][0]['payload']['interval_days'], 1)

    def test_source_revocation_skips_without_fabricating_activity(self):
        self.word(); session = self.start()
        with self.accounts.transaction() as connection:
            connection.execute("UPDATE content_books SET visibility='blocked' WHERE id=%s", (self.book_id,))
        self.assertIsNone(self.review.state(self.uid)['active']['current']['item'])
        with self.assertRaises(SaaSError): self.answer(session)
        done = self.answer(session, 'skip')
        self.assertEqual(done['completed'], 0); self.assertEqual(done['skipped'], 1)
        self.assertEqual(self.review.state(self.uid)['stats']['todayReviewed'], 0)

    def test_other_owner_cannot_read_or_answer_session(self):
        self.word(); session = self.start()
        other_id = str(self.other['id'])
        self.assertEqual(self.review.state(other_id)['items'], [])
        with self.assertRaises(SaaSError) as exc:
            self.review.answer(other_id, {'sessionId': session['id'], 'step': 0, 'attemptKey': 'foreign', 'rating': 'good'})
        self.assertEqual(exc.exception.status, 404)

    def test_missing_meaning_can_only_be_skipped(self):
        self.word(meaning=''); session = self.start()
        with self.assertRaises(SaaSError): self.answer(session)
        self.assertEqual(self.answer(session, 'skip')['completed'], 0)

    def test_schedule_is_bounded_and_invalid_dates_are_due(self):
        self.assertLess(due_time({'due_at': 'bad'}), utcnow())
        self.assertEqual(next_interval({'interval_days': 'bad'}, 'good', False, False), 2)
        self.assertEqual(next_interval({'interval_days': 60}, 'easy', False, False), 90)
        self.assertAlmostEqual(next_interval({}, 'again', False, False), 10 / 1440)

    def test_official_source_access(self):
        self.word()
        with self.accounts.transaction() as connection:
            connection.execute("INSERT INTO catalog_books(id,source_content_book_id,title,rights_status,publication_status) VALUES('review-official',%s,'官方来源','licensed','published')", (self.book_id,))
            connection.execute("INSERT INTO user_library(id,user_id,catalog_book_id) VALUES(%s,%s,'review-official')", (new_id(), self.uid))
        session = self.start()
        self.assertTrue(session['current']['item']['official'])
        self.assertEqual(session['current']['item']['bookId'], 'review-official')
        self.assertEqual(self.answer(session)['status'], 'completed')

    def test_http_auth_csrf_and_recovery(self):
        self.word()
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
        process = subprocess.Popen([sys.executable, 'tools/reader_server.py'], env={**self.environment,
            'READER_HOST': '127.0.0.1', 'READER_PORT': str(port), 'BOOTSTRAP_ADMIN_EMAIL': '', 'BOOTSTRAP_ADMIN_PASSWORD': ''},
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        def request(path, method='GET', body=None, cookies='', csrf=''):
            client = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            headers = {'Content-Type': 'application/json', 'Cookie': cookies, 'X-Device-Id': 'vocabulary-review-http'}
            if csrf: headers['X-CSRF-Token'] = csrf
            try:
                client.request(method, path, json.dumps(body) if body is not None else None, headers)
                response = client.getresponse()
                return response.status, response.getheaders(), json.loads(response.read())
            finally: client.close()
        try:
            for _ in range(100):
                try:
                    if request('/api/health')[0] == 200: break
                except OSError: time.sleep(.1)
            self.assertEqual(request('/api/workspace/review')[0], 401)
            status, headers, _ = request('/api/auth/login', 'POST', {'email': 'workspace-owner@local.test', 'password': 'workspace owner password'})
            self.assertEqual(status, 200)
            cookies = '; '.join(value.split(';', 1)[0] for name, value in headers if name.lower() == 'set-cookie')
            csrf = next(value.split('=', 1)[1] for value in cookies.split('; ') if value.startswith('shiyue_csrf='))
            self.assertEqual(request('/api/workspace/review/start', 'POST', {}, cookies)[0], 403)
            self.assertEqual(request('/api/workspace/review/answer', 'POST', {}, cookies)[0], 403)
            status, _, result = request('/api/workspace/review/start', 'POST', {'size': 5, 'scope': 'due', 'idempotencyKey': 'http-start'}, cookies, csrf)
            self.assertEqual(status, 200); session = result['session']
            self.assertEqual(request('/api/workspace/review', cookies=cookies)[2]['active']['id'], session['id'])
            body = {'sessionId': session['id'], 'step': 0, 'rating': 'good', 'attemptKey': 'http-answer'}
            self.assertEqual(request('/api/workspace/review/answer', 'POST', body, cookies, csrf)[2]['session']['status'], 'completed')
            self.assertTrue(request('/api/workspace/review/answer', 'POST', body, cookies, csrf)[2]['idempotent'])
            self.assertEqual(request('/api/rewards/status', cookies=cookies)[2]['balance'], 2)
            with self.accounts.transaction() as connection:
                connection.execute('UPDATE users SET email_verified_at=NULL WHERE id=%s', (self.uid,))
            self.assertEqual(request('/api/workspace/review', cookies=cookies)[0], 403)
            self.assertEqual(request('/api/workspace/review/start', 'POST', {}, cookies, csrf)[0], 403)
        finally:
            process.terminate(); process.wait(timeout=10)
            process.stderr.close()


if __name__ == '__main__': unittest.main()
