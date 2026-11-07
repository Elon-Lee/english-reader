#!/usr/bin/env python3
"""Install and verify the persistent original-audio aligner, online or offline."""
import argparse
import fcntl
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.request import urlopen

MODEL_FILE = 'wav2vec2_fairseq_base_ls960_asr_ls960.pth'
MODEL_SHA256 = '488fd4f16de84438ffc945334278c1b9fb9b7159a806c1080b16111a958c945d'
MODEL_URL = 'https://download.pytorch.org/torchaudio/models/' + MODEL_FILE
CPU_INDEX = 'https://download.pytorch.org/whl/cpu'
READY = 'SHIYUE_ALIGNER_READY'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def requirements(arch, system='Linux'):
    suffix = '+cpu' if system == 'Linux' and arch == 'x86_64' else ''
    return ['numpy==1.26.4', 'torch==2.2.2' + suffix, 'torchaudio==2.2.2' + suffix]


def download_model(destination):
    """Never publish an incomplete/unverified checkpoint."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and sha256(destination) == MODEL_SHA256:
        return
    for attempt in range(3):
        temporary = destination.with_name(destination.name + '.' + uuid.uuid4().hex + '.part')
        try:
            with urlopen(MODEL_URL, timeout=60) as source, temporary.open('wb') as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
            if sha256(temporary) != MODEL_SHA256:
                raise ValueError('Acoustic model checksum mismatch')
            temporary.replace(destination)
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)
        finally:
            temporary.unlink(missing_ok=True)


PROBE = r'''
import io, subprocess, wave
import numpy as np
import torch
import torchaudio
assert np.__version__ == '1.26.4', 'Unexpected numpy version'
assert torch.__version__.split('+')[0] == '2.2.2', 'Unexpected torch version'
assert torchaudio.__version__.split('+')[0] == '2.2.2', 'Unexpected torchaudio version'
assert torch.version.cuda is None, 'CPU runtime required'
torch.set_num_threads(2)
torch.set_num_interop_threads(1)
pcm = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi',
    '-i', 'sine=frequency=440:duration=1', '-ar', '16000', '-ac', '1', '-f', 'wav', '-'])
with wave.open(io.BytesIO(pcm)) as audio:
    assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (16000, 1, 2)
    samples = np.frombuffer(audio.readframes(16000), dtype=np.int16).copy()
waveform = torch.from_numpy(samples).float().unsqueeze(0) / 32768
bundle = torchaudio.pipelines.WAV2VEC2_ASR_BASE_960H
model = bundle.get_model().eval()
with torch.inference_mode():
    emissions, _ = model(waveform)
    assert emissions.shape[0] == 1 and emissions.shape[2] == len(bundle.get_labels())
    assert torch.isfinite(emissions).all()
    probs = torch.log_softmax(torch.tensor([[[0., 5., 0.], [5., 0., 0.], [0., 0., 5.]]]), -1)
    path, scores = torchaudio.functional.forced_align(probs, torch.tensor([[1, 2]], dtype=torch.int32))
    assert len(torchaudio.functional.merge_tokens(path[0], scores[0])) == 2
print('SHIYUE_ALIGNER_READY')
'''


def check(base, python=None, model_home=None):
    python = Path(python or base / 'venv/bin/python')
    model_home = Path(model_home or base / 'models')
    checkpoint = model_home / 'hub/checkpoints' / MODEL_FILE
    if not python.is_file() or not checkpoint.is_file() or sha256(checkpoint) != MODEL_SHA256:
        raise ValueError('Original-audio aligner environment/model missing or checksum invalid')
    result = subprocess.run([str(python), '-c', PROBE], check=True, text=True,
                            capture_output=True, timeout=180,
                            env={**os.environ, 'TORCH_HOME': str(model_home), 'OMP_NUM_THREADS': '2'})
    if READY not in result.stdout:
        raise ValueError('Original-audio aligner inference failed')
    print(result.stdout.strip(), flush=True)


def validate_bundle(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('modelSha256') != MODEL_SHA256:
        raise ValueError('Unexpected offline acoustic model')
    files = manifest.get('files', {})
    if MODEL_FILE not in files or not any(name.endswith('.whl') for name in files):
        raise ValueError('Incomplete offline aligner bundle')
    for name, digest in files.items():
        if Path(name).name != name or sha256(directory / name) != digest:
            raise ValueError('Offline aligner artifact checksum mismatch: ' + name)
    if files[MODEL_FILE] != MODEL_SHA256:
        raise ValueError('Offline acoustic model checksum mismatch')


def install(root, offline=None):
    if sys.version_info[:2] != (3, 11):
        raise ValueError('Python 3.11 is required for the original-audio aligner')
    base = root / '.local/forced-aligner'
    base.mkdir(parents=True, exist_ok=True)
    with (base / 'install.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            check(base)
            return
        except (ValueError, OSError, subprocess.SubprocessError):
            print('Preparing original-audio aligner CPU environment', flush=True)
        if offline:
            validate_bundle(offline)
        checkpoint = base / 'models/hub/checkpoints' / MODEL_FILE
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        if not checkpoint.is_file() or sha256(checkpoint) != MODEL_SHA256:
            if offline:
                temporary = checkpoint.with_suffix('.' + uuid.uuid4().hex + '.part')
                try:
                    shutil.copyfile(offline / MODEL_FILE, temporary)
                    if sha256(temporary) != MODEL_SHA256:
                        raise ValueError('Copied acoustic model checksum mismatch')
                    temporary.replace(checkpoint)
                finally:
                    temporary.unlink(missing_ok=True)
            else:
                download_model(checkpoint)
        stage = Path(tempfile.mkdtemp(prefix='runtime-', dir=base))
        try:
            subprocess.run([sys.executable, '-m', 'venv', str(stage)], check=True)
            command = [str(stage / 'bin/python'), '-m', 'pip', 'install', '--disable-pip-version-check']
            if offline:
                command += ['--no-index', '--find-links', str(offline)]
            elif platform.system() == 'Linux' and platform.machine() == 'x86_64':
                command += ['--extra-index-url', CPU_INDEX]
            subprocess.run(command + requirements(platform.machine(), platform.system()), check=True, timeout=1800)
            check(base, stage / 'bin/python')
            link = base / ('venv-' + uuid.uuid4().hex)
            link.symlink_to(stage.name, target_is_directory=True)
            current = base / 'venv'
            if current.is_dir() and not current.is_symlink():
                current.rename(base / ('previous-' + uuid.uuid4().hex))
            link.replace(current)
        except Exception:
            shutil.rmtree(stage)
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--offline-dir', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        check(args.root / '.local/forced-aligner', os.environ.get('SHIYUE_CTC_PYTHON'),
              os.environ.get('SHIYUE_CTC_MODEL_HOME'))
    else:
        install(args.root, args.offline_dir)


if __name__ == '__main__':
    main()
