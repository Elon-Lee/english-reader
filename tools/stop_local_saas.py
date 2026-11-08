#!/usr/bin/env python3
"""Compatibility entry: stop only services owned by the independent local stack."""
import os
from pathlib import Path
import sys

if __name__ == '__main__':
    os.execv(sys.executable, [sys.executable, str(Path(__file__).with_name('run_local_dev.py')), 'stop'])
