#!/usr/bin/env python3
"""Verify a database dump checksum and a media manifest against MEDIA_ROOT."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    hasher=hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda:source.read(1024*1024),b""):hasher.update(block)
    return hasher.hexdigest()


def main() -> int:
    parser=argparse.ArgumentParser(description="Verify a Shiyue SaaS backup")
    parser.add_argument("backup",type=Path)
    parser.add_argument("--media-root",type=Path,required=True)
    parser.add_argument("--max-files",type=int,default=0,help="Optional bounded verification for a quick drill")
    args=parser.parse_args();backup=args.backup.resolve();root=args.media_root.resolve()
    meta=json.loads((backup/"backup.json").read_text(encoding="utf-8"));dump=backup/meta["databaseDump"]
    if digest(dump)!=meta["databaseSha256"]:raise SystemExit("数据库备份校验失败")
    manifest=json.loads((backup/"media-manifest.json").read_text(encoding="utf-8"));checked=0
    for item in manifest.get("files",[]):
        path=(root/item["path"]).resolve()
        try:path.relative_to(root)
        except ValueError:raise SystemExit("媒体清单路径越界")
        if not path.is_file() or path.stat().st_size!=int(item["bytes"]) or digest(path)!=item["sha256"]:raise SystemExit(f"媒体校验失败：{item['path']}")
        checked+=1
        if args.max_files and checked>=args.max_files:break
    print(json.dumps({"verifiedDatabase":True,"verifiedMediaFiles":checked,"manifestMediaFiles":len(manifest.get("files",[]))},ensure_ascii=False))
    return 0

if __name__=="__main__":raise SystemExit(main())
