-- User decision: legacy SQLite audio/video/YouTube titles are not automatic
-- SaaS private-workspace imports. Keep their landing records and media for
-- later manual official-catalog review, but hide them from owner workspaces.
UPDATE content_books
SET visibility='blocked',updated_at=NOW()
WHERE source_type IN ('audio','video','youtube')
  AND visibility IN ('private','draft')
  AND source_path NOT LIKE 'workspace/%';
