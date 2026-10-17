-- CloudCat one-time redemption codes and catalog-level media capacity limits.
ALTER TABLE commerce_product_versions
  ADD COLUMN IF NOT EXISTS purchase_url TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS commerce_redemption_batches (
  id TEXT PRIMARY KEY,
  product_version_id TEXT NOT NULL REFERENCES commerce_product_versions(id) ON DELETE RESTRICT,
  requested_count INTEGER NOT NULL CHECK (requested_count > 0),
  note TEXT NOT NULL DEFAULT '',
  created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS commerce_redemption_batches_created_idx
  ON commerce_redemption_batches(created_at DESC);

CREATE TABLE IF NOT EXISTS commerce_redemption_codes (
  id TEXT PRIMARY KEY,
  batch_id TEXT NOT NULL REFERENCES commerce_redemption_batches(id) ON DELETE RESTRICT,
  product_version_id TEXT NOT NULL REFERENCES commerce_product_versions(id) ON DELETE RESTRICT,
  code_hash TEXT NOT NULL UNIQUE,
  code_prefix TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','redeemed','revoked')),
  redeemed_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  redeemed_at TIMESTAMPTZ,
  subscription_id TEXT REFERENCES subscriptions(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS commerce_redemption_codes_batch_idx
  ON commerce_redemption_codes(batch_id, status, created_at);
CREATE INDEX IF NOT EXISTS commerce_redemption_codes_user_idx
  ON commerce_redemption_codes(redeemed_by, redeemed_at DESC);

INSERT INTO plan_versions(id,plan_id,display_name,rank,period_days,quotas_json,pricing_json,active)
SELECT 'free-v2',p.id,'免费版',0,30,
  pv.quotas_json || '{"official_library_capacity":0,"official_unlocks":0,"mp3_imports":0,"video_imports":0,"youtube_imports":0,"video_library_capacity":2,"audio_library_capacity":5,"storage_bytes":1073741824}'::jsonb,
  '{}'::jsonb,TRUE
FROM plans p JOIN plan_versions pv ON pv.id='free-v1'
WHERE p.slug='free'
ON CONFLICT(id) DO NOTHING;

UPDATE users SET plan_version='free-v2',updated_at=NOW()
WHERE plan_version='free-v1';

UPDATE commerce_product_versions SET status='retired',retired_at=NOW()
WHERE status='published';

INSERT INTO plan_versions(id,plan_id,display_name,rank,period_days,quotas_json,pricing_json,active)
SELECT 'commerce-advanced-30-v2',p.id,'进阶会员月卡',2,30,
  '{"official_library_capacity":0,"official_unlocks":0,"video_library_capacity":20,"audio_library_capacity":50,"storage_bytes":5368709120,"ai_context_generations":300,"ai_grammar_generations":100,"mp3_imports":0,"video_imports":0,"youtube_imports":0,"devices":2}'::jsonb,
  '{"currency":"CNY","amount_cents":1900,"duration_days":30,"commerce_product_version":"advanced-30-v2"}'::jsonb,FALSE
FROM plans p WHERE p.slug='advanced'
ON CONFLICT(id) DO NOTHING;

INSERT INTO plan_versions(id,plan_id,display_name,rank,period_days,quotas_json,pricing_json,active)
SELECT 'commerce-pro-30-v2',p.id,'Pro会员月卡',2,30,
  '{"official_library_capacity":0,"official_unlocks":0,"video_library_capacity":100,"audio_library_capacity":200,"storage_bytes":21474836480,"ai_context_generations":300,"ai_grammar_generations":100,"mp3_imports":0,"video_imports":0,"youtube_imports":0,"devices":2}'::jsonb,
  '{"currency":"CNY","amount_cents":4900,"duration_days":30,"commerce_product_version":"pro-30-v2"}'::jsonb,FALSE
FROM plans p WHERE p.slug='pro'
ON CONFLICT(id) DO NOTHING;

INSERT INTO commerce_product_versions(
  id,product_id,version_number,plan_version_id,display_name,short_name,tagline,description,
  duration_days,amount_cents,currency,benefits_json,featured,status
)
SELECT 'advanced-30-v2',cp.id,2,'commerce-advanced-30-v2','进阶会员月卡','进阶版','把公版与私人材料放进同一学习空间','每次购买获得 30 天进阶权益。最多收藏 20 个视频、50 个音频（公版与私人合计），私人学习空间上限 5 GB。',
  30,1900,'CNY','["私人学习空间最多 5 GB","最多收藏 20 个视频（公版 + 私人）","最多收藏 50 个音频（公版 + 私人）","公版及授权学习材料不限次数","一次购买 30 天，不自动续费"]'::jsonb,TRUE,'draft'
FROM commerce_products cp WHERE cp.slug='advanced-30'
ON CONFLICT(id) DO NOTHING;

INSERT INTO commerce_product_versions(
  id,product_id,version_number,plan_version_id,display_name,short_name,tagline,description,
  duration_days,amount_cents,currency,benefits_json,featured,status
)
SELECT 'pro-30-v2',cp.id,2,'commerce-pro-30-v2','Pro会员月卡','Pro版','为高频学习留出更大的材料空间','每次购买获得 30 天 Pro 权益。最多收藏 100 个视频、200 个音频（公版与私人合计），私人学习空间上限 20 GB。',
  30,4900,'CNY','["私人学习空间最多 20 GB","最多收藏 100 个视频（公版 + 私人）","最多收藏 200 个音频（公版 + 私人）","公版及授权学习材料不限次数","一次购买 30 天，不自动续费"]'::jsonb,FALSE,'draft'
FROM commerce_products cp WHERE cp.slug='pro-30'
ON CONFLICT(id) DO NOTHING;
