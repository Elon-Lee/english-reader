#!/bin/sh
# Install the independent local toolchain on macOS or Linux from verified sources.
# Existing project data and configuration are never replaced.
set -eu
cd "$(dirname "$0")/.."
project_dir=$PWD
tool_dir="$project_dir/.local/local-dev/tools"
mkdir -p "$tool_dir"
chmod 700 "$project_dir/.local/local-dev"
case "$(uname -s)" in
  Darwin) node_os=darwin; java_os=macos; python_os=macos ;;
  Linux) node_os=linux; java_os=linux; python_os=linux ;;
  *) echo '仅支持 macOS / Linux；Windows 请使用 Ubuntu 24.04 WSL2。' >&2; exit 1 ;;
esac
case "$(uname -m)" in
  x86_64) node_arch=x64; java_arch=x64 ;;
  arm64|aarch64) node_arch=arm64; java_arch=aarch64 ;;
  *) echo '仅支持 x86_64 / arm64。' >&2; exit 1 ;;
esac
if [ -f .local/local-dev/postgres/postmaster.pid ]; then
  echo '请先执行 ./start-reader.sh --stop-saas-local，再安装或更新依赖。' >&2; exit 1
fi
for dependency in make cc curl tar shasum; do
  command -v "$dependency" >/dev/null || { echo "缺少 $dependency，请先按 docs/LOCAL_DEVELOPMENT.md 安装系统前置依赖。" >&2; exit 1; }
done
local_python="${LOCAL_PYTHON_BIN:-}"
if [ -z "$local_python" ]; then
  for candidate in python3.11 python3.12 python3.13 python3 /usr/local/opt/python@3.11/bin/python3.11 /opt/homebrew/opt/python@3.11/bin/python3.11 "$HOME/.local/share/uv/python/cpython-3.11-$python_os-$(uname -m)-none/bin/python3.11"; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; assert sys.version_info >= (3,11)' >/dev/null 2>&1; then
      local_python=$(command -v "$candidate"); break
    fi
  done
fi
if [ -z "$local_python" ]; then echo '需要 Python 3.11+；安装方法见 docs/LOCAL_DEVELOPMENT.md。' >&2; exit 1; fi
"$local_python" -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'

verify_sha256() {
  actual=$(shasum -a 256 "$1" | awk '{print $1}')
  if [ "$actual" != "$2" ]; then echo "SHA256 校验失败：$1" >&2; exit 1; fi
}
if [ ! -x "$tool_dir/postgresql/bin/pg_ctl" ]; then
  archive="$tool_dir/postgresql-16.15.tar.bz2"
  curl -fL --retry 2 https://ftp.postgresql.org/pub/source/v16.15/postgresql-16.15.tar.bz2 -o "$archive"
  verify_sha256 "$archive" c1575341fa7bd40f5274ea465b34390f4dc64cdd0770af327005caaeb9f6b7ed
  tar -xjf "$archive" -C "$tool_dir"
  (
    cd "$tool_dir/postgresql-16.15"
    if [ "$node_os" = darwin ]; then
      openssl_dir="${LOCAL_OPENSSL_DIR:-/usr/local/opt/openssl@3}"
      if [ ! -d "$openssl_dir/include/openssl" ]; then openssl_dir=/opt/homebrew/opt/openssl@3; fi
      if [ ! -d "$openssl_dir/include/openssl" ]; then echo '请先安装 openssl@3 或设置 LOCAL_OPENSSL_DIR。' >&2; exit 1; fi
      ./configure --prefix="$tool_dir/postgresql" --without-icu --without-readline --with-openssl \
        --with-includes="$openssl_dir/include" --with-libraries="$openssl_dir/lib"
    else
      ./configure --prefix="$tool_dir/postgresql" --without-icu --without-readline --with-openssl
    fi
    make -j4
    make install
  ) > "$tool_dir/postgresql-install.log" 2>&1
fi
if [ ! -x "$tool_dir/redis/bin/redis-server" ]; then
  archive="$tool_dir/redis-7.4.7.tar.gz"
  curl -fL --retry 2 https://download.redis.io/releases/redis-7.4.7.tar.gz -o "$archive"
  verify_sha256 "$archive" c97e57b0df330a9e091cacff012bebe763c275398cf36ff44cdba876814b595b
  tar -xzf "$archive" -C "$tool_dir"
  make -C "$tool_dir/redis-7.4.7" -j4 BUILD_TLS=no MALLOC=libc install PREFIX="$tool_dir/redis" \
    > "$tool_dir/redis-install.log" 2>&1
fi
if [ ! -x "$tool_dir/node/bin/node" ]; then
  node_name="node-v22.16.0-$node_os-$node_arch"
  curl -fL --retry 2 "https://nodejs.org/dist/v22.16.0/$node_name.tar.gz" -o "$tool_dir/$node_name.tar.gz"
  curl -fL --retry 2 https://nodejs.org/dist/v22.16.0/SHASUMS256.txt -o "$tool_dir/node-SHASUMS256.txt"
  node_sha=$(awk -v filename="$node_name.tar.gz" '$2 == filename {print $1}' "$tool_dir/node-SHASUMS256.txt")
  verify_sha256 "$tool_dir/$node_name.tar.gz" "$node_sha"
  tar -xzf "$tool_dir/$node_name.tar.gz" -C "$tool_dir"
  ln -s "$node_name" "$tool_dir/node"
fi
if [ ! -x .local/captcha-tools/jdk/bin/javac ]; then
  java_dir="$project_dir/.local/captcha-tools"
  mkdir -p "$java_dir"
  java_name="amazon-corretto-21-$java_arch-$java_os-jdk.tar.gz"
  curl -fL --retry 2 "https://corretto.aws/downloads/latest/$java_name" -o "$java_dir/$java_name"
  curl -fL --retry 2 "https://corretto.aws/downloads/latest/$java_name.sha256" -o "$java_dir/$java_name.sha256"
  java_sha=$(awk '{print $1}' "$java_dir/$java_name.sha256")
  verify_sha256 "$java_dir/$java_name" "$java_sha"
  java_unpack=$(mktemp -d "$java_dir/jdk21.XXXXXX")
  tar -xzf "$java_dir/$java_name" -C "$java_unpack"
  java_root=$(tar -tzf "$java_dir/$java_name" | awk -F/ 'NF && $1 != "." {print $1; exit}')
  if [ "$node_os" = darwin ]; then java_root="$java_root/Contents/Home"; fi
  test -x "$java_unpack/$java_root/bin/javac"
  ln -s "$java_unpack/$java_root" "$java_dir/jdk"
fi
if [ ! -x .local/saas-venv/bin/python ]; then
  "$local_python" -m venv .local/saas-venv
fi
.local/saas-venv/bin/python -m pip install -r requirements-saas.txt
PATH="$tool_dir/node/bin:$PATH" npm ci --no-audit --no-fund
# Make the prepared project JDK explicit; ignore stale JAVA_HOME from other sessions.
JAVA_HOME="$project_dir/.local/captcha-tools/jdk" sh services/captcha/build.sh --check
JAVA_HOME="$project_dir/.local/captcha-tools/jdk" .local/saas-venv/bin/python -c \
  'import sys; sys.path.insert(0,"tools"); import run_local_dev as d; d.ensure_captcha_build(dict(d.os.environ), d.ROOT / "services/captcha/target/shiyue-captcha-1.0.0.jar")'
echo '本地依赖已就绪，运行 ./start-reader.sh --saas-local 启动全部调试服务。'
