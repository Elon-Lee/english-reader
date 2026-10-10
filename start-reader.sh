#!/bin/sh
set -eu
cd "$(dirname "$0")"
# .env is intentionally ignored by Git. It is optional and is only needed for
# the staged PostgreSQL/SaaS rollout; legacy local-reader startup is unchanged.
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
smoke_mode=0
saas_test_mode=0
saas_smoke_mode=0
readiness_mode=0
backup_mode=0
local_saas_mode=0
saas_ui_smoke_mode=0
stop_debug_mode=0
stop_local_saas_mode=0
saas_walkthrough_mode=0
if [ "${1:-}" = "--saas-walkthrough" ]; then
  saas_walkthrough_mode=1
  READER_PORT="${2:-8790}"
  SHIYUE_BROWSER_PASSWORD="${3:-}"
  SHIYUE_WALKTHROUGH_ONLY="${4:-}"
  SHIYUE_RUN_WALKTHROUGH=1
  export SHIYUE_BROWSER_PASSWORD SHIYUE_RUN_WALKTHROUGH SHIYUE_WALKTHROUGH_ONLY
elif [ "${1:-}" = "--stop-saas-local" ]; then
  stop_local_saas_mode=1
elif [ "${1:-}" = "--stop-debug" ]; then
  stop_debug_mode=1
elif [ "${1:-}" = "--saas-ui-smoke" ]; then
  saas_ui_smoke_mode=1
  READER_PORT="${2:-8792}"
elif [ "${1:-}" = "--saas-local" ]; then
  local_saas_mode=1
  READER_PORT="${2:-8790}"
elif [ "${1:-}" = "--saas-backup" ]; then
  backup_mode=1
elif [ "${1:-}" = "--readiness" ]; then
  readiness_mode=1
elif [ "${1:-}" = "--saas-smoke" ]; then
  saas_smoke_mode=1
  READER_PORT="${2:-8795}"
elif [ "${1:-}" = "--saas-test" ]; then
  saas_test_mode=1
elif [ "${1:-}" = "--smoke" ]; then
  smoke_mode=1
  READER_PORT="${2:-8785}"
elif [ "$#" -gt 0 ]; then
  READER_PORT="$1"
fi
export READER_HOST="${READER_HOST:-0.0.0.0}"
export READER_PORT="${READER_PORT:-8765}"
reader_python="${READER_PYTHON:-python3}"
if [ -z "${READER_PYTHON:-}" ] && [ -x .local/saas-venv/bin/python ]; then
  reader_python=".local/saas-venv/bin/python"
fi
if [ "$smoke_mode" -eq 1 ]; then
  exec "$reader_python" tools/local_smoke.py
fi
if [ "$saas_test_mode" -eq 1 ]; then
  exec "$reader_python" tools/run_saas_debug.py
fi
if [ "$saas_smoke_mode" -eq 1 ]; then
  exec "$reader_python" tools/saas_http_smoke.py
fi
if [ "$readiness_mode" -eq 1 ]; then
  exec "$reader_python" tools/saas_readiness.py --env-file .env
fi
if [ "$backup_mode" -eq 1 ]; then
  exec "$reader_python" tools/run_saas_backup.py
fi
if [ "$local_saas_mode" -eq 1 ]; then
  exec "$reader_python" tools/run_local_saas.py
fi
if [ "$saas_ui_smoke_mode" -eq 1 ]; then
  export SHIYUE_SAAS_ENABLED=1
  export READER_HOST=127.0.0.1
  export BOOTSTRAP_ADMIN_EMAIL=
  export BOOTSTRAP_ADMIN_PASSWORD=
  exec "$reader_python" tools/saas_ui_smoke.py
fi
if [ "$stop_debug_mode" -eq 1 ]; then
  exec "$reader_python" tools/stop_debug_services.py
fi
if [ "$stop_local_saas_mode" -eq 1 ]; then
  exec "$reader_python" tools/stop_local_saas.py
fi
if [ "$saas_walkthrough_mode" -eq 1 ]; then
  exec "$reader_python" tools/run_local_saas.py
fi
exec "$reader_python" tools/reader_server.py
