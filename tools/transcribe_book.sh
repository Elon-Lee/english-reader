#!/bin/sh
set -eu
if [ "$#" -lt 3 ]; then
  echo "Usage: $0 <audio> <book.json> <output-prefix>" >&2
  exit 2
fi
ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
AUDIO=$1
BOOK=$2
PREFIX=$3
mkdir -p "$(dirname "$PREFIX")"
CLI="$ROOT_DIR/tools/vendor/whisper.cpp/build/bin/whisper-cli"
MODEL="$ROOT_DIR/tools/vendor/whisper.cpp/models/ggml-base.en.bin"
"$CLI" -m "$MODEL" -f "$AUDIO" -l en -t 4 -p 2 -ng -ml 1 -sow -ojf -of "$PREFIX" -np
python3 "$ROOT_DIR/tools/align_whisper.py" --book "$BOOK" --whisper "$PREFIX.json" --report "$PREFIX-alignment.json"
