#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

if ! command -v mkcert >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "正在安装 mkcert…"
    brew install mkcert
  else
    echo "请先安装 mkcert，然后重新运行本脚本。" >&2
    exit 1
  fi
fi

echo "接下来会把 mkcert 本地CA加入系统信任库，系统可能要求输入密码。"
mkcert -install

mkdir -p .local/https
names="localhost 127.0.0.1 ::1"
for interface in en0 en1; do
  address=$(ipconfig getifaddr "$interface" 2>/dev/null || true)
  if [ -n "$address" ]; then names="$names $address"; fi
done

# shellcheck disable=SC2086
mkcert -cert-file .local/https/reader-cert.pem -key-file .local/https/reader-key.pem $names
chmod 600 .local/https/reader-key.pem

echo "HTTPS证书已生成。启动命令：./start-reader-https.sh"
echo "默认HTTPS端口：8766"
echo "其他局域网设备也必须信任 mkcert 根证书；根证书目录：$(mkcert -CAROOT)"
