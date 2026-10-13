-- Public product catalog with immutable, auditable versions. Products are the
-- stable merchandising identity; every name, price, duration, and benefit
-- change creates a new version so historical purchases never drift.

CREATE TABLE IF NOT EXISTS commerce_products (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  family_slug TEXT NOT NULL,
  display_order INTEGER NOT NULL DEFAULT 0,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS commerce_product_versions (
  id TEXT PRIMARY KEY,
  product_id TEXT NOT NULL REFERENCES commerce_products(id) ON DELETE RESTRICT,
  version_number INTEGER NOT NULL CHECK (version_number > 0),
  plan_version_id TEXT NOT NULL REFERENCES plan_versions(id) ON DELETE RESTRICT,
  display_name TEXT NOT NULL,
  short_name TEXT NOT NULL,
  tagline TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  duration_days INTEGER NOT NULL CHECK (duration_days > 0),
  amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
  currency TEXT NOT NULL DEFAULT 'CNY',
  benefits_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  featured BOOLEAN NOT NULL DEFAULT FALSE,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','retired')),
  created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  published_at TIMESTAMPTZ,
  retired_at TIMESTAMPTZ,
  UNIQUE(product_id, version_number)
);
CREATE UNIQUE INDEX IF NOT EXISTS commerce_product_current_idx
  ON commerce_product_versions(product_id) WHERE status='published';
CREATE INDEX IF NOT EXISTS commerce_product_versions_history_idx
  ON commerce_product_versions(product_id, version_number DESC);

ALTER TABLE payment_orders DROP CONSTRAINT IF EXISTS payment_orders_provider_check;
ALTER TABLE payment_orders ADD CONSTRAINT payment_orders_provider_check CHECK (provider IN ('paddle','mbdpay'));
ALTER TABLE payment_orders ALTER COLUMN billing_interval DROP NOT NULL;
ALTER TABLE payment_orders DROP CONSTRAINT IF EXISTS payment_orders_billing_interval_check;
ALTER TABLE payment_orders ADD CONSTRAINT payment_orders_billing_interval_check CHECK (billing_interval IS NULL OR billing_interval IN ('month','year'));
ALTER TABLE payment_orders ADD COLUMN IF NOT EXISTS product_version_id TEXT REFERENCES commerce_product_versions(id) ON DELETE RESTRICT;
ALTER TABLE payment_orders ADD COLUMN IF NOT EXISTS duration_days INTEGER CHECK (duration_days IS NULL OR duration_days > 0);
ALTER TABLE payment_orders ADD COLUMN IF NOT EXISTS product_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE payment_orders ADD COLUMN IF NOT EXISTS entitlement_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb;

INSERT INTO commerce_products(id,slug,family_slug,display_order) VALUES
  ('product-advanced-30','advanced-30','advanced',10),
  ('product-advanced-365','advanced-365','advanced',20),
  ('product-pro-30','pro-30','pro',30),
  ('product-pro-365','pro-365','pro',40)
ON CONFLICT(id) DO NOTHING;

INSERT INTO commerce_product_versions(
  id,product_id,version_number,plan_version_id,display_name,short_name,tagline,description,
  duration_days,amount_cents,benefits_json,featured,status,published_at
) VALUES
  ('advanced-30-v1','product-advanced-30',1,'advanced-v1','进阶会员 30 天','进阶 30 天','把每一次阅读变成可积累的理解力','适合开始建立稳定精读、跟读和复习习惯的学习者。',30,3900,
   '["公版及授权学习材料使用额度 12 次","词汇语境分析 300 次","句法分析 100 次","音视频学习导入 13 次","20 GB 私人学习空间","最多 2 台设备"]'::jsonb,FALSE,'published',NOW()),
  ('advanced-365-v1','product-advanced-365',1,'advanced-v1','进阶会员 365 天','进阶 365 天','一年持续学习，比零散努力更有效','一次购买 365 天权益，不自动续费，到期前主动提醒。',365,29900,
   '["公版及授权学习材料使用额度 12 次/周期","词汇语境分析 300 次/周期","句法分析 100 次/周期","音视频学习导入 13 次/周期","20 GB 私人学习空间","最多 2 台设备"]'::jsonb,TRUE,'published',NOW()),
  ('pro-30-v1','product-pro-30',1,'pro-v1','Pro 会员 30 天','Pro 30 天','为高频输入与深度训练准备','适合高频使用视频精听、AI 分析和大量私人材料的学习者。',30,7900,
   '["公版及授权学习材料使用额度 40 次","词汇语境分析 1500 次","句法分析 500 次","音视频学习导入 50 次","100 GB 私人学习空间","最多 5 台设备"]'::jsonb,FALSE,'published',NOW()),
  ('pro-365-v1','product-pro-365',1,'pro-v1','Pro 会员 365 天','Pro 365 天','长期深度学习，不被工具限制','一次购买 365 天完整 Pro 权益，不自动续费。',365,59900,
   '["公版及授权学习材料使用额度 40 次/周期","词汇语境分析 1500 次/周期","句法分析 500 次/周期","音视频学习导入 50 次/周期","100 GB 私人学习空间","最多 5 台设备"]'::jsonb,FALSE,'published',NOW())
ON CONFLICT(id) DO NOTHING;
