-- Publish corrected annual product versions. The membership engine now opens
-- a new usage period every plan period (30 days for current paid plans) while
-- retaining the single fixed-term subscription. V1 remains immutable for
-- historical orders and is merely retired from new sales.

UPDATE commerce_product_versions
SET status='retired',retired_at=NOW()
WHERE id IN ('advanced-365-v1','pro-365-v1') AND status='published';

INSERT INTO commerce_product_versions(
  id,product_id,version_number,plan_version_id,display_name,short_name,tagline,description,
  duration_days,amount_cents,benefits_json,featured,status,published_at
) VALUES
  ('advanced-365-v2','product-advanced-365',2,'advanced-v1','进阶会员 365 天','进阶 365 天','一年持续学习，比零散努力更有效','一次购买 365 天权益，不自动续费；学习额度每 30 天自动重置。',365,29900,
   '["公版及授权学习材料使用额度 12 次/30天","词汇语境分析 300 次/30天","句法分析 100 次/30天","音视频学习导入 13 次/30天","20 GB 私人学习空间","最多 2 台设备"]'::jsonb,TRUE,'published',NOW()),
  ('pro-365-v2','product-pro-365',2,'pro-v1','Pro 会员 365 天','Pro 365 天','长期深度学习，不被工具限制','一次购买 365 天完整 Pro 权益，不自动续费；学习额度每 30 天自动重置。',365,59900,
   '["公版及授权学习材料使用额度 40 次/30天","词汇语境分析 1500 次/30天","句法分析 500 次/30天","音视频学习导入 50 次/30天","100 GB 私人学习空间","最多 5 台设备"]'::jsonb,FALSE,'published',NOW())
ON CONFLICT(id) DO NOTHING;
