"""Durable FIFO shared by domestic official and international private imports."""
from __future__ import annotations

import copy
import threading

from saas_resources import as_json

_DISPATCHERS = {}
_GUARD = threading.Lock()
_LOCK = 'workspace-import-global-processing'


def enabled(environment):
    # Online serialization remains enforced even when the memory budget is 0.
    return environment.get('SHIYUE_DEPLOYMENT_MODE') == 'remote' or environment.get('SHIYUE_IMPORT_SERIAL') == '1'


def dispatch_once(service):
    """Hold a session advisory lock for the entire processing tree's lifetime."""
    connection = service.accounts._connect()
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0))', (_LOCK,))
            if not cursor.fetchone()[0]:
                return False
            cursor.execute("""SELECT *, updated_at < NOW()-INTERVAL '80 minutes' AS stale
                FROM workspace_import_tasks WHERE queue_order IS NOT NULL
                  AND status IN ('queued','running') ORDER BY queue_order,id LIMIT 1""")
            task = service.accounts._one(cursor)
            if not task or task['status'] == 'running' and not task['stale']:
                return False
            processor = copy.copy(service)
            processor.official = bool(as_json(task['metadata_json']).get('officialImport'))
            try:
                processor.complete(task['user_id'], task['id'], _queue_claimed=True)
            except Exception:
                # Startup/permission failures can happen before complete's normal
                # failure handler. Never let one such task block the whole FIFO.
                cursor.execute("""UPDATE workspace_import_tasks SET status='failed',step='导入失败',
                    error=CASE WHEN error='' THEN '导入处理未完成，请检查账号权限或处理器配置后重试。' ELSE error END,
                    updated_at=NOW() WHERE id=%s AND status IN ('queued','running')""", (task['id'],))
            return True
    finally:
        # Closing the connection also releases the lock after failures/restarts.
        connection.close()


def start_dispatcher(service):
    """Poll persisted jobs after restarts; no model or worker per waiting task."""
    if not enabled(service.accounts.environment) or service.accounts.environment.get('SHIYUE_IMPORT_DISPATCHER') == '0':
        return
    key = id(service.accounts)
    with _GUARD:
        if key in _DISPATCHERS:
            _DISPATCHERS[key].set()
            return
        wake = threading.Event()
        _DISPATCHERS[key] = wake

        def run():
            while True:
                try:
                    if dispatch_once(service):
                        continue
                except Exception:
                    # A transient database outage leaves queued jobs intact.
                    pass
                wake.wait(2)
                wake.clear()

        threading.Thread(target=run, daemon=True, name='import-fifo').start()
