#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
cd "$project_dir"

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
smoke_mode=0
if [ "${1:-}" = "--smoke" ]; then
  smoke_mode=1
  READER_HTTPS_PORT="${2:-8786}"
elif [ "$#" -gt 0 ]; then
  READER_HTTPS_PORT="$1"
fi

cert="$project_dir/.local/https/reader-cert.pem"
key="$project_dir/.local/https/reader-key.pem"
if [ ! -f "$cert" ] || [ ! -f "$key" ]; then
  echo "未找到可信HTTPS证书，请先运行：./tools/setup_https.sh" >&2
  exit 1
fi

export READER_HOST="${READER_HOST:-0.0.0.0}"
export READER_PORT="${READER_HTTPS_PORT:-8766}"
export READER_TLS_CERT="$cert"
export READER_TLS_KEY="$key"
reader_python="${READER_PYTHON:-python3}"
if [ -z "${READER_PYTHON:-}" ] && [ -x .local/saas-venv/bin/python ]; then
  reader_python=".local/saas-venv/bin/python"
fi
if [ "$smoke_mode" -eq 1 ]; then
  exec "$reader_python" tools/local_smoke.py
fi
exec "$reader_python" tools/reader_server.py
