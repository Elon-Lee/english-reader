#!/usr/bin/env python3
"""Register an existing MEDIA_ROOT tree as private SaaS media assets.

The script is deliberately additive: it never moves, removes, or regenerates
media. It can be re-run safely; existing storage paths are skipped.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from saas_auth import SaaSConfigurationError, SaaSService
from saas_media import MediaService
from saas_membership import MembershipService


def main() -> int:
    parser=argparse.ArgumentParser(description="Inventory an existing Shiyue MEDIA_ROOT into PostgreSQL media_assets")
    parser.add_argument("--owner-email",required=True,help="Existing administrator email that owns migrated private media")
    parser.add_argument("--media-root",type=Path,default=Path(os.environ.get("MEDIA_ROOT","books")))
    parser.add_argument("--limit",type=int,default=0,help="Optional max files for a dry operational batch")
    parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args();root=args.media_root.expanduser().resolve()
    if not root.is_dir():parser.error(f"媒体目录不存在：{root}")
    service=SaaSService(os.environ.get("DATABASE_URL",""));service.assert_configured();media=MediaService(service,MembershipService(service),root)
    with service.transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE email=%s",(args.owner_email.strip().casefold(),));owner=service._one(cursor)
            if not owner:raise SaaSConfigurationError("找不到媒体所有者账号。")
            owner_id=owner["id"]
            cursor.execute("SELECT id,source_path FROM content_books WHERE owner_id=%s",(owner_id,));sources=service._many(cursor)
            cursor.execute("SELECT storage_path FROM media_assets");registered={row["storage_path"] for row in service._many(cursor)}
    prefixes=sorted(((str(row["source_path"]).strip("/"),row["id"]) for row in sources),key=lambda item:len(item[0]),reverse=True)
    scanned=added=skipped=failed=0
    for path in sorted(root.rglob("*")):
        if not path.is_file():continue
        relative=str(path.relative_to(root));scanned+=1
        if relative in registered:skipped+=1;continue
        content_book_id=next((book_id for prefix,book_id in prefixes if prefix and (relative==prefix or relative.startswith(prefix+"/"))),None)
        if args.dry_run:
            added+=1
        else:
            try:
                kind="generated" if "/.reader/" in f"/{relative}" or relative.startswith(".reader/") else "source"
                media.register(owner_id,owner_id,"private",relative,kind,content_book_id=content_book_id)
                added+=1
            except Exception as exc:
                failed+=1;print(f"FAILED\t{relative}\t{exc}")
        if args.limit and scanned>=args.limit:break
        if scanned%100==0:print(f"progress scanned={scanned} added={added} skipped={skipped} failed={failed}",flush=True)
    print(f"inventory scanned={scanned} added={added} skipped={skipped} failed={failed} dryRun={args.dry_run}")
    return 1 if failed else 0


if __name__=="__main__":raise SystemExit(main())
