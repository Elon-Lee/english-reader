#!/bin/sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
PYTHON_BIN=${SHIYUE_GRAMMAR_PYTHON:-"$ROOT_DIR/.local/forced-aligner/venv/bin/python"}
MODEL_DIR=${SHIYUE_GRAMMAR_MODEL_DIR:-"$ROOT_DIR/.local/grammar/stanza"}
if [ ! -x "$PYTHON_BIN" ]; then
  echo "缺少 Python 3.11 对齐环境：$PYTHON_BIN" >&2
  exit 1
fi
"$PYTHON_BIN" -m pip install stanza
SHIYUE_GRAMMAR_MODEL_DIR="$MODEL_DIR" "$PYTHON_BIN" - <<'PY'
import os,stanza
stanza.download("en",model_dir=os.environ["SHIYUE_GRAMMAR_MODEL_DIR"],processors="tokenize,pos,lemma,depparse,constituency")
PY
echo "Stanza 英文句法模型已安装到：$MODEL_DIR"
