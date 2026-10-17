-- Older commerce seed/restore scripts can insert immutable historical rows
-- without merchandising reference-price fields. Runtime writes still derive
-- the sale price from the configured original price and discount percentage.
ALTER TABLE commerce_product_versions
  DROP CONSTRAINT IF EXISTS commerce_product_price_discount_check;

ALTER TABLE commerce_product_versions
  ADD CONSTRAINT commerce_product_price_discount_check
  CHECK (original_amount_cents >= 0 AND discount_percent BETWEEN 1 AND 100);
