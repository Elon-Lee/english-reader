-- Phase 3: reviewed official catalog and a user-owned official library.
-- Existing content_books are deliberately not inserted here: every migrated
-- title remains the administrator's private content until explicitly reviewed.

CREATE TABLE IF NOT EXISTS catalog_series (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS catalog_tags (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS catalog_books (
  id TEXT PRIMARY KEY,
  source_content_book_id TEXT UNIQUE REFERENCES content_books(id) ON DELETE RESTRICT,
  series_id TEXT REFERENCES catalog_series(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  english_title TEXT NOT NULL DEFAULT '',
  author TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  level TEXT NOT NULL DEFAULT '',
  resource_type TEXT NOT NULL DEFAULT 'book' CHECK (resource_type IN ('book', 'audio', 'video', 'youtube')),
  estimated_minutes INTEGER NOT NULL DEFAULT 0 CHECK (estimated_minutes >= 0),
  sentence_count INTEGER NOT NULL DEFAULT 0 CHECK (sentence_count >= 0),
  word_count INTEGER NOT NULL DEFAULT 0 CHECK (word_count >= 0),
  cover_url TEXT NOT NULL DEFAULT '',
  preview_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  rights_status TEXT NOT NULL DEFAULT 'private' CHECK (rights_status IN ('public_domain', 'licensed', 'private', 'prohibited')),
  publication_status TEXT NOT NULL DEFAULT 'draft' CHECK (publication_status IN ('draft', 'published', 'archived')),
  featured_rank INTEGER NOT NULL DEFAULT 0,
  published_at TIMESTAMPTZ,
  created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  reviewed_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (publication_status <> 'published' OR rights_status IN ('public_domain', 'licensed'))
);
CREATE INDEX IF NOT EXISTS catalog_books_public_idx ON catalog_books(publication_status, rights_status, featured_rank DESC, published_at DESC);
CREATE INDEX IF NOT EXISTS catalog_books_series_idx ON catalog_books(series_id, level, resource_type);

CREATE TABLE IF NOT EXISTS catalog_book_tags (
  catalog_book_id TEXT NOT NULL REFERENCES catalog_books(id) ON DELETE CASCADE,
  tag_id TEXT NOT NULL REFERENCES catalog_tags(id) ON DELETE CASCADE,
  PRIMARY KEY (catalog_book_id, tag_id)
);

CREATE TABLE IF NOT EXISTS user_library (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  catalog_book_id TEXT NOT NULL REFERENCES catalog_books(id) ON DELETE CASCADE,
  shelf_state TEXT NOT NULL DEFAULT 'active' CHECK (shelf_state IN ('active', 'later')),
  added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, catalog_book_id)
);
CREATE INDEX IF NOT EXISTS user_library_user_idx ON user_library(user_id, shelf_state, added_at DESC);

CREATE TABLE IF NOT EXISTS official_book_unlocks (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  catalog_book_id TEXT NOT NULL REFERENCES catalog_books(id) ON DELETE RESTRICT,
  usage_period_id TEXT NOT NULL REFERENCES usage_periods(id) ON DELETE RESTRICT,
  reservation_id TEXT UNIQUE REFERENCES quota_reservations(id) ON DELETE SET NULL,
  unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, catalog_book_id)
);
CREATE INDEX IF NOT EXISTS official_book_unlocks_user_idx ON official_book_unlocks(user_id, unlocked_at DESC);
