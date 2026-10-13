-- Restore the initial storefront catalog if an isolated acceptance database
-- previously truncated plan versions with CASCADE. Safe and idempotent in
-- normal environments where 0019 already inserted the same records.

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
