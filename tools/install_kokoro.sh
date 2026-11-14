#!/bin/sh
set -eu
root_dir=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
kokoro_home=${SHIYUE_KOKORO_HOME:-"$root_dir/.local/kokoro"}
kokoro_python=${PYTHON311:-"$root_dir/.local/saas-venv/bin/python"}
"$kokoro_python" -c 'import sys; assert sys.version_info[:2] == (3, 11), "Kokoro installer requires Python 3.11"'
"$kokoro_python" -m venv "$kokoro_home/venv"
"$kokoro_home/venv/bin/python" -m pip install -r "$root_dir/requirements-kokoro.txt"
"$kokoro_home/venv/bin/python" -m pip install 'https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl'
exec "$kokoro_home/venv/bin/python" "$root_dir/tools/setup_kokoro.py" --home "$kokoro_home"
