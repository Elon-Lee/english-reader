"""Account learning plans and factual dashboard summaries."""
from datetime import timedelta
import json

from saas_auth import SaaSError
from saas_membership import as_json, timestamp
from saas_rewards import local_day

DEFAULT_PLAN = {'readingMinutes': 10, 'reviewWords': 5, 'weeklyMinutes': 120}


class LearningService:
    def __init__(self, workspace, review):
        self.workspace, self.review = workspace, review
        self.accounts = workspace.accounts

    def update_plan(self, user_id, payload):
        allowed = {'readingMinutes': (5, 10, 15, 20, 30), 'reviewWords': (5, 10, 20),
                   'weeklyMinutes': (30, 60, 90, 120, 180, 240, 300)}
        if set(payload) != set(allowed) or any(type(payload[k]) is not int or payload[k] not in values for k, values in allowed.items()):
            raise SaaSError('invalid_learning_plan', '请选择有效的听读、复习和每周目标。', 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                self.workspace._user(cursor, user_id)
                cursor.execute("""INSERT INTO workspace_settings(user_id,key,value_json) VALUES(%s,'learning_plan',%s::jsonb)
                    ON CONFLICT(user_id,key) DO UPDATE SET value_json=EXCLUDED.value_json,updated_at=NOW()""",
                    (user_id, json.dumps(payload)))
        return {'plan': dict(payload)}

    def state(self, user_id):
        review = self.review.state(user_id)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                user = self.workspace._user(cursor, user_id)
                today = local_day(user['timezone'])
                monday = today - timedelta(days=today.weekday())
                cursor.execute("SELECT value_json FROM workspace_settings WHERE user_id=%s AND key='learning_plan'", (user_id,))
                row = self.accounts._one(cursor)
                plan = {**DEFAULT_PLAN, **(as_json(row['value_json']) if row else {})}
                cursor.execute("SELECT day,payload FROM content_learning_daily WHERE owner_id=%s AND day<=%s ORDER BY day DESC LIMIT 730", (user_id, today))
                rows = self.accounts._many(cursor)
                days = [{'day': row['day'].isoformat(), 'payload': as_json(row['payload'])} for row in rows]
                active = {row['day'] for row in rows if any(float(as_json(row['payload']).get(key) or 0) > 0 for key in ('reading_seconds', 'sentences', 'reviews', 'shadow_attempts'))}
                current = today if today in active else today-timedelta(days=1)
                streak = 0
                while current in active:
                    streak += 1
                    current -= timedelta(days=1)
                today_payload = next((as_json(row['payload']) for row in rows if row['day'] == today), {})
                week_seconds = sum(float(as_json(row['payload']).get('reading_seconds') or 0) for row in rows if row['day'] >= monday)
                cursor.execute("""SELECT COUNT(*) AS total FROM content_vocabulary WHERE owner_id=%s
                    AND (created_at AT TIME ZONE %s)::date=%s""", (user_id, user['timezone'], today))
                new_words = int(self.accounts._one(cursor)['total'])
                cursor.execute("""SELECT reading_seconds,sentences,created_at FROM workspace_activity_events
                    WHERE user_id=%s AND reading_seconds>0 ORDER BY created_at DESC LIMIT 1""", (user_id,))
                last = self.accounts._one(cursor)
        def session_summary(session):
            return {key: value for key, value in session.items() if key not in ('current', 'weakWords')} if session else None
        return {'today': {'day': today.isoformat(), 'readingSeconds': float(today_payload.get('reading_seconds') or 0),
                          'reviewedWords': review['stats']['todayReviewed'], 'newWords': new_words},
                'week': {'start': monday.isoformat(), 'readingSeconds': week_seconds},
                'learningStreak': streak, 'timezone': user['timezone'], 'plan': plan, 'days': days,
                'review': {'stats': review['stats'], 'active': session_summary(review['active']), 'latest': session_summary(review['latest'])},
                'lastReading': {'readingSeconds': int(last['reading_seconds']), 'sentences': int(last['sentences']), 'savedAt': timestamp(last['created_at'])} if last else None}
