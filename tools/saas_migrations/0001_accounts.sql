-- Phase 1: identity, sessions, invitations, and a PostgreSQL landing area for
-- migrated single-user data.  IDs are generated in application code so this
-- migration does not require pgcrypto or uuid-ossp extensions.

CREATE TABLE IF NOT EXISTS roles (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'deleted')),
  email_verified_at TIMESTAMPTZ,
  plan_version TEXT NOT NULL DEFAULT 'free-v1',
  timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_login_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS user_roles (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS user_sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  device_id TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  csrf_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  revoked_at TIMESTAMPTZ,
  ip_address TEXT NOT NULL DEFAULT '',
  user_agent TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS user_sessions_active_idx ON user_sessions (user_id, expires_at) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  device_key TEXT NOT NULL,
  label TEXT NOT NULL DEFAULT '',
  user_agent TEXT NOT NULL DEFAULT '',
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  revoked_at TIMESTAMPTZ,
  UNIQUE (user_id, device_key)
);
CREATE INDEX IF NOT EXISTS devices_active_idx ON devices (user_id, last_seen_at DESC) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS email_verifications (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS invitations (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  max_uses INTEGER NOT NULL DEFAULT 1 CHECK (max_uses > 0),
  used_count INTEGER NOT NULL DEFAULT 0 CHECK (used_count >= 0),
  expires_at TIMESTAMPTZ,
  created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS invitation_uses (
  id TEXT PRIMARY KEY,
  invitation_id TEXT NOT NULL REFERENCES invitations(id) ON DELETE RESTRICT,
  user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ip_address TEXT NOT NULL DEFAULT '',
  UNIQUE (invitation_id, email)
);

-- These tables are the read-only migration landing area for the prior SQLite
-- library.  Their owner_id lets later phases enforce tenant boundaries before
-- the catalog/library UX is switched over.
CREATE TABLE IF NOT EXISTS content_books (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  title TEXT NOT NULL,
  english_title TEXT NOT NULL DEFAULT '',
  series TEXT NOT NULL DEFAULT '',
  level TEXT NOT NULL DEFAULT '',
  source_type TEXT NOT NULL DEFAULT 'book',
  source_path TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ready',
  visibility TEXT NOT NULL DEFAULT 'private' CHECK (visibility IN ('private', 'draft', 'published', 'blocked')),
  cover_url TEXT NOT NULL DEFAULT '',
  page_base_url TEXT NOT NULL DEFAULT '',
  audio_url TEXT NOT NULL DEFAULT '',
  pdf_url TEXT NOT NULL DEFAULT '',
  video_url TEXT NOT NULL DEFAULT '',
  duration DOUBLE PRECISION NOT NULL DEFAULT 0,
  alignment TEXT NOT NULL DEFAULT '',
  data_json JSONB NOT NULL,
  quality_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS content_books_owner_idx ON content_books (owner_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS content_vocabulary (
  legacy_id BIGINT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  book_id TEXT NOT NULL REFERENCES content_books(id) ON DELETE CASCADE,
  sentence_id TEXT NOT NULL,
  word_index INTEGER NOT NULL,
  payload JSONB NOT NULL,
  UNIQUE (owner_id, book_id, sentence_id, word_index)
);

CREATE TABLE IF NOT EXISTS content_word_annotations (
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  book_id TEXT NOT NULL REFERENCES content_books(id) ON DELETE CASCADE,
  sentence_id TEXT NOT NULL,
  word_index INTEGER NOT NULL,
  payload JSONB NOT NULL,
  PRIMARY KEY (owner_id, book_id, sentence_id, word_index)
);

CREATE TABLE IF NOT EXISTS content_learning_daily (
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  day DATE NOT NULL,
  payload JSONB NOT NULL,
  PRIMARY KEY (owner_id, day)
);

CREATE TABLE IF NOT EXISTS content_sentence_grammar (
  book_id TEXT NOT NULL REFERENCES content_books(id) ON DELETE CASCADE,
  sentence_id TEXT NOT NULL,
  payload JSONB NOT NULL,
  PRIMARY KEY (book_id, sentence_id)
);
