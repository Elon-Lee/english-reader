-- Do not invent creation dates for historical vocabulary.
ALTER TABLE content_vocabulary ADD COLUMN created_at TIMESTAMPTZ;
CREATE INDEX vocabulary_owner_created ON content_vocabulary(owner_id,created_at);
