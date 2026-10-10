#!/usr/bin/env python3
"""Create and fully verify the configured external SaaS backup."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from saas_auth import ROOT


def main()->int:
    database_url=str(os.environ.get("DATABASE_URL","")).strip();media_root=Path(os.environ.get("MEDIA_ROOT",str(ROOT/"books"))).expanduser().resolve();output_root=Path(os.environ.get("SAAS_BACKUP_ROOT","")).expanduser()
    if not database_url:raise SystemExit("DATABASE_URL is required")
    if not output_root.is_absolute():raise SystemExit("SAAS_BACKUP_ROOT must be an absolute path")
    backup=subprocess.run([sys.executable,str(ROOT/"tools/saas_backup.py"),"--database-url",database_url,"--media-root",str(media_root),"--output-root",str(output_root)],cwd=ROOT,text=True,capture_output=True,check=True)
    result=json.loads(backup.stdout.strip().splitlines()[-1]);verify=subprocess.run([sys.executable,str(ROOT/"tools/saas_backup_verify.py"),result["backup"],"--media-root",str(media_root)],cwd=ROOT,text=True,capture_output=True,check=True)
    print(json.dumps({"status":"ok","backup":result,"verification":json.loads(verify.stdout)},ensure_ascii=False,indent=2));return 0


if __name__=="__main__":raise SystemExit(main())
