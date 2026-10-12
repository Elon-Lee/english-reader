#!/usr/bin/env python3
"""Generate and register the missing low-bandwidth SaaS video variant."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import uuid
from pathlib import Path

from saas_auth import SaaSService, new_id
from saas_media import MediaService
from saas_membership import MembershipService, as_json


def parser() -> argparse.ArgumentParser:
    value=argparse.ArgumentParser()
    value.add_argument("--asset-id",action="append",default=[])
    value.add_argument("--all",action="store_true",help="Process every active private video missing the low variant.")
    value.add_argument("--repair-audio",action="store_true",help="Replace existing silent low variants from their original source video.")
    return value


def has_audio(path:Path)->bool:
    result=subprocess.run(["ffprobe","-v","error","-select_streams","a","-show_entries","stream=index","-of","csv=p=0",str(path)],capture_output=True,text=True,timeout=60)
    return result.returncode==0 and bool(result.stdout.strip())


def replace_registered_file(accounts:SaaSService,memberships:MembershipService,media:MediaService,target:Path,staged:Path)->int:
    relative=target.relative_to(media.media_root).as_posix();new_size=staged.stat().st_size;new_digest=media._digest(staged);backup=target.with_name(f".{target.name}.{uuid.uuid4().hex}.bak")
    os.replace(target,backup);os.replace(staged,target)
    try:
        with accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,owner_id,scope,original_bytes FROM media_assets WHERE storage_path=%s AND status='active' FOR UPDATE",(relative,));primary=accounts._many(cursor)
                cursor.execute("""SELECT av.id,av.asset_id,av.byte_size,ma.owner_id,ma.scope FROM asset_variants av
                    JOIN media_assets ma ON ma.id=av.asset_id WHERE av.storage_path=%s AND av.deleted_at IS NULL AND ma.status='active' FOR UPDATE""",(relative,));variants=accounts._many(cursor)
                deltas={};asset_owners={}
                for row in primary:deltas[row["id"]]=deltas.get(row["id"],0)+new_size-int(row["original_bytes"]);asset_owners[row["id"]]=row["owner_id"]
                for row in variants:deltas[row["asset_id"]]=deltas.get(row["asset_id"],0)+new_size-int(row["byte_size"]);asset_owners[row["asset_id"]]=row["owner_id"]
                owners={}
                for asset_id,delta in deltas.items():owners[asset_owners[asset_id]]=owners.get(asset_owners[asset_id],0)+max(0,delta)
                for owner_id,delta in owners.items():
                    if delta<=0:continue
                    context=memberships._context(cursor,owner_id);limit=int(as_json(context["period"]["limits_json"]).get("storage_bytes",0));used=media._private_bytes(cursor,owner_id)
                    if used+delta>limit:raise RuntimeError(f"storage quota exceeded for {owner_id}: {used}+{delta}>{limit}")
                cursor.execute("UPDATE media_assets SET original_bytes=%s,sha256=%s WHERE storage_path=%s AND status='active'",(new_size,new_digest,relative))
                cursor.execute("UPDATE asset_variants SET byte_size=%s,sha256=%s,content_type='video/mp4' WHERE storage_path=%s AND deleted_at IS NULL",(new_size,new_digest,relative))
                for asset_id,delta in deltas.items():
                    if not delta:continue
                    variant_delta=sum(new_size-int(row["byte_size"]) for row in variants if row["asset_id"]==asset_id)
                    if variant_delta:cursor.execute("UPDATE media_assets SET generated_bytes=generated_bytes+%s WHERE id=%s",(variant_delta,asset_id))
                    cursor.execute("UPDATE asset_usage SET charged_bytes=charged_bytes+%s WHERE asset_id=%s",(delta,asset_id))
                    cursor.execute("SELECT owner_id FROM media_assets WHERE id=%s",(asset_id,));owner_id=(accounts._one(cursor)or{})["owner_id"];context=memberships._context(cursor,owner_id)
                    cursor.execute("""INSERT INTO usage_ledger(id,user_id,usage_period_id,feature,quantity,reason,idempotency_key,metadata_json)
                        VALUES(%s,%s,%s,'storage_bytes',%s,'adjustment',%s,%s::jsonb) ON CONFLICT DO NOTHING""",(new_id(),owner_id,context["period"]["id"],delta,f"asset:{asset_id}:low-audio:{new_digest}",json.dumps({"assetId":asset_id,"bytes":delta,"repair":"low_video_audio"})))
                    cursor.execute("INSERT INTO security_events(id,user_id,event_type,metadata_json) VALUES(%s,%s,'media_variant_repaired',%s::jsonb)",(new_id(),owner_id,json.dumps({"assetId":asset_id,"variant":"low","bytes":new_size})))
    except Exception:
        if target.exists():os.replace(target,staged)
        os.replace(backup,target)
        raise
    backup.unlink(missing_ok=True)
    return new_size


def main() -> int:
    args=parser().parse_args()
    if not args.all and not args.asset_id:raise SystemExit("use --asset-id ID or --all")
    accounts=SaaSService(os.environ.get("DATABASE_URL"),dict(os.environ));memberships=MembershipService(accounts);media=MediaService(accounts,memberships)
    values=[];where=""
    if args.asset_id:
        where="AND ma.id=ANY(%s)";values.append(args.asset_id)
    with accounts.transaction() as connection:
        with connection.cursor() as cursor:
            if args.repair_audio:
                cursor.execute(f"""SELECT ma.id,ma.owner_id,ma.storage_path,av.storage_path AS low_storage_path FROM media_assets ma
                JOIN asset_variants av ON av.asset_id=ma.id AND av.deleted_at IS NULL AND av.variant_name='low' AND av.content_type LIKE 'video/%%'
                WHERE ma.scope='private' AND ma.status='active' AND ma.content_type LIKE 'video/%%' AND ma.kind<>'generated' {where}
                ORDER BY ma.created_at""",tuple(values))
            else:
                cursor.execute(f"""SELECT ma.id,ma.owner_id,ma.storage_path,NULL::text AS low_storage_path FROM media_assets ma
                WHERE ma.scope='private' AND ma.status='active' AND ma.content_type LIKE 'video/%%' {where}
                AND NOT EXISTS (SELECT 1 FROM asset_variants av WHERE av.asset_id=ma.id AND av.deleted_at IS NULL
                AND av.variant_name='low' AND av.content_type LIKE 'video/%%') ORDER BY ma.created_at""",tuple(values))
            rows=accounts._many(cursor)
    ffmpeg=Path(os.environ.get("SHIYUE_FFMPEG","ffmpeg")).expanduser();completed=[];failed=[]
    for row in rows:
        try:
            _,source=media._safe_path(row["storage_path"])
            if args.repair_audio:
                _,target=media._safe_path(row["low_storage_path"])
                if not has_audio(source):completed.append({"assetId":row["id"],"status":"source_has_no_audio"});continue
                if has_audio(target):completed.append({"assetId":row["id"],"status":"already_has_audio"});continue
                staged=target.with_name(f".{target.stem}.{uuid.uuid4().hex}.repair.mp4")
            else:target=source.parent/f"video-low-{str(row['id'])[:10]}.mp4";staged=target
            subprocess.run([str(ffmpeg),"-y","-v","error","-i",str(source),"-map","0:v:0","-map","0:a:0?","-vf","scale=640:360:force_original_aspect_ratio=decrease:force_divisible_by=2","-c:v","libx264","-preset","veryfast","-crf","27","-maxrate","380k","-bufsize","760k","-g","50","-keyint_min","50","-pix_fmt","yuv420p","-threads","2","-c:a","aac","-b:a","96k","-ac","2","-movflags","+faststart",str(staged)],check=True,timeout=3600)
            if args.repair_audio:completed.append({"assetId":row["id"],"bytes":replace_registered_file(accounts,memberships,media,target,staged),"status":"repaired"})
            else:
                relative=target.relative_to(media.media_root).as_posix();result=media.add_variants(str(row["owner_id"]),str(row["id"]),[{"name":"low","storagePath":relative,"contentType":"video/mp4"}]);completed.append({"assetId":row["id"],"bytes":result["addedBytes"],"status":"created"})
        except Exception as exc:failed.append({"assetId":row["id"],"error":str(exc)[:240]})
    print({"selected":len(rows),"completed":completed,"failed":failed})
    return 1 if failed else 0


if __name__=="__main__":raise SystemExit(main())
