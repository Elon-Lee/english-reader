#!/usr/bin/env python3
"""Reviewed official catalog and per-user official library service."""
from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime
from typing import Any

from saas_auth import SaaSError, SaaSService, new_id
from saas_membership import MembershipService, as_json, timestamp


RIGHTS = {"public_domain", "licensed", "private", "prohibited"}
PUBLICATION = {"draft", "published", "archived"}
SHELF_STATES = {"active", "later"}


def slugify(value: Any) -> str:
    raw=str(value or "").strip()
    text = re.sub(r"[^a-z0-9]+", "-", raw.casefold()).strip("-")
    return text[:80] or f"item-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"


class CatalogService:
    def __init__(self, accounts: SaaSService, memberships: MembershipService):
        self.accounts, self.memberships = accounts, memberships

    def _tags(self, cursor: Any, book_ids: list[str]) -> dict[str, list[dict[str, str]]]:
        if not book_ids: return {}
        cursor.execute(
            """SELECT cbt.catalog_book_id,ct.id,ct.slug,ct.title FROM catalog_book_tags cbt
            JOIN catalog_tags ct ON ct.id=cbt.tag_id WHERE cbt.catalog_book_id=ANY(%s) ORDER BY ct.title""",
            (book_ids,),
        )
        output: dict[str, list[dict[str, str]]] = {}
        for row in self.accounts._many(cursor):
            output.setdefault(row["catalog_book_id"], []).append({"id": row["id"], "slug": row["slug"], "title": row["title"]})
        return output

    def _state(self, cursor: Any, user_id: str | None, book_ids: list[str]) -> dict[str, dict[str, bool]]:
        if not user_id or not book_ids: return {}
        cursor.execute(
            """SELECT cb.id,
            EXISTS(SELECT 1 FROM user_library ul WHERE ul.user_id=%s AND ul.catalog_book_id=cb.id) AS in_library
            FROM catalog_books cb WHERE cb.id=ANY(%s)""",
            (user_id, book_ids),
        )
        return {row["id"]: {"inLibrary": bool(row["in_library"])} for row in self.accounts._many(cursor)}

    def _book(self, row: dict[str, Any], tags: list[dict[str, str]], state: dict[str, bool] | None = None, detail: bool = False) -> dict[str, Any]:
        result = {
            "id": row["id"], "title": row["title"], "englishTitle": row["english_title"], "author": row["author"],
            "series": {"id": row.get("series_id"), "slug": row.get("series_slug", ""), "title": row.get("series_title", "")},
            "level": row["level"], "resourceType": row["resource_type"], "estimatedMinutes": int(row["estimated_minutes"]),
            "sentenceCount": int(row["sentence_count"]), "wordCount": int(row["word_count"]), "coverUrl": row["cover_url"],
            "tags": tags, "featuredRank": int(row["featured_rank"]), "publishedAt": timestamp(row.get("published_at")),
            "inLibrary": bool((state or {}).get("inLibrary")), "unlocked": bool((state or {}).get("inLibrary")),
        }
        if detail:
            result.update({"description": row["description"], "preview": row["preview_json"] if isinstance(row["preview_json"], list) else json.loads(row["preview_json"] or "[]"),
                           "readerReady": result["inLibrary"], "readerNotice": "加入书架后即可阅读，音视频收藏数量受当前套餐限制。"})
        return result

    def catalog(self, user_id: str | None = None, query: str = "", series: str = "", level: str = "", resource_type: str = "", tag: str = "", limit: int = 60) -> dict[str, Any]:
        terms, values = ["cb.publication_status='published'", "cb.rights_status IN ('public_domain','licensed')"], []
        if query.strip():
            terms.append("(cb.title ILIKE %s OR cb.english_title ILIKE %s OR cb.author ILIKE %s OR cs.title ILIKE %s)"); values += [f"%{query.strip()}%"] * 4
        if series.strip(): terms.append("cs.slug=%s"); values.append(series.strip())
        if level.strip(): terms.append("cb.level=%s"); values.append(level.strip())
        if resource_type.strip(): terms.append("cb.resource_type=%s"); values.append(resource_type.strip())
        if tag.strip(): terms.append("EXISTS(SELECT 1 FROM catalog_book_tags fcbt JOIN catalog_tags fct ON fct.id=fcbt.tag_id WHERE fcbt.catalog_book_id=cb.id AND fct.slug=%s)"); values.append(tag.strip())
        limit = max(1, min(100, int(limit or 60)))
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"""SELECT cb.*,cs.slug AS series_slug,cs.title AS series_title FROM catalog_books cb
                LEFT JOIN catalog_series cs ON cs.id=cb.series_id WHERE {' AND '.join(terms)}
                ORDER BY cb.featured_rank DESC,cb.published_at DESC,cb.created_at DESC LIMIT %s""", (*values, limit))
                rows = self.accounts._many(cursor); ids=[row["id"] for row in rows];tags_by=self._tags(cursor,ids); states=self._state(cursor,user_id,ids)
                return {"books":[self._book(row,tags_by.get(row["id"],[]),states.get(row["id"])) for row in rows]}

    def series(self) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT cs.id,cs.slug,cs.title,COUNT(cb.id) AS book_count FROM catalog_series cs
                JOIN catalog_books cb ON cb.series_id=cs.id AND cb.publication_status='published' AND cb.rights_status IN ('public_domain','licensed')
                GROUP BY cs.id ORDER BY cs.sort_order,cs.title""")
                return {"series":[{"id":r["id"],"slug":r["slug"],"title":r["title"],"bookCount":int(r["book_count"])} for r in self.accounts._many(cursor)]}

    def tags(self) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT ct.id,ct.slug,ct.title,COUNT(cbt.catalog_book_id) AS book_count FROM catalog_tags ct
                JOIN catalog_book_tags cbt ON cbt.tag_id=ct.id JOIN catalog_books cb ON cb.id=cbt.catalog_book_id
                WHERE cb.publication_status='published' AND cb.rights_status IN ('public_domain','licensed') GROUP BY ct.id ORDER BY ct.title""")
                return {"tags":[{"id":r["id"],"slug":r["slug"],"title":r["title"],"bookCount":int(r["book_count"])} for r in self.accounts._many(cursor)]}

    def detail(self, catalog_book_id: str, user_id: str | None = None) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT cb.*,cs.slug AS series_slug,cs.title AS series_title FROM catalog_books cb LEFT JOIN catalog_series cs ON cs.id=cb.series_id
                WHERE cb.id=%s AND cb.publication_status='published' AND cb.rights_status IN ('public_domain','licensed')""", (catalog_book_id,))
                row=self.accounts._one(cursor)
                if not row: raise SaaSError("catalog_book_not_found", "读物不存在或尚未上架。", 404)
                return {"book":self._book(row,self._tags(cursor,[catalog_book_id]).get(catalog_book_id,[]),self._state(cursor,user_id,[catalog_book_id]).get(catalog_book_id),True)}

    def library(self, user_id: str) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT cb.*,cs.slug AS series_slug,cs.title AS series_title,ul.shelf_state,ul.added_at,
                TRUE AS unlocked
                FROM user_library ul JOIN catalog_books cb ON cb.id=ul.catalog_book_id LEFT JOIN catalog_series cs ON cs.id=cb.series_id
                WHERE ul.user_id=%s ORDER BY ul.added_at DESC""",(user_id,))
                rows=self.accounts._many(cursor);ids=[row["id"] for row in rows];tags=self._tags(cursor,ids)
                items=[]
                for row in rows:
                    book=self._book(row,tags.get(row["id"],[]),{"inLibrary":True,"unlocked":bool(row["unlocked"])})
                    book["shelfState"],book["addedAt"]=row["shelf_state"],timestamp(row["added_at"]);items.append(book)
                return {"items":items}

    def reader(self,user_id:str,catalog_book_id:str)->dict[str,Any]:
        """Only current library members can read official content."""
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT cb.id,cb.title,cb.english_title,cb.level,cb.resource_type,cb.estimated_minutes,cb.source_content_book_id,src.duration,src.data_json
                FROM catalog_books cb JOIN content_books src ON src.id=cb.source_content_book_id
                JOIN user_library ou ON ou.catalog_book_id=cb.id AND ou.user_id=%s
                WHERE cb.id=%s AND cb.publication_status='published' AND cb.rights_status IN ('public_domain','licensed')""",(user_id,catalog_book_id))
                row=self.accounts._one(cursor)
                if not row:raise SaaSError("catalog_book_locked","请先将读物加入书架后再开始阅读。",403)
                data=as_json(row["data_json"]);sentences=[]
                for item in data.get("sentences",[]) if isinstance(data.get("sentences",[]),list) else []:
                    if not isinstance(item,dict):continue
                    text=str(item.get("text","")).strip()
                    if text:sentences.append({"id":str(item.get("id",len(sentences))),"text":text,"translation":str(item.get("translation","")).strip(),"start":item.get("start"),"end":item.get("end"),"page":item.get("page"),"section":item.get("section"),"words":item.get("words",[]) if isinstance(item.get("words",[]),list) else []})
                cursor.execute("""SELECT id,kind,content_type,original_bytes,generated_bytes FROM media_assets
                WHERE status='active' AND (catalog_book_id=%s OR content_book_id=%s) ORDER BY CASE WHEN catalog_book_id=%s THEN 0 ELSE 1 END,created_at""",(catalog_book_id,row["source_content_book_id"],catalog_book_id));assets=[]
                for item in self.accounts._many(cursor):
                    cursor.execute("SELECT variant_name,content_type,byte_size FROM asset_variants WHERE asset_id=%s AND deleted_at IS NULL ORDER BY variant_name",(item["id"],));variants=[{"name":variant["variant_name"],"contentType":variant["content_type"],"bytes":int(variant["byte_size"]),"url":f"/api/media/{item['id']}?variant={variant['variant_name']}"} for variant in self.accounts._many(cursor)]
                    assets.append({"id":item["id"],"kind":item["kind"],"contentType":item["content_type"],"bytes":int(item["original_bytes"])+int(item["generated_bytes"]),"url":f"/api/media/{item['id']}","variants":variants})
                playable=any(str(asset["contentType"]).startswith(("audio/","video/")) or any(str(variant["contentType"]).startswith(("audio/","video/")) for variant in asset["variants"]) for asset in assets)
                cursor.execute("SELECT last_sentence_id,reading_seconds,completed_at FROM workspace_progress WHERE user_id=%s AND content_book_id=%s",(user_id,row["source_content_book_id"]));progress=self.accounts._one(cursor)or{}
                return {"book":{"id":row["id"],"title":row["title"],"englishTitle":row["english_title"],"level":row["level"],"resourceType":row["resource_type"],"estimatedMinutes":int(row["estimated_minutes"]),"duration":float(row["duration"] or 0),"sentences":sentences,"mediaAssets":assets,"mediaReady":playable,"mediaNotice":"已连接受鉴权媒体，可在阅读器中播放。" if playable else "该读物当前只有正文，暂未找到可播放音视频。","progress":{"lastSentenceId":progress.get("last_sentence_id","") or "","readingSeconds":int(progress.get("reading_seconds",0)or 0),"completedAt":timestamp(progress.get("completed_at"))}}}

    def _published_book(self,cursor:Any,catalog_book_id:str)->dict[str,Any]:
        cursor.execute("SELECT * FROM catalog_books WHERE id=%s AND publication_status='published' AND rights_status IN ('public_domain','licensed') FOR UPDATE",(catalog_book_id,))
        row=self.accounts._one(cursor)
        if not row:raise SaaSError("catalog_book_not_found","读物不存在或尚未上架。",404)
        return row

    def add_or_unlock(self,user_id:str,catalog_book_id:str,unlock:bool=True,shelf_state:str="active")->dict[str,Any]:
        if shelf_state not in SHELF_STATES:raise SaaSError("invalid_shelf_state","书架状态无效。",400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE id=%s AND status='active' FOR UPDATE",(user_id,))
                if not self.accounts._one(cursor):raise SaaSError("account_unavailable","账号不可用。",403)
                self._published_book(cursor,catalog_book_id)
                context=self.memberships._context(cursor,user_id,lock_user=False)
                cursor.execute("SELECT * FROM user_library WHERE user_id=%s AND catalog_book_id=%s FOR UPDATE",(user_id,catalog_book_id));existing=self.accounts._one(cursor)
                if not existing:
                    cursor.execute("SELECT resource_type FROM catalog_books WHERE id=%s",(catalog_book_id,));resource=self.accounts._one(cursor) or {}
                    kind="video" if resource.get("resource_type") in {"video","youtube"} else "audio" if resource.get("resource_type")=="audio" else ""
                    self.memberships.assert_media_capacity(cursor,user_id,context,kind)
                    cursor.execute("INSERT INTO user_library(id,user_id,catalog_book_id,shelf_state) VALUES(%s,%s,%s,%s)",(new_id(),user_id,catalog_book_id,shelf_state))
                self.memberships._audit(cursor,user_id,None,"catalog_library_add",{"catalogBookId":catalog_book_id})
                # Legacy API alias only: there is no independent unlock state.
                return {"bookId":catalog_book_id,"inLibrary":True,"unlocked":True,"readerReady":True}

    def remove(self,user_id:str,catalog_book_id:str)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE id=%s AND status='active' FOR UPDATE",(user_id,))
                if not self.accounts._one(cursor):raise SaaSError("account_unavailable","账号不可用。",403)
                cursor.execute("DELETE FROM user_library WHERE user_id=%s AND catalog_book_id=%s RETURNING id",(user_id,catalog_book_id))
                if self.accounts._one(cursor):
                    self.memberships._audit(cursor,user_id,None,"catalog_library_remove",{"catalogBookId":catalog_book_id})
                return {"status":"removed","bookId":catalog_book_id,"inLibrary":False,"unlocked":False}

    def review(self,actor_id:str,source_book_id:str,rights_status:str,publication_status:str,updates:dict[str,Any]|None=None)->dict[str,Any]:
        rights_status,publication_status=str(rights_status),str(publication_status)
        if rights_status not in RIGHTS or publication_status not in PUBLICATION:raise SaaSError("invalid_catalog_review","版权或发布状态无效。",400)
        if publication_status=="published" and rights_status not in {"public_domain","licensed"}:raise SaaSError("rights_required","只有公版或已授权内容可以上架。",409)
        updates=updates or {}
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM content_books WHERE id=%s FOR UPDATE",(source_book_id,));source=self.accounts._one(cursor)
                if not source:raise SaaSError("source_book_not_found","原始内容不存在。",404)
                data=as_json(source["data_json"]);sentences=data.get("sentences",[]) if isinstance(data.get("sentences",[]),list) else []
                series_title=str(updates.get("seriesTitle",source.get("series","") or "未分组")).strip() or "未分组";slug=slugify(series_title)
                cursor.execute("SELECT id FROM catalog_series WHERE slug=%s FOR UPDATE",(slug,));series=self.accounts._one(cursor)
                if not series:
                    series={"id":new_id()};cursor.execute("INSERT INTO catalog_series(id,slug,title) VALUES(%s,%s,%s)",(series["id"],slug,series_title))
                preview=[{"id":str(item.get("id","")),"text":str(item.get("text","")).strip()} for item in sentences[:3] if str(item.get("text","")).strip()]
                cursor.execute("SELECT id FROM catalog_books WHERE source_content_book_id=%s FOR UPDATE",(source_book_id,));existing=self.accounts._one(cursor);book_id=existing["id"] if existing else new_id()
                title=str(updates.get("title",source["title"])).strip() or source["title"];english=str(updates.get("englishTitle",source.get("english_title","") or "")).strip();author=str(updates.get("author","")).strip();description=str(updates.get("description","")).strip();level=str(updates.get("level",source.get("level","") or "")).strip();rtype=str(source.get("source_type","book") or "book");rtype=rtype if rtype in {"book","audio","video","youtube"} else "book";minutes=max(0,round(float(source.get("duration",0)or 0)/60));words=sum(len(item.get("words",[])) for item in sentences if isinstance(item,dict))
                cursor.execute("""INSERT INTO catalog_books(id,source_content_book_id,series_id,title,english_title,author,description,level,resource_type,estimated_minutes,sentence_count,word_count,cover_url,preview_json,rights_status,publication_status,featured_rank,published_at,created_by,reviewed_by)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,CASE WHEN %s='published' THEN NOW() ELSE NULL END,%s,%s)
                ON CONFLICT (source_content_book_id) DO UPDATE SET series_id=EXCLUDED.series_id,title=EXCLUDED.title,english_title=EXCLUDED.english_title,author=EXCLUDED.author,description=EXCLUDED.description,level=EXCLUDED.level,resource_type=EXCLUDED.resource_type,estimated_minutes=EXCLUDED.estimated_minutes,sentence_count=EXCLUDED.sentence_count,word_count=EXCLUDED.word_count,cover_url=EXCLUDED.cover_url,preview_json=EXCLUDED.preview_json,rights_status=EXCLUDED.rights_status,publication_status=EXCLUDED.publication_status,featured_rank=EXCLUDED.featured_rank,published_at=CASE WHEN EXCLUDED.publication_status='published' THEN COALESCE(catalog_books.published_at,NOW()) ELSE NULL END,reviewed_by=EXCLUDED.reviewed_by,updated_at=NOW()""",
                (book_id,source_book_id,series["id"],title,english,author,description,level,rtype,minutes,len(sentences),words,source.get("cover_url","") or "",json.dumps(preview),rights_status,publication_status,int(updates.get("featuredRank",0)or 0),publication_status,actor_id,actor_id))
                tags=updates.get("tags",[])
                if not isinstance(tags,list):raise SaaSError("invalid_catalog_review","标签必须是数组。",400)
                cursor.execute("SELECT id FROM catalog_books WHERE source_content_book_id=%s",(source_book_id,));book=self.accounts._one(cursor);book_id=book["id"]
                cursor.execute("DELETE FROM catalog_book_tags WHERE catalog_book_id=%s",(book_id,))
                for tag in sorted({str(item).strip() for item in tags if str(item).strip()}):
                    tag_slug=slugify(tag);cursor.execute("SELECT id FROM catalog_tags WHERE slug=%s",(tag_slug,));tag_row=self.accounts._one(cursor)
                    if not tag_row:
                        tag_row={"id":new_id()};cursor.execute("INSERT INTO catalog_tags(id,slug,title) VALUES(%s,%s,%s)",(tag_row["id"],tag_slug,tag))
                    cursor.execute("INSERT INTO catalog_book_tags(catalog_book_id,tag_id) VALUES(%s,%s)",(book_id,tag_row["id"]))
                self.memberships._audit(cursor,actor_id,actor_id,"catalog_review",{"sourceBookId":source_book_id,"catalogBookId":book_id,"rights":rights_status,"publication":publication_status})
                cursor.execute("SELECT cb.*,cs.slug AS series_slug,cs.title AS series_title FROM catalog_books cb LEFT JOIN catalog_series cs ON cs.id=cb.series_id WHERE cb.id=%s",(book_id,));row=self.accounts._one(cursor)
                return {"book":self._book(row,self._tags(cursor,[book_id]).get(book_id,[]),detail=True)}

    def review_sources(self)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT cb.id AS source_book_id,cb.title,cb.english_title,cb.series,cb.level,cb.source_type,cb.cover_url,
                cat.id AS catalog_book_id,cat.rights_status,cat.publication_status FROM content_books cb LEFT JOIN catalog_books cat ON cat.source_content_book_id=cb.id ORDER BY cb.updated_at DESC""")
                return {"sources":[{"sourceBookId":row["source_book_id"],"title":row["title"],"englishTitle":row["english_title"],"series":row["series"],"level":row["level"],"resourceType":row["source_type"],"coverUrl":row["cover_url"],"catalogBookId":row["catalog_book_id"],"rightsStatus":row["rights_status"] or "private","publicationStatus":row["publication_status"] or "draft"} for row in self.accounts._many(cursor)]}
