-- Official import topics are captured at import time and used to seed catalog tags on review.
ALTER TABLE content_books ADD COLUMN IF NOT EXISTS topics JSONB NOT NULL DEFAULT '[]'::jsonb;
CREATE INDEX IF NOT EXISTS catalog_books_level_idx ON catalog_books(level, resource_type, publication_status);
