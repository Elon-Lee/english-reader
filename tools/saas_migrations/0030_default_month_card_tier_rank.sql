-- Correct the default Advanced card tier so Pro redemptions upgrade immediately.
-- Prices, quotas, product snapshots and historical orders stay unchanged.
UPDATE plan_versions
SET rank=1
WHERE id='commerce-advanced-30-v2' AND rank=2;
