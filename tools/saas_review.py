"""Durable, owner-scoped vocabulary recall sessions and atomic answer saves."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from saas_auth import SaaSError, new_id, utcnow
from saas_membership import as_json, timestamp
from saas_rewards import local_day


def due_time(payload: dict) -> datetime:
    try:
        value = datetime.fromisoformat(str(payload.get('due_at') or payload.get('dueAt') or '').replace('Z', '+00:00'))
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def next_interval(payload: dict, rating: str, repeated: bool, hinted: bool) -> float:
    try:
        previous = max(1, min(90, float(payload.get('interval_days') or 1)))
    except (ValueError, TypeError):
        previous = 1
    if rating == 'again':
        return 10 / 1440
    if repeated or hinted or rating == 'hard':
        return 1
    return min(90, max(2 if rating == 'good' else 4, previous * (2 if rating == 'good' else 3)))


class ReviewService:
    def __init__(self, workspace):
        self.workspace = workspace
        self.accounts = workspace.accounts

    def _items(self, cursor, user_id: str) -> list[dict]:
        cursor.execute("""SELECT v.legacy_id,v.sentence_id,v.word_index,v.payload,
            COALESCE(c.id,b.id) AS book_id,COALESCE(c.title,b.title) AS title,c.id IS NOT NULL AS official
            FROM content_vocabulary v JOIN content_books b ON b.id=v.book_id
            LEFT JOIN catalog_books c ON c.source_content_book_id=b.id
            WHERE v.owner_id=%s AND (
              (b.owner_id=%s AND b.visibility IN ('private','draft') AND c.id IS NULL) OR
              (c.publication_status='published' AND c.rights_status IN ('public_domain','licensed')
               AND EXISTS(SELECT 1 FROM user_library l WHERE l.user_id=%s AND l.catalog_book_id=c.id)))""",
            (user_id, user_id, user_id))
        return [{'id': int(row['legacy_id']), 'bookId': row['book_id'], 'sentenceId': row['sentence_id'],
                 'wordIndex': int(row['word_index']), 'payload': as_json(row['payload']),
                 'bookTitle': row['title'], 'official': row['official']} for row in self.accounts._many(cursor)]

    def _view(self, row: dict | None, items: list[dict]) -> dict | None:
        if not row:
            return None
        state = as_json(row['state_json'])
        by_id = {item['id']: item for item in items}
        queue, step = state['queue'], state['step']
        current = queue[step] if step < len(queue) else None
        current_item = by_id.get(current['id']) if current else None
        results = list(state['results'].values())
        weak = [result for result in results if result['firstRating'] in ('again', 'hard')]
        return {'id': row['id'], 'status': row['status'], 'step': step, 'total': state['total'],
                'attemptTotal': len(queue), 'completed': sum(result['firstRating'] != 'skip' for result in results),
                'skipped': sum(result['firstRating'] == 'skip' for result in results),
                'firstRemembered': sum(result['firstRating'] in ('good', 'easy') and not result['hinted'] for result in results),
                'reinforced': sum(result['firstRating'] in ('again', 'hard') and result['rating'] in ('good', 'easy') for result in results),
                'weakCount': sum(result['rating'] in ('again', 'hard') for result in results),
                'weakWords': [{'item': by_id.get(result['id']), 'rating': result['rating']} for result in weak if result['id'] in by_id],
                'current': {'item': current_item, 'repeated': current['repeated']} if current else None,
                'createdAt': timestamp(row['created_at']), 'updatedAt': timestamp(row['updated_at']),
                'nextDueAt': min((result['dueAt'] for result in results if result.get('dueAt')), default=None)}

    def state(self, user_id: str) -> dict:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                user = self.workspace._user(cursor, user_id)
                items = self._items(cursor, user_id)
                now, day = utcnow(), local_day(user['timezone'])
                due = [item for item in items if due_time(item['payload']) <= now]
                cursor.execute("SELECT * FROM vocabulary_review_sessions WHERE user_id=%s AND status='active'", (user_id,))
                active = self.accounts._one(cursor)
                cursor.execute("SELECT * FROM vocabulary_review_sessions WHERE user_id=%s AND status='completed' ORDER BY updated_at DESC LIMIT 1", (user_id,))
                latest = self.accounts._one(cursor)
                cursor.execute("""SELECT COUNT(DISTINCT a.vocabulary_id) FILTER(WHERE a.activity_day=%s) AS today,
                    COUNT(DISTINCT a.activity_day) AS days FROM vocabulary_review_answers a
                    JOIN vocabulary_review_sessions s ON s.id=a.session_id
                    WHERE s.user_id=%s AND a.activity_day BETWEEN %s AND %s AND a.rating<>'skip'""",
                    (day, user_id, day-timedelta(days=6), day))
                counts = self.accounts._one(cursor)
                future = [due_time(item['payload']) for item in items if due_time(item['payload']) > now]
                return {'active': self._view(active, items), 'latest': self._view(latest, items),
                        'stats': {'total': len(items), 'due': len(due), 'new': sum(not item['payload'].get('reviews') for item in due),
                                  'todayReviewed': int(counts['today']), 'reviewDays': int(counts['days']),
                                  'sources': len({item['bookId'] for item in items}),
                                  'nextDueAt': timestamp(min(future)) if future else None},
                        'items': items}

    def start(self, user_id: str, data: dict) -> dict:
        key = str(data.get('idempotencyKey') or '').strip()
        if not key or len(key) > 100:
            raise SaaSError('invalid_idempotency_key', '缺少本轮复习操作标识，请重试。', 400)
        size, scope = data.get('size', 10), data.get('scope', 'due')
        if type(size) is not int or size not in (5, 10, 20) or scope not in ('due', 'difficult', 'all', 'selected'):
            raise SaaSError('invalid_review_options', '请选择有效的复习范围和每轮词数。', 400)
        ids = data.get('vocabularyIds', [])
        if scope == 'selected' and (not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(type(value) is not int or value < 1 for value in ids)):
            raise SaaSError('invalid_review_options', '本次生词范围无效，请回到学习空间重新选择。', 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                self.workspace._user(cursor, user_id)
                items = self._items(cursor, user_id)
                cursor.execute("SELECT * FROM vocabulary_review_sessions WHERE user_id=%s AND (request_key=%s OR status='active') ORDER BY (request_key=%s) DESC LIMIT 1", (user_id, key, key))
                existing = self.accounts._one(cursor)
                if existing:
                    options = as_json(existing['state_json']).get('options', {})
                    if existing['request_key'] == key and options and options != ({'size': size, 'scope': scope, 'vocabularyIds': sorted(set(ids))} if scope == 'selected' else {'size': size, 'scope': scope}):
                        raise SaaSError('review_key_conflict', '同一操作标识不能创建不同的复习计划。', 409)
                    return {'session': self._view(existing, items)}
                selected = sorted((item for item in items if
                    (scope == 'all' or scope == 'selected' and item['id'] in ids or scope == 'due' and due_time(item['payload']) <= utcnow() or
                     scope == 'difficult' and item['payload'].get('rating') in ('again', 'hard')) and
                    str(item['payload'].get('word') or item['payload'].get('form') or '').strip()),
                    key=lambda item: (due_time(item['payload']), item['id']))[:size]
                if not selected:
                    raise SaaSError('review_queue_empty', '当前范围没有可复习的生词，请调整范围或先去阅读。', 409)
                state = {'queue': [{'id': item['id'], 'repeated': False} for item in selected],
                         'step': 0, 'total': len(selected), 'results': {}, 'version': 1,
                         'options': {'size': size, 'scope': scope, **({'vocabularyIds': sorted(set(ids))} if scope == 'selected' else {})}}
                cursor.execute("INSERT INTO vocabulary_review_sessions(id,user_id,request_key,state_json) VALUES(%s,%s,%s,%s::jsonb) RETURNING *",
                               (new_id(), user_id, key, json.dumps(state)))
                return {'session': self._view(self.accounts._one(cursor), items)}

    def answer(self, user_id: str, data: dict) -> dict:
        session_id, key = str(data.get('sessionId') or ''), str(data.get('attemptKey') or '')
        step, rating, hinted = data.get('step'), data.get('rating'), data.get('hinted', False)
        if not key or len(key) > 100 or type(step) is not int or rating not in ('again', 'hard', 'good', 'easy', 'skip') or type(hinted) is not bool:
            raise SaaSError('invalid_review_answer', '复习提交数据无效，请刷新后重试。', 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                user = self.workspace._user(cursor, user_id)
                cursor.execute("SELECT * FROM vocabulary_review_sessions WHERE id=%s AND user_id=%s FOR UPDATE", (session_id, user_id))
                row = self.accounts._one(cursor)
                if not row:
                    raise SaaSError('review_session_not_found', '这轮复习不存在或你无权访问。', 404)
                items = self._items(cursor, user_id)
                cursor.execute("SELECT step,rating,hinted FROM vocabulary_review_answers WHERE session_id=%s AND attempt_key=%s", (session_id, key))
                receipt = self.accounts._one(cursor)
                if receipt:
                    if receipt['step'] != step or receipt['rating'] != rating or receipt['hinted'] != hinted:
                        raise SaaSError('review_key_conflict', '同一操作标识不能提交不同答案。', 409)
                    return {'session': self._view(row, items), 'idempotent': True}
                state = as_json(row['state_json'])
                if row['status'] != 'active' or step != state['step']:
                    raise SaaSError('review_step_conflict', '复习进度已在其他页面更新，请同步进度后继续。', 409)
                entry = state['queue'][step]
                item = next((item for item in items if item['id'] == entry['id']), None)
                if not item and rating != 'skip':
                    raise SaaSError('review_source_unavailable', '来源已不可访问，请跳过此词继续。', 409)
                now, day = utcnow(), local_day(user['timezone'])
                due_at = None
                if rating != 'skip':
                    storage_id, _ = self.workspace._learning_book(cursor, user_id, item['bookId'], True)
                    cursor.execute('SELECT payload FROM content_vocabulary WHERE legacy_id=%s AND owner_id=%s FOR UPDATE', (item['id'], user_id))
                    current = self.accounts._one(cursor)
                    if not current:
                        raise SaaSError('review_source_unavailable', '生词已移除，请跳过此词继续。', 409)
                    payload = as_json(current['payload'])
                    if not str(payload.get('meaning') or '').strip():
                        raise SaaSError('review_meaning_missing', '该词缺少释义，请回原文补充或跳过。', 409)
                    interval = next_interval(payload, rating, entry['repeated'], hinted)
                    due_at = timestamp(now + timedelta(days=interval))
                    try:
                        reviews = max(0, int(payload.get('reviews') or 0))
                    except (ValueError, TypeError):
                        reviews = 0
                    payload.update({'rating': rating, 'interval_days': interval, 'due_at': due_at,
                                    'reviews': reviews+1, 'last_reviewed_at': timestamp(now), 'review_schedule_version': 1})
                    cursor.execute('UPDATE content_vocabulary SET payload=%s::jsonb WHERE legacy_id=%s AND owner_id=%s', (json.dumps(payload), item['id'], user_id))
                    cursor.execute("INSERT INTO workspace_activity_events(id,user_id,idempotency_key,content_book_id,activity_day) VALUES(%s,%s,%s,%s,%s)",
                                   (new_id(), user_id, f'review:{session_id}:{step}', storage_id, day))
                    cursor.execute("""INSERT INTO content_learning_daily(owner_id,day,payload) VALUES(%s,%s,%s::jsonb)
                        ON CONFLICT(owner_id,day) DO UPDATE SET payload=content_learning_daily.payload ||
                        jsonb_build_object('reviews',COALESCE((content_learning_daily.payload->>'reviews')::int,0)+1,'updated_at',%s::text)""",
                        (user_id, day, json.dumps({'reviews': 1, 'updated_at': timestamp(now)}), timestamp(now)))
                cursor.execute("""INSERT INTO vocabulary_review_answers(session_id,step,attempt_key,vocabulary_id,rating,repeated,hinted,activity_day)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""", (session_id, step, key, entry['id'], rating, entry['repeated'], hinted, day))
                previous = state['results'].get(str(entry['id']))
                state['results'][str(entry['id'])] = {'id': entry['id'], 'firstRating': previous['firstRating'] if previous else rating,
                    'hinted': previous['hinted'] if previous else hinted,
                    'rating': previous['rating'] if rating == 'skip' and previous else rating,
                    'dueAt': due_at or (previous or {}).get('dueAt')}
                if rating in ('again', 'hard') and not entry['repeated']:
                    state['queue'].append({'id': entry['id'], 'repeated': True})
                state['step'] += 1
                status = 'completed' if state['step'] >= len(state['queue']) else 'active'
                cursor.execute('UPDATE vocabulary_review_sessions SET state_json=%s::jsonb,status=%s,updated_at=NOW() WHERE id=%s RETURNING *',
                               (json.dumps(state), status, session_id))
                updated = self.accounts._one(cursor)
                if item and rating != 'skip':
                    item['payload'] = payload
                return {'session': self._view(updated, items), 'idempotent': False, 'nextDueAt': due_at}
