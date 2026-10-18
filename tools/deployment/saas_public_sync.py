#!/usr/bin/env python3
"""Export/apply catalog-backed public SaaS content without touching user state."""
from __future__ import annotations

import argparse,gzip,hashlib,json,os
from datetime import date,datetime
from decimal import Decimal
from pathlib import Path


TABLE_KEYS={
    "catalog_series":["id"],"catalog_tags":["id"],"content_books":["id"],"catalog_books":["id"],
    "catalog_book_tags":["catalog_book_id","tag_id"],"content_sentence_grammar":["book_id","sentence_id"],
    "media_assets":["id"],"asset_variants":["id"],
}
JSON_COLUMNS={"content_books":{"data_json","quality_json"},"catalog_books":{"preview_json"},"content_sentence_grammar":{"payload"}}

# Local review decisions are never publishing authority on the destination.
EXPORT_CATALOG_WHERE="publication_status IN ('draft','published') AND rights_status IN ('public_domain','licensed','private')"


def pending_catalog(items):
    return [{**item,"publication_status":"draft","reviewed_by":None,"published_at":None} for item in items]


def content_fingerprints(tables):
    """Track the uploaded revision independently of online moderation decisions."""
    fingerprints={}
    for book in tables["catalog_books"]:
        source_id=book.get("source_content_book_id")
        assets=[item for item in tables["media_assets"] if item.get("content_book_id")==source_id or item.get("catalog_book_id")==book["id"]]
        asset_ids={item["id"] for item in assets}
        tags=[item for item in tables["catalog_book_tags"] if item["catalog_book_id"]==book["id"]]
        tag_ids={item["tag_id"] for item in tags}
        data={"catalog":pending_catalog([book])[0],
              "source":[item for item in tables["content_books"] if item["id"]==source_id],
              "grammar":[item for item in tables["content_sentence_grammar"] if item["book_id"]==source_id],
              "assets":assets,"variants":[item for item in tables["asset_variants"] if item["asset_id"] in asset_ids],
              "tags":tags,"tagDefinitions":[item for item in tables["catalog_tags"] if item["id"] in tag_ids],
              "series":[item for item in tables["catalog_series"] if item["id"]==book.get("series_id")]}
        encoded=json.dumps(data,ensure_ascii=False,sort_keys=True,default=json_default,separators=(',',':')).encode()
        fingerprints[book["id"]]=hashlib.sha256(encoded).hexdigest()
    return fingerprints


def json_default(value):
    if isinstance(value,(datetime,date)):return value.isoformat()
    if isinstance(value,Decimal):return int(value) if value==value.to_integral_value() else str(value)
    raise TypeError(type(value).__name__)


def rows(cursor,query,params=()):
    cursor.execute(query,params);return [dict(item) for item in cursor.fetchall()]


def safe_media_path(root:Path,value:str)->Path:
    relative=Path(str(value or ""))
    if relative.is_absolute() or ".." in relative.parts:raise ValueError(f"非法媒体路径：{value}")
    target=(root/relative).resolve();target.relative_to(root.resolve());return target


