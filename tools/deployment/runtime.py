"""Bootstrap a clean Linux node without requiring a previous project image."""
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import tarfile
import tempfile
import urllib.request

WHISPER_VERSION = '1.7.6'
SOURCE_URL = 'https://codeload.github.com/ggml-org/whisper.cpp/tar.gz/refs/tags/v' + WHISPER_VERSION
SOURCE_SHA256 = '166140e9a6d8a36f787a2bd77f8f44dd64874f12dd8359ff7c1f4f9acb86202e'
MODEL_URL = 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin'
MODEL_SHA256 = 'a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002'


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def download_verified(url, destination, expected):
    destination = Path(destination)
    if destination.is_file() and digest(destination) == expected:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, suffix='.download')
    try:
        with os.fdopen(descriptor, 'wb') as output, urllib.request.urlopen(url, timeout=120) as source:
            shutil.copyfileobj(source, output, 1024 * 1024)
        if digest(temporary) != expected:
            raise ValueError('部署依赖 SHA-256 校验失败：' + destination.name)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination


def prepare_model(job, root):
    legacy = Path(root) / 'tools/vendor/whisper.cpp/models/ggml-base.en.bin'
    job.write('准备录音转写模型，按固定 SHA-256 校验并复用本机缓存')
    if legacy.is_file() and digest(legacy) == MODEL_SHA256:
        return legacy
    model = Path(root) / '.local/deployment/runtime/models/ggml-base.en.bin'
    return download_verified(MODEL_URL, model, MODEL_SHA256)


def prepare_context(job, root, cache):
    cache = Path(cache)
    job.write('准备固定版本 whisper.cpp 源码，用于空节点运行镜像构建')
    source = download_verified(SOURCE_URL, cache / ('whisper-v' + WHISPER_VERSION + '.tar.gz'), SOURCE_SHA256)
    context = cache / ('runtime-source-v' + WHISPER_VERSION + '.tar.gz')
    with tarfile.open(source) as upstream, tarfile.open(context, 'w:gz') as output:
        output.add(Path(root) / 'deployment/docker/Dockerfile.runtime', arcname='Dockerfile')
        prefix = 'whisper.cpp-' + WHISPER_VERSION + '/'
        for member in upstream.getmembers():
            if not member.name.startswith(prefix):
                continue
            relative = member.name[len(prefix):]
            if not relative or '..' in Path(relative).parts or not (member.isdir() or member.isfile()):
                continue
            content = upstream.extractfile(member) if member.isfile() else None
            member.name = 'whisper.cpp/' + relative
            output.addfile(member, content)
    return context, digest(context)


def build(job, remote, root, cache, image, arch):
    if arch not in ('amd64', 'arm64'):
        raise ValueError('不支持的 Linux 运行镜像架构：' + arch)
    context, checksum = prepare_context(job, root, cache)
    uploaded = '/tmp/shiyue-runtime-source-' + checksum[:16] + '.tar.gz'
    remote.scp(context, uploaded)
    job.write('空节点从源码构建 Linux 运行环境（Python、FFmpeg、whisper.cpp），不依赖旧项目镜像')
    remote.ssh(f'''set -euo pipefail
archive={shlex.quote(uploaded)}
test "$(sha256sum "$archive" | cut -d' ' -f1)" = {shlex.quote(checksum)}
build_dir=$(mktemp -d /tmp/shiyue-runtime-build.XXXXXX)
trap 'rm -rf -- "$build_dir"; rm -f -- "$archive"' EXIT
tar -xzf "$archive" -C "$build_dir"
pull_base() {{
  official="$1"
  docker image inspect "$official" >/dev/null 2>&1 && return 0
  if docker pull "m.daocloud.io/docker.io/library/$official"; then
    docker tag "m.daocloud.io/docker.io/library/$official" "$official"
  else
    docker pull "$official"
  fi
}}
pull_base debian:bookworm-slim
pull_base python:3.11-slim-bookworm
mirror=http://deb.debian.org
security=http://deb.debian.org/debian-security
if curl --fail --silent --location --max-time 15 -o /dev/null http://mirrors.aliyun.com/debian/dists/bookworm/InRelease && \
   curl --fail --silent --location --max-time 15 -o /dev/null http://mirrors.aliyun.com/debian-security/dists/bookworm-security/InRelease; then
  mirror=http://mirrors.aliyun.com
  security=http://mirrors.aliyun.com/debian-security
fi
docker build --platform linux/{arch} --build-arg "DEBIAN_MIRROR=$mirror" --build-arg "DEBIAN_SECURITY_MIRROR=$security" -t {shlex.quote(image)} "$build_dir"
docker run --rm --network none {shlex.quote(image)} sh -ec 'python3 --version; ffmpeg -version >/dev/null; /opt/shiyue/whisper/whisper-cli --help >/dev/null 2>&1'
echo SHIYUE_RUNTIME_BUILT
''')
