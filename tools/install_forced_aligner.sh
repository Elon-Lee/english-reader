#!/bin/sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
PYTHON=${PYTHON311:-$(command -v python3.11 || true)}
if [ ! -x "$PYTHON" ]; then
  echo "Python 3.11 is required. Set PYTHON311 to its executable path." >&2
  exit 1
fi
exec "$PYTHON" "$ROOT_DIR/tools/forced_aligner_setup.py" --root "$ROOT_DIR" "$@"
