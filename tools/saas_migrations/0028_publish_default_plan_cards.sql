-- Publish the three configured plan cards. Paid plans remain non-purchasable
-- until their CloudCat URLs are added; the frontend renders that state.
UPDATE commerce_product_versions
SET status='published',published_at=NOW()
WHERE id IN ('advanced-30-v2','pro-30-v2') AND status='draft';

UPDATE plan_versions SET active=TRUE
WHERE id IN ('commerce-advanced-30-v2','commerce-pro-30-v2');
