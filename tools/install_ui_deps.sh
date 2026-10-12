#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "[1/5] 检查 Node.js / npm"
node --version
npm --version

OFFICIAL_REGISTRY="https://registry.npmjs.org/"
MIRROR_REGISTRY="https://registry.npmmirror.com/"
OLD_REGISTRY="$(npm config get registry 2>/dev/null || true)"
SELECTED_REGISTRY="$OFFICIAL_REGISTRY"

echo "[2/5] 检查 npm 官方源"
if curl -fsSI --max-time 12 "${OFFICIAL_REGISTRY}bootstrap" >/dev/null 2>&1; then
  echo "官方源可访问：${OFFICIAL_REGISTRY}"
else
  echo "官方源不可访问，尝试镜像：${MIRROR_REGISTRY}"
  if ! curl -fsSI --max-time 12 "${MIRROR_REGISTRY}bootstrap" >/dev/null 2>&1; then
    echo "错误：官方源和镜像都无法访问。请检查 DNS、代理或网络权限。" >&2
    exit 2
  fi
  SELECTED_REGISTRY="$MIRROR_REGISTRY"
fi

echo "[3/5] 使用 registry：${SELECTED_REGISTRY}"
npm install \
  --registry="${SELECTED_REGISTRY}" \
  --fetch-retries=3 \
  --fetch-retry-factor=2 \
  --fetch-retry-mintimeout=1000 \
  --fetch-retry-maxtimeout=10000 \
  --fetch-timeout=60000

echo "[4/5] 验证依赖"
node -e 'for (const name of ["bootstrap/package.json", "bootstrap-icons/package.json"]) { console.log(name + ": " + require.resolve(name)); }'

echo "[5/5] 安装完成"
echo "当前 registry：${SELECTED_REGISTRY}"
if [[ -n "${OLD_REGISTRY}" && "${OLD_REGISTRY}" != "undefined" ]]; then
  echo "如需恢复安装前 registry："
  echo "npm config set registry ${OLD_REGISTRY}"
fi
echo "现在可以运行：npm run check:js && npm run test:ui"
