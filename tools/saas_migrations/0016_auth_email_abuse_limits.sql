-- Persist authentication-email abuse limits across processes and restarts.

ALTER TABLE invitations
  ADD COLUMN IF NOT EXISTS verification_email_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE invitations
  DROP CONSTRAINT IF EXISTS invitations_verification_email_count_check;

ALTER TABLE invitations
  ADD CONSTRAINT invitations_verification_email_count_check
  CHECK (verification_email_count >= 0);

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS password_reset_request_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS password_reset_locked_at TIMESTAMPTZ;

ALTER TABLE users
  DROP CONSTRAINT IF EXISTS users_password_reset_request_count_check;

ALTER TABLE users
  ADD CONSTRAINT users_password_reset_request_count_check
  CHECK (password_reset_request_count >= 0);
