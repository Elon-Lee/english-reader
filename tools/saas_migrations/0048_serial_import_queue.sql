-- Only explicitly submitted processing enters the shared FIFO. Uploads and
-- incomplete companion audio must never block other users' processing.
CREATE SEQUENCE IF NOT EXISTS workspace_import_queue_order_seq;
ALTER TABLE workspace_import_tasks ADD COLUMN IF NOT EXISTS queue_order BIGINT;
CREATE INDEX IF NOT EXISTS workspace_import_tasks_queue_idx
  ON workspace_import_tasks(queue_order) WHERE status IN ('queued','running');

-- Retain recoverability of work interrupted by this upgrade.
UPDATE workspace_import_tasks SET queue_order=nextval('workspace_import_queue_order_seq')
WHERE status='running' AND queue_order IS NULL;
