-- Preserve value-based upgrade conversions with sub-day precision.
ALTER TABLE membership_change_orders
  ADD COLUMN IF NOT EXISTS carry_seconds BIGINT NOT NULL DEFAULT 0 CHECK (carry_seconds >= 0);
