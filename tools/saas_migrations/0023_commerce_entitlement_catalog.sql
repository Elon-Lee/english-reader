-- Separate enforced built-in quota features from configurable display-only
-- benefits. Configured benefits are snapshotted into every immutable product
-- version so later edits never rewrite historical purchases.

CREATE TABLE IF NOT EXISTS commerce_configured_benefits (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  default_text TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE commerce_product_versions
  ADD COLUMN IF NOT EXISTS configured_benefits_json JSONB NOT NULL DEFAULT '[]'::jsonb;

INSERT INTO commerce_configured_benefits(id,code,display_name,description,default_text) VALUES
  ('benefit-support-7x8','support-7x8','7×8 小时客服支持','工作日与周末指定时段内提供使用咨询和订单支持。','7×8 小时客服支持'),
  ('benefit-renewal-reminder','renewal-reminder','到期提醒','会员到期前通过站内或邮件提醒用户自主续费。','到期前主动提醒')
ON CONFLICT(code) DO NOTHING;

