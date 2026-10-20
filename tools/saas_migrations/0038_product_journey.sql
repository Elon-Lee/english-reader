-- Only authenticated purchase intent and server-confirmed learning milestones.
-- Never store redemption codes, payment credentials, or external payment status.
CREATE TABLE product_journey_events (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL CHECK (event_type IN ('first_reading','first_word_saved','plan_selected','purchase_departure')),
  product_version_id TEXT REFERENCES commerce_product_versions(id) ON DELETE SET NULL,
  idempotency_key TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id,idempotency_key)
);
CREATE INDEX product_journey_events_user_type_idx ON product_journey_events(user_id,event_type,created_at);
CREATE INDEX product_journey_events_created_idx ON product_journey_events(created_at);
