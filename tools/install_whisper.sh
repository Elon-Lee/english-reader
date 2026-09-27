#!/bin/sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
SOURCE="$ROOT_DIR/tools/vendor/whisper.cpp"
if [ ! -d "$SOURCE/.git" ]; then
  git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git "$SOURCE"
fi
cmake -S "$SOURCE" -B "$SOURCE/build" -DWHISPER_BUILD_EXAMPLES=ON -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_SERVER=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build "$SOURCE/build" --config Release -j 4
if [ ! -f "$SOURCE/models/ggml-base.en.bin" ]; then
  "$SOURCE/models/download-ggml-model.sh" base.en
fi
echo "Whisper ready: $SOURCE/build/bin/whisper-cli"