def export_bundle(database_url:str,media_root:Path,bundle:Path,manifest:Path)->dict:
    import psycopg
    from psycopg.rows import dict_row
    media_root=media_root.expanduser().resolve()
    with psycopg.connect(database_url,row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            catalog_books=pending_catalog(rows(cursor,f"SELECT * FROM catalog_books WHERE {EXPORT_CATALOG_WHERE} ORDER BY id"))
            catalog_ids=[item["id"] for item in catalog_books];source_ids=[item["source_content_book_id"] for item in catalog_books if item.get("source_content_book_id")]
            if catalog_ids:
                series_ids=[item["series_id"] for item in catalog_books if item.get("series_id")]
                catalog_series=rows(cursor,"SELECT * FROM catalog_series WHERE id=ANY(%s) ORDER BY id",(series_ids,)) if series_ids else []
                catalog_book_tags=rows(cursor,"SELECT * FROM catalog_book_tags WHERE catalog_book_id=ANY(%s) ORDER BY catalog_book_id,tag_id",(catalog_ids,))
                tag_ids=[item["tag_id"] for item in catalog_book_tags]
                catalog_tags=rows(cursor,"SELECT * FROM catalog_tags WHERE id=ANY(%s) ORDER BY id",(tag_ids,)) if tag_ids else []
            else:catalog_series=[];catalog_book_tags=[];catalog_tags=[]
            content_books=rows(cursor,"SELECT * FROM content_books WHERE id=ANY(%s) ORDER BY id",(source_ids,)) if source_ids else []
            grammar=rows(cursor,"SELECT * FROM content_sentence_grammar WHERE book_id=ANY(%s) ORDER BY book_id,sentence_id",(source_ids,)) if source_ids else []
            if source_ids or catalog_ids:
                media_assets=rows(cursor,"SELECT * FROM media_assets WHERE content_book_id=ANY(%s) OR catalog_book_id=ANY(%s) ORDER BY id",(source_ids or [""],catalog_ids or [""]))
            else:media_assets=[]
            asset_ids=[item["id"] for item in media_assets]
            variants=rows(cursor,"SELECT * FROM asset_variants WHERE asset_id=ANY(%s) ORDER BY asset_id,variant_name",(asset_ids,)) if asset_ids else []
    files=[];seen=set()
    for item,size_key in [(item,"original_bytes") for item in media_assets if item.get("status")=="active"]+[(item,"byte_size") for item in variants if not item.get("deleted_at")]:
        value=item.get("storage_path","")
        if not value or value in seen:continue
        path=safe_media_path(media_root,value)
        if not path.is_file():raise ValueError(f"公共媒体文件不存在：{value}")
        seen.add(value);files.append({"path":value,"size":path.stat().st_size,"mtime":path.stat().st_mtime_ns,"expectedBytes":int(item.get(size_key,0)or 0)})
    payload={"format":1,"tables":{"catalog_series":catalog_series,"catalog_tags":catalog_tags,"content_books":content_books,"catalog_books":catalog_books,"catalog_book_tags":catalog_book_tags,"content_sentence_grammar":grammar,"media_assets":media_assets,"asset_variants":variants}}
    bundle.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(bundle,"wt",encoding="utf-8") as output:json.dump(payload,output,ensure_ascii=False,default=json_default)
    metadata={"format":1,"catalogIds":catalog_ids,"sourceBookIds":source_ids,"assetIds":asset_ids,"files":files,"contentFingerprints":content_fingerprints(payload["tables"])}
    manifest.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
    return {"catalogBooks":len(catalog_books),"sourceBooks":len(content_books),"grammarSentences":len(grammar),"assets":len(media_assets),"variants":len(variants),"files":len(files),"bytes":sum(item["size"] for item in files)}


def upsert_rows(cursor,table,items):
    if not items:return
    from psycopg import sql
    from psycopg.types.json import Jsonb
    keys=TABLE_KEYS[table];columns=list(items[0]);updates=[column for column in columns if column not in keys]
    conflict=(sql.SQL("DO UPDATE SET {}") .format(sql.SQL(",").join(sql.SQL("{}=EXCLUDED.{}").format(sql.Identifier(column),sql.Identifier(column)) for column in updates)) if updates else sql.SQL("DO NOTHING"))
    statement=sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) {}").format(
        sql.Identifier(table),sql.SQL(",").join(map(sql.Identifier,columns)),sql.SQL(",").join([sql.Placeholder() for _ in columns]),
        sql.SQL(",").join(map(sql.Identifier,keys)),conflict,
    )
    json_columns=JSON_COLUMNS.get(table,set())
    for item in items:
        values=[Jsonb(item[column]) if column in json_columns and isinstance(item[column],(dict,list)) else item[column] for column in columns]
        cursor.execute(statement,values)


