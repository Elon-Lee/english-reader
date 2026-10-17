-- Replace the old fixed-term storefront with CloudCat-backed monthly products.
-- Existing product and entitlement versions stay immutable for history.

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
