"""Provision CPU alignment artifacts from the deployment machine, without node egress."""
import json
import shlex
import subprocess
import sys
import tarfile
from pathlib import Path

from forced_aligner_setup import (CPU_INDEX, MODEL_FILE, MODEL_SHA256, READY,
                                  download_model, requirements, sha256, validate_bundle)


def prepare_bundle(job, cache, arch):
    if arch not in {'x86_64', 'aarch64'}:
        raise ValueError('Unsupported original-audio aligner architecture: ' + arch)
    directory = Path(cache) / ('aligner-cp311-' + arch)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        validate_bundle(directory)
    except (OSError, ValueError, KeyError):
        job.write('准备 Linux CPU 对齐依赖和原音模型（首次下载较大，后续复用校验缓存）')
        command = [sys.executable, '-m', 'pip', 'download', '--disable-pip-version-check',
                   '--only-binary=:all:', '--python-version', '311', '--implementation', 'cp',
                   '--abi', 'cp311', '--platform', 'manylinux2014_' + arch,
                   '--platform', 'linux_' + arch, '--dest', str(directory), '--timeout', '60', '--retries', '3']
        if arch == 'x86_64':
            command += ['--extra-index-url', CPU_INDEX]
        subprocess.run(command + requirements(arch), check=True, timeout=1800)
        download_model(directory / MODEL_FILE)
        files = {p.name: sha256(p) for p in directory.iterdir() if p.suffix == '.whl' or p.name == MODEL_FILE}
        (directory / 'manifest.json').write_text(json.dumps({'modelSha256': MODEL_SHA256, 'files': files}, indent=2))
        validate_bundle(directory)
    archive = directory.parent / (directory.name + '.tar')
    # Do not gzip already compressed wheels/model; keep CPU and memory bounded.
    with tarfile.open(archive, 'w', dereference=True) as output:
        manifest = json.loads((directory / 'manifest.json').read_text())
        for name in [*sorted(manifest['files']), 'manifest.json']:
            output.add(directory / name, arcname=name)
    return archive, sha256(archive)


def check_command(container='shiyue-saas-candidate'):
    return ('docker exec ' + shlex.quote(container) +
            ' python3 /app/tools/forced_aligner_setup.py --root /app --check')


def ensure_remote(job, remote, target, release, image, cache):
    root = target['remote_root']
    release_path = root + '/releases/' + release
    def run(arguments, artifacts=False):
        options = ['docker run --rm --network none',
                   '-v ' + shlex.quote(release_path + '/tools:/app/tools:ro,z'),
                   '-v ' + shlex.quote(root + '/shared/.local:/app/.local:z')]
        if artifacts:
            options.append('-v ' + shlex.quote(root + '/shared/aligner-artifacts/' + digest + ':/artifacts:ro,z'))
        return ' '.join(options + [shlex.quote(image), 'python3 /app/tools/forced_aligner_setup.py --root /app', arguments])
    job.write('检查持久化原音对齐环境和模型，执行真实 CPU 推理')
    output = remote.ssh('if ' + run('--check') + ' >/dev/null 2>&1; then echo SHIYUE_ALIGNER_REUSED; else echo SHIYUE_ALIGNER_INSTALL_REQUIRED; fi')
    if 'SHIYUE_ALIGNER_REUSED' in output:
        return
    arch = remote.ssh('uname -m').strip().splitlines()[-1]
    arch = {'amd64': 'x86_64', 'arm64': 'aarch64'}.get(arch, arch)
    archive, digest = prepare_bundle(job, cache, arch)
    job.write('上传 CPU 对齐依赖和校验模型，远程离线安装')
    uploaded = '/tmp/shiyue-' + archive.name
    remote.scp(archive, uploaded)
    script = f'''set -euo pipefail
archive={shlex.quote(uploaded)}
actual=$(sha256sum "$archive" | cut -d' ' -f1)
[ "$actual" = {shlex.quote(digest)} ] || {{ echo '对齐安装包校验失败' >&2; exit 8; }}
artifacts={shlex.quote(root + '/shared/aligner-artifacts/' + digest)}
mkdir -p "$artifacts" {shlex.quote(root + '/shared/.local')}
tar -xf "$archive" -C "$artifacts"
{run('--offline-dir /artifacts', True)}
rm -f "$archive"
'''
    output = remote.ssh(script)
    if READY not in output:
        raise ValueError('原音对齐环境未通过真实推理检查，停止部署')
