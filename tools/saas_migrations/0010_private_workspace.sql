-- Follow-up Phase 7: owner-scoped private learning workspace for migrated
-- content and future PostgreSQL-native importers.

CREATE SEQUENCE IF NOT EXISTS content_vocabulary_legacy_id_seq;
SELECT setval('content_vocabulary_legacy_id_seq', GREATEST((SELECT COALESCE(MAX(legacy_id),0)+1 FROM content_vocabulary),1), false);
ALTER TABLE content_vocabulary ALTER COLUMN legacy_id SET DEFAULT nextval('content_vocabulary_legacy_id_seq');

CREATE TABLE IF NOT EXISTS workspace_progress (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  content_book_id TEXT NOT NULL REFERENCES content_books(id) ON DELETE CASCADE,
  last_sentence_id TEXT NOT NULL DEFAULT '',
  reading_seconds BIGINT NOT NULL DEFAULT 0 CHECK (reading_seconds >= 0),
  completed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, content_book_id)
);

CREATE TABLE IF NOT EXISTS workspace_settings (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS workspace_activity_events (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  idempotency_key TEXT NOT NULL,
  content_book_id TEXT REFERENCES content_books(id) ON DELETE SET NULL,
  activity_day DATE NOT NULL,
  reading_seconds BIGINT NOT NULL DEFAULT 0 CHECK (reading_seconds >= 0),
  sentences INTEGER NOT NULL DEFAULT 0 CHECK (sentences >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS workspace_activity_user_idx ON workspace_activity_events(user_id, activity_day DESC);
