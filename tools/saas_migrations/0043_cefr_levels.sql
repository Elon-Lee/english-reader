-- Migrate level values to CEFR standard (A1, A2, B1, B2, C1, C2)
-- Convert legacy levels to their CEFR equivalents

UPDATE catalog_books SET level = 'A1' WHERE level IN ('starter', 'beginner');
UPDATE catalog_books SET level = 'A2' WHERE level = 'elementary';
UPDATE catalog_books SET level = 'B1' WHERE level IN ('preIntermediate', 'pre-intermediate', 'intermediate');
UPDATE catalog_books SET level = 'B2' WHERE level IN ('upperIntermediate', 'upper-intermediate');
UPDATE catalog_books SET level = 'C1' WHERE level = 'advanced';
UPDATE catalog_books SET level = 'C2' WHERE level = 'proficiency';

UPDATE content_books SET level = 'A1' WHERE level IN ('starter', 'beginner');
UPDATE content_books SET level = 'A2' WHERE level = 'elementary';
UPDATE content_books SET level = 'B1' WHERE level IN ('preIntermediate', 'pre-intermediate', 'intermediate');
UPDATE content_books SET level = 'B2' WHERE level IN ('upperIntermediate', 'upper-intermediate');
UPDATE content_books SET level = 'C1' WHERE level = 'advanced';
UPDATE content_books SET level = 'C2' WHERE level = 'proficiency';
