#!/bin/sh
set -eu

if command -v 7zz >/dev/null 2>&1 || command -v 7z >/dev/null 2>&1 || command -v extract_chmLib >/dev/null 2>&1; then
  echo "CHM 提取工具已安装。"
  exit 0
fi

if command -v brew >/dev/null 2>&1; then
  brew install sevenzip
  exit 0
fi

echo "未找到 CHM 提取工具。请安装 7-Zip 或 chmlib：" >&2
echo "  macOS: brew install sevenzip" >&2
echo "  Debian/Ubuntu: sudo apt install 7zip 或 libchm-bin" >&2
exit 1
