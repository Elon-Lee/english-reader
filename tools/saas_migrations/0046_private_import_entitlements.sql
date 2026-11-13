-- New sale versions preserve existing order/redemption snapshots and links.
-- Effective caps for older subscriptions are enforced by ResourceService.
DO $$
DECLARE
  source RECORD;
  product_version TEXT;
  plan_version TEXT;
  capacity BIGINT;
  capacity_gb INTEGER;
  benefits JSONB;
  next_version INTEGER;
BEGIN
  FOR source IN
    SELECT cp.family_slug,cpv.*,pv.plan_id,pv.rank,pv.period_days,pv.quotas_json,
           pv.pricing_json,pv.active AS plan_active
    FROM commerce_products cp
    JOIN commerce_product_versions cpv ON cpv.product_id=cp.id
    JOIN plan_versions pv ON pv.id=cpv.plan_version_id
    WHERE cpv.status='published' AND cp.family_slug IN ('free','advanced','pro')
      AND cpv.id NOT LIKE '%-imports-v1'
  LOOP
    product_version := source.id || '-imports-v1';
    plan_version := 'imports-' || source.id;
    capacity_gb := CASE source.family_slug WHEN 'advanced' THEN 1 WHEN 'pro' THEN 5 ELSE 0 END;
    capacity := capacity_gb::BIGINT * 1073741824;
    SELECT COALESCE(jsonb_agg(item ORDER BY position), '[]'::JSONB) INTO benefits
      FROM jsonb_array_elements_text(source.benefits_json) WITH ORDINALITY AS b(item,position)
      WHERE item NOT LIKE '%私人%空间%' AND item NOT LIKE '%导入%';
    benefits := benefits || CASE WHEN capacity=0
      THEN '["免费版不支持私人空间及读物导入，升级套餐后可使用"]'::JSONB
      ELSE jsonb_build_array('私人学习空间最多 ' || capacity_gb || ' GB',
                            '支持文档、音频、视频及在线视频导入，不按导入次数收费') END;
    INSERT INTO plan_versions(id,plan_id,display_name,rank,period_days,quotas_json,pricing_json,active)
    VALUES(plan_version,source.plan_id,source.display_name,source.rank,source.period_days,
      source.quotas_json || jsonb_build_object('storage_bytes',capacity),
      source.pricing_json || jsonb_build_object('commerce_product_version',product_version),source.plan_active)
    ON CONFLICT(id) DO NOTHING;
    SELECT MAX(version_number)+1 INTO next_version FROM commerce_product_versions WHERE product_id=source.product_id;
    UPDATE commerce_product_versions SET status='retired',retired_at=NOW() WHERE id=source.id;
    INSERT INTO commerce_product_versions(
      id,product_id,version_number,plan_version_id,display_name,short_name,tagline,description,
      duration_days,amount_cents,currency,benefits_json,featured,status,published_at,
      original_amount_cents,discount_percent,purchase_url,configured_benefits_json)
    VALUES(product_version,source.product_id,next_version,plan_version,source.display_name,source.short_name,
      CASE WHEN capacity=0 THEN '从书城读物开始学习' ELSE source.tagline END,
      CASE WHEN capacity=0 THEN '免费阅读公版及授权材料；私人空间及读物导入需升级到进阶版或 Pro 版。'
           ELSE '支持个人读物导入，私人学习空间上限 ' || capacity_gb || ' GB。' END,
      source.duration_days,source.amount_cents,source.currency,benefits,source.featured,'published',NOW(),
      source.original_amount_cents,source.discount_percent,source.purchase_url,source.configured_benefits_json)
    ON CONFLICT(id) DO NOTHING;
  END LOOP;
END $$;
