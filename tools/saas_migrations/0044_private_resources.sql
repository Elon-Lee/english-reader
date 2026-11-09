-- Resource accounting no longer requires a commercial plan or subscription.
-- Historical records and their foreign keys remain intact.
ALTER TABLE users ALTER COLUMN plan_version DROP NOT NULL;
ALTER TABLE users ALTER COLUMN plan_version DROP DEFAULT;
ALTER TABLE usage_periods ALTER COLUMN plan_version_id DROP NOT NULL;
ALTER TABLE workspace_import_tasks ALTER COLUMN plan_version_id DROP NOT NULL;

CREATE TABLE IF NOT EXISTS resource_audit (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  actor_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS resource_audit_user_idx ON resource_audit(user_id, created_at DESC);
