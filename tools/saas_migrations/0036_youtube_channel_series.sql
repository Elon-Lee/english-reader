-- Only replace the automatic import label; preserve manually assigned series.
UPDATE content_books
SET series = BTRIM(data_json->'youtube'->>'channel'), updated_at = NOW()
WHERE source_type = 'youtube' AND series IN ('', '私人导入')
  AND COALESCE(BTRIM(data_json->'youtube'->>'channel'), '') <> '';

INSERT INTO catalog_series(id, slug, title)
SELECT DISTINCT 'youtube-channel-' || MD5(src.series),
       'youtube-channel-' || MD5(src.series), src.series
FROM catalog_books cb JOIN content_books src ON src.id=cb.source_content_book_id
LEFT JOIN catalog_series cs ON cs.id=cb.series_id
WHERE src.source_type='youtube' AND src.series <> '' AND src.series <> '私人导入'
  AND COALESCE(cs.title, '') IN ('', '私人导入')
ON CONFLICT DO NOTHING;

UPDATE catalog_books cb SET series_id=channel.id, updated_at=NOW()
FROM content_books src, catalog_series channel
WHERE cb.source_content_book_id=src.id AND src.source_type='youtube'
  AND channel.id='youtube-channel-' || MD5(src.series)
  AND (cb.series_id IS NULL OR cb.series_id IN (SELECT id FROM catalog_series WHERE title='私人导入'));
