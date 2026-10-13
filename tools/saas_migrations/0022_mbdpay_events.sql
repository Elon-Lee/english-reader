-- Permit verified Mianbaoduo Pay webhook events in the shared provider event
-- ledger. External recurring subscriptions remain Paddle-only because the
-- Mianbaoduo integration sells fixed-term, one-time products.

ALTER TABLE payment_provider_events DROP CONSTRAINT IF EXISTS payment_provider_events_provider_check;
ALTER TABLE payment_provider_events ADD CONSTRAINT payment_provider_events_provider_check CHECK (provider IN ('paddle','mbdpay'));
