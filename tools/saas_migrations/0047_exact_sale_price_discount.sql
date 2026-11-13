-- Keep exact integer-cent sale prices independent of display-only discounts.
-- Very small positive prices can round to 0.0 折; do not rewrite old snapshots.
ALTER TABLE commerce_product_versions
  DROP CONSTRAINT IF EXISTS commerce_product_price_discount_check;
ALTER TABLE commerce_product_versions
  ADD CONSTRAINT commerce_product_price_discount_check
  CHECK (original_amount_cents >= 0 AND discount_percent BETWEEN 0 AND 100);
