-- Personal imports retain personal ownership, including previously reviewed imports.
UPDATE media_assets ma SET catalog_book_id=NULL,scope='private'
WHERE ma.catalog_book_id IN (
  SELECT c.id FROM catalog_books c JOIN workspace_import_tasks t ON t.output_book_id=c.source_content_book_id
  WHERE COALESCE(t.metadata_json->>'officialImport','false')<>'true'
);

UPDATE content_books b SET visibility='private',updated_at=NOW()
WHERE EXISTS (SELECT 1 FROM workspace_import_tasks t WHERE t.output_book_id=b.id
  AND COALESCE(t.metadata_json->>'officialImport','false')<>'true');

DELETE FROM official_book_unlocks WHERE catalog_book_id IN (
  SELECT c.id FROM catalog_books c JOIN workspace_import_tasks t ON t.output_book_id=c.source_content_book_id
  WHERE COALESCE(t.metadata_json->>'officialImport','false')<>'true'
);

DELETE FROM catalog_books c USING workspace_import_tasks t
WHERE t.output_book_id=c.source_content_book_id
  AND COALESCE(t.metadata_json->>'officialImport','false')<>'true';
