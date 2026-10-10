#!/usr/bin/env python3
"""Inventory and authorization layer for filesystem-backed SaaS media."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from saas_auth import SaaSError, SaaSService, new_id
from saas_membership import MembershipService, as_json, timestamp


class MediaService:
    def __init__(self, accounts: SaaSService, memberships: MembershipService, media_root: Path | None = None):
        root = media_root or Path(os.environ.get("MEDIA_ROOT", "") or accounts.environment.get("MEDIA_ROOT", "") or (accounts and Path(__file__).resolve().parents[1] / "books"))
        self.accounts, self.memberships, self.media_root = accounts, memberships, root.expanduser().resolve()

    def _safe_path(self, relative: Any) -> tuple[str, Path]:
        value = str(relative or "").strip().replace("\\", "/")
        if not value or value.startswith("/"):
            raise SaaSError("invalid_media_path", "媒体路径必须是 MEDIA_ROOT 下的相对路径。", 400)
        path = (self.media_root / value).resolve()
        try: path.relative_to(self.media_root)
        except ValueError as exc: raise SaaSError("invalid_media_path", "媒体路径越界。", 400) from exc
        return value, path

    @staticmethod
    def _digest(path: Path) -> str:
        hasher=hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda:source.read(1024*1024),b""):hasher.update(block)
        return hasher.hexdigest()

    def _file_record(self, relative: Any, content_type: str = "") -> dict[str, Any]:
        normalized,path=self._safe_path(relative)
        if not path.is_file():raise SaaSError("media_not_found","媒体文件不存在。",404)
        return {"storage_path":normalized,"byte_size":path.stat().st_size,"sha256":self._digest(path),"content_type":content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"}

    def _private_bytes(self, cursor: Any, user_id: str) -> int:
        cursor.execute("""SELECT COALESCE(SUM(original_bytes+generated_bytes),0) AS total FROM media_assets
        WHERE owner_id=%s AND scope='private' AND status='active'""",(user_id,))
        return int((self.accounts._one(cursor)or{"total":0})["total"])

    def ensure_private_capacity(self,user_id:str,bytes_to_add:int)->dict[str,int]:
        """Fast upload preflight; register() repeats the locked final check."""
        if bytes_to_add<0:raise SaaSError("invalid_media_size","媒体大小无效。",400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                context=self.memberships._context(cursor,user_id);limit=int(as_json(context["period"]["limits_json"]).get("storage_bytes",0));used=self._private_bytes(cursor,user_id)
                if used+bytes_to_add>limit:
                    raise SaaSError("quota_exceeded","私人学习空间不足。",409,{"feature":"storage_bytes","plan":context["plan"]["id"],"used":used,"limit":limit,"resetAt":timestamp(context["period"]["ends_at"]),"recommendedPlan":self.memberships._recommended_plan(context["plan"]["id"])})
                return {"used":used,"limit":limit,"available":max(0,limit-used)}

    def register(self, actor_id: str, owner_id: str, scope: str, storage_path: str, kind: str = "media", content_type: str = "", catalog_book_id: str | None = None, content_book_id: str | None = None, variants: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if scope not in {"official","private"}:raise SaaSError("invalid_media_scope","媒体范围无效。",400)
        primary=self._file_record(storage_path,content_type);variants=variants or []
        if not isinstance(variants,list):raise SaaSError("invalid_media_variant","媒体变体必须是数组。",400)
        parsed_variants=[]
        for value in variants:
            if not isinstance(value,dict):raise SaaSError("invalid_media_variant","媒体变体无效。",400)
            name=str(value.get("name","")).strip()
            if not name or len(name)>100:raise SaaSError("invalid_media_variant","媒体变体名称无效。",400)
            parsed={"variant_name":name,**self._file_record(value.get("storagePath"),str(value.get("contentType","")or""))}
            parsed_variants.append(parsed)
        total=primary["byte_size"]+sum(item["byte_size"] for item in parsed_variants)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE id=%s FOR UPDATE",(owner_id,))
                if not cursor.fetchone():raise SaaSError("user_not_found","媒体所有者不存在。",404)
                if scope=="official":
                    if not catalog_book_id:raise SaaSError("catalog_book_required","官方媒体必须关联官方读物。",400)
                    cursor.execute("SELECT id FROM catalog_books WHERE id=%s FOR UPDATE",(catalog_book_id,))
                    if not cursor.fetchone():raise SaaSError("catalog_book_not_found","官方读物不存在。",404)
                if scope=="private":
                    context=self.memberships._context(cursor,owner_id);limit=int(as_json(context["period"]["limits_json"]).get("storage_bytes",0));used=self._private_bytes(cursor,owner_id)
                    if used+total>limit:
                        raise SaaSError("quota_exceeded","私人学习空间不足。",409,{"feature":"storage_bytes","plan":context["plan"]["id"],"used":used,"limit":limit,"resetAt":timestamp(context["period"]["ends_at"]),"recommendedPlan":self.memberships._recommended_plan(context["plan"]["id"])})
                cursor.execute("SELECT id FROM media_assets WHERE storage_path=%s FOR UPDATE",(primary["storage_path"],))
                if self.accounts._one(cursor):raise SaaSError("media_path_exists","该媒体路径已经登记。",409)
                asset_id=new_id();generated=sum(item["byte_size"] for item in parsed_variants)
                cursor.execute("""INSERT INTO media_assets(id,owner_id,scope,kind,content_type,original_bytes,generated_bytes,sha256,storage_path,content_book_id,catalog_book_id)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(asset_id,owner_id,scope,str(kind or "media")[:100],primary["content_type"],primary["byte_size"],generated,primary["sha256"],primary["storage_path"],content_book_id or None,catalog_book_id or None))
                for variant in parsed_variants:
                    cursor.execute("INSERT INTO asset_variants(id,asset_id,variant_name,content_type,byte_size,sha256,storage_path) VALUES(%s,%s,%s,%s,%s,%s,%s)",(new_id(),asset_id,variant["variant_name"],variant["content_type"],variant["byte_size"],variant["sha256"],variant["storage_path"]))
                if scope=="private":
                    cursor.execute("INSERT INTO asset_usage(asset_id,user_id,charged_bytes) VALUES(%s,%s,%s)",(asset_id,owner_id,total))
                    cursor.execute("""INSERT INTO usage_ledger(id,user_id,usage_period_id,feature,quantity,reason,idempotency_key,metadata_json)
                    VALUES(%s,%s,%s,'storage_bytes',%s,'storage_settlement',%s,%s::jsonb)""",(new_id(),owner_id,context["period"]["id"],total,f"asset:{asset_id}:charge",json.dumps({"assetId":asset_id,"bytes":total})))
                cursor.execute("INSERT INTO security_events(id,user_id,event_type,metadata_json) VALUES(%s,%s,'media_registered',%s::jsonb)",(new_id(),owner_id,json.dumps({"assetId":asset_id,"scope":scope,"bytes":total,"actorId":actor_id})))
                return {"id":asset_id,"scope":scope,"ownerId":owner_id,"storagePath":primary["storage_path"],"originalBytes":primary["byte_size"],"generatedBytes":generated,"totalBytes":total,"variants":[{"name":item["variant_name"],"bytes":item["byte_size"]} for item in parsed_variants]}

    def add_variants(self, actor_id: str, asset_id: str, variants: list[dict[str, Any]]) -> dict[str, Any]:
        """Attach generated files to an existing private source asset.

        Import processors register the uploaded source immediately, then create
        derivatives outside a database transaction.  This method performs the
        final locked capacity check and makes variant attachment idempotent by
        accepting an already registered variant only when its path and digest
        still match.
        """
        if not isinstance(variants,list) or not variants:
            raise SaaSError("invalid_media_variant","媒体变体必须是非空数组。",400)
        parsed=[]
        names=set()
        for value in variants:
            if not isinstance(value,dict):raise SaaSError("invalid_media_variant","媒体变体无效。",400)
            name=str(value.get("name","")).strip()
            if not name or len(name)>100 or name in names:raise SaaSError("invalid_media_variant","媒体变体名称无效或重复。",400)
            names.add(name);parsed.append({"variant_name":name,**self._file_record(value.get("storagePath"),str(value.get("contentType","")or""))})
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM media_assets WHERE id=%s FOR UPDATE",(asset_id,));asset=self.accounts._one(cursor)
                if not asset:raise SaaSError("media_not_found","媒体不存在。",404)
                if asset["owner_id"]!=actor_id:raise SaaSError("media_access_denied","你无权修改该媒体。",403)
                if asset["scope"]!="private" or asset["status"]!="active":raise SaaSError("media_not_active","媒体当前不能添加变体。",409)
                cursor.execute("SELECT * FROM asset_variants WHERE asset_id=%s AND variant_name=ANY(%s)",(asset_id,list(names)))
                existing={row["variant_name"]:row for row in self.accounts._many(cursor)};pending=[]
                for item in parsed:
                    old=existing.get(item["variant_name"])
                    if old:
                        if old["deleted_at"] is not None or old["storage_path"]!=item["storage_path"] or old["sha256"]!=item["sha256"]:
                            raise SaaSError("media_variant_exists","同名媒体变体已经登记。",409)
                        continue
                    pending.append(item)
                added=sum(item["byte_size"] for item in pending)
                if added:
                    context=self.memberships._context(cursor,asset["owner_id"]);limit=int(as_json(context["period"]["limits_json"]).get("storage_bytes",0));used=self._private_bytes(cursor,asset["owner_id"])
                    if used+added>limit:
                        raise SaaSError("quota_exceeded","私人学习空间不足。",409,{"feature":"storage_bytes","plan":context["plan"]["id"],"used":used,"limit":limit,"resetAt":timestamp(context["period"]["ends_at"]),"recommendedPlan":self.memberships._recommended_plan(context["plan"]["id"])})
                    for item in pending:
                        cursor.execute("INSERT INTO asset_variants(id,asset_id,variant_name,content_type,byte_size,sha256,storage_path) VALUES(%s,%s,%s,%s,%s,%s,%s)",(new_id(),asset_id,item["variant_name"],item["content_type"],item["byte_size"],item["sha256"],item["storage_path"]))
                    cursor.execute("UPDATE media_assets SET generated_bytes=generated_bytes+%s WHERE id=%s",(added,asset_id))
                    cursor.execute("UPDATE asset_usage SET charged_bytes=charged_bytes+%s WHERE asset_id=%s AND user_id=%s",(added,asset_id,asset["owner_id"]))
                    cursor.execute("""INSERT INTO usage_ledger(id,user_id,usage_period_id,feature,quantity,reason,idempotency_key,metadata_json)
                    VALUES(%s,%s,%s,'storage_bytes',%s,'storage_settlement',%s,%s::jsonb)""",(new_id(),asset["owner_id"],context["period"]["id"],added,f"asset:{asset_id}:variants:"+",".join(sorted(item["variant_name"] for item in pending)),json.dumps({"assetId":asset_id,"bytes":added,"variants":[item["variant_name"] for item in pending]})))
                cursor.execute("SELECT generated_bytes FROM media_assets WHERE id=%s",(asset_id,));generated=int((self.accounts._one(cursor)or{"generated_bytes":0})["generated_bytes"])
                return {"id":asset_id,"addedBytes":added,"generatedBytes":generated,"variants":[{"name":item["variant_name"],"bytes":item["byte_size"]} for item in parsed]}

    def _accessible(self, cursor: Any, user_id: str, asset_id: str, variant_name: str | None = None) -> dict[str, Any]:
        cursor.execute("SELECT * FROM media_assets WHERE id=%s AND status='active' FOR UPDATE",(asset_id,));asset=self.accounts._one(cursor)
        if not asset:raise SaaSError("media_not_found","媒体不存在或已删除。",404)
        allowed=asset["owner_id"]==user_id
        if not allowed and asset["scope"]=="official" and asset.get("catalog_book_id"):
            cursor.execute("""SELECT EXISTS(SELECT 1 FROM catalog_books cb JOIN official_book_unlocks ou ON ou.catalog_book_id=cb.id AND ou.user_id=%s
            WHERE cb.id=%s AND cb.publication_status='published' AND cb.rights_status IN ('public_domain','licensed')) AS allowed""",(user_id,asset["catalog_book_id"]))
            allowed=bool((self.accounts._one(cursor)or{"allowed":False})["allowed"])
        if not allowed and asset.get("content_book_id"):
            cursor.execute("""SELECT EXISTS(SELECT 1 FROM catalog_books cb JOIN official_book_unlocks ou ON ou.catalog_book_id=cb.id AND ou.user_id=%s
            WHERE cb.source_content_book_id=%s AND cb.publication_status='published' AND cb.rights_status IN ('public_domain','licensed')) AS allowed""",(user_id,asset["content_book_id"]))
            allowed=bool((self.accounts._one(cursor)or{"allowed":False})["allowed"])
        if not allowed:raise SaaSError("media_access_denied","你无权访问该媒体。",403)
        target={"storage_path":asset["storage_path"],"content_type":asset["content_type"],"byte_size":int(asset["original_bytes"]),"variant_name":None}
        if variant_name:
            cursor.execute("SELECT * FROM asset_variants WHERE asset_id=%s AND variant_name=%s AND deleted_at IS NULL",(asset_id,variant_name));variant=self.accounts._one(cursor)
            if not variant:raise SaaSError("media_variant_not_found","媒体变体不存在。",404)
            target={"storage_path":variant["storage_path"],"content_type":variant["content_type"],"byte_size":int(variant["byte_size"]),"variant_name":variant_name}
        cursor.execute("""INSERT INTO asset_usage(asset_id,user_id,access_count,first_accessed_at,last_accessed_at,charged_bytes)
        VALUES(%s,%s,1,NOW(),NOW(),0) ON CONFLICT (asset_id,user_id) DO UPDATE SET access_count=asset_usage.access_count+1,last_accessed_at=NOW()""",(asset_id,user_id))
        return {"asset":asset,"target":target}

    def stream(self,user_id:str,asset_id:str,variant_name:str|None=None)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                result=self._accessible(cursor,user_id,asset_id,variant_name)
        _,path=self._safe_path(result["target"]["storage_path"])
        if not path.is_file():raise SaaSError("media_not_found","媒体文件不存在。",404)
        result["path"]=path;return result

    def list_assets(self,scope:str="",owner_id:str="",limit:int=100,offset:int=0)->dict[str,Any]:
        terms=[];values=[]
        if scope:terms.append("scope=%s");values.append(scope)
        if owner_id:terms.append("owner_id=%s");values.append(owner_id)
        where=("WHERE "+" AND ".join(terms)) if terms else ""
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) AS total FROM media_assets {where}",values);total=int((self.accounts._one(cursor)or{"total":0})["total"]);page_size=max(1,min(100,int(limit)));start=max(0,int(offset));cursor.execute(f"SELECT * FROM media_assets {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",(*values,page_size,start))
                return {"assets":[{"id":r["id"],"ownerId":r["owner_id"],"scope":r["scope"],"kind":r["kind"],"contentType":r["content_type"],"originalBytes":int(r["original_bytes"]),"generatedBytes":int(r["generated_bytes"]),"storagePath":r["storage_path"],"catalogBookId":r["catalog_book_id"],"status":r["status"],"createdAt":timestamp(r["created_at"])} for r in self.accounts._many(cursor)],"total":total,"limit":page_size,"offset":start}

    def delete(self,actor_id:str,asset_id:str,is_admin:bool=False)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM media_assets WHERE id=%s FOR UPDATE",(asset_id,));asset=self.accounts._one(cursor)
                if not asset:raise SaaSError("media_not_found","媒体不存在。",404)
                if asset["owner_id"]!=actor_id and not is_admin:raise SaaSError("media_access_denied","你无权删除该媒体。",403)
                if asset["status"]=="deleted":return {"id":asset_id,"status":"deleted","idempotent":True}
                total=int(asset["original_bytes"])+int(asset["generated_bytes"])
                cursor.execute("UPDATE media_assets SET status='deleted',deleted_at=NOW() WHERE id=%s",(asset_id,));cursor.execute("UPDATE asset_variants SET deleted_at=NOW() WHERE asset_id=%s AND deleted_at IS NULL",(asset_id,))
                if asset["scope"]=="private":
                    context=self.memberships._context(cursor,asset["owner_id"])
                    cursor.execute("""INSERT INTO usage_ledger(id,user_id,usage_period_id,feature,quantity,reason,idempotency_key,metadata_json)
                    VALUES(%s,%s,%s,'storage_bytes',%s,'storage_settlement',%s,%s::jsonb) ON CONFLICT DO NOTHING""",(new_id(),asset["owner_id"],context["period"]["id"],-total,f"asset:{asset_id}:release",json.dumps({"assetId":asset_id,"bytes":total})))
                cursor.execute("INSERT INTO security_events(id,user_id,event_type,metadata_json) VALUES(%s,%s,'media_deleted',%s::jsonb)",(new_id(),asset["owner_id"],json.dumps({"assetId":asset_id,"actorId":actor_id})))
                return {"id":asset_id,"status":"deleted","idempotent":False,"purgePending":True}

    def purge_deleted(self,trash_root:Path,dry_run:bool=True)->dict[str,Any]:
        trash_root=trash_root.resolve();trash_root.mkdir(parents=True,exist_ok=True);moved=[]
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,storage_path FROM media_assets WHERE status='deleted' ORDER BY deleted_at")
                assets=self.accounts._many(cursor)
                for asset in assets:
                    cursor.execute("SELECT storage_path FROM asset_variants WHERE asset_id=%s",(asset["id"],));paths=[asset["storage_path"]]+[row["storage_path"] for row in self.accounts._many(cursor)]
                    for relative in paths:
                        _,path=self._safe_path(relative)
                        if path.exists():
                            destination=trash_root/f"{asset['id']}-{path.name}"
                            moved.append({"assetId":asset["id"],"path":relative,"trashPath":str(destination)})
                            if not dry_run:destination.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(path),str(destination))
        return {"dryRun":dry_run,"files":moved}
