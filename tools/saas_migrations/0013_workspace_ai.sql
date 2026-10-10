-- Tenant-scoped cached AI results. Quota is charged only when a new input hash
-- is generated; repeated reads return this cache without a new reservation.

CREATE TABLE IF NOT EXISTS workspace_ai_results (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  content_book_id TEXT NOT NULL REFERENCES content_books(id) ON DELETE CASCADE,
  result_type TEXT NOT NULL CHECK (result_type IN ('word_context', 'sentence_grammar')),
  content_key TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  payload JSONB NOT NULL,
  provider TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (owner_id, result_type, content_key, input_hash)
);

CREATE INDEX IF NOT EXISTS workspace_ai_results_book_idx
  ON workspace_ai_results(owner_id, content_book_id, result_type, updated_at DESC);
