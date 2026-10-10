#!/usr/bin/env python3
"""Restore a custom dump into a disposable *_test PostgreSQL database."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


def main() -> int:
    parser=argparse.ArgumentParser(description="Restore drill for a Shiyue SaaS backup")
    parser.add_argument("backup",type=Path)
    parser.add_argument("--database-url",required=True)
    args=parser.parse_args();database=args.database_url;name=urlsplit(database).path.rsplit("/",1)[-1]
    if not name.endswith("_test"):parser.error("恢复演练目标数据库必须以 _test 结尾。")
    restore=shutil.which("pg_restore") or "/usr/local/opt/postgresql@16/bin/pg_restore"
    if not Path(restore).is_file():parser.error("找不到 pg_restore。")
    backup=args.backup.resolve();meta=json.loads((backup/"backup.json").read_text(encoding="utf-8"));dump=backup/meta["databaseDump"]
    subprocess.run([restore,"--clean","--if-exists","--no-owner","--dbname",database,str(dump)],check=True)
    try:
        import psycopg
    except ImportError as exc:raise SystemExit("恢复演练需要 psycopg。") from exc
    with psycopg.connect(database) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM schema_migrations");migrations=cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM media_assets");assets=cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users");users=cursor.fetchone()[0]
    print(json.dumps({"restored":True,"database":name,"migrations":migrations,"users":users,"mediaAssets":assets},ensure_ascii=False))
    return 0

if __name__=="__main__":raise SystemExit(main())
