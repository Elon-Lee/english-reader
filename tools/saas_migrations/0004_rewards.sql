-- Phase 4: check-ins, growth points, redemptions, and member invitations.

CREATE TABLE IF NOT EXISTS checkins (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  checkin_day DATE NOT NULL,
  timezone TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('regular', 'makeup')),
  streak_count INTEGER NOT NULL DEFAULT 1 CHECK (streak_count > 0),
  makeup_redemption_id TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, checkin_day)
);
CREATE INDEX IF NOT EXISTS checkins_user_day_idx ON checkins(user_id, checkin_day DESC);

CREATE TABLE IF NOT EXISTS reward_catalog (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  cost_points INTEGER NOT NULL CHECK (cost_points > 0),
  reward_type TEXT NOT NULL CHECK (reward_type IN ('quota_credit', 'makeup_card')),
  feature TEXT NOT NULL DEFAULT '',
  quantity BIGINT NOT NULL DEFAULT 1 CHECK (quantity > 0),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reward_ledger (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  month_key TEXT NOT NULL,
  reward_day DATE,
  event_type TEXT NOT NULL,
  event_key TEXT NOT NULL,
  points INTEGER NOT NULL,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, event_type, event_key)
);
CREATE INDEX IF NOT EXISTS reward_ledger_user_month_idx ON reward_ledger(user_id, month_key, created_at);

CREATE TABLE IF NOT EXISTS reward_redemptions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  reward_catalog_id TEXT NOT NULL REFERENCES reward_catalog(id) ON DELETE RESTRICT,
  cost_points INTEGER NOT NULL CHECK (cost_points > 0),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'used', 'cancelled')),
  idempotency_key TEXT NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS reward_redemptions_user_idx ON reward_redemptions(user_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS reward_daily_activity (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  activity_day DATE NOT NULL,
  timezone TEXT NOT NULL,
  reading_seconds BIGINT NOT NULL DEFAULT 0 CHECK (reading_seconds >= 0),
  sentences INTEGER NOT NULL DEFAULT 0 CHECK (sentences >= 0),
  reviews INTEGER NOT NULL DEFAULT 0 CHECK (reviews >= 0),
  valid_reading_awarded BOOLEAN NOT NULL DEFAULT FALSE,
  review_awarded BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, activity_day)
);

CREATE TABLE IF NOT EXISTS reward_activity_events (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  idempotency_key TEXT NOT NULL,
  activity_day DATE NOT NULL,
  reading_seconds BIGINT NOT NULL DEFAULT 0 CHECK (reading_seconds >= 0),
  sentences INTEGER NOT NULL DEFAULT 0 CHECK (sentences >= 0),
  reviews INTEGER NOT NULL DEFAULT 0 CHECK (reviews >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS member_invites (
  id TEXT PRIMARY KEY,
  inviter_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  invitation_id TEXT NOT NULL UNIQUE REFERENCES invitations(id) ON DELETE RESTRICT,
  invitee_id TEXT UNIQUE REFERENCES users(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'registered', 'effective_learning', 'paid', 'cancelled')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  registered_at TIMESTAMPTZ,
  effective_learning_at TIMESTAMPTZ,
  first_paid_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS member_invites_inviter_idx ON member_invites(inviter_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS member_invite_rewards (
  id TEXT PRIMARY KEY,
  member_invite_id TEXT NOT NULL REFERENCES member_invites(id) ON DELETE CASCADE,
  reward_type TEXT NOT NULL CHECK (reward_type IN ('effective_learning', 'first_paid')),
  points INTEGER NOT NULL CHECK (points > 0),
  fraud_blocked BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (member_invite_id, reward_type)
);

ALTER TABLE checkins ADD CONSTRAINT checkins_makeup_redemption_fk FOREIGN KEY (makeup_redemption_id) REFERENCES reward_redemptions(id) ON DELETE SET NULL;

INSERT INTO reward_catalog(id,code,title,description,cost_points,reward_type,feature,quantity,sort_order) VALUES
  ('reward-ai-context-10','ai_context_10','10次 AI 语境精讲','兑换后立即补发到当前账期。',20,'quota_credit','ai_context_generations',10,10),
  ('reward-ai-grammar-5','ai_grammar_5','5次智能句法分析','兑换后立即补发到当前账期。',30,'quota_credit','ai_grammar_generations',5,20),
  ('reward-official-unlock-1','official_unlock_1','1次官方读物解锁','兑换后立即补发到当前账期。',80,'quota_credit','official_unlocks',1,30),
  ('reward-mp3-import-1','mp3_import_1','1次 MP3 智能导入','兑换后立即补发到当前账期。',150,'quota_credit','mp3_imports',1,40),
  ('reward-makeup-card-1','makeup_card_1','1张补签卡','可在过去日期补签一次。',20,'makeup_card','',1,50)
ON CONFLICT (id) DO NOTHING;
