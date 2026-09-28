#!/bin/sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
TARGET="$ROOT_DIR/.local/bin/yt-dlp"
mkdir -p "$(dirname "$TARGET")"
curl -fL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos -o "$TARGET"
chmod +x "$TARGET"
"$TARGET" --version
