ALTER TABLE payment_orders DROP CONSTRAINT IF EXISTS payment_orders_provider_check;
ALTER TABLE payment_orders ADD CONSTRAINT payment_orders_provider_check
  CHECK (provider IN ('paddle','mbdpay','alipay'));

ALTER TABLE payment_orders DROP CONSTRAINT IF EXISTS payment_orders_status_check;
ALTER TABLE payment_orders ADD CONSTRAINT payment_orders_status_check
  CHECK (status IN ('pending','paid','failed','cancelled','refunding','refunded'));

ALTER TABLE payment_orders
  ADD COLUMN IF NOT EXISTS refund_amount_cents INTEGER NOT NULL DEFAULT 0 CHECK (refund_amount_cents >= 0),
  ADD COLUMN IF NOT EXISTS refund_reason TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS refund_requested_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS refunded_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS membership_change_order_id TEXT REFERENCES membership_change_orders(id) ON DELETE SET NULL;
ALTER TABLE payment_orders
  ADD COLUMN IF NOT EXISTS membership_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS payment_code_url TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS payment_orders_admin_idx
  ON payment_orders(provider,status,created_at DESC);

CREATE INDEX IF NOT EXISTS commerce_redemption_codes_admin_idx
  ON commerce_redemption_codes(status,redeemed_at DESC,created_at DESC);
