-- Existing invitation-only accounts keep their uniform personal resource floor.
-- An entry never changes this policy; only new international registration opts in.
ALTER TABLE users ADD COLUMN IF NOT EXISTS account_resource_policy TEXT NOT NULL DEFAULT 'private';
ALTER TABLE users ADD CONSTRAINT users_account_resource_policy_check
  CHECK (account_resource_policy IN ('private','commercial'));
