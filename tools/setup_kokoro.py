#!/usr/bin/env python3
"""Explicit administrator-only download and offline preflight for Kokoro."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen

MODEL_REVISION = 'f3ff3571791e39611d31c381e3a41a3af07b4987'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', type=Path, required=True)
    args = parser.parse_args()
    home = args.home.resolve()
    home.mkdir(parents=True, exist_ok=True)
    os.environ.update(HF_HOME=str(home / 'cache'), HF_HUB_DISABLE_XET='1')
    from huggingface_hub import snapshot_download
    revision = MODEL_REVISION
    voices = ['af_heart', 'am_michael', 'bf_emma', 'bm_george']
    snapshot_download('hexgrad/Kokoro-82M', revision=revision, local_dir=str(home / 'model'),
                      allow_patterns=['config.json', 'kokoro-v1_0.pth', 'README.md', 'VOICES.md']
                      + [f'voices/{voice}.pt' for voice in voices])
    if 'license: apache-2.0' not in (home / 'model/README.md').read_text():
        raise RuntimeError('Model license must be reviewed before installation')
    with urlopen('https://www.apache.org/licenses/LICENSE-2.0.txt', timeout=30) as response:
        (home / 'model/LICENSE').write_bytes(response.read())
    probe = home / 'preflight-input.json'
    probe.write_text(json.dumps({'voice': 'af_heart', 'speed': 1,
                                'sentences': [{'id': 's-1', 'text': 'A quiet morning is a good time to read a book.',
                                               'words': [{'text': word} for word in 'A quiet morning is a good time to read a book'.split()]}]}))
    environment = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'}
    subprocess.run([sys.executable, str(Path(__file__).with_name('kokoro_worker.py')),
                    '--home', str(home), '--input', str(probe), '--output', str(home / 'preflight-timing.json'),
                    '--audio', str(home / 'preflight.wav'), '--max-bytes', str(10 * 1024**2)],
                   env=environment, check=True)
    checkpoint = home / 'model/kokoro-v1_0.pth'
    manifest = {'version': 1, 'model': 'hexgrad/Kokoro-82M', 'revision': revision, 'voices': voices,
                'sha256': hashlib.sha256(checkpoint.read_bytes()).hexdigest(), 'offlinePreflight': True}
    temporary = home / 'ready.tmp'
    temporary.write_text(json.dumps(manifest, indent=2) + '\n')
    temporary.replace(home / 'ready.json')
    print('Kokoro offline preflight passed; runtime ready.')


if __name__ == '__main__':
    main()
