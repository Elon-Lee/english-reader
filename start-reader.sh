#!/bin/sh
set -eu
cd "$(dirname "$0")"
# Dispatch before loading .env or READER_PYTHON from older/manual environments.
case "${1:---saas-local}" in
  --saas-local|--stop-saas-local|--restart-saas-local|--status-saas-local)
    case "${1:---saas-local}" in
      --stop-saas-local) local_action=stop ;;
      --restart-saas-local) local_action=restart ;;
      --status-saas-local) local_action=status ;;
      *) local_action=start ;;
    esac
    if [ "$#" -gt 1 ] && { [ "$local_action" != start ] || [ "$#" -gt 2 ] || [ "$2" != 8790 ]; }; then
      echo '本地启动使用 ./start-reader.sh --saas-local；固定前端 4173、后台 8790。' >&2
      exit 2
    fi
    if [ ! -x .local/saas-venv/bin/python ]; then
      echo '请先运行 sh tools/install_local_services.sh；完整说明见 docs/LOCAL_DEVELOPMENT.md。' >&2
      exit 2
    fi
    exec .local/saas-venv/bin/python tools/run_local_dev.py "$local_action"
    ;;
esac
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
saas_ui_smoke_mode=0
stop_debug_mode=0
saas_walkthrough_mode=0
if [ "${1:-}" = "--saas-walkthrough" ]; then
  saas_walkthrough_mode=1
  READER_PORT="${2:-8790}"
  SHIYUE_BROWSER_PASSWORD="${3:-}"
  SHIYUE_WALKTHROUGH_ONLY="${4:-}"
  SHIYUE_RUN_WALKTHROUGH=1
  export SHIYUE_BROWSER_PASSWORD SHIYUE_RUN_WALKTHROUGH SHIYUE_WALKTHROUGH_ONLY
elif [ "${1:-}" = "--stop-debug" ]; then
  stop_debug_mode=1
elif [ "${1:-}" = "--saas-ui-smoke" ]; then
  saas_ui_smoke_mode=1
  READER_PORT="${2:-8792}"
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
export SHIYUE_DEPLOYMENT_MODE="${SHIYUE_DEPLOYMENT_MODE:-local}"
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
if [ "$saas_walkthrough_mode" -eq 1 ]; then
  exec "$reader_python" tools/run_local_saas.py
fi
exec "$reader_python" tools/reader_server.py
