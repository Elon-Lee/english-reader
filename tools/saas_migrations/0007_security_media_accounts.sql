-- Phase 6: media inventory, secure access, account lifecycle, and audits.

CREATE TABLE IF NOT EXISTS media_assets (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  scope TEXT NOT NULL CHECK (scope IN ('official', 'private')),
  kind TEXT NOT NULL DEFAULT 'media',
  content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
  original_bytes BIGINT NOT NULL DEFAULT 0 CHECK (original_bytes >= 0),
  generated_bytes BIGINT NOT NULL DEFAULT 0 CHECK (generated_bytes >= 0),
  sha256 TEXT NOT NULL,
  storage_path TEXT NOT NULL UNIQUE,
  content_book_id TEXT REFERENCES content_books(id) ON DELETE SET NULL,
  catalog_book_id TEXT REFERENCES catalog_books(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deleted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS media_assets_owner_idx ON media_assets(owner_id, scope, status);
CREATE INDEX IF NOT EXISTS media_assets_catalog_idx ON media_assets(catalog_book_id, status);

CREATE TABLE IF NOT EXISTS asset_variants (
  id TEXT PRIMARY KEY,
  asset_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
  variant_name TEXT NOT NULL,
  content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
  byte_size BIGINT NOT NULL CHECK (byte_size >= 0),
  sha256 TEXT NOT NULL,
  storage_path TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ,
  UNIQUE (asset_id, variant_name)
);
CREATE INDEX IF NOT EXISTS asset_variants_asset_idx ON asset_variants(asset_id, deleted_at);

CREATE TABLE IF NOT EXISTS asset_usage (
  asset_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  access_count BIGINT NOT NULL DEFAULT 0 CHECK (access_count >= 0),
  first_accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  charged_bytes BIGINT NOT NULL DEFAULT 0 CHECK (charged_bytes >= 0),
  PRIMARY KEY (asset_id, user_id)
);

CREATE TABLE IF NOT EXISTS account_deletion_requests (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK (status IN ('requested', 'cancelled', 'completed')),
  requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  scheduled_for TIMESTAMPTZ NOT NULL,
  cancelled_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS account_deletion_due_idx ON account_deletion_requests(status, scheduled_for);

CREATE TABLE IF NOT EXISTS security_events (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  ip_address TEXT NOT NULL DEFAULT '',
  event_type TEXT NOT NULL,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS security_events_created_idx ON security_events(created_at DESC);
