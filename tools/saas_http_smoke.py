#!/usr/bin/env python3
"""Authenticated HTTP smoke against the disposable PostgreSQL SaaS database."""
from __future__ import annotations

import http.cookiejar
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


ROOT=Path(__file__).resolve().parents[1]
PORT=int(os.environ.get("READER_PORT","8795"));BASE=f"http://127.0.0.1:{PORT}"


def database_url(base:str,name:str)->str:
    parsed=urlsplit(base);return urlunsplit((parsed.scheme,parsed.netloc,"/"+name,parsed.query,parsed.fragment))


def main()->int:
    formal=str(os.environ.get("DATABASE_URL","")).strip();test_name=str(os.environ.get("SHIYUE_SAAS_TEST_DATABASE_NAME","shiyue_phase1_test"));test_url=database_url(formal,test_name)
    temp_media=tempfile.TemporaryDirectory(prefix="shiyue-saas-http-smoke-")
    environment={**os.environ,"DATABASE_URL":test_url,"SHIYUE_SAAS_ENABLED":"1","READER_HOST":"127.0.0.1","READER_PORT":str(PORT),"MEDIA_ROOT":temp_media.name,"BOOTSTRAP_ADMIN_EMAIL":"","BOOTSTRAP_ADMIN_PASSWORD":""}
    process=subprocess.Popen([sys.executable,str(ROOT/"tools/reader_server.py")],cwd=ROOT,env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    jar=http.cookiejar.CookieJar();opener=build_opener(HTTPCookieProcessor(jar));checks=[];device_id="saas-http-smoke-device"
    def csrf()->str:return next((cookie.value for cookie in jar if cookie.name=="shiyue_csrf"),"")
    def request(path:str,method:str="GET",payload=None,headers=None,expected=(200,)):
        body=None;actual_headers={"X-Device-Id":device_id,**(headers or {})}
        if payload is not None:
            if isinstance(payload,bytes):body=payload
            else:body=json.dumps(payload).encode();actual_headers.setdefault("Content-Type","application/json")
        if method not in {"GET","HEAD","OPTIONS"} and csrf():actual_headers["X-CSRF-Token"]=csrf()
        try:
            response=opener.open(Request(BASE+path,data=body,headers=actual_headers,method=method),timeout=20);status=response.status;data=response.read();response_headers={key.lower():value for key,value in response.headers.items()}
        except HTTPError as exc:status=exc.code;data=exc.read();response_headers={key.lower():value for key,value in exc.headers.items()}
        if status not in expected:raise AssertionError(f"{method} {path}: expected {expected}, got {status}: {data[:500]!r}")
        try:value=json.loads(data) if data else {}
        except json.JSONDecodeError:value=data
        return status,response_headers,value
    def check(name,condition,detail=""):
        checks.append({"name":name,"ok":bool(condition),"detail":str(detail)})
        if not condition:raise AssertionError(f"{name}: {detail}")
    try:
        deadline=time.time()+15
        while time.time()<deadline:
            if process.poll() is not None:raise RuntimeError("SaaS reader exited during startup")
            try:status,headers,health=request("/api/health");break
            except Exception:time.sleep(.1)
        else:raise RuntimeError("SaaS reader did not become healthy")
        check("SaaS health",health.get("saasEnabled") is True,health);check("CSP","content-security-policy" in headers,headers)
        _,_,commerce=request("/api/commerce/products");check("public commerce catalog",len(commerce.get("products",[]))>=4 and commerce.get("payment",{}).get("automaticRenewal") is False,commerce)
        _,_,homepage=request("/");check("public product homepage",isinstance(homepage,bytes) and "把英语材料真正读懂".encode() in homepage)
        status,_,_=request("/api/workspace/books",expected=(401,));check("unauthenticated isolation",status==401)
        try:
            from saas_auth import SaaSService
            service=SaaSService(environment=environment)
            with service.transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT id FROM users WHERE email=%s",("ai-owner@local.test",));row=cursor.fetchone()
                    if row:
                        user_id=row[0] if not isinstance(row,dict) else row["id"]
                        cursor.execute("UPDATE devices SET revoked_at=NOW() WHERE user_id=%s AND id<>%s AND revoked_at IS NULL",(user_id,device_id))
                        cursor.execute("UPDATE user_sessions SET revoked_at=NOW() WHERE user_id=%s AND device_id<>%s AND revoked_at IS NULL",(user_id,device_id))
        except Exception:pass
        _,_,login=request("/api/auth/login","POST",{"email":"ai-owner@local.test","password":"ai owner password"});check("login",login.get("user",{}).get("email")=="ai-owner@local.test",login);check("csrf cookie",bool(csrf()))
        _,_,usage=request("/api/membership/usage");check("membership",usage.get("plan",{}).get("id")=="free-v1",usage.get("plan"))
        _,_,plans=request("/api/membership/plans");check("membership plans",len(plans.get("plans",[]))>=1,plans)
        _,_,requests_before=request("/api/membership/requests");check("membership requests",isinstance(requests_before.get("requests"),list),requests_before)
        _,_,preferences=request("/api/preferences");check("preferences read",isinstance(preferences,dict),preferences)
        _,_,saved_preferences=request("/api/preferences","POST",{"readerMode":"shadow","density":"compact","reminder":"daily","readerLayout":"stack","eyeComfort":True,"focusMode":False,"sentenceAutoPause":True,"shortcutPrevious":"a","shortcutRepeat":"s","shortcutNext":"d","shortcutPlay":"space","wordTipSeconds":2.5,"reviewPageSize":15,"manualRepeatCount":4,"manualPauseSeconds":1.5,"highlightLeadMs":80,"heatmapRange":"quarter","playbackRate":1.25});check("preferences write",saved_preferences.get("preferences",{}).get("readerMode")=="shadow",saved_preferences)
        _,_,preferences_after=request("/api/preferences");check("preferences persisted",preferences_after.get("density")=="compact" and preferences_after.get("reminder")=="daily",preferences_after)
        check("advanced preferences persisted",preferences_after.get("readerLayout")=="stack" and preferences_after.get("sentenceAutoPause") is True and preferences_after.get("reviewPageSize")==15,preferences_after)
        context_used_before=next(item for item in usage["usage"] if item["feature"]=="ai_context_generations")["used"]
        _,_,catalog=request("/api/catalog");check("catalog",isinstance(catalog.get("books"),list))
        key="smoke-"+uuid.uuid4().hex;_,_,created=request("/api/workspace/imports","POST",{"kind":"text","title":"SaaS HTTP Smoke","filename":"smoke.txt","idempotencyKey":key},expected=(201,));task_id=created["task"]["id"]
        source=b"SaaS smoke first sentence. SaaS smoke second sentence!";_,_,uploaded=request(f"/api/workspace/imports/{task_id}/upload","POST",source,{"Content-Type":"text/plain","X-Upload-Filename":"smoke.txt"});check("upload",uploaded["task"]["status"]=="queued")
        _,_,completed=request(f"/api/workspace/imports/{task_id}/complete","POST",{});check("complete import",completed["task"]["status"]=="complete");book_id=completed["task"]["outputBookId"]
        _,_,reader=request(f"/api/workspace/books/{quote(book_id)}/reader");book=reader["book"];check("private reader",len(book.get("sentences",[]))==2);sentence=book["sentences"][0];asset=book["mediaAssets"][0]
        status,range_headers,data=request(asset["url"],headers={"Range":"bytes=0-4"},expected=(206,));check("private media range",status==206 and data==b"SaaS ",range_headers)
        vocab_payload={"word":"SaaS","root":"saas","phonetic":"","meaning":"软件即服务","context":sentence["text"],"note":"smoke","rating":"unknown","interval_days":1,"due_at":"2026-10-11T00:00:00+08:00","reviews":0}
        _,_,saved=request("/api/workspace/vocabulary","POST",{"bookId":book_id,"sentenceId":sentence["id"],"wordIndex":0,"payload":vocab_payload},expected=(201,));check("vocabulary",saved.get("payload",{}).get("meaning")=="软件即服务")
        _,_,annotation=request("/api/workspace/annotations","POST",{"bookId":book_id,"sentenceId":sentence["id"],"wordIndex":0,"payload":{"note":"smoke note"}});check("annotation",annotation.get("payload",{}).get("note")=="smoke note")
        _,_,activity=request("/api/workspace/activity","POST",{"bookId":book_id,"readingSeconds":600,"sentences":5,"lookups":1,"reviews":1,"sessions":1,"lastSentenceId":sentence["id"],"idempotencyKey":"smoke-activity-"+uuid.uuid4().hex});check("activity",activity.get("reviews")==1 and activity.get("lookups")==1,activity)
        status,_,ai_failure=request("/api/word-context","POST",{"bookId":book_id,"sentenceId":sentence["id"],"wordIndex":0},expected=(503,));check("AI unavailable is controlled",ai_failure.get("code")=="ai_provider_unavailable",ai_failure)
        _,_,usage_after=request("/api/membership/usage");context_usage=next(item for item in usage_after["usage"] if item["feature"]=="ai_context_generations");check("AI reservation released",context_usage["reserved"]==0 and context_usage["used"]==context_used_before,context_usage)
        _,_,exported=request("/api/account/export");check("account export",book_id in {item["id"] for item in exported.get("privateBooks",[])})
        _,_,deleted=request(f"/api/workspace/books/{quote(book_id)}","DELETE",{"confirmTitle":book["title"]});check("private book delete",deleted.get("status")=="deleted",deleted)
        status,_,_=request(f"/api/workspace/books/{quote(book_id)}/reader",expected=(404,));check("deleted book inaccessible",status==404)
        if login.get("user",{}).get("isAdmin"):
            _,_,admin_dashboard=request("/api/admin/dashboard");check("admin dashboard",isinstance(admin_dashboard.get("users"),dict),admin_dashboard)
            _,_,catalog_sources=request("/api/admin/catalog/sources");check("catalog moderation",isinstance(catalog_sources.get("sources"),list),catalog_sources)
            _,_,media_assets=request("/api/admin/media-assets?limit=5");check("media inventory",isinstance(media_assets.get("assets"),list),media_assets)
            _,_,platform_config=request("/api/admin/platform-config");check("platform config",platform_config.get("dioco",{}).get("source")=="database",platform_config)
            _,_,generated_invites=request("/api/admin/invitations","POST",{"code":"","count":2,"maxUses":1,"channel":"smoke","note":"batch smoke"},expected=(201,));check("batch invitation generation",generated_invites.get("count")==2 and all(item.get("code") for item in generated_invites.get("invitations",[])),generated_invites)
            _,_,searched_invites=request("/api/admin/invitations?q=batch%20smoke&limit=5");check("invitation search",searched_invites.get("total",0)>=2,searched_invites)
            _,_,deployment=request("/api/deployment/config");check("deployment dashboard",isinstance(deployment.get("targets"),list) and isinstance(deployment.get("jobs"),list),deployment)
        else:
            status,_,denied=request("/api/admin/dashboard",expected=(403,));check("admin isolation",denied.get("code")=="admin_required",denied)
        request("/api/auth/logout","POST",{});status,_,_=request("/api/workspace/books",expected=(401,));check("logout",status==401)
        print(json.dumps({"status":"ok","baseUrl":BASE,"checks":checks,"bookId":book_id},ensure_ascii=False,indent=2));return 0
    except Exception as exc:
        print(json.dumps({"status":"failed","baseUrl":BASE,"error":str(exc),"checks":checks},ensure_ascii=False,indent=2),file=sys.stderr);return 1
    finally:
        if process.poll() is None:
            try:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=5)
            except Exception:
                try:os.killpg(process.pid,signal.SIGKILL)
                except Exception:pass
        stderr=process.stderr.read() if process.stderr else ""
        if "Traceback" in stderr:print(stderr,file=sys.stderr)
        temp_media.cleanup()


if __name__=="__main__":raise SystemExit(main())
