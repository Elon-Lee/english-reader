-- Phase 2: immutable plan versions, manual subscriptions, and transactional
-- usage accounting.  Usage limits are copied to usage_periods so later plan
-- versions never rewrite an existing member's entitlement.

CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS plan_versions (
  id TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
  display_name TEXT NOT NULL,
  rank INTEGER NOT NULL CHECK (rank >= 0),
  period_days INTEGER NOT NULL CHECK (period_days > 0),
  quotas_json JSONB NOT NULL,
  pricing_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  retired_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS plan_versions_plan_idx ON plan_versions(plan_id, rank DESC);

CREATE TABLE IF NOT EXISTS manual_orders (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  plan_version_id TEXT NOT NULL REFERENCES plan_versions(id) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('draft', 'completed', 'cancelled', 'refunded')),
  starts_at TIMESTAMPTZ NOT NULL,
  ends_at TIMESTAMPTZ NOT NULL CHECK (ends_at > starts_at),
  amount_cents INTEGER NOT NULL DEFAULT 0 CHECK (amount_cents >= 0),
  currency TEXT NOT NULL DEFAULT 'CNY',
  note TEXT NOT NULL DEFAULT '',
  created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS manual_orders_user_idx ON manual_orders(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS subscriptions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  plan_version_id TEXT NOT NULL REFERENCES plan_versions(id) ON DELETE RESTRICT,
  status TEXT NOT NULL CHECK (status IN ('active', 'grace_period', 'expired', 'suspended')),
  starts_at TIMESTAMPTZ NOT NULL,
  ends_at TIMESTAMPTZ NOT NULL CHECK (ends_at > starts_at),
  manual_order_id TEXT UNIQUE REFERENCES manual_orders(id) ON DELETE SET NULL,
  note TEXT NOT NULL DEFAULT '',
  created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS subscriptions_effective_idx ON subscriptions(user_id, status, starts_at, ends_at DESC);

CREATE TABLE IF NOT EXISTS usage_periods (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  subscription_id TEXT REFERENCES subscriptions(id) ON DELETE SET NULL,
  plan_version_id TEXT NOT NULL REFERENCES plan_versions(id) ON DELETE RESTRICT,
  period_key TEXT NOT NULL,
  starts_at TIMESTAMPTZ NOT NULL,
  ends_at TIMESTAMPTZ NOT NULL CHECK (ends_at > starts_at),
  limits_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, period_key)
);
CREATE INDEX IF NOT EXISTS usage_periods_current_idx ON usage_periods(user_id, starts_at, ends_at DESC);

CREATE TABLE IF NOT EXISTS quota_reservations (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  usage_period_id TEXT NOT NULL REFERENCES usage_periods(id) ON DELETE CASCADE,
  feature TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  quantity BIGINT NOT NULL DEFAULT 1 CHECK (quantity > 0),
  state TEXT NOT NULL CHECK (state IN ('reserved', 'settled', 'released')),
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  settled_at TIMESTAMPTZ,
  released_at TIMESTAMPTZ,
  UNIQUE (user_id, feature, idempotency_key)
);
CREATE INDEX IF NOT EXISTS quota_reservations_period_idx ON quota_reservations(usage_period_id, feature, state);

CREATE TABLE IF NOT EXISTS usage_ledger (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  usage_period_id TEXT NOT NULL REFERENCES usage_periods(id) ON DELETE CASCADE,
  feature TEXT NOT NULL,
  quantity BIGINT NOT NULL,
  reason TEXT NOT NULL CHECK (reason IN ('consumption', 'credit', 'adjustment', 'storage_settlement')),
  reservation_id TEXT UNIQUE REFERENCES quota_reservations(id) ON DELETE SET NULL,
  idempotency_key TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS usage_ledger_idempotency_idx ON usage_ledger(user_id, feature, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS usage_ledger_period_idx ON usage_ledger(usage_period_id, feature, created_at);

CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  storage_bytes BIGINT NOT NULL DEFAULT 0 CHECK (storage_bytes >= 0),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deleted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS assets_owner_idx ON assets(owner_id, status);

CREATE TABLE IF NOT EXISTS membership_audit (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  actor_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS membership_audit_user_idx ON membership_audit(user_id, created_at DESC);

INSERT INTO plans(id, slug, display_name) VALUES
  ('plan-free', 'free', '免费版'),
  ('plan-advanced', 'advanced', '进阶版'),
  ('plan-pro', 'pro', 'Pro版')
ON CONFLICT (id) DO NOTHING;

INSERT INTO plan_versions(id, plan_id, display_name, rank, period_days, quotas_json, pricing_json) VALUES
  ('free-v1', 'plan-free', '免费版', 0, 30,
   '{"official_library_capacity":5,"official_unlocks":2,"ai_context_generations":20,"ai_grammar_generations":10,"mp3_imports":1,"video_imports":1,"youtube_imports":1,"storage_bytes":1073741824,"devices":1}'::jsonb,
   '{}'::jsonb),
  ('advanced-v1', 'plan-advanced', '进阶版', 1, 30,
   '{"official_library_capacity":30,"official_unlocks":12,"ai_context_generations":300,"ai_grammar_generations":100,"mp3_imports":5,"video_imports":3,"youtube_imports":5,"storage_bytes":21474836480,"devices":2}'::jsonb,
   '{"currency":"CNY","monthly_cents":3900,"annual_cents":29900}'::jsonb),
  ('pro-v1', 'plan-pro', 'Pro版', 2, 30,
   '{"official_library_capacity":100,"official_unlocks":40,"ai_context_generations":1500,"ai_grammar_generations":500,"mp3_imports":20,"video_imports":10,"youtube_imports":20,"storage_bytes":107374182400,"devices":5}'::jsonb,
   '{"currency":"CNY","monthly_cents":7900,"annual_cents":59900}'::jsonb)
ON CONFLICT (id) DO NOTHING;
