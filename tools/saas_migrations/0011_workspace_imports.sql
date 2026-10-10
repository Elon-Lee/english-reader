-- PostgreSQL-native private import task protocol. Every job captures its
-- creator, plan version and optional quota reservation before processing.

CREATE TABLE IF NOT EXISTS workspace_import_tasks (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  workspace_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('text', 'document', 'mp3', 'video', 'youtube')),
  status TEXT NOT NULL CHECK (status IN ('uploading', 'queued', 'running', 'complete', 'failed', 'cancelled', 'awaiting_processor')),
  title TEXT NOT NULL DEFAULT '',
  original_filename TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  source_asset_id TEXT REFERENCES media_assets(id) ON DELETE SET NULL,
  output_book_id TEXT REFERENCES content_books(id) ON DELETE SET NULL,
  quota_reservation_id TEXT REFERENCES quota_reservations(id) ON DELETE SET NULL,
  plan_version_id TEXT NOT NULL DEFAULT '',
  progress INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
  step TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  UNIQUE (user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS workspace_import_tasks_user_idx ON workspace_import_tasks(user_id, status, created_at DESC);
