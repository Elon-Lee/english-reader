-- Make membership changes explicit and auditable while preserving existing
-- subscription periods as the source of entitlement truth.
CREATE TABLE IF NOT EXISTS membership_change_orders (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source TEXT NOT NULL DEFAULT 'cloudcat',
  source_code_id TEXT REFERENCES commerce_redemption_codes(id) ON DELETE SET NULL,
  from_plan_version_id TEXT REFERENCES plan_versions(id) ON DELETE RESTRICT,
  to_plan_version_id TEXT NOT NULL REFERENCES plan_versions(id) ON DELETE RESTRICT,
  current_subscription_id TEXT REFERENCES subscriptions(id) ON DELETE SET NULL,
  created_subscription_id TEXT REFERENCES subscriptions(id) ON DELETE SET NULL,
  change_type TEXT NOT NULL CHECK (change_type IN ('first_purchase','renewal','upgrade','downgrade')),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','scheduled','applied','cancelled','refunded','failed')),
  effective_at TIMESTAMPTZ NOT NULL,
  carry_days INTEGER NOT NULL DEFAULT 0 CHECK (carry_days >= 0),
  amount_cents INTEGER NOT NULL DEFAULT 0 CHECK (amount_cents >= 0),
  idempotency_key TEXT,
  note TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS membership_change_orders_user_idx
  ON membership_change_orders(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS membership_change_orders_effective_idx
  ON membership_change_orders(user_id, status, effective_at);
CREATE UNIQUE INDEX IF NOT EXISTS membership_change_orders_idempotency_idx
  ON membership_change_orders(user_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS membership_events (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  change_order_id TEXT REFERENCES membership_change_orders(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS membership_events_user_idx
  ON membership_events(user_id, created_at DESC);
