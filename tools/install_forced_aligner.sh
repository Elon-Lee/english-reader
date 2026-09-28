#!/bin/sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
PYTHON=${PYTHON311:-/usr/local/bin/python3.11}
VENV="$ROOT_DIR/.local/forced-aligner/venv"
if [ ! -x "$PYTHON" ]; then
  echo "Python 3.11 is required. Install with: brew install python@3.11" >&2
  exit 1
fi
"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/pip" install 'numpy<2' 'torch==2.2.2' 'torchaudio==2.2.2'
mkdir -p "$ROOT_DIR/.local/forced-aligner/models"
TORCH_HOME="$ROOT_DIR/.local/forced-aligner/models" "$VENV/bin/python" -c 'import torchaudio; torchaudio.pipelines.WAV2VEC2_ASR_BASE_960H.get_model(); print("Forced aligner ready")'
