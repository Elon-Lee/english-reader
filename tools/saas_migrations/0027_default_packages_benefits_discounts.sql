-- Persist reference prices/discount rates and publish the free plan card.
ALTER TABLE commerce_product_versions
  ADD COLUMN IF NOT EXISTS original_amount_cents INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS discount_percent INTEGER NOT NULL DEFAULT 100;

UPDATE commerce_product_versions
SET original_amount_cents=amount_cents,discount_percent=100
WHERE original_amount_cents=0 AND amount_cents>0;

ALTER TABLE commerce_product_versions
  ADD CONSTRAINT commerce_product_price_discount_check
  CHECK (original_amount_cents >= 0 AND discount_percent BETWEEN 1 AND 100
    AND amount_cents = (original_amount_cents * discount_percent + 50) / 100);

UPDATE commerce_product_versions
SET original_amount_cents=3167,discount_percent=60,
    benefits_json='[
      "私人学习空间最多 5 GB",
      "最多收藏 20 个视频（公版 + 私人）",
      "最多收藏 50 个音频（公版 + 私人）",
      "免费包含：公版及授权学习材料不限次使用",
      "免费包含：公版书架收藏不限量",
      "免费包含：词汇语境分析 300 次/30天",
      "免费包含：句法分析 100 次/30天",
      "免费包含：音频、视频及在线视频导入，不按导入次数收费",
      "免费包含：最多同时登录 2 台设备"
    ]'::jsonb
WHERE id='advanced-30-v2' AND status='draft';

UPDATE commerce_product_versions
SET original_amount_cents=8167,discount_percent=60,
    benefits_json='[
      "私人学习空间最多 20 GB",
      "最多收藏 100 个视频（公版 + 私人）",
      "最多收藏 200 个音频（公版 + 私人）",
      "免费包含：公版及授权学习材料不限次使用",
      "免费包含：公版书架收藏不限量",
      "免费包含：词汇语境分析 300 次/30天",
      "免费包含：句法分析 100 次/30天",
      "免费包含：音频、视频及在线视频导入，不按导入次数收费",
      "免费包含：最多同时登录 2 台设备"
    ]'::jsonb
WHERE id='pro-30-v2' AND status='draft';

INSERT INTO commerce_products(id,slug,family_slug,display_order)
VALUES('product-free','free','free',0)
ON CONFLICT(id) DO NOTHING;

INSERT INTO commerce_product_versions(
  id,product_id,version_number,plan_version_id,display_name,short_name,tagline,description,
  duration_days,amount_cents,original_amount_cents,discount_percent,currency,benefits_json,featured,status,published_at
)
VALUES(
  'free-plan-v1','product-free',1,'free-v2','免费版','免费','从自己的材料开始学习','永久免费使用基础学习空间；升级后可获得更大的私人空间和更高的音视频收藏上限。',
  30,0,0,100,'CNY','[
    "永久免费，无需支付",
    "私人学习空间最多 1 GB",
    "最多收藏 2 个视频（公版 + 私人）",
    "最多收藏 5 个音频（公版 + 私人）",
    "免费包含：公版及授权学习材料不限次使用",
    "免费包含：词汇语境分析 20 次/30天",
    "免费包含：句法分析 10 次/30天",
    "免费包含：音频、视频及在线视频导入，不按导入次数收费",
    "免费包含：最多同时登录 1 台设备"
  ]'::jsonb,TRUE,'published',NOW()
)
ON CONFLICT(id) DO NOTHING;
