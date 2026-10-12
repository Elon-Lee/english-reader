#!/usr/bin/env python3
"""Generate and register the missing low-bandwidth SaaS video variant."""
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from saas_auth import SaaSService
from saas_media import MediaService
from saas_membership import MembershipService


def parser() -> argparse.ArgumentParser:
    value=argparse.ArgumentParser()
    value.add_argument("--asset-id",action="append",default=[])
    value.add_argument("--all",action="store_true",help="Process every active private video missing the low variant.")
    return value


def main() -> int:
    args=parser().parse_args()
    if not args.all and not args.asset_id:raise SystemExit("use --asset-id ID or --all")
    accounts=SaaSService(os.environ.get("DATABASE_URL"),dict(os.environ));memberships=MembershipService(accounts);media=MediaService(accounts,memberships)
    values=[];where=""
    if args.asset_id:
        where="AND ma.id=ANY(%s)";values.append(args.asset_id)
    with accounts.transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"""SELECT ma.id,ma.owner_id,ma.storage_path FROM media_assets ma
            WHERE ma.scope='private' AND ma.status='active' AND ma.content_type LIKE 'video/%%' {where}
            AND NOT EXISTS (SELECT 1 FROM asset_variants av WHERE av.asset_id=ma.id AND av.deleted_at IS NULL
            AND av.variant_name='low' AND av.content_type LIKE 'video/%%') ORDER BY ma.created_at""",tuple(values));rows=accounts._many(cursor)
    ffmpeg=Path(os.environ.get("SHIYUE_FFMPEG","ffmpeg")).expanduser();completed=[];failed=[]
    for row in rows:
        try:
            _,source=media._safe_path(row["storage_path"]);target=source.parent/f"video-low-{str(row['id'])[:10]}.mp4"
            if not target.is_file() or target.stat().st_mtime_ns<source.stat().st_mtime_ns:
                subprocess.run([str(ffmpeg),"-y","-v","error","-i",str(source),"-map","0:v:0","-an","-vf","scale=640:360:force_original_aspect_ratio=decrease:force_divisible_by=2","-c:v","libx264","-preset","veryfast","-crf","27","-maxrate","380k","-bufsize","760k","-g","50","-keyint_min","50","-pix_fmt","yuv420p","-threads","2","-movflags","+faststart",str(target)],check=True,timeout=3600)
            relative=target.relative_to(media.media_root).as_posix();result=media.add_variants(str(row["owner_id"]),str(row["id"]),[{"name":"low","storagePath":relative,"contentType":"video/mp4"}]);completed.append({"assetId":row["id"],"bytes":result["addedBytes"]})
        except Exception as exc:failed.append({"assetId":row["id"],"error":str(exc)[:240]})
    print({"selected":len(rows),"completed":completed,"failed":failed})
    return 1 if failed else 0


if __name__=="__main__":raise SystemExit(main())
