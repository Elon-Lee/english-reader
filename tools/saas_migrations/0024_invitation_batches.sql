-- Invitations created in one operation are presented and managed as one
-- batch summary. Existing invitations become one-item legacy batches.

CREATE TABLE IF NOT EXISTS invitation_batches (
  id TEXT PRIMARY KEY,
  requested_count INTEGER NOT NULL CHECK (requested_count > 0),
  max_uses INTEGER NOT NULL CHECK (max_uses > 0),
  expires_at TIMESTAMPTZ,
  created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  note TEXT NOT NULL DEFAULT '',
  channel TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS invitation_batches_created_idx ON invitation_batches(created_at DESC);

ALTER TABLE invitations ADD COLUMN IF NOT EXISTS batch_id TEXT REFERENCES invitation_batches(id) ON DELETE RESTRICT;

INSERT INTO invitation_batches(id,requested_count,max_uses,expires_at,created_by,note,channel,created_at)
SELECT 'legacy-batch-' || id,1,max_uses,expires_at,created_by,note,channel,created_at
FROM invitations WHERE batch_id IS NULL
ON CONFLICT(id) DO NOTHING;

UPDATE invitations SET batch_id='legacy-batch-' || id WHERE batch_id IS NULL;
ALTER TABLE invitations ALTER COLUMN batch_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS invitations_batch_idx ON invitations(batch_id,created_at);

