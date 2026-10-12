-- Customer-initiated membership changes. Payment remains provider-specific,
-- while the SaaS core records a tenant-safe request for admin fulfilment.
CREATE TABLE IF NOT EXISTS membership_change_requests (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  current_plan_version_id TEXT NOT NULL REFERENCES plan_versions(id) ON DELETE RESTRICT,
  requested_plan_version_id TEXT NOT NULL REFERENCES plan_versions(id) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'cancelled', 'rejected')),
  note TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS membership_change_requests_user_idx ON membership_change_requests(user_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS membership_change_requests_pending_idx ON membership_change_requests(user_id) WHERE status='pending';
