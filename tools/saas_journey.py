"""Account-scoped learning guidance and learning activity summaries."""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from saas_auth import SaaSError, SaaSService, new_id, utcnow
from saas_resources import as_json, timestamp


def learning_milestone(cursor: Any, user_id: str, event: str) -> None:
    if event not in {"first_reading", "first_word_saved"}:
        raise ValueError("Unknown learning milestone")
    cursor.execute("""INSERT INTO product_journey_events(id,user_id,event_type,idempotency_key)
        VALUES(%s,%s,%s,%s) ON CONFLICT(user_id,idempotency_key) DO NOTHING""",
        (new_id(), user_id, event, f"milestone:{event}"))


class JourneyService:
    def __init__(self, accounts: SaaSService):
        self.accounts = accounts

    def _user(self, cursor: Any, user_id: str) -> None:
        cursor.execute("SELECT id FROM users WHERE id=%s AND status='active' FOR UPDATE", (user_id,))
        if not cursor.fetchone():
            raise SaaSError("account_unavailable", "账号不可用。", 403)

    def _state(self, cursor: Any, user_id: str) -> dict[str, Any]:
        cursor.execute("SELECT key,value_json FROM workspace_settings WHERE user_id=%s AND key='learning_guide'", (user_id,))
        settings = {row["key"]: as_json(row["value_json"]) for row in self.accounts._many(cursor)}
        cursor.execute("""SELECT
            EXISTS(SELECT 1 FROM reward_activity_events WHERE user_id=%s AND reading_seconds>0)
              OR EXISTS(SELECT 1 FROM content_learning_daily WHERE owner_id=%s AND COALESCE((payload->>'reading_seconds')::numeric,0)>0) AS has_read,
            EXISTS(SELECT 1 FROM content_vocabulary WHERE owner_id=%s) AS has_word,
            EXISTS(SELECT 1 FROM user_library WHERE user_id=%s)
              OR EXISTS(SELECT 1 FROM content_books b WHERE owner_id=%s AND visibility='private'
                AND NOT EXISTS(SELECT 1 FROM catalog_books c WHERE c.source_content_book_id=b.id)) AS has_book""",
            (user_id, user_id, user_id, user_id, user_id))
        learning = self.accounts._one(cursor)
        return {"guide": {"dismissed": bool(settings.get("learning_guide", {}).get("dismissed")),
                           "hasBook": bool(learning["has_book"]), "hasRead": bool(learning["has_read"]), "hasWord": bool(learning["has_word"])}}

    def state(self, user_id: str) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                self._user(cursor, user_id)
                return self._state(cursor, user_id)

    def update(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        if action not in {"dismiss_guide", "restore_guide"}:
            raise SaaSError("invalid_journey_action", "操作无效。", 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                self._user(cursor, user_id)
                self._setting(cursor, user_id, "learning_guide", {"dismissed": action == "dismiss_guide"})
                return self._state(cursor, user_id)

    @staticmethod
    def _setting(cursor: Any, user_id: str, key: str, value: dict[str, Any]) -> None:
        cursor.execute("""INSERT INTO workspace_settings(user_id,key,value_json) VALUES(%s,%s,%s::jsonb)
            ON CONFLICT(user_id,key) DO UPDATE SET value_json=EXCLUDED.value_json,updated_at=NOW()""", (user_id, key, json.dumps(value)))

    def report(self, days: Any = 30) -> dict[str, Any]:
        try:
            days = int(days)
        except (ValueError, TypeError) as exc:
            raise SaaSError("invalid_report_period", "统计周期无效。", 400) from exc
        if days not in {7, 30, 90}:
            raise SaaSError("invalid_report_period", "请选择 7、30 或 90 天。", 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT applied_at FROM schema_migrations WHERE version='0038_product_journey.sql'")
                started = self.accounts._one(cursor)["applied_at"]
                since = max(started, utcnow() - timedelta(days=days))
                cursor.execute("""WITH cohort AS (SELECT id,email_verified_at FROM users WHERE created_at>=%s),
                    milestones AS (SELECT c.id,c.email_verified_at,
                      MIN(e.created_at) FILTER(WHERE event_type='first_reading') AS first_read,
                      MIN(e.created_at) FILTER(WHERE event_type='first_word_saved') AS first_word
                      FROM cohort c LEFT JOIN product_journey_events e ON e.user_id=c.id GROUP BY c.id,c.email_verified_at),
                    stages AS (SELECT *, (GREATEST(first_read,first_word) AT TIME ZONE 'Asia/Shanghai')::date AS first_day FROM milestones)
                    SELECT COUNT(*) AS registered,COUNT(*) FILTER(WHERE email_verified_at IS NOT NULL) AS verified,
                      COUNT(*) FILTER(WHERE first_read IS NOT NULL) AS reading,
                      COUNT(*) FILTER(WHERE first_read IS NOT NULL AND first_word IS NOT NULL) AS saved_word,
                      COUNT(*) FILTER(WHERE first_read IS NOT NULL AND first_word IS NOT NULL
                        AND first_day+1<(NOW() AT TIME ZONE 'Asia/Shanghai')::date) AS return_eligible,
                      COUNT(*) FILTER(WHERE first_read IS NOT NULL AND first_word IS NOT NULL
                        AND first_day+1<(NOW() AT TIME ZONE 'Asia/Shanghai')::date
                        AND (EXISTS(SELECT 1 FROM reward_activity_events a WHERE a.user_id=stages.id
                          AND a.reading_seconds>0 AND (a.created_at AT TIME ZONE 'Asia/Shanghai')::date=first_day+1)
                          OR EXISTS(SELECT 1 FROM workspace_activity_events a WHERE a.user_id=stages.id
                          AND a.reading_seconds>0 AND (a.created_at AT TIME ZONE 'Asia/Shanghai')::date=first_day+1))) AS returned
                    FROM stages""", (since,))
                learning = {key: int(value) for key, value in self.accounts._one(cursor).items()}
                return {"days": days, "measurementStartedAt": timestamp(started), "since": timestamp(since),
                        "timezone": "Asia/Shanghai", "learning": learning}
