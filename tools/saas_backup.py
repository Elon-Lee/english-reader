#!/usr/bin/env python3
"""Create a recoverable local PostgreSQL dump plus media manifest.

Designed for cron/launchd. It never deletes existing backups; retention can be
applied by an external reviewed job after restore drills are documented.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from saas_auth import ROOT


def digest(path: Path) -> str:
    value=hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda:source.read(1024*1024),b""):value.update(block)
    return value.hexdigest()


def main() -> int:
    parser=argparse.ArgumentParser(description="Create Shiyue SaaS database/media backup manifest")
    parser.add_argument("--database-url",default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--media-root",type=Path,default=Path(os.environ.get("MEDIA_ROOT",str(ROOT/"books"))))
    parser.add_argument("--output-root",type=Path,default=ROOT/".local"/"saas-backups")
    parser.add_argument("--include-media",action="store_true",help="Copy media files as well as producing a verified manifest")
    args=parser.parse_args()
    if not args.database_url:parser.error("需要 DATABASE_URL 或 --database-url")
    pg_dump=shutil.which("pg_dump") or str(Path("/usr/local/opt/postgresql@16/bin/pg_dump"))
    if not Path(pg_dump).is_file():parser.error("找不到 pg_dump；请安装 PostgreSQL 16。")
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");target=args.output_root/stamp;target.mkdir(parents=True,exist_ok=False)
    dump=target/"database.dump"
    subprocess.run([pg_dump,"--format=custom","--no-owner","--file",str(dump),args.database_url],check=True)
    media_root=args.media_root.expanduser().resolve();manifest=[]
    if media_root.is_dir():
        for path in sorted(media_root.rglob("*")):
            if not path.is_file():continue
            relative=str(path.relative_to(media_root));manifest.append({"path":relative,"bytes":path.stat().st_size,"sha256":digest(path)})
    (target/"media-manifest.json").write_text(json.dumps({"mediaRoot":str(media_root),"files":manifest},ensure_ascii=False,indent=2),encoding="utf-8")
    if args.include_media and media_root.is_dir():shutil.copytree(media_root,target/"media",dirs_exist_ok=False)
    meta={"createdAt":datetime.now(timezone.utc).isoformat(),"databaseDump":"database.dump","databaseSha256":digest(dump),"mediaFiles":len(manifest),"includeMedia":bool(args.include_media)}
    (target/"backup.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"backup":str(target),**meta},ensure_ascii=False))
    return 0


if __name__=="__main__":raise SystemExit(main())
