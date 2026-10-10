-- Invitation codes are granted by operations or campaigns, not implicitly
-- unlimited for every paid member.
CREATE TABLE IF NOT EXISTS member_invite_allowances (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  quantity_remaining INTEGER NOT NULL CHECK (quantity_remaining >= 0),
  source TEXT NOT NULL DEFAULT 'admin',
  note TEXT NOT NULL DEFAULT '',
  expires_at TIMESTAMPTZ,
  created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS member_invite_allowances_available_idx ON member_invite_allowances(user_id, expires_at, created_at) WHERE quantity_remaining > 0;
