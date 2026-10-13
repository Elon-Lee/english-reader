-- Paddle Billing integration. Provider events are stored separately from the
-- immutable membership ledger so webhook retries remain idempotent and manual
-- subscriptions continue to work unchanged.

CREATE TABLE IF NOT EXISTS payment_orders (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  plan_version_id TEXT NOT NULL REFERENCES plan_versions(id) ON DELETE RESTRICT,
  provider TEXT NOT NULL CHECK (provider IN ('paddle')),
  billing_interval TEXT NOT NULL CHECK (billing_interval IN ('month', 'year')),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'failed', 'cancelled', 'refunded')),
  amount_cents INTEGER NOT NULL DEFAULT 0 CHECK (amount_cents >= 0),
  currency TEXT NOT NULL DEFAULT 'CNY',
  idempotency_key TEXT NOT NULL,
  external_transaction_id TEXT,
  external_subscription_id TEXT,
  starts_at TIMESTAMPTZ,
  ends_at TIMESTAMPTZ,
  error_code TEXT,
  error_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, idempotency_key),
  UNIQUE (provider, external_transaction_id)
);
CREATE INDEX IF NOT EXISTS payment_orders_user_idx ON payment_orders(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS external_subscriptions (
  provider TEXT NOT NULL CHECK (provider IN ('paddle')),
  external_id TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  plan_version_id TEXT NOT NULL REFERENCES plan_versions(id) ON DELETE RESTRICT,
  local_subscription_id TEXT REFERENCES subscriptions(id) ON DELETE SET NULL,
  customer_id TEXT,
  status TEXT NOT NULL,
  billing_interval TEXT NOT NULL CHECK (billing_interval IN ('month', 'year')),
  current_period_start TIMESTAMPTZ,
  current_period_end TIMESTAMPTZ,
  cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (provider, external_id)
);
CREATE INDEX IF NOT EXISTS external_subscriptions_user_idx ON external_subscriptions(user_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS payment_provider_events (
  provider TEXT NOT NULL CHECK (provider IN ('paddle')),
  event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'processed', 'failed', 'ignored')),
  occurred_at TIMESTAMPTZ,
  processed_at TIMESTAMPTZ,
  error_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (provider, event_id)
);
