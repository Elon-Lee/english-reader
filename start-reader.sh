#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 tools/reader_server.py