def apply_bundle(database_url:str,bundle:Path,previous_manifest:Path|None=None)->dict:
    import psycopg
    payload=json.loads(gzip.open(bundle,"rt",encoding="utf-8").read());tables=payload["tables"]
    current={"catalogIds":[item["id"] for item in tables["catalog_books"]],"assetIds":[item["id"] for item in tables["media_assets"]]}
    previous={}
    if previous_manifest and previous_manifest.is_file():previous=json.loads(previous_manifest.read_text(encoding="utf-8"))
    fingerprints=content_fingerprints(tables)
    tables["catalog_books"]=pending_catalog(tables["catalog_books"])
    principal_ids=set()
    for item in tables["content_books"]:principal_ids.add(item["owner_id"])
    for item in tables["media_assets"]:principal_ids.add(item["owner_id"])
    for item in tables["catalog_books"]:
        principal_ids.update(value for value in (item.get("created_by"),item.get("reviewed_by")) if value)
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            if principal_ids:
                cursor.execute("SELECT id FROM users WHERE id=ANY(%s)",(list(principal_ids),));found={row[0] for row in cursor.fetchall()};missing=principal_ids-found
                if missing:
                    cursor.execute("SELECT u.id FROM users u JOIN user_roles ur ON ur.user_id=u.id JOIN roles r ON r.id=ur.role_id WHERE r.name='admin' AND u.status='active' ORDER BY u.created_at LIMIT 1")
                    row=cursor.fetchone()
                    if not row:raise ValueError("远程缺少可承接公共内容的管理员账号")
                    fallback=row[0]
                    for item in tables["content_books"]:
                        if item.get("owner_id") in missing:item["owner_id"]=fallback
                    for item in tables["media_assets"]:
                        if item.get("owner_id") in missing:item["owner_id"]=fallback
                    for item in tables["catalog_books"]:
                        for column in ("created_by","reviewed_by"):
                            if item.get(column) in missing:item[column]=fallback
            for table in ("catalog_series","catalog_tags"):
                upsert_rows(cursor,table,tables[table])
            # Unchanged retries preserve the destination's review and edits. New
            # uploads and changed revisions must be reviewed on the destination.
            from psycopg.rows import dict_row
            pending=0;changed_catalog=set();changed_sources=set()
            with connection.cursor(row_factory=dict_row) as review_cursor:
                for item in sorted(tables["catalog_books"],key=lambda row:row["id"]):
                    review_cursor.execute("SELECT * FROM catalog_books WHERE id=%s FOR UPDATE",(item["id"],))
                    existing=review_cursor.fetchone()
                    unchanged=previous.get("contentFingerprints",{}).get(item["id"])==fingerprints[item["id"]]
                    if existing and unchanged:
                        continue
                    pending+=1
                    changed_catalog.add(item["id"])
                    if item.get("source_content_book_id"):
                        changed_sources.add(item["source_content_book_id"])
                        upsert_rows(cursor,"content_books",[source for source in tables["content_books"] if source["id"]==item["source_content_book_id"]])
                    upsert_rows(cursor,"catalog_books",[item])
            catalog_ids=sorted(changed_catalog)
            if catalog_ids:cursor.execute("DELETE FROM catalog_book_tags WHERE catalog_book_id=ANY(%s)",(catalog_ids,))
            upsert_rows(cursor,"catalog_book_tags",[item for item in tables["catalog_book_tags"] if item["catalog_book_id"] in changed_catalog])
            source_ids=sorted(changed_sources)
            if source_ids:cursor.execute("DELETE FROM content_sentence_grammar WHERE book_id=ANY(%s)",(source_ids,))
            upsert_rows(cursor,"content_sentence_grammar",[item for item in tables["content_sentence_grammar"] if item["book_id"] in changed_sources])
            changed_assets=[item for item in tables["media_assets"] if item.get("content_book_id") in changed_sources or item.get("catalog_book_id") in changed_catalog]
            changed_asset_ids={item["id"] for item in changed_assets}
            upsert_rows(cursor,"media_assets",changed_assets);upsert_rows(cursor,"asset_variants",[item for item in tables["asset_variants"] if item["asset_id"] in changed_asset_ids])
            removed_catalog=sorted(set(previous.get("catalogIds",[]))-set(current["catalogIds"]))
            removed_assets=sorted(set(previous.get("assetIds",[]))-set(current["assetIds"]))
            if removed_catalog:cursor.execute("UPDATE catalog_books SET publication_status='archived',updated_at=NOW() WHERE id=ANY(%s)",(removed_catalog,))
            if removed_assets:cursor.execute("UPDATE media_assets SET status='deleted',deleted_at=COALESCE(deleted_at,NOW()) WHERE id=ANY(%s)",(removed_assets,))
        connection.commit()
    return {"catalogBooks":len(current["catalogIds"]),"pendingReviewBooks":pending,"sourceBooks":len(tables["content_books"]),"assets":len(current["assetIds"]),"removedCatalogBooks":len(removed_catalog),"removedAssets":len(removed_assets)}


def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest="command",required=True)
    export=sub.add_parser("export");export.add_argument("--database-url",default=os.environ.get("DATABASE_URL",""));export.add_argument("--media-root",type=Path,default=Path(os.environ.get("MEDIA_ROOT","books")));export.add_argument("--bundle",type=Path,required=True);export.add_argument("--manifest",type=Path,required=True)
    apply=sub.add_parser("apply");apply.add_argument("--database-url",default=os.environ.get("DATABASE_URL",""));apply.add_argument("--bundle",type=Path,required=True);apply.add_argument("--previous-manifest",type=Path)
    args=parser.parse_args()
    if not args.database_url:parser.error("DATABASE_URL is required")
    result=export_bundle(args.database_url,args.media_root,args.bundle,args.manifest) if args.command=="export" else apply_bundle(args.database_url,args.bundle,args.previous_manifest)
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":main()
