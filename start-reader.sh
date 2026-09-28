#!/bin/sh
set -eu
cd "$(dirname "$0")"
export READER_HOST="${READER_HOST:-0.0.0.0}"
export READER_PORT="${READER_PORT:-8765}"
python3 tools/reader_server.py
