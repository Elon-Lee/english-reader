#!/bin/sh
set -eu
cd "$(dirname "$0")"

cert=".local/https/reader-cert.pem"
key=".local/https/reader-key.pem"
if [ ! -f "$cert" ] || [ ! -f "$key" ]; then
  echo "未找到可信HTTPS证书，请先运行：./tools/setup_https.sh" >&2
  exit 1
fi

export READER_HOST="${READER_HOST:-0.0.0.0}"
export READER_PORT="${READER_HTTPS_PORT:-8766}"
export READER_TLS_CERT="$cert"
export READER_TLS_KEY="$key"
exec python3 tools/reader_server.py
