#!/usr/bin/env python3
"""Static reader server plus a local-only Whisper endpoint for shadowing."""
import json
import base64
import gzip
import hashlib
import hmac
import io
import mimetypes
import os
import re
import signal
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import defaultdict, deque
from http.cookies import SimpleCookie
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from library_db import BOOKS_ROOT, active_import_jobs, add_daily, annotate_word, canonical_youtube_series, create_job, delete_book, delete_import_jobs, dictionary, get_book, get_book_chunk, get_book_manifest, get_job, get_sentence_grammar, get_settings as db_get_settings, import_duplicates, imported_books, learning_days, library, mark_import_jobs_cancelling, now, pending_import_jobs, save_sentence_grammar, save_vocab, scan_catalog, set_settings, touch_book, update_job, update_vocab, vocabulary_list
from deployment import manager as deployment_manager
from saas_auth import SaaSConfigurationError, SaaSError, SaaSService, token_hash
from saas_admin import AdminService
from saas_accounts import AccountLifecycleService
from saas_catalog import CatalogService
from saas_media import MediaService
from saas_membership import MembershipService
from saas_rewards import RewardService
from saas_workspace import WorkspaceService
from saas_review import ReviewService
from saas_learning import LearningService
from saas_journey import JourneyService
from saas_imports import WorkspaceImportService
from saas_ai import WorkspaceAIService
from saas_billing import PaddleBillingService
from saas_cache import SaaSCache
from saas_commerce import CommerceService
from saas_redemptions import RedemptionService
from saas_payments import AlipayService
from youtube_subtitles import has_translated_english_track,select_chinese_track,select_native_english_track

ROOT=Path(__file__).resolve().parents[1]
READER=ROOT/"reader"
SITE=READER/"site"
CLI=Path(os.environ.get("SHIYUE_WHISPER_CLI",str(ROOT/"tools/vendor/whisper.cpp/build/bin/whisper-cli"))).expanduser()
MODEL=Path(os.environ.get("SHIYUE_WHISPER_MODEL",str(ROOT/"tools/vendor/whisper.cpp/models/ggml-base.en.bin"))).expanduser()
GRAMMAR_PYTHON=Path(os.environ.get("SHIYUE_GRAMMAR_PYTHON",str(ROOT/".local/forced-aligner/venv/bin/python"))).expanduser()
YTDLP=ROOT/".local/bin/yt-dlp"
NODE=Path(shutil.which("node") or "/usr/local/bin/node")
PRIVATE_CONFIG=ROOT/".dioco.local.json"
CACHE=ROOT/".cache/dioco"
CACHE.mkdir(parents=True,exist_ok=True)
LEMMA_FILE=ROOT/"tools/vendor/ECDICT/lemma.en.txt"
LEMMA_INDEX=None
COVER_CACHE=BOOKS_ROOT/".reader/catalog-covers"
COVER_CACHE.mkdir(parents=True,exist_ok=True)
COVER_LOCK=threading.Lock()
VIDEO_UPLOADS=ROOT/".local/video-uploads"
VIDEO_UPLOADS.mkdir(parents=True,exist_ok=True)
UPSTREAM="https://api-cdn-plus.dioco.io"
UPSTREAM_HEADERS={
    "Accept":"application/json, text/plain, */*",
    "Origin":"https://www.youtube.com",
    "Referer":"https://www.youtube.com/",
    "User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/153.0 Safari/537.36",
}
IMPORT_LOCK=threading.Lock()
RUNTIME_MODE=os.environ.get("SHIYUE_RUNTIME_MODE","full")
DEPLOYMENT_MODE=os.environ.get("SHIYUE_DEPLOYMENT_MODE","remote")
ACTIVE_IMPORT_PROCESSES={}
ACTIVE_PROCESS_LOCK=threading.Lock()
SAAS=SaaSService.from_env()
MEMBERSHIPS=MembershipService(SAAS)
CATALOG=CatalogService(SAAS,MEMBERSHIPS)
REWARDS=RewardService(SAAS,MEMBERSHIPS)
ADMIN=AdminService(SAAS,MEMBERSHIPS)
MEDIA=MediaService(SAAS,MEMBERSHIPS)
ACCOUNTS=AccountLifecycleService(SAAS)
WORKSPACE=WorkspaceService(SAAS)
REVIEW=ReviewService(WORKSPACE)
LEARNING=LearningService(WORKSPACE,REVIEW)
JOURNEY=JourneyService(SAAS)
WORKSPACE_IMPORTS=WorkspaceImportService(SAAS,MEMBERSHIPS,MEDIA)
OFFICIAL_IMPORTS=WorkspaceImportService(SAAS,MEMBERSHIPS,MEDIA,official=True)
WORKSPACE_AI=WorkspaceAIService(SAAS,MEMBERSHIPS)
BILLING=PaddleBillingService(SAAS,MEMBERSHIPS)
PAYMENTS=AlipayService(SAAS,MEMBERSHIPS)
COMMERCE=CommerceService(SAAS,PAYMENTS)
REDEMPTIONS=RedemptionService(SAAS,MEMBERSHIPS)
CACHE_SERVICE=SaaSCache()
RATE_LIMIT_LOCK=threading.Lock()
RATE_LIMIT_BUCKETS=defaultdict(deque)
RATE_LIMIT_RULES={
    "/api/auth/login":(10,300),"/api/auth/register":(8,3600),"/api/auth/forgot-password":(5,3600),
    "/api/auth/login/replace-device":(10,300),
    "/api/auth/reset-password":(8,3600),"/api/checkins":(30,3600),"/api/word-context":(60,3600),"/api/sentence-grammar":(60,3600),
    "/api/word-hover":(300,3600),"/api/word-dictionary":(120,3600),"/api/membership/redeem":(10,300),
}

def run_import_process(job_id,command,log_path):
    job=get_job(job_id)
    if not job or job["status"] not in {"queued","running"}:return
    log_path.parent.mkdir(parents=True,exist_ok=True)
    with log_path.open("w") as output:
        process=subprocess.Popen([str(item) for item in command],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        with ACTIVE_PROCESS_LOCK:ACTIVE_IMPORT_PROCESSES[job_id]=process
        update_job(job_id,pid=process.pid)
        try:process.wait()
        finally:
            with ACTIVE_PROCESS_LOCK:ACTIVE_IMPORT_PROCESSES.pop(job_id,None)

def process_tree_for_jobs(job_ids):
    targets={int(job_id) for job_id in job_ids};roots=set()
    with ACTIVE_PROCESS_LOCK:
        roots.update(process.pid for job_id,process in ACTIVE_IMPORT_PROCESSES.items() if job_id in targets and process.poll() is None)
    for job_id in targets:
        job=get_job(job_id)
        if job and job.get("pid"):roots.add(int(job["pid"]))
    try:lines=subprocess.check_output(["ps","-ax","-o","pid=,ppid=,command="],text=True).splitlines()
    except Exception:lines=[]
    children={};commands={}
    for line in lines:
        match=re.match(r"\s*(\d+)\s+(\d+)\s+(.*)",line)
        if not match:continue
        pid,ppid,command=int(match.group(1)),int(match.group(2)),match.group(3);children.setdefault(ppid,[]).append(pid);commands[pid]=command
        if any(re.search(rf"import_(?:video_|youtube_)?worker\.py\s+{job_id}(?:\s|$)",command) for job_id in targets):roots.add(pid)
    result=set(roots);stack=list(roots)
    while stack:
        for child in children.get(stack.pop(),[]):
            if child not in result:result.add(child);stack.append(child)
    return result

def terminate_processes(pids):
    pids={pid for pid in pids if pid>1 and pid!=os.getpid()}
    for pid in sorted(pids,reverse=True):
        try:os.kill(pid,signal.SIGTERM)
        except ProcessLookupError:pass
    deadline=time.time()+3
    while pids and time.time()<deadline:
        pids={pid for pid in pids if _process_exists(pid)}
        if pids:time.sleep(.1)
    for pid in sorted(pids,reverse=True):
        try:os.kill(pid,signal.SIGKILL)
        except ProcessLookupError:pass

def _process_exists(pid):
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return True

class TextExtractor(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]
    def handle_data(self,data): self.parts.append(data)
    def text(self): return "".join(self.parts).strip()

def private_config():
    config={"userEmail":os.environ.get("DIOCO_USER_EMAIL",""),"diocoToken":os.environ.get("DIOCO_TOKEN","")}
    if PRIVATE_CONFIG.exists():
        config.update({k:v for k,v in json.loads(PRIVATE_CONFIG.read_text()).items() if v})
    return config

def cache_path(kind,key,suffix="json"):
    digest=hashlib.sha256(key.encode()).hexdigest()
    folder=CACHE/kind; folder.mkdir(parents=True,exist_ok=True)
    return folder/f"{digest}.{suffix}"

def lemma_index():
    global LEMMA_INDEX
    if LEMMA_INDEX is not None:return LEMMA_INDEX
    index={}
    if LEMMA_FILE.exists():
        for line in LEMMA_FILE.read_text(errors="replace").splitlines():
            match=re.match(r"^([^/]+)/([0-9]+)\s*->\s*(.+)$",line)
            if not match:continue
            root,frequency,forms=match.group(1).casefold(),int(match.group(2)),match.group(3)
            for form in [root,*forms.split(",")]:
                form=form.strip().casefold()
                if form and frequency>index.get(form,("",-1))[1]:index[form]=(root,frequency)
    LEMMA_INDEX=index;return index

def infer_lemma(word):return lemma_index().get(word.casefold(),("",0))[0]

def upstream_json(path,params=None,payload=None,timeout=20):
    url=UPSTREAM+path
    if params: url += "?"+urlencode(params)
    headers=dict(UPSTREAM_HEADERS); data=None
    if payload is not None:
        data=json.dumps(payload,ensure_ascii=False).encode(); headers["Content-Type"]="application/json"
    request=Request(url,data=data,headers=headers,method="POST" if payload is not None else "GET")
    with urlopen(request,timeout=timeout) as response:
        return json.loads(response.read())

def plain_html(value):
    parser=TextExtractor(); parser.feed(value or ""); return parser.text()

class Handler(SimpleHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(READER),**kwargs)
    def end_headers(self):
        self.send_header("Permissions-Policy","microphone=(self)")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options","DENY")
        self.send_header("Cross-Origin-Opener-Policy","same-origin")
        self.send_header("Cross-Origin-Resource-Policy","same-origin")
        if SAAS.enabled:
            self.send_header("Content-Security-Policy","default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if urlsplit(getattr(self,"path","")).path.lower().endswith((".mp3",".wav",".m4a",".ogg")):
            self.send_header("Accept-Ranges","bytes")
        super().end_headers()
    def rate_limit(self,path):
        rule=RATE_LIMIT_RULES.get(path)
        if not rule:return True
        maximum,window=rule;now_time=time.monotonic();key=(path,self.client_address[0])
        with RATE_LIMIT_LOCK:
            bucket=RATE_LIMIT_BUCKETS[key]
            while bucket and bucket[0]<=now_time-window:bucket.popleft()
            if len(bucket)>=maximum:
                retry=max(1,int(window-(now_time-bucket[0])))
                self.reply({"code":"rate_limited","error":"请求过于频繁，请稍后重试。","retryAfter":retry},429,extra_headers=(("Retry-After",str(retry)),));return False
            bucket.append(now_time)
        return True

    def do_GET(self):
        route=urlsplit(self.path)
        if SAAS.enabled and route.path.startswith("/api/payments/alipay/orders/"):
            if not self.require_saas_user(verified=True):return
            try:self.reply(PAYMENTS.order_status(str(self._saas_session["id"]),unquote(route.path.rsplit("/",1)[1])))
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"alipay_unavailable","error":str(exc)},503)
            return
        if route.path in {"/terms","/privacy","/content-policy","/refunds","/copyright"}:
            if SAAS.enabled:self.reply({"code":"backend_only","error":"该端口仅提供后台 API。"},404)
            else:self.serve_legal_page(route.path)
            return
        if route.path=="/api/auth/debug-browser-login":
            self.debug_browser_login(route);return
        if route.path.startswith("/api/auth/"):
            self.auth_get(route.path); return
        if SAAS.enabled and (route.path=="/api/commerce/products" or route.path.startswith("/api/commerce/products/")):
            try:
                if route.path=="/api/commerce/products":self.reply(COMMERCE.public_catalog(),cache_control="public, max-age=60");return
                self.reply(COMMERCE.product(unquote(route.path.rsplit("/",1)[1])),cache_control="public, max-age=60");return
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"commerce_unavailable","error":str(exc)},503)
            return
        if SAAS.enabled and route.path.startswith("/api/commerce/orders/"):
            self.reply({"code":"payment_provider_retired","error":"支付订单接口已停用；请通过云猫购买并在拾页兑换。"},410)
            return
        if SAAS.enabled and (route.path=="/api/workspace/imports" or route.path.startswith("/api/workspace/imports/")):
            if not self.require_saas_user(verified=True):return
            self.workspace_import_get(route);return
        if SAAS.enabled and (route.path=="/api/workspace/books" or route.path.startswith("/api/workspace/books/") or route.path in {"/api/workspace/vocabulary","/api/workspace/annotations","/api/workspace/learning-days","/api/workspace/journey","/api/workspace/review","/api/workspace/learning"}):
            if not self.require_saas_user(verified=True):return
            self.workspace_get(route);return
        if SAAS.enabled and route.path.startswith("/api/media/"):
            if not self.require_saas_user(verified=True):return
            self.media_get(route);return
        if SAAS.enabled and route.path in {"/api/account/export","/api/account/deletion-status"}:
            if not self.require_saas_user():return
            self.account_get(route.path);return
        if SAAS.enabled and route.path == "/api/preferences":
            if not self.require_saas_user(verified=True):return
            self.reply(SAAS.preferences(str(self._saas_session["id"])));return
        if SAAS.enabled and route.path.startswith("/api/admin/"):
            if not self.require_saas_user():return
            self.admin_get(route);return
        if SAAS.enabled and route.path in {"/api/rewards/status","/api/rewards/catalog","/api/rewards/ledger"}:
            if not self.require_saas_user():return
            self.rewards_get(route.path);return
        if SAAS.enabled and route.path.startswith("/api/catalog/books/") and route.path.endswith("/reader"):
            if not self.require_saas_user(verified=True):return
            self.catalog_reader_get(route.path);return
        if SAAS.enabled and (route.path=="/api/catalog" or route.path in {"/api/catalog/series","/api/catalog/tags"} or route.path.startswith("/api/catalog/books/")):
            self.catalog_get(route);return
        if SAAS.enabled and route.path=="/api/library":
            if not self.require_saas_user():return
            self.catalog_library_get();return
        if SAAS.enabled and route.path=="/api/admin/catalog/sources":
            if not self.require_saas_user():return
            self.catalog_admin_get();return
        if SAAS.enabled and route.path=="/api/billing/config":
            if not self.require_saas_user(verified=True):return
            self.reply(BILLING.public_config());return
        if SAAS.enabled and (route.path in {"/api/membership","/api/membership/usage","/api/membership/orders","/api/membership/plans","/api/membership/requests","/api/membership/change-orders","/api/membership/change-preview","/api/admin/commerce/redemption-batches"} or route.path.startswith("/api/membership/change-orders/")):
            if not self.require_saas_user(): return
            self.membership_get(route.path); return
        if SAAS.enabled and route.path in {"/api/word-hover","/api/word-dictionary","/api/word-tts"}:
            if not self.require_saas_user(verified=True):return
            query=parse_qs(route.query)
            if route.path=="/api/word-hover":self.word_hover(query);return
            if route.path=="/api/word-dictionary":self.word_dictionary(query);return
            self.word_tts(query);return
        if SAAS.enabled and route.path.startswith("/api/") and route.path != "/api/health":
            if not self.require_saas_user(): return
            # Existing reader handlers still write the single-user SQLite
            # database.  Do not expose them under a multi-tenant flag until
            # their PostgreSQL workspace adapter lands; allowing them through
            # would leak the administrator's legacy data to new accounts.
            if not route.path.startswith("/api/deployment/"):
                self.saas_content_pending(); return
        if route.path == "/api/health":
            cache=CACHE_SERVICE.status();healthy=not cache["enabled"] or cache["ready"]
            self.reply({"status":"ok" if healthy else "degraded","runtimeMode":RUNTIME_MODE,"saasEnabled":SAAS.enabled,"redisEnabled":cache["enabled"],"redisReady":cache["ready"],"books":len(library()),"time":now()},200 if healthy else 503); return
        if route.path.startswith("/api/deployment/"):
            if not self.deployment_allowed():return
            query=parse_qs(route.query)
            try:target_id=int((query.get("targetId") or [0])[0])
            except (TypeError,ValueError):target_id=0
            if route.path == "/api/deployment/config": self.reply({"targets":deployment_manager.list_targets(),"jobs":deployment_manager.recent_jobs(limit=20),"invalidCount":deployment_manager.invalid_job_count(),"status":deployment_manager.dashboard_status(target_id or None)});return
            if route.path == "/api/deployment/releases": self.reply({"releases":deployment_manager.remote_releases(target_id) if target_id else []});return
            if route.path.startswith("/api/deployment/jobs/"):
                try:job_id=int(route.path.rsplit("/",1)[1]);offset=int((parse_qs(route.query).get("offset") or [0])[0])
                except ValueError:self.reply({"error":"invalid job"},400);return
                result=deployment_manager.job_info(job_id,offset);self.reply(result or {"error":"job not found"},200 if result else 404);return
            self.send_error(404);return
        if route.path == "/api/library": self.reply({"books":library()},cache_control="private, max-age=15, stale-while-revalidate=120"); return
        if route.path == "/api/vocabulary": self.reply({"items":vocabulary_list()}); return
        if route.path == "/api/learning/days": self.reply({"days":learning_days(365)}); return
        if route.path == "/api/local-dictionary": self.reply(dictionary(),cache_control="private, max-age=3600"); return
        if route.path == "/api/import/catalog": self.reply({"series":scan_catalog()}); return
        if route.path == "/api/import/cover": self.import_cover(parse_qs(route.query)); return
        if route.path == "/api/import/jobs": self.reply({"jobs":active_import_jobs(),"pendingJobs":pending_import_jobs()}); return
        if route.path.startswith("/api/import/jobs/"):
            try: job=get_job(int(route.path.rsplit("/",1)[1]))
            except ValueError: job=None
            self.reply(job or {"error":"job not found"},200 if job else 404); return
        if route.path.startswith("/api/books/"):
            value=unquote(route.path.split("/api/books/",1)[1]);parts=value.split("/");book_id=parts[0]
            cache_control="no-store"
            if len(parts)==2 and parts[1]=="manifest":result=get_book_manifest(book_id);cache_control="private, max-age=60, stale-while-revalidate=300"
            elif len(parts)==3 and parts[1]=="chunks":
                try:result=get_book_chunk(book_id,int(parts[2]));cache_control="private, max-age=3600, stale-while-revalidate=86400"
                except ValueError:result=None
            else:result=get_book(book_id)
            self.reply(result or {"error":"book not found"},200 if result else 404,cache_control=cache_control); return
        if route.path == "/api/settings": self.get_settings(); return
        if route.path == "/api/word-hover": self.word_hover(parse_qs(route.query)); return
        if route.path == "/api/word-dictionary": self.word_dictionary(parse_qs(route.query)); return
        if route.path == "/api/word-tts": self.word_tts(parse_qs(route.query)); return
        if SAAS.enabled:
            self.reply({"code":"backend_only","error":"该端口仅提供后台 API。"},404);return
        if route.path.startswith("/books/"):
            self.serve_books_file(route.path); return
        range_header=self.headers.get("Range")
        if range_header and self.serve_range(range_header): return
        if self.serve_reader_asset(route):return
        super().do_GET()
    def serve_saas_site(self,route):
        spa_routes={"/", "/app", "/pricing", "/login", "/register", "/support", "/verify-email", "/reset-password"}
        relative="index.html" if route.path in spa_routes or route.path.startswith("/purchase/") else unquote(route.path).lstrip("/")
        path=(SITE/relative).resolve()
        try:path.relative_to(SITE.resolve())
        except ValueError:self.send_error(403);return True
        if not path.is_file():return False
        stat=path.stat();etag=f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        if self.headers.get("If-None-Match")==etag:
            self.send_response(304);self.send_header("ETag",etag);self.send_header("Cache-Control","public, max-age=31536000, immutable" if path.suffix in {".js",".css",".svg",".png",".woff",".woff2"} else "no-cache");self.end_headers();return True
        data=path.read_bytes();content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream";compressible=path.suffix.lower() in {".html",".js",".css",".json",".svg",".txt"}
        encoded=compressible and "gzip" in self.headers.get("Accept-Encoding","").lower() and len(data)>1024
        if encoded:data=gzip.compress(data,compresslevel=6)
        self.send_response(200);self.send_header("Content-Type",content_type);self.send_header("Content-Length",str(len(data)));self.send_header("ETag",etag);self.send_header("Cache-Control","public, max-age=31536000, immutable" if path.suffix in {".js",".css",".svg",".png",".woff",".woff2"} else "no-cache")
        if encoded:self.send_header("Content-Encoding","gzip");self.send_header("Vary","Accept-Encoding")
        self.end_headers();self.wfile.write(data);return True
    def serve_reader_asset(self,route):
        relative=unquote(route.path).lstrip("/") or "index.html";path=(READER/relative).resolve()
        try:path.relative_to(READER.resolve())
        except ValueError:self.send_error(403);return True
        if not path.is_file():return False
        stat=path.stat();etag=f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        if self.headers.get("If-None-Match")==etag:
            self.send_response(304);self.send_header("ETag",etag);self.send_header("Cache-Control","public, max-age=31536000, immutable" if route.query and path.suffix in {".js",".css"} else "no-cache");self.end_headers();return True
        data=path.read_bytes();content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream";compressible=path.suffix.lower() in {".html",".js",".css",".json",".svg",".txt"}
        encoded=compressible and "gzip" in self.headers.get("Accept-Encoding","").lower() and len(data)>1024
        if encoded:data=gzip.compress(data,compresslevel=6)
        self.send_response(200);self.send_header("Content-Type",content_type);self.send_header("Content-Length",str(len(data)));self.send_header("ETag",etag);self.send_header("Cache-Control","public, max-age=31536000, immutable" if route.query and path.suffix in {".js",".css"} else "no-cache")
        if encoded:self.send_header("Content-Encoding","gzip");self.send_header("Vary","Accept-Encoding")
        self.end_headers();self.wfile.write(data);return True
    def serve_legal_page(self,path):
        pages={"/terms":"terms.html","/privacy":"privacy.html","/content-policy":"content-policy.html","/refunds":"refunds.html","/copyright":"copyright.html"}
        target=(READER/"legal"/pages[path]).resolve()
        try:target.relative_to((READER/"legal").resolve())
        except ValueError:self.send_error(403);return
        if not target.is_file():self.send_error(404);return
        data=target.read_bytes();self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Cache-Control","no-cache");self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
    def serve_media_file(self,path,content_type,range_header=""):
        size=path.stat().st_size
        if not range_header:
            self.send_response(200);self.send_header("Content-Type",content_type);self.send_header("Accept-Ranges","bytes");self.send_header("Cache-Control","private, no-store");self.send_header("Content-Length",str(size));self.end_headers();start,end=0,size-1
        else:
            match=re.fullmatch(r"bytes=(\d*)-(\d*)",range_header.strip())
            if not match:self.send_response(416);self.send_header("Content-Range",f"bytes */{size}");self.end_headers();return
            first,last=match.groups()
            if first:start=int(first);end=min(int(last),size-1) if last else size-1
            elif last:length=min(int(last),size);start=size-length;end=size-1
            else:self.send_response(416);self.send_header("Content-Range",f"bytes */{size}");self.end_headers();return
            if start<0 or start>=size or end<start:self.send_response(416);self.send_header("Content-Range",f"bytes */{size}");self.end_headers();return
            length=end-start+1;self.send_response(206);self.send_header("Content-Type",content_type);self.send_header("Accept-Ranges","bytes");self.send_header("Content-Range",f"bytes {start}-{end}/{size}");self.send_header("Cache-Control","private, no-store");self.send_header("Content-Length",str(length));self.end_headers()
        with path.open("rb") as source:
            source.seek(start);remaining=end-start+1
            while remaining:
                chunk=source.read(min(256*1024,remaining))
                if not chunk:break
                try:self.wfile.write(chunk)
                except (BrokenPipeError,ConnectionResetError):break
                remaining-=len(chunk)
    def serve_range(self,range_header):
        relative=unquote(urlsplit(self.path).path).lstrip("/")
        path=(READER/relative).resolve()
        try: path.relative_to(READER.resolve())
        except ValueError: self.send_error(403); return True
        if not path.is_file(): return False
        match=re.fullmatch(r"bytes=(\d*)-(\d*)",range_header.strip())
        if not match: self.send_error(416); return True
        size=path.stat().st_size; first,last=match.groups()
        if first:
            start=int(first); end=min(int(last),size-1) if last else size-1
        elif last:
            length=min(int(last),size); start=size-length; end=size-1
        else: self.send_error(416); return True
        if start<0 or start>=size or end<start:
            self.send_response(416); self.send_header("Content-Range",f"bytes */{size}"); self.end_headers(); return True
        length=end-start+1
        self.send_response(206)
        self.send_header("Content-Type",mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges","bytes")
        self.send_header("Content-Range",f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length",str(length)); self.end_headers()
        with path.open("rb") as source:
            source.seek(start); remaining=length
            while remaining:
                chunk=source.read(min(256*1024,remaining))
                if not chunk: break
                try: self.wfile.write(chunk)
                except (BrokenPipeError,ConnectionResetError): break
                remaining-=len(chunk)
        return True
    def do_POST(self):
        route=urlsplit(self.path)
        if not self.rate_limit(route.path):return
        if SAAS.enabled and route.path=="/api/payments/alipay/orders":
            if not self.require_saas_user(verified=True) or not self.require_csrf():return
            try:
                item=self.json_body();self.reply(PAYMENTS.create_order(str(self._saas_session["id"]),item.get("productVersionId"),item.get("idempotencyKey")),201)
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"alipay_unavailable","error":str(exc)},503)
            return
        if SAAS.enabled and route.path.startswith("/api/payments/alipay/orders/") and route.path.endswith("/simulate-paid"):
            if not self.require_saas_user(verified=True) or not self.require_csrf():return
            try:
                order_id=unquote(route.path[len("/api/payments/alipay/orders/"):-len("/simulate-paid")].rstrip("/"))
                self.reply(PAYMENTS.simulate_paid(str(self._saas_session["id"]),order_id))
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"alipay_unavailable","error":str(exc)},503)
            return
        if SAAS.enabled and route.path=="/api/commerce/webhooks/mbdpay":
            self.reply({"code":"payment_provider_retired","error":"该支付通知接口已停用。"},410);return
        if SAAS.enabled and route.path=="/api/billing/webhooks/paddle":
            length=int(self.headers.get("Content-Length","0") or 0)
            if length<=0 or length>2*1024*1024:
                self.reply({"code":"invalid_paddle_event","error":"Paddle webhook 请求体无效。"},400);return
            raw_body=self.rfile.read(length)
            try:self.reply(BILLING.handle_webhook(raw_body,self.headers.get("Paddle-Signature","")))
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"billing_unavailable","error":str(exc)},503)
            except Exception:self.reply({"code":"billing_webhook_failed","error":"支付通知处理失败，Paddle 将自动重试。"},500)
            return
        if SAAS.enabled and route.path=="/api/payments/alipay/notify":
            length=int(self.headers.get("Content-Length","0") or 0)
            if length<=0 or length>64*1024:
                self.reply({"code":"invalid_alipay_notify","error":"支付宝通知请求无效。"},400);return
            try:
                values=parse_qs(self.rfile.read(length).decode("utf-8"),keep_blank_values=True)
                PAYMENTS.notify({key:items[-1] for key,items in values.items()})
                self.reply_text("success")
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"alipay_unavailable","error":str(exc)},503)
            except Exception:self.reply({"code":"alipay_notify_failed","error":"支付通知处理失败，请稍后重试。"},500)
            return
        if route.path.startswith("/api/auth/"):
            self.auth_post(route.path); return
        if SAAS.enabled and (route.path=="/api/workspace/imports" or route.path.startswith("/api/workspace/imports/")):
            if not self.require_saas_user(verified=True) or not self.require_csrf():return
            self.workspace_import_post(route);return
        if SAAS.enabled and route.path in {"/api/workspace/vocabulary","/api/workspace/annotations","/api/workspace/activity","/api/workspace/progress","/api/workspace/journey","/api/workspace/learning/plan","/api/workspace/review/start","/api/workspace/review/answer"}:
            if not self.require_saas_user(verified=True) or not self.require_csrf():return
            self.workspace_post(route.path);return
        if SAAS.enabled and route.path in {"/api/word-context","/api/sentence-grammar"}:
            if not self.require_saas_user(verified=True) or not self.require_csrf():return
            self.workspace_ai_post(route.path);return
        if SAAS.enabled and route.path in {"/api/account/deletion","/api/account/deletion/cancel"}:
            if not self.require_saas_user() or not self.require_csrf():return
            self.account_post(route.path);return
        if SAAS.enabled and route.path == "/api/preferences":
            if not self.require_saas_user(verified=True) or not self.require_csrf():return
            try:self.reply({"preferences":SAAS.update_preferences(str(self._saas_session["id"]),self.json_body())})
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"preferences_unavailable","error":str(exc)},503)
            return
        if SAAS.enabled and route.path.startswith("/api/admin/"):
            if not self.require_saas_user() or not self.require_csrf():return
            self.admin_post(route.path);return
        if SAAS.enabled and route.path in {"/api/checkins","/api/rewards/redeem","/api/rewards/activity","/api/rewards/complete-book","/api/member-invites"}:
            if not self.require_saas_user(verified=True) or not self.require_csrf():return
            self.rewards_post(route.path);return
        if SAAS.enabled and (route.path=="/api/library/items" or route.path.startswith("/api/catalog/books/") or route.path=="/api/admin/catalog/books"):
            if not self.require_saas_user(verified=not route.path.startswith("/api/admin/")) or not self.require_csrf():return
            self.catalog_post(route.path);return
        if SAAS.enabled and route.path in {"/api/admin/subscriptions","/api/admin/manual-orders"}:
            if not self.require_saas_user() or not self.require_csrf(): return
            self.membership_post(route.path); return
        if SAAS.enabled and route.path=="/api/membership/requests":
            if not self.require_saas_user(verified=True) or not self.require_csrf():return
            try:
                item=self.json_body();self.reply(MEMBERSHIPS.request_change(str(self._saas_session["id"]),str(item.get("planVersion","")).strip(),str(item.get("note","")or"")),201)
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"membership_unavailable","error":str(exc)},503)
            return
        if SAAS.enabled and route.path=="/api/membership/redeem":
            if not self.require_saas_user(verified=True) or not self.require_csrf():return
            try:
                if not PAYMENTS.public_config()["redemptionEnabled"]:
                    raise SaaSError("redemption_disabled", "兑换码开通当前暂未开放。", 503)
                item=self.json_body()
                self.reply(REDEMPTIONS.redeem(str(self._saas_session["id"]),item.get("code"),item.get("idempotencyKey")))
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"membership_unavailable","error":str(exc)},503)
            return
        if SAAS.enabled and route.path=="/api/membership/change-orders":
            if not self.require_saas_user(verified=True) or not self.require_csrf():return
            try:
                item=self.json_body(); self.reply(MEMBERSHIPS.cancel_change_order(str(self._saas_session["id"]), str(item.get("id", "")).strip()))
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            return
        if SAAS.enabled and route.path=="/api/commerce/orders":
            self.reply({"code":"payment_provider_retired","error":"请通过云猫购买并在拾页兑换。"},410);return
        if SAAS.enabled and route.path in {"/api/billing/checkout","/api/billing/manage"}:
            if not self.require_saas_user(verified=True) or not self.require_csrf():return
            try:
                item=self.json_body() if int(self.headers.get("Content-Length","0") or 0)>0 else {}
                user_id=str(self._saas_session["id"])
                if route.path=="/api/billing/checkout":
                    self.reply(BILLING.create_checkout(user_id,item.get("planVersion"),item.get("billingInterval"),item.get("idempotencyKey")),201);return
                self.reply(BILLING.management_links(user_id));return
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"billing_unavailable","error":str(exc)},503)
            return
        if SAAS.enabled and route.path.startswith("/api/"):
            must_verify=route.path.startswith("/api/import") or route.path in {"/api/word-context","/api/sentence-grammar"}
            if not self.require_saas_user(verified=must_verify): return
            if not self.require_csrf(): return
            if not route.path.startswith("/api/deployment/"):
                self.saas_content_pending(); return
        if route.path.startswith("/api/deployment/"):
            if not self.deployment_allowed():return
            if SAAS.enabled and not self.require_csrf():return
            try:item=self.json_body()
            except Exception:self.reply({"error":"invalid json"},400);return
            try:
                target_id=int(item.get("targetId") or item.get("id") or 0)
                if self.path == "/api/deployment/config":self.reply({"target":deployment_manager.save_target(item,str(item.get("password","")).strip())});return
                if route.path == "/api/deployment/jobs/delete-invalid":
                    audit=(lambda result: ADMIN.record_action(str(self._saas_session["id"]),"deployment_jobs_delete_invalid",payload=result)) if SAAS.enabled else None
                    result=deployment_manager.delete_invalid_jobs(audit=audit)
                    self.reply(result);return
                if not target_id:self.reply({"error":"请选择远程节点"},400);return
                if self.path == "/api/deployment/test":self.reply({"jobId":deployment_manager.start_test(target_id)},202);return
                if self.path == "/api/deployment/deploy":self.reply({"jobId":deployment_manager.start_saas_deploy(target_id,bool(item.get("reinstall")))},202);return
                if self.path in {"/api/deployment/upgrade","/api/deployment/saas-upgrade"}:self.reply({"jobId":deployment_manager.start_saas_upgrade(target_id)},202);return
                if self.path == "/api/deployment/sync":self.reply({"jobId":deployment_manager.start_saas_public_sync(target_id)},202);return
                if self.path == "/api/deployment/uninstall":self.reply({"jobId":deployment_manager.start_uninstall(target_id,str(item.get("confirmName","")).strip())},202);return
                if self.path == "/api/deployment/delete-config":self.reply({"result":deployment_manager.delete_target_config(target_id)});return
                if self.path == "/api/deployment/cleanup":self.reply({"jobId":deployment_manager.start_cleanup(target_id,item.get("retentionDays",30))},202);return
                if self.path == "/api/deployment/rollback":
                    release=str(item.get("releaseId","")).strip()
                    if not release.startswith("code-"):self.reply({"error":"invalid release"},400);return
                    self.reply({"jobId":deployment_manager.start_rollback(target_id,release)},202);return
            except Exception as exc:self.reply({"error":str(exc)},400);return
            self.send_error(404);return
        if RUNTIME_MODE=="reader" and route.path.startswith("/api/import"):
            self.reply({"error":"远程阅读节点不允许执行导入"},403);return
        if route.path.startswith("/api/books/") and route.path.endswith("/delete"): self.remove_book(); return
        if route.path == "/api/import/jobs/cancel-active": self.cancel_active_imports(); return
        if route.path == "/api/import/youtube/info": self.youtube_info(); return
        if route.path == "/api/import/youtube": self.start_youtube_import(); return
        if route.path == "/api/import/video/init": self.init_video_upload(); return
        if route.path.startswith("/api/import/video/upload/"): self.upload_video_part(); return
        if route.path.startswith("/api/import/video/complete/"): self.complete_video_upload(); return
        if route.path == "/api/activity": self.record_activity(); return
        if route.path == "/api/vocabulary": self.create_vocabulary(); return
        if route.path.startswith("/api/vocabulary/"): self.change_vocabulary(); return
        if route.path == "/api/word-annotation": self.save_annotation(); return
        if route.path == "/api/preferences": self.update_preferences(); return
        if route.path == "/api/import/batch": self.start_batch_import(); return
        if route.path == "/api/import": self.start_import(); return
        if route.path == "/api/settings": self.update_settings(); return
        if route.path == "/api/word-context": self.word_context(); return
        if route.path == "/api/sentence-grammar": self.sentence_grammar(); return
        if route.path != "/api/transcribe": self.send_error(404); return
        length=int(self.headers.get("Content-Length","0"))
        if length<=0 or length>20*1024*1024: self.send_error(413); return
        suffix=".webm" if "webm" in self.headers.get("Content-Type","") else ".audio"
        try:
            with tempfile.TemporaryDirectory(prefix="shiyue-whisper-") as tmp:
                source=Path(tmp)/("recording"+suffix); wav=Path(tmp)/"recording.wav"; prefix=Path(tmp)/"result"
                source.write_bytes(self.rfile.read(length))
                subprocess.run(["ffmpeg","-y","-v","error","-i",str(source),"-ar","16000","-ac","1",str(wav)],check=True,timeout=30)
                subprocess.run([str(CLI),"-m",str(MODEL),"-f",str(wav),"-l","en","-t","4","-p","2","-ng","-oj","-of",str(prefix),"-np"],
                               check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=120)
                data=json.loads((prefix.with_suffix(".json")).read_text())
                text=" ".join(x.get("text","").strip() for x in data.get("transcription",[])).strip()
                self.reply({"text":text,"engine":"whisper.cpp","model":"base.en"})
        except Exception as exc:
            self.reply({"error":str(exc)},500)
    def do_DELETE(self):
        route=urlsplit(self.path)
        if SAAS.enabled and route.path.startswith("/api/membership/change-orders/"):
            if not self.require_saas_user(verified=True) or not self.require_csrf():return
            try:
                change_id=unquote(route.path.rsplit("/",1)[1])
                self.reply(MEMBERSHIPS.cancel_change_order(str(self._saas_session["id"]), change_id))
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"membership_unavailable","error":str(exc)},503)
            return
        if SAAS.enabled and route.path.startswith("/api/admin/invitation-batches/") and route.path.endswith("/invitations"):
            if not self.require_saas_user() or not self.require_csrf():return
            if not self._saas_session.get("is_admin"):
                self.reply({"code":"admin_required","error":"该操作仅允许管理员执行。"},403);return
            batch_id=unquote(route.path[len("/api/admin/invitation-batches/"):-len("/invitations")].rstrip("/"))
            try:
                item=self.json_body() if int(self.headers.get("Content-Length","0") or 0)>0 else {}
                self.reply(ADMIN.delete_unused_invitations(str(self._saas_session["id"]),batch_id,item.get("invitationIds",[])))
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"admin_unavailable","error":str(exc)},503)
            return
        if SAAS.enabled and route.path.startswith("/api/admin/users/") and "/devices/" in route.path:
            if not self.require_saas_user() or not self.require_csrf():return
            if not self._saas_session.get("is_admin"):
                self.reply({"code":"admin_required","error":"该操作仅允许管理员执行。"},403);return
            prefix="/api/admin/users/";user_id,device_id=route.path[len(prefix):].split("/devices/",1)
            try:self.reply(ADMIN.revoke_device(str(self._saas_session["id"]),unquote(user_id),unquote(device_id),"运营后台撤销异常设备"))
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"admin_unavailable","error":str(exc)},503)
            return
        if SAAS.enabled and route.path.startswith("/api/admin/users/") and route.path.count("/")==4:
            if not self.require_saas_user() or not self.require_csrf():return
            if not self._saas_session.get("is_admin"):
                self.reply({"code":"admin_required","error":"该操作仅允许管理员执行。"},403);return
            user_id=unquote(route.path[len("/api/admin/users/"):])
            try:self.reply(ADMIN.delete_unverified_user(str(self._saas_session["id"]),user_id))
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"admin_unavailable","error":str(exc)},503)
            return
        if SAAS.enabled and route.path.startswith("/api/media/"):
            if not self.require_saas_user() or not self.require_csrf():return
            self.reply({"code":"book_deletion_required","error":"请在我的书架或运营后台内容管理中永久删除读物。"},409)
            return
        if SAAS.enabled and route.path.startswith("/api/library/items/"):
            if not self.require_saas_user(verified=True) or not self.require_csrf():return
            try:self.reply(CATALOG.remove(str(self._saas_session["id"]),unquote(route.path.rsplit("/",1)[1])))
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"saas_unavailable","error":str(exc)},503)
            return
        if SAAS.enabled and route.path.startswith("/api/workspace/books/"):
            if not self.require_saas_user(verified=True) or not self.require_csrf():return
            try:
                item=self.json_body() if int(self.headers.get("Content-Length","0") or 0)>0 else {}
                self.reply(WORKSPACE.delete_book(str(self._saas_session["id"]),unquote(route.path.rsplit("/",1)[1]),str(item.get("confirmTitle","") or "")))
            except SaaSError as exc:self.reply(exc.payload(),exc.status)
            except SaaSConfigurationError as exc:self.reply({"code":"workspace_unavailable","error":str(exc)},503)
            return
        if not route.path.startswith("/api/auth/devices/"):
            self.send_error(404); return
        if not SAAS.enabled:
            self.reply({"error":"SaaS 账号功能尚未启用"},404); return
        if not self.require_saas_user() or not self.require_csrf(): return
        device_id=unquote(route.path.rsplit("/",1)[1])
        try:
            SAAS.revoke_device(str(self._saas_session["id"]),device_id)
            self.reply({"status":"revoked"})
        except SaaSError as exc:
            self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:
            self.reply({"code":"saas_unavailable","error":str(exc)},503)
    def cookie_value(self,name):
        try:
            cookies=SimpleCookie();cookies.load(self.headers.get("Cookie","") or "")
            return cookies[name].value if name in cookies else ""
        except (KeyError,ValueError):
            return ""
    def session_cookie_headers(self,session_token="",csrf_token="",clear=False):
        secure="; Secure" if bool(os.environ.get("READER_TLS_CERT")) or os.environ.get("APP_BASE_URL","").startswith("https://") else ""
        if clear:
            return [
                ("Set-Cookie",f"shiyue_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax{secure}"),
                ("Set-Cookie",f"shiyue_csrf=; Path=/; Max-Age=0; SameSite=Lax{secure}"),
            ]
        return [
            ("Set-Cookie",f"shiyue_session={session_token}; Path=/; Max-Age={30*24*60*60}; HttpOnly; SameSite=Lax{secure}"),
            ("Set-Cookie",f"shiyue_csrf={csrf_token}; Path=/; Max-Age={30*24*60*60}; SameSite=Lax{secure}"),
        ]
    def require_saas_user(self,verified=False):
        try:
            session=SAAS.authenticate(self.cookie_value("shiyue_session"))
        except SaaSConfigurationError as exc:
            self.reply({"code":"saas_unavailable","error":str(exc)},503);return False
        if not session:
            self.reply({"code":"authentication_required","error":"请先登录。"},401);return False
        if verified and not session.get("email_verified_at"):
            self.reply({"code":"email_not_verified","error":"请先验证邮箱后再使用该功能。"},403);return False
        self._saas_session=session
        return True
    def require_csrf(self):
        try:
            SAAS.assert_csrf(self._saas_session,self.headers.get("X-CSRF-Token"))
            return True
        except SaaSError as exc:
            self.reply(exc.payload(),exc.status);return False
    def saas_content_pending(self):
        self.reply({"code":"saas_content_migration_pending","error":"多租户内容工作区尚未切换完成；为保护现有私人数据，此接口暂不可用。"},503)
    def auth_get(self,path):
        if not SAAS.enabled:
            self.reply({"code":"saas_disabled","error":"SaaS 账号功能尚未启用。"},404);return
        if path=="/api/auth/me":
            if not self.require_saas_user():return
            headers=()
            raw_session=self.cookie_value("shiyue_session")
            supplied=self.cookie_value("shiyue_csrf")
            stored=str(self._saas_session.get("csrf_hash", ""))
            if not supplied or not hmac.compare_digest(stored,token_hash(supplied)):
                try:
                    rotated_session,csrf=SAAS.recover_csrf(str(self._saas_session["session_id"]),raw_session)
                    headers=tuple(self.session_cookie_headers(rotated_session,csrf))
                except SaaSError as exc:
                    self.reply(exc.payload(),exc.status);return
            self.reply({"user":{**SAAS.public_user(self._saas_session),"canManagePlatform":self.can_manage_platform()}},extra_headers=headers)
            return
        if path=="/api/auth/devices":
            if not self.require_saas_user():return
            try:self.reply({"devices":SAAS.devices(str(self._saas_session["id"]),str(self._saas_session.get("device_id") or ""))})
            except SaaSConfigurationError as exc:self.reply({"code":"saas_unavailable","error":str(exc)},503)
            return
        self.reply({"error":"not found"},404)
    def debug_browser_login(self,route):
        secret=os.environ.get("SHIYUE_BROWSER_AUDIT_SECRET","");email=os.environ.get("SHIYUE_BROWSER_AUDIT_EMAIL","");password=os.environ.get("SHIYUE_BROWSER_AUDIT_PASSWORD","")
        query=parse_qs(route.query);supplied=(query.get("token")or[""])[0];screen=(query.get("screen")or["catalog"])[0]
        allowed={"catalog","library","my-library","workspace","stats","vocab","rewards","membership","admin","platform","settings","reader"}
        if not secret or not email or not password or supplied!=secret or self.client_address[0] not in {"127.0.0.1","::1"}:self.reply({"error":"not found"},404);return
        try:
            device_key=(query.get("device")or["browser-audit-device"])[0]
            result=SAAS.login(email,password,device_key,self.headers.get("User-Agent","") or "browser-audit",self.client_address[0]);params={"screen":screen if screen in allowed else "catalog"}
            for key in ("reader","id","book"):
                value=(query.get(key)or[""])[0]
                if value:params[key]=value
            location="/?"+urlencode(params)
            self.send_response(302);self.send_header("Location",location)
            for key,value in self.session_cookie_headers(result["sessionToken"],result["csrfToken"]):self.send_header(key,value)
            self.send_header("Content-Length","0");self.end_headers()
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:self.reply({"code":"saas_unavailable","error":str(exc)},503)
    def auth_post(self,path):
        if not SAAS.enabled:
            self.reply({"code":"saas_disabled","error":"SaaS 账号功能尚未启用。"},404);return
        try:item=self.json_body()
        except Exception:self.reply({"code":"invalid_payload","error":"请求数据无效。"},400);return
        try:
            if path=="/api/auth/register":
                result=SAAS.register(item.get("email"),item.get("password"),item.get("invitationCode",item.get("invitation_code")),item.get("displayName",""),self.client_address[0])
                self.reply(result,201);return
            if path=="/api/auth/verify-email":
                self.reply(SAAS.verify_email(item.get("token")));return
            if path=="/api/auth/login":
                device_id=self.headers.get("X-Device-Id","") or item.get("deviceId","")
                result=SAAS.login(item.get("email"),item.get("password"),device_id,self.headers.get("User-Agent",""),self.client_address[0])
                self.reply({"user":result["user"]},extra_headers=self.session_cookie_headers(result["sessionToken"],result["csrfToken"]));return
            if path=="/api/auth/login/replace-device":
                device_id=self.headers.get("X-Device-Id","") or item.get("deviceId","")
                replace_device_id=str(item.get("replaceDeviceId","")).strip()
                if not replace_device_id:
                    raise SaaSError("invalid_device", "请选择要解除的设备。", 400)
                result=SAAS.login(item.get("email"),item.get("password"),device_id,self.headers.get("User-Agent",""),self.client_address[0],replace_device_id)
                self.reply({"user":result["user"]},extra_headers=self.session_cookie_headers(result["sessionToken"],result["csrfToken"]));return
            if path=="/api/auth/logout":
                if not self.require_saas_user() or not self.require_csrf():return
                SAAS.logout(self._saas_session)
                self.reply({"status":"logged_out"},extra_headers=self.session_cookie_headers(clear=True));return
            if path=="/api/auth/forgot-password":
                SAAS.forgot_password(item.get("email"))
                self.reply({"status":"accepted"});return
            if path=="/api/auth/reset-password":
                SAAS.reset_password(item.get("token"),item.get("password"))
                self.reply({"status":"password_reset"});return
            self.reply({"error":"not found"},404)
        except SaaSError as exc:
            self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:
            self.reply({"code":"saas_unavailable","error":str(exc)},503)
    def membership_get(self,path):
        try:
            user_id=str(self._saas_session["id"])
            if path=="/api/membership": self.reply(MEMBERSHIPS.membership(user_id));return
            if path=="/api/membership/usage": self.reply(MEMBERSHIPS.usage(user_id));return
            if path=="/api/membership/orders": self.reply({"orders":MEMBERSHIPS.orders(user_id)});return
            if path=="/api/membership/change-orders": self.reply({"changeOrders":MEMBERSHIPS.change_orders(user_id)});return
            if path=="/api/membership/change-preview":
                target=(parse_qs(urlsplit(self.path).query).get("targetPlan") or [""])[0]
                self.reply(MEMBERSHIPS.change_preview(user_id, unquote(target)));return
            if path=="/api/admin/commerce/redemption-batches":
                if not self._saas_session.get("is_admin"):
                    self.reply({"code":"admin_required","error":"该操作仅允许管理员执行。"},403);return
                self.reply(REDEMPTIONS.batches(parse_qs(urlsplit(self.path).query).get("limit",[100])[0]));return
            if path=="/api/membership/plans":self.reply(MEMBERSHIPS.plans());return
            if path=="/api/membership/requests":self.reply(MEMBERSHIPS.change_requests(user_id));return
            self.reply({"error":"not found"},404)
        except SaaSError as exc:
            self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:
            self.reply({"code":"saas_unavailable","error":str(exc)},503)
    def optional_saas_user(self):
        try:
            session=SAAS.authenticate(self.cookie_value("shiyue_session"))
            return str(session["id"]) if session else None
        except SaaSConfigurationError:
            return None
    def catalog_get(self,route):
        try:
            user_id=self.optional_saas_user();query=parse_qs(route.query)
            if route.path=="/api/catalog":
                self.reply(CATALOG.catalog(user_id,(query.get("q")or[""])[0],(query.get("series")or[""])[0],(query.get("level")or[""])[0],(query.get("resourceType")or[""])[0],(query.get("tag")or[""])[0],(query.get("limit")or[60])[0]));return
            if route.path=="/api/catalog/series":self.reply(CATALOG.series());return
            if route.path=="/api/catalog/tags":self.reply(CATALOG.tags());return
            if route.path.startswith("/api/catalog/books/"):
                self.reply(CATALOG.detail(unquote(route.path.rsplit("/",1)[1]),user_id));return
            self.reply({"error":"not found"},404)
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except (SaaSConfigurationError,ValueError) as exc:self.reply({"code":"saas_unavailable","error":str(exc)},503)
    def catalog_library_get(self):
        try:self.reply(CATALOG.library(str(self._saas_session["id"])))
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:self.reply({"code":"saas_unavailable","error":str(exc)},503)
    def catalog_reader_get(self,path):
        try:
            book_id=unquote(path[len("/api/catalog/books/"):-len("/reader")].rstrip("/"))
            trial=parse_qs(urlsplit(self.path).query).get("trial",["0"])[0]=="1"
            self.reply(CATALOG.reader(str(self._saas_session["id"]),book_id,trial=trial))
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:self.reply({"code":"saas_unavailable","error":str(exc)},503)
    def catalog_admin_get(self):
        if not self._saas_session.get("is_admin"):
            self.reply({"code":"admin_required","error":"该操作仅允许管理员执行。"},403);return
        try:self.reply(CATALOG.review_sources())
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:self.reply({"code":"saas_unavailable","error":str(exc)},503)
    def admin_required(self):
        if self._saas_session.get("is_admin"):return True
        self.reply({"code":"admin_required","error":"该操作仅允许管理员执行。"},403);return False
    def admin_get(self,route):
        if not self.admin_required():return
        if route.path=="/api/admin/content-imports" or route.path.startswith("/api/admin/content-imports/"):
            self.workspace_import_get(route,OFFICIAL_IMPORTS,"/api/admin/content-imports");return
        if route.path=="/api/admin/platform-config" and not self.deployment_allowed():return
        try:
            path,query=route.path,parse_qs(route.query)
            if path=="/api/admin/dashboard":self.reply(ADMIN.dashboard());return
            if path=="/api/admin/journey-report":self.reply(JOURNEY.report((query.get("days")or[30])[0]));return
            if path=="/api/admin/users":self.reply(ADMIN.users((query.get("q")or[""])[0],(query.get("limit")or[100])[0]));return
            if path.startswith("/api/admin/users/"):
                self.reply(ADMIN.user_detail(unquote(path.rsplit("/",1)[1])));return
            if path=="/api/admin/invitations":self.reply(ADMIN.invitations((query.get("limit")or[100])[0],(query.get("q")or[""])[0],(query.get("offset")or[0])[0]));return
            if path=="/api/admin/invitation-batches":self.reply(ADMIN.invitation_batches((query.get("limit")or[50])[0],(query.get("q")or[""])[0],(query.get("offset")or[0])[0]));return
            if path.startswith("/api/admin/invitation-batches/"):self.reply(ADMIN.invitation_batch_detail(unquote(path.rsplit("/",1)[1])));return
            if path=="/api/admin/plan-versions":self.reply(ADMIN.plan_versions());return
            if path=="/api/admin/commerce/products":self.reply(COMMERCE.admin_catalog());return
            if path=="/api/admin/payment-config":self.reply(PAYMENTS.admin_config());return
            if path=="/api/admin/payment-orders":self.reply(PAYMENTS.list_orders((query.get("q")or[""])[0],(query.get("status")or[""])[0],(query.get("limit")or[20])[0],(query.get("offset")or[0])[0]));return
            if path.startswith("/api/admin/payment-orders/"):
                self.reply(PAYMENTS.admin_order_detail(unquote(path.rsplit("/",1)[1])));return
            if path=="/api/admin/commerce/redemption-records":self.reply(REDEMPTIONS.admin_records((query.get("q")or[""])[0],(query.get("status")or[""])[0],(query.get("limit")or[20])[0],(query.get("offset")or[0])[0]));return
            if path=="/api/admin/commerce/entitlements":self.reply(COMMERCE.entitlement_catalog());return
            if path=="/api/admin/catalog/sources":self.reply(CATALOG.review_sources());return
            if path=="/api/admin/audit":self.reply(ADMIN.audit((query.get("limit")or[20])[0],(query.get("q")or[""])[0],(query.get("action")or[""])[0],(query.get("offset")or[0])[0]));return
            if path=="/api/admin/platform-config":self.reply(ADMIN.platform_config());return
            if path=="/api/admin/exports/summary":self.reply(ADMIN.export_summary());return
            if path=="/api/admin/media-assets":self.reply(MEDIA.user_storage((query.get("ownerId")or[""])[0],(query.get("limit")or[20])[0],(query.get("offset")or[0])[0]));return
            self.reply({"error":"not found"},404)
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except (SaaSConfigurationError,ValueError) as exc:self.reply({"code":"admin_unavailable","error":str(exc)},503)
    def admin_post(self,path):
        if not self.admin_required():return
        if path=="/api/admin/content-imports" or path.startswith("/api/admin/content-imports/"):
            self.workspace_import_post(urlsplit(path),OFFICIAL_IMPORTS,"/api/admin/content-imports");return
        if path=="/api/admin/platform-config" and not self.deployment_allowed():return
        try:item=self.json_body()
        except Exception:self.reply({"code":"invalid_payload","error":"请求数据无效。"},400);return
        if not isinstance(item,dict):self.reply({"code":"invalid_payload","error":"请求数据无效。"},400);return
        try:
            actor_id=str(self._saas_session["id"])
            if path=="/api/admin/catalog/delete":
                self.reply(CATALOG.delete_book(actor_id,str(item.get("sourceBookId","")).strip(),str(item.get("confirmTitle","")).strip()));return
            if path=="/api/admin/catalog/books":
                self.reply(CATALOG.review(actor_id,str(item.get("sourceBookId","")).strip(),str(item.get("rightsStatus","")).strip(),str(item.get("publicationStatus","")).strip(),item));return
            if path=="/api/admin/invitations":
                self.reply(ADMIN.create_invitations(actor_id,str(item.get("code","")).strip(),item.get("maxUses",1),item.get("count",1),item.get("expiresAt"),str(item.get("note","")or""),str(item.get("channel","")or"")),201);return
            if path=="/api/admin/platform-config":
                self.reply(ADMIN.update_platform_config(actor_id,item));return
            if path=="/api/admin/payment-config":
                self.reply(PAYMENTS.update_config(actor_id,item));return
            if path.startswith("/api/admin/payment-orders/") and path.endswith("/refund"):
                order_id=unquote(path[len("/api/admin/payment-orders/"):-len("/refund")].rstrip("/"));self.reply(PAYMENTS.refund(actor_id,order_id,str(item.get("reason", ""))));return
            if path.startswith("/api/admin/payment-orders/") and path.endswith("/sync-refund"):
                order_id=unquote(path[len("/api/admin/payment-orders/"):-len("/sync-refund")].rstrip("/"));self.reply(PAYMENTS.sync_refund(actor_id,order_id));return
            if path=="/api/admin/quotas/adjust":
                key=str(item.get("idempotencyKey","")).strip() or hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()
                self.reply(ADMIN.adjust_quota(actor_id,str(item.get("userId","")).strip(),str(item.get("feature","")).strip(),item.get("quantity"),str(item.get("reason","")or""),key));return
            if path=="/api/admin/member-invite-allowances":
                self.reply(ADMIN.grant_invite_allowance(actor_id,str(item.get("userId","")).strip(),item.get("quantity"),str(item.get("reason","")or""),item.get("expiresAt"),item.get("idempotencyKey")),201);return
            if path=="/api/admin/plan-versions":
                self.reply(ADMIN.create_plan_version(actor_id,item.get("id"),item.get("planSlug"),item.get("name"),item.get("rank"),item.get("periodDays"),item.get("quotas"),item.get("pricing")),201);return
            if path=="/api/admin/media-assets":
                result=MEDIA.register(actor_id,str(item.get("ownerId","")).strip(),str(item.get("scope","")).strip(),str(item.get("storagePath","")).strip(),str(item.get("kind","")or"media"),str(item.get("contentType","")or""),str(item.get("catalogBookId","")or"") or None,str(item.get("contentBookId","")or"") or None,item.get("variants") or []);ADMIN.record_action(actor_id,"media_asset_registered",str(item.get("ownerId","")).strip(),str(item.get("note","")or""),{"assetId":result["id"],"scope":result["scope"],"bytes":result["totalBytes"]});self.reply(result,201);return
            if path=="/api/admin/media-assets/purge":
                result=MEDIA.purge_deleted(ROOT/".local"/"media-trash",bool(item.get("dryRun",True)));ADMIN.record_action(actor_id,"media_purge",None,"",{"dryRun":result["dryRun"],"files":len(result["files"])});self.reply(result);return
            if path=="/api/admin/account-deletions/cleanup":
                result=ACCOUNTS.cleanup_due_deletions();ADMIN.record_action(actor_id,"account_deletion_cleanup",None,"",result);self.reply(result);return
            if path=="/api/admin/manual-orders":
                result=MEMBERSHIPS.create_manual_order(actor_id,str(item.get("userId","")).strip(),str(item.get("planVersion","")).strip(),item.get("startsAt"),item.get("endsAt"),str(item.get("note","")or""),item.get("amountCents",0),item.get("idempotencyKey"));REWARDS.on_first_paid(str(item.get("userId","")).strip());ADMIN.record_action(actor_id,"manual_order_created",str(item.get("userId","")).strip(),str(item.get("note","")or""),{"orderId":result["order"]["id"],"plan":item.get("planVersion")});self.reply(result,201);return
            if path=="/api/admin/subscriptions":
                action=str(item.get("action","create")).strip()
                if action=="create":
                    result=MEMBERSHIPS.create_manual_order(actor_id,str(item.get("userId","")).strip(),str(item.get("planVersion","")).strip(),item.get("startsAt"),item.get("endsAt"),str(item.get("note","")or""),item.get("amountCents",0),item.get("idempotencyKey"));REWARDS.on_first_paid(str(item.get("userId","")).strip());ADMIN.record_action(actor_id,"manual_subscription_created",str(item.get("userId","")).strip(),str(item.get("note","")or""),{"subscriptionId":result["subscription"]["id"]});self.reply(result,201);return
                result=MEMBERSHIPS.update_subscription(actor_id,str(item.get("subscriptionId","")).strip(),action,item.get("endsAt"),str(item.get("note","")or""),item.get("idempotencyKey"));ADMIN.record_action(actor_id,f"subscription_{action}",None,str(item.get("note","")or""),{"subscriptionId":item.get("subscriptionId")});self.reply(result);return
            if path=="/api/admin/commerce/products":
                self.reply(COMMERCE.create_product(actor_id,item.get("slug"),item.get("family"),item.get("displayOrder",100)),201);return
            if path=="/api/admin/invitations/delete-expired":
                self.reply(ADMIN.delete_expired_invitations(actor_id));return
            if path=="/api/admin/commerce/redemption-batches":
                self.reply(REDEMPTIONS.generate(actor_id,item.get("productVersionId"),item.get("count"),item.get("note","")),201);return
            if path=="/api/admin/commerce/redemption-codes/revoke":
                self.reply(REDEMPTIONS.revoke(actor_id,item.get("code"),item.get("reason")));return
            if path=="/api/admin/commerce/configured-benefits":
                self.reply(COMMERCE.create_configured_benefit(actor_id,item),201);return
            if path.startswith("/api/admin/commerce/configured-benefits/"):
                benefit_id=unquote(path.rsplit("/",1)[1]);self.reply(COMMERCE.update_configured_benefit(actor_id,benefit_id,item));return
            if path.startswith("/api/admin/commerce/products/") and path.endswith("/versions"):
                product_id=unquote(path[len("/api/admin/commerce/products/"):-len("/versions")].rstrip("/"));self.reply(COMMERCE.create_version(actor_id,product_id,item),201);return
            if path.startswith("/api/admin/commerce/products/") and path.endswith("/status"):
                product_id=unquote(path[len("/api/admin/commerce/products/"):-len("/status")].rstrip("/"));self.reply(COMMERCE.set_product_active(actor_id,product_id,bool(item.get("active"))));return
            if path.startswith("/api/admin/commerce/versions/") and path.endswith("/publish"):
                version_id=unquote(path[len("/api/admin/commerce/versions/"):-len("/publish")].rstrip("/"));self.reply(COMMERCE.publish_version(actor_id,version_id));return
            if path.startswith("/api/admin/commerce/versions/") and path.endswith("/purchase-link"):
                version_id=unquote(path[len("/api/admin/commerce/versions/"):-len("/purchase-link")].rstrip("/"));self.reply(COMMERCE.update_draft_purchase_url(actor_id,version_id,item.get("purchaseUrl")));return
            if path.startswith("/api/admin/users/") and path.endswith("/status"):
                user_id=unquote(path[len("/api/admin/users/"):-len("/status")].rstrip("/"));self.reply(ADMIN.set_user_status(actor_id,user_id,str(item.get("status","")).strip(),str(item.get("reason","")or"")));return
            if path.startswith("/api/admin/users/") and path.endswith("/verify"):
                user_id=unquote(path[len("/api/admin/users/"):-len("/verify")].rstrip("/"));self.reply(ADMIN.verify_user(actor_id,user_id));return
            if path.startswith("/api/admin/commerce/products/") and path.endswith("/delete"):
                product_id=unquote(path[len("/api/admin/commerce/products/"):-len("/delete")].rstrip("/"));self.reply(COMMERCE.delete_unlisted_product(actor_id,product_id));return
            self.reply({"error":"not found"},404)
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:self.reply({"code":"admin_unavailable","error":str(exc)},503)
    def media_get(self,route):
        try:
            asset_id=unquote(route.path.rsplit("/",1)[1]);variant=(parse_qs(route.query).get("variant")or[None])[0]
            trial_book=(parse_qs(route.query).get('trialBook')or[''])[0]
            result=MEDIA.trial_stream(str(self._saas_session["id"]),asset_id,trial_book,variant) if trial_book else MEDIA.stream(str(self._saas_session["id"]),asset_id,variant)
            self.serve_media_file(result["path"],result["target"]["content_type"],self.headers.get("Range","") or "")
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:self.reply({"code":"media_unavailable","error":str(exc)},503)
    def account_get(self,path):
        try:
            if path=="/api/account/export":self.reply(ACCOUNTS.export(str(self._saas_session["id"])),cache_control="private, no-store");return
            if path=="/api/account/deletion-status":self.reply(ACCOUNTS.deletion_status(str(self._saas_session["id"])));return
            self.reply({"error":"not found"},404)
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:self.reply({"code":"account_unavailable","error":str(exc)},503)
    def account_post(self,path):
        try:item=self.json_body()
        except Exception:self.reply({"code":"invalid_payload","error":"请求数据无效。"},400);return
        if not isinstance(item,dict):self.reply({"code":"invalid_payload","error":"请求数据无效。"},400);return
        try:
            user_id=str(self._saas_session["id"])
            if path=="/api/account/deletion":self.reply(ACCOUNTS.request_deletion(user_id,str(item.get("reason","")or"")));return
            if path=="/api/account/deletion/cancel":self.reply(ACCOUNTS.cancel_deletion(user_id));return
            self.reply({"error":"not found"},404)
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:self.reply({"code":"account_unavailable","error":str(exc)},503)
    def workspace_get(self,route):
        try:
            user_id=str(self._saas_session["id"]);path,query=route.path,parse_qs(route.query)
            if path=="/api/workspace/books":self.reply(WORKSPACE.list_books(user_id));return
            if path.startswith("/api/workspace/books/") and path.endswith("/reader"):
                book_id=unquote(path[len("/api/workspace/books/"):-len("/reader")].rstrip("/"));self.reply(WORKSPACE.reader(user_id,book_id));return
            if path=="/api/workspace/vocabulary":self.reply(WORKSPACE.vocabulary(user_id,(query.get("bookId")or[""])[0]));return
            if path=="/api/workspace/annotations":self.reply(WORKSPACE.annotations(user_id,(query.get("bookId")or[""])[0]));return
            if path=="/api/workspace/learning-days":self.reply(WORKSPACE.learning_days(user_id,(query.get("limit")or[365])[0]));return
            if path=="/api/workspace/journey":self.reply(JOURNEY.state(user_id));return
            if path=="/api/workspace/review":self.reply(REVIEW.state(user_id));return
            if path=="/api/workspace/learning":self.reply(LEARNING.state(user_id));return
            self.reply({"error":"not found"},404)
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except (SaaSConfigurationError,ValueError) as exc:self.reply({"code":"workspace_unavailable","error":str(exc)},503)
    def workspace_post(self,path):
        try:item=self.json_body()
        except Exception:self.reply({"code":"invalid_payload","error":"请求数据无效。"},400);return
        if not isinstance(item,dict):self.reply({"code":"invalid_payload","error":"请求数据无效。"},400);return
        try:
            user_id=str(self._saas_session["id"])
            if path=="/api/workspace/journey":self.reply(JOURNEY.update(user_id,item));return
            if path=="/api/workspace/learning/plan":self.reply(LEARNING.update_plan(user_id,item));return
            if path=="/api/workspace/review/start":self.reply(REVIEW.start(user_id,item));return
            if path=="/api/workspace/review/answer":
                result=REVIEW.answer(user_id,item)
                if item.get('rating')!='skip':
                    try:result['reward']=REWARDS.activity(user_id,0,0,1,f"review:{item.get('sessionId')}:{item.get('step')}")
                    except SaaSError:result['rewardDeferred']=True
                self.reply(result);return
            if path=="/api/workspace/vocabulary":self.reply(WORKSPACE.save_vocabulary(user_id,str(item.get("bookId","")).strip(),str(item.get("sentenceId","")).strip(),item.get("wordIndex"),item.get("payload")),201);return
            if path=="/api/workspace/annotations":self.reply(WORKSPACE.annotate(user_id,str(item.get("bookId","")).strip(),str(item.get("sentenceId","")).strip(),item.get("wordIndex"),item.get("payload")));return
            if path=="/api/workspace/progress":self.reply(WORKSPACE.save_progress(user_id,str(item.get("bookId","")).strip(),str(item.get("lastSentenceId","")).strip(),item.get("completed",False)));return
            if path=="/api/workspace/activity":
                result=WORKSPACE.activity(user_id,str(item.get("bookId","")).strip(),item.get("readingSeconds",0),item.get("sentences",0),str(item.get("lastSentenceId","")or""),str(item.get("idempotencyKey","")).strip(),item.get("lookups",0),item.get("reviews",0),item.get("shadowAttempts",0),item.get("sessions",0))
                try:result["reward"]=REWARDS.activity(user_id,item.get("readingSeconds",0),item.get("sentences",0),item.get("reviews",0),str(item.get("idempotencyKey","")).strip())
                except SaaSError:result["rewardDeferred"]=True
                self.reply(result);return
            self.reply({"error":"not found"},404)
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:self.reply({"code":"workspace_unavailable","error":str(exc)},503)
    def workspace_ai_post(self,path):
        try:item=self.json_body()
        except Exception:self.reply({"code":"invalid_payload","error":"请求数据无效。"},400);return
        if not isinstance(item,dict):self.reply({"code":"invalid_payload","error":"请求数据无效。"},400);return
        try:
            user_id=str(self._saas_session["id"]);book_id=str(item.get("bookId","")).strip();sentence_id=str(item.get("sentenceId","")).strip()
            if path=="/api/word-context":self.reply(WORKSPACE_AI.context(user_id,book_id,sentence_id,item.get("wordIndex"),item.get("word")));return
            if path=="/api/sentence-grammar":self.reply(WORKSPACE_AI.grammar(user_id,book_id,sentence_id));return
            self.reply({"error":"not found"},404)
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:self.reply({"code":"workspace_ai_unavailable","error":str(exc)},503)
    def workspace_import_get(self,route,service=None,base="/api/workspace/imports"):
        service=service or WORKSPACE_IMPORTS
        try:
            user_id=str(self._saas_session["id"]);path=route.path
            if path==base:
                query=parse_qs(route.query)
                self.reply(service.list(user_id,(query.get("limit")or[100])[0],(query.get("page")or[1])[0]));return
            if path==base+"/match-audio":
                query=parse_qs(route.query);self.reply(service.match_audio(user_id,(query.get("filename")or[""])[0]));return
            task_id=unquote(path.rsplit("/",1)[1]);tasks=service.list(user_id,200)["tasks"];task=next((item for item in tasks if item["id"]==task_id),None)
            self.reply({"task":task} if task else {"code":"import_task_not_found","error":"导入任务不存在或你无权访问。"},200 if task else 404);return
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except (SaaSConfigurationError,ValueError) as exc:self.reply({"code":"workspace_unavailable","error":str(exc)},503)
    def workspace_import_post(self,route,service=None,base="/api/workspace/imports"):
        service=service or WORKSPACE_IMPORTS
        path,user_id=route.path,str(self._saas_session["id"])
        try:
            if path.endswith('/upload-audio'):
                task_id=unquote(path[len(base+'/'):-len('/upload-audio')].rstrip('/'));length=int(self.headers.get('Content-Length','0'))
                if length<=0 or length>2*1024*1024*1024:raise SaaSError('upload_too_large','MP3 文件大小无效。',413)
                self.reply({'task':service.upload_audio(user_id,task_id,self.headers.get('X-Upload-Filename',''),self.rfile.read(length))});return
            if path.endswith("/upload"):
                task_id=unquote(path[len(base+"/"):-len("/upload")].rstrip("/"));length=int(self.headers.get("Content-Length","0"))
                if length<=0 or length>20*1024*1024*1024:raise SaaSError("upload_too_large","上传文件大小无效。",413)
                filename=self.headers.get("X-Upload-Filename","") or "source"
                data=self.rfile.read(length)
                self.reply({"task":service.upload(user_id,task_id,filename,data,self.headers.get("Content-Type","") or "application/octet-stream")});return
            try:item=self.json_body()
            except Exception:raise SaaSError("invalid_payload","请求数据无效。",400)
            if not isinstance(item,dict):raise SaaSError("invalid_payload","请求数据无效。",400)
            if path==base+"/delete-invalid":
                self.reply(service.delete_invalid(user_id));return
            if path==base:
                result=service.create(user_id,str(item.get("kind","")).strip(),str(item.get("title","")or""),str(item.get("filename","")or""),str(item.get("idempotencyKey","")).strip(),str(item.get("sourceUrl","")or""),item.get("metadata") if isinstance(item.get("metadata"),dict) else {})
                self.reply(result,201);return
            if path.endswith("/complete"):
                task_id=unquote(path[len(base+"/"):-len("/complete")].rstrip("/"));result=service.submit_complete(user_id,task_id);self.reply(result,202 if result.get('asynchronous') else 200);return
            if path.endswith("/retry"):
                task_id=unquote(path[len(base+"/"):-len("/retry")].rstrip("/"));self.reply(service.retry(user_id,task_id));return
            if path.endswith("/cancel"):
                task_id=unquote(path[len(base+"/"):-len("/cancel")].rstrip("/"));self.reply(service.cancel(user_id,task_id));return
            self.reply({"error":"not found"},404)
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except (SaaSConfigurationError,ValueError) as exc:self.reply({"code":"workspace_import_unavailable","error":str(exc)},503)
    def catalog_post(self,path):
        try:item=self.json_body()
        except Exception:self.reply({"code":"invalid_payload","error":"请求数据无效。"},400);return
        if not isinstance(item,dict):self.reply({"code":"invalid_payload","error":"请求数据无效。"},400);return
        try:
            user_id=str(self._saas_session["id"])
            if path=="/api/library/items":
                self.reply(CATALOG.add_or_unlock(user_id,str(item.get("bookId","")).strip(),False,str(item.get("shelfState","active"))),201);return
            if path.startswith("/api/catalog/books/") and path.endswith("/unlock"):
                book_id=unquote(path[len("/api/catalog/books/"):-len("/unlock")].rstrip("/"));self.reply(CATALOG.add_or_unlock(user_id,book_id,True,str(item.get("shelfState","active"))));return
            if path=="/api/admin/catalog/books":
                if not self._saas_session.get("is_admin"):
                    self.reply({"code":"admin_required","error":"该操作仅允许管理员执行。"},403);return
                result=CATALOG.review(user_id,str(item.get("sourceBookId","")).strip(),str(item.get("rightsStatus","")).strip(),str(item.get("publicationStatus","")).strip(),item)
                self.reply(result);return
            self.reply({"error":"not found"},404)
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:self.reply({"code":"saas_unavailable","error":str(exc)},503)
    def rewards_get(self,path):
        try:
            user_id=str(self._saas_session["id"])
            if path=="/api/rewards/status":self.reply(REWARDS.status(user_id));return
            if path=="/api/rewards/catalog":self.reply(REWARDS.catalog(user_id));return
            if path=="/api/rewards/ledger":self.reply(REWARDS.ledger(user_id));return
            self.reply({"error":"not found"},404)
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:self.reply({"code":"saas_unavailable","error":str(exc)},503)
    def rewards_post(self,path):
        try:item=self.json_body()
        except Exception:self.reply({"code":"invalid_payload","error":"请求数据无效。"},400);return
        if not isinstance(item,dict):self.reply({"code":"invalid_payload","error":"请求数据无效。"},400);return
        try:
            user_id=str(self._saas_session["id"])
            if path=="/api/checkins":self.reply(REWARDS.checkin(user_id,item.get("day")));return
            if path=="/api/rewards/redeem":self.reply(REWARDS.redeem(user_id,str(item.get("code","")).strip(),str(item.get("idempotencyKey","")).strip()));return
            if path=="/api/rewards/activity":self.reply(REWARDS.activity(user_id,item.get("readingSeconds",0),item.get("sentences",0),item.get("reviews",0),str(item.get("idempotencyKey","")).strip()));return
            if path=="/api/rewards/complete-book":self.reply(REWARDS.complete_book(user_id,str(item.get("bookId","")).strip()));return
            if path=="/api/member-invites":
                key=str(item.get("idempotencyKey","")).strip()
                if not key or len(key)>255:raise SaaSError("invalid_idempotency_key","操作标识无效。",400)
                self.reply(REWARDS.issue_invite(user_id,key),201);return
            self.reply({"error":"not found"},404)
        except SaaSError as exc:self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:self.reply({"code":"saas_unavailable","error":str(exc)},503)
    def membership_post(self,path):
        if not self._saas_session.get("is_admin"):
            self.reply({"code":"admin_required","error":"该操作仅允许管理员执行。"},403);return
        try:item=self.json_body()
        except Exception:self.reply({"code":"invalid_payload","error":"请求数据无效。"},400);return
        if not isinstance(item,dict):self.reply({"code":"invalid_payload","error":"请求数据无效。"},400);return
        try:
            actor_id=str(self._saas_session["id"])
            if path=="/api/admin/manual-orders":
                result=MEMBERSHIPS.create_manual_order(actor_id,str(item.get("userId","")).strip(),str(item.get("planVersion","")).strip(),item.get("startsAt"),item.get("endsAt"),str(item.get("note","") or ""),item.get("amountCents",0),item.get("idempotencyKey"))
                REWARDS.on_first_paid(str(item.get("userId","")).strip())
                self.reply(result,201);return
            action=str(item.get("action","create")).strip()
            if action=="create":
                result=MEMBERSHIPS.create_manual_order(actor_id,str(item.get("userId","")).strip(),str(item.get("planVersion","")).strip(),item.get("startsAt"),item.get("endsAt"),str(item.get("note","") or ""),item.get("amountCents",0),item.get("idempotencyKey"))
                REWARDS.on_first_paid(str(item.get("userId","")).strip())
                self.reply(result,201);return
            result=MEMBERSHIPS.update_subscription(actor_id,str(item.get("subscriptionId","")).strip(),action,item.get("endsAt"),str(item.get("note","") or ""),item.get("idempotencyKey"))
            self.reply(result);return
        except SaaSError as exc:
            self.reply(exc.payload(),exc.status)
        except SaaSConfigurationError as exc:
            self.reply({"code":"saas_unavailable","error":str(exc)},503)
    def remove_book(self):
        parts=self.path.split("/")
        if len(parts)<5:self.reply({"error":"invalid book id"},400);return
        book_id=unquote(parts[3])
        try:item=self.json_body();confirmed=str(item.get("confirmTitle","")).strip();result=delete_book(book_id,confirmed)
        except ValueError as exc:self.reply({"error":str(exc)},400);return
        except Exception as exc:self.reply({"error":f"删除失败：{exc}"},500);return
        self.reply({"status":"deleted","book":result})
    def cancel_active_imports(self):
        try:item=self.json_body()
        except Exception:self.reply({"error":"invalid json"},400);return
        if not isinstance(item,dict) or item.get("confirm") is not True:self.reply({"error":"需要确认中断并删除任务"},400);return
        jobs=pending_import_jobs();job_ids=[job["id"] for job in jobs]
        if not job_ids:self.reply({"status":"empty","removed":0,"jobs":[]});return
        mark_import_jobs_cancelling(job_ids)
        pids=process_tree_for_jobs(job_ids);terminate_processes(pids)
        cleaned=[]
        for job in jobs:
            source_path=job["source_path"];preserved=bool(imported_books([source_path]));removed=[]
            try:
                source=(BOOKS_ROOT/source_path).resolve();source.relative_to(BOOKS_ROOT.resolve())
                if source.is_dir() and not preserved:
                    target=source if job.get("kind") in {"video","youtube"} else source/".reader"
                    if target.exists():shutil.rmtree(target);removed.append(str(target.relative_to(ROOT)))
            except (ValueError,OSError):pass
            for prefix in ("import","whisper","video-import","video-whisper","youtube","youtube-import"):
                try:(ROOT/".local"/f"{prefix}-{job['id']}.log").unlink(missing_ok=True)
                except OSError:pass
            cleaned.append({"id":job["id"],"sourcePath":source_path,"preservedImportedBook":preserved,"removed":removed})
        delete_import_jobs(job_ids)
        self.reply({"status":"cancelled","removed":len(job_ids),"killedPids":sorted(pids),"jobs":cleaned})
    def start_import(self):
        length=int(self.headers.get("Content-Length","0"))
        try: incoming=json.loads(self.rfile.read(length))
        except Exception: self.reply({"error":"invalid json"},400); return
        relative=str(incoming.get("path","")).strip()
        try:
            source=(BOOKS_ROOT/relative).resolve(); source.relative_to(BOOKS_ROOT.resolve())
        except Exception: self.reply({"error":"invalid book path"},400); return
        if not source.is_dir(): self.reply({"error":"book not found"},404); return
        duplicates=imported_books([relative])
        if duplicates and not incoming.get("allowReimport"):
            self.reply({"error":"该书已经导入","code":"duplicate_import","duplicates":duplicates},409);return
        job_id=create_job(relative,"books")
        threading.Thread(target=self.run_import_queue,args=([(job_id,relative)],),daemon=True).start()
        self.reply({"jobId":job_id,"status":"queued"},202)
    def start_batch_import(self):
        length=int(self.headers.get("Content-Length","0"))
        try: incoming=json.loads(self.rfile.read(length)); paths=incoming.get("paths",[])
        except Exception: self.reply({"error":"invalid json"},400); return
        if not isinstance(paths,list) or not paths or len(paths)>151: self.reply({"error":"请选择1至151本书"},400); return
        duplicates=imported_books(paths)
        if duplicates and not incoming.get("allowReimport"):
            self.reply({"error":"所选书籍中包含已经导入的内容","code":"duplicate_import","duplicates":duplicates},409);return
        queue=[];batch_id=uuid.uuid4().hex
        for value in paths:
            relative=str(value).strip()
            try: source=(BOOKS_ROOT/relative).resolve(); source.relative_to(BOOKS_ROOT.resolve())
            except Exception: self.reply({"error":f"invalid book path: {relative}"},400); return
            if not source.is_dir(): self.reply({"error":f"book not found: {relative}"},404); return
            queue.append((create_job(relative,"books",batch_id),relative))
        threading.Thread(target=self.run_import_queue,args=(queue,),daemon=True).start()
        self.reply({"jobIds":[job_id for job_id,_ in queue],"status":"queued","mode":"sequential"},202)
    def init_video_upload(self):
        try:item=self.json_body()
        except Exception:self.reply({"error":"invalid json"},400);return
        if not isinstance(item,dict):self.reply({"error":"invalid json"},400);return
        title=str(item.get("title","")).strip();series=str(item.get("series","")).strip() or "视频课程";media_filename=str(item.get("videoFilename","source.mp4"));media_suffix=Path(media_filename).suffix.lower();media_type="audio" if media_suffix in {".mp3",".m4a",".wav",".flac",".aac",".ogg",".opus"} else "video"
        if not title:self.reply({"error":"请输入媒体标题"},400);return
        duplicates=import_duplicates(title,series,media_type)
        if duplicates and not item.get("allowReimport"):
            self.reply({"error":"该媒体已经导入","code":"duplicate_import","duplicates":duplicates},409);return
        upload_id=uuid.uuid4().hex;folder=VIDEO_UPLOADS/upload_id;folder.mkdir(parents=True)
        metadata={"title":title,"englishTitle":str(item.get("englishTitle","")).strip(),"series":series,"level":str(item.get("level","")).strip(),"sourceType":media_type,"mediaType":media_type,
                  "subtitleStrategy":str(item.get("subtitleStrategy","auto")),"videoFilename":media_filename,"subtitleFilename":str(item.get("subtitleFilename",""))}
        (folder/"metadata.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2));self.reply({"uploadId":upload_id},201)
    def valid_youtube_url(self,value):
        try:
            parsed=urlsplit(value); host=(parsed.hostname or "").lower()
            return parsed.scheme in {"http","https"} and (host=="youtu.be" or host=="youtube.com" or host.endswith(".youtube.com"))
        except Exception:return False
    def youtube_info(self):
        try:item=self.json_body(); url=str(item.get("url","")).strip()
        except Exception:self.reply({"error":"invalid json"},400);return
        if not self.valid_youtube_url(url):self.reply({"error":"请输入有效的 YouTube 地址"},400);return
        try:
            output=subprocess.check_output([str(YTDLP),"--js-runtimes",f"node:{NODE}","--dump-single-json","--no-playlist","--skip-download",url],text=True,stderr=subprocess.STDOUT,timeout=90)
            data=json.loads(output); subtitles=data.get("subtitles") or {}; automatic=data.get("automatic_captions") or {};channel=data.get("channel") or data.get("uploader","") or "YouTube";track=select_native_english_track(data);chinese=select_chinese_track(data)
            self.reply({"id":data.get("id",""),"title":data.get("title","") or "YouTube Video","channel":channel,"series":canonical_youtube_series(channel),
                        "duration":data.get("duration",0),"thumbnail":data.get("thumbnail","") or "","hasEnglishSubtitles":bool(track and track["source"]=="manual"),
                        "hasEnglishAutoCaptions":bool(track and track["source"]=="automatic"),"englishSubtitleTrack":track["code"] if track else "","hasChineseSubtitles":bool(chinese),"chineseSubtitleTrack":chinese["code"] if chinese else "","chineseSubtitleSource":chinese["source"] if chinese else "","chineseSubtitleTranslated":bool(chinese and chinese["translated"]),"translatedEnglishRejected":has_translated_english_track(data),"webpageUrl":data.get("webpage_url",url)})
        except subprocess.TimeoutExpired:self.reply({"error":"解析超时，请稍后重试"},504)
        except subprocess.CalledProcessError as exc:self.reply({"error":"无法解析视频，可能需要登录、Cookie或该视频不可访问","detail":exc.output[-800:]},502)
        except Exception as exc:self.reply({"error":str(exc)},502)
    def start_youtube_import(self):
        try:item=self.json_body(); url=str(item.get("url","")).strip(); title=str(item.get("title","")).strip(); channel=str(item.get("channel","")).strip();series=canonical_youtube_series(channel);item["series"]=series
        except Exception:self.reply({"error":"invalid json"},400);return
        if not self.valid_youtube_url(url):self.reply({"error":"请输入有效的 YouTube 地址"},400);return
        if not title:self.reply({"error":"标题不能为空"},400);return
        duplicates=import_duplicates(title,series,"youtube",str(item.get("videoId","")).strip())
        if duplicates and not item.get("allowReimport"):
            self.reply({"error":"该 YouTube 视频已经导入","code":"duplicate_import","duplicates":duplicates},409);return
        request_id=uuid.uuid4().hex; request_file=ROOT/".local"/f"youtube-request-{request_id}.json"; request_file.write_text(json.dumps(item,ensure_ascii=False,indent=2))
        job_id=create_job(f"youtube:{item.get('videoId','') or request_id[:8]}","youtube")
        def launch():
            with IMPORT_LOCK:
                try:run_import_process(job_id,[sys.executable,ROOT/"tools/import_youtube_worker.py",job_id,request_file],ROOT/".local"/f"youtube-import-{job_id}.log")
                finally:request_file.unlink(missing_ok=True)
        threading.Thread(target=launch,daemon=True).start();self.reply({"jobId":job_id,"status":"queued"},202)
    def upload_video_part(self):
        upload_id=self.path.split("/api/import/video/upload/",1)[1].split("?",1)[0]
        folder=(VIDEO_UPLOADS/upload_id).resolve()
        try:folder.relative_to(VIDEO_UPLOADS.resolve())
        except ValueError:self.reply({"error":"invalid upload"},400);return
        if not folder.is_dir():self.reply({"error":"upload not found"},404);return
        query=parse_qs(urlsplit(self.path).query);kind=(query.get("kind") or ["video"])[0]
        if kind not in {"video","subtitle"}:self.reply({"error":"invalid part"},400);return
        length=int(self.headers.get("Content-Length","0"));limit=20*1024*1024*1024 if kind=="video" else 20*1024*1024
        if length<=0 or length>limit:self.reply({"error":"invalid file size"},413);return
        metadata=json.loads((folder/"metadata.json").read_text());original=metadata.get("videoFilename" if kind=="video" else "subtitleFilename","")
        suffix=Path(original).suffix.lower() or (".mp4" if kind=="video" else ".srt")
        if kind=="video" and suffix not in {".mp4",".mov",".m4v",".mp3",".m4a",".wav",".flac",".aac",".ogg",".opus"}:suffix=".mp4"
        if kind=="subtitle" and suffix not in {".srt",".vtt"}:suffix=".srt"
        target=folder/("source"+suffix if kind=="video" else "subtitles"+suffix)
        remaining=length
        with target.open("wb") as output:
            while remaining:
                chunk=self.rfile.read(min(1024*1024,remaining))
                if not chunk:break
                output.write(chunk);remaining-=len(chunk)
        if remaining:self.reply({"error":"upload interrupted"},400);return
        self.reply({"status":"uploaded","kind":kind,"bytes":length})
    def complete_video_upload(self):
        length=int(self.headers.get("Content-Length","0"))
        if length: self.rfile.read(length)
        upload_id=self.path.split("/api/import/video/complete/",1)[1].split("?",1)[0];folder=(VIDEO_UPLOADS/upload_id).resolve()
        if not folder.is_dir():self.reply({"error":"upload not found"},404);return
        metadata=json.loads((folder/"metadata.json").read_text());media=next(iter(folder.glob("source.*")),None)
        if not media:self.reply({"error":"media missing"},400);return
        media_type=metadata.get("mediaType","video");safe=re.sub(r"[^\w\-\u4e00-\u9fff]+","-",metadata["title"]).strip("-") or media_type
        relative=str(Path(metadata["series"])/f"{media_type}.{safe}-{upload_id[:8]}");destination=BOOKS_ROOT/relative;destination.mkdir(parents=True,exist_ok=True)
        shutil.move(str(media),destination/("source"+media.suffix.lower()))
        subtitle=next(iter(folder.glob("subtitles.*")),None)
        if subtitle:shutil.move(str(subtitle),destination/("subtitles"+subtitle.suffix.lower()))
        (destination/".video-import.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2));shutil.rmtree(folder)
        job_id=create_job(relative,"video");threading.Thread(target=self.run_video_import_queue,args=([(job_id,relative)],),daemon=True).start();self.reply({"jobId":job_id,"status":"queued"},202)
    def run_import_queue(self,queue):
        with IMPORT_LOCK:
            for job_id,relative in queue:
                run_import_process(job_id,[sys.executable,ROOT/"tools/import_worker.py",job_id,relative],ROOT/".local"/f"import-{job_id}.log")
    def run_video_import_queue(self,queue):
        with IMPORT_LOCK:
            for job_id,relative in queue:
                run_import_process(job_id,[sys.executable,ROOT/"tools/import_video_worker.py",job_id,relative],ROOT/".local"/f"video-import-{job_id}.log")
    def serve_books_file(self,url_path):
        relative=unquote(url_path.split("/books/",1)[1]); path=(BOOKS_ROOT/relative).resolve()
        try: path.relative_to(BOOKS_ROOT.resolve())
        except ValueError: self.send_error(403); return
        if not path.is_file(): self.send_error(404); return
        stat=path.stat();etag=f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        if self.headers.get("If-None-Match")==etag and not self.headers.get("Range"):
            self.send_response(304);self.send_header("ETag",etag);self.send_header("Cache-Control",self.book_cache_control(path));self.end_headers();return
        range_header=self.headers.get("Range")
        if range_header: self.send_path_range(path,range_header); return
        size=stat.st_size; self.send_response(200); self.send_header("Content-Type",mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length",str(size)); self.send_header("Accept-Ranges","bytes");self.send_header("ETag",etag);self.send_header("Cache-Control",self.book_cache_control(path)); self.end_headers()
        self.send_file_content(path,0,size)
    def send_path_range(self,path,range_header):
        match=re.fullmatch(r"bytes=(\d*)-(\d*)",range_header.strip()); size=path.stat().st_size
        if not match: self.send_error(416); return
        first,last=match.groups()
        if first: start=int(first); end=min(int(last),size-1) if last else size-1
        else: length=min(int(last),size); start=size-length; end=size-1
        if start<0 or start>=size or end<start:
            self.send_response(416); self.send_header("Content-Range",f"bytes */{size}"); self.end_headers(); return
        length=end-start+1;stat=path.stat();etag=f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'; self.send_response(206); self.send_header("Content-Type",mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges","bytes"); self.send_header("Content-Range",f"bytes {start}-{end}/{size}"); self.send_header("Content-Length",str(length));self.send_header("ETag",etag);self.send_header("Cache-Control",self.book_cache_control(path)); self.end_headers()
        self.send_file_content(path,start,length)
    def send_file_content(self,path,start,length):
        try:
            with path.open("rb") as source:
                sent=self.connection.sendfile(source,offset=start,count=length)
                if sent is None:return
        except (AttributeError,OSError,BrokenPipeError,ConnectionResetError):
            try:
                with path.open("rb") as source:
                    source.seek(start);remaining=length
                    while remaining:
                        chunk=source.read(min(256*1024,remaining))
                        if not chunk:break
                        self.wfile.write(chunk);remaining-=len(chunk)
            except (BrokenPipeError,ConnectionResetError,OSError):pass
    def book_cache_control(self,path):
        suffix=path.suffix.lower()
        if suffix in {".jpg",".jpeg",".png",".webp",".svg"}:return "public, max-age=604800, stale-while-revalidate=86400"
        if suffix in {".mp3",".mp4",".m4a",".ogg",".wav"}:return "public, max-age=86400, stale-while-revalidate=3600"
        return "public, max-age=3600"
    def get_settings(self):
        config=private_config(); token=config.get("diocoToken","")
        shortcuts=db_get_settings({"shortcutPrevious":"a","shortcutRepeat":"s","shortcutNext":"d","shortcutPlay":"space","shelfView":"tile","currentSeries":"","readerLayout":"side","wordTipSeconds":2,"reviewPageSize":10,"manualRepeatCount":3,"manualPauseSeconds":2,"highlightLeadMs":0,"eyeComfort":False,"heatmapRange":"year","sentenceAutoPause":False})
        self.reply({"userEmail":config.get("userEmail",""),"tokenConfigured":bool(token),
                    "tokenMask":("••••••••"+token[-4:]) if token else "","runtimeMode":RUNTIME_MODE,**shortcuts})
    def update_settings(self):
        length=int(self.headers.get("Content-Length","0"))
        if length<=0 or length>10000: self.reply({"error":"invalid payload"},400); return
        try: incoming=json.loads(self.rfile.read(length))
        except Exception: self.reply({"error":"invalid json"},400); return
        current=private_config(); email=str(incoming.get("userEmail",current.get("userEmail",""))).strip()
        token=str(incoming.get("diocoToken","")).strip() or current.get("diocoToken","")
        if not email or "@" not in email: self.reply({"error":"请输入有效邮箱"},400); return
        if not token: self.reply({"error":"请输入令牌"},400); return
        defaults={"shortcutPrevious":"a","shortcutRepeat":"s","shortcutNext":"d","shortcutPlay":"space"}
        current_shortcuts=db_get_settings(defaults)
        shortcut_values={key:str(incoming.get(key,current_shortcuts[key])).strip().lower() for key in defaults}
        if any(not value for value in shortcut_values.values()): self.reply({"error":"快捷键不能为空"},400); return
        if len(set(shortcut_values.values()))!=len(shortcut_values): self.reply({"error":"快捷键不能重复"},400); return
        PRIVATE_CONFIG.write_text(json.dumps({"userEmail":email,"diocoToken":token},ensure_ascii=False,indent=2))
        os.chmod(PRIVATE_CONFIG,0o600)
        set_settings(shortcut_values)
        extra={}
        try: extra["wordTipSeconds"]=max(.5,min(10,float(incoming.get("wordTipSeconds",2))))
        except (TypeError,ValueError): extra["wordTipSeconds"]=2
        try: extra["reviewPageSize"]=max(5,min(50,int(incoming.get("reviewPageSize",10))))
        except (TypeError,ValueError): extra["reviewPageSize"]=10
        try: extra["manualRepeatCount"]=max(1,min(10,int(incoming.get("manualRepeatCount",3))))
        except (TypeError,ValueError): extra["manualRepeatCount"]=3
        try: extra["manualPauseSeconds"]=max(.5,min(10,float(incoming.get("manualPauseSeconds",2))))
        except (TypeError,ValueError): extra["manualPauseSeconds"]=2
        try: extra["highlightLeadMs"]=max(-300,min(600,int(incoming.get("highlightLeadMs",0))))
        except (TypeError,ValueError): extra["highlightLeadMs"]=0
        extra["eyeComfort"]=bool(incoming.get("eyeComfort",False))
        set_settings(extra)
        self.get_settings()
    def update_preferences(self):
        length=int(self.headers.get("Content-Length","0"))
        try: incoming=json.loads(self.rfile.read(length))
        except Exception: self.reply({"error":"invalid json"},400); return
        allowed={}
        if incoming.get("shelfView") in {"tile","list"}: allowed["shelfView"]=incoming["shelfView"]
        if "currentSeries" in incoming: allowed["currentSeries"]=str(incoming["currentSeries"])
        if incoming.get("readerLayout") in {"side","stack"}: allowed["readerLayout"]=incoming["readerLayout"]
        if "eyeComfort" in incoming: allowed["eyeComfort"]=bool(incoming["eyeComfort"])
        if "sentenceAutoPause" in incoming: allowed["sentenceAutoPause"]=bool(incoming["sentenceAutoPause"])
        if incoming.get("heatmapRange") in {"year","quarter","month","week"}: allowed["heatmapRange"]=incoming["heatmapRange"]
        if not allowed: self.reply({"error":"no valid preferences"},400); return
        set_settings(allowed); self.reply({"status":"saved",**allowed})
    def json_body(self,max_length=100000):
        length=int(self.headers.get("Content-Length","0"))
        if length<=0 or length>max_length: raise ValueError("invalid payload")
        return json.loads(self.rfile.read(length))
    def record_activity(self):
        try: item=self.json_body()
        except Exception: self.reply({"error":"invalid json"},400); return
        book_id=str(item.get("bookId","")).strip()
        if book_id and item.get("open"): touch_book(book_id)
        add_daily(reading_seconds=max(0,float(item.get("readingSeconds",0) or 0)),sentences=max(0,int(item.get("sentences",0) or 0)),
                  lookups=max(0,int(item.get("lookups",0) or 0)),reviews=max(0,int(item.get("reviews",0) or 0)),
                  shadow_attempts=max(0,int(item.get("shadowAttempts",0) or 0)),sessions=max(0,int(item.get("sessions",0) or 0)))
        self.reply({"status":"saved"})
    def create_vocabulary(self):
        try: item=self.json_body(); save_vocab(item); add_daily(reviews=0)
        except Exception as exc: self.reply({"error":str(exc)},400); return
        self.reply({"status":"saved","items":vocabulary_list()})
    def change_vocabulary(self):
        try: vocab_id=int(self.path.rsplit("/",1)[1]); item=self.json_body(); update_vocab(vocab_id,item); add_daily(reviews=1)
        except Exception as exc: self.reply({"error":str(exc)},400); return
        self.reply({"status":"saved","items":vocabulary_list()})
    def save_annotation(self):
        try:
            item=self.json_body(); result=annotate_word(str(item["bookId"]),str(item["sentenceId"]),int(item["wordIndex"]),
                corrected_word=item.get("correctedWord"),note=item.get("note"))
        except Exception as exc: self.reply({"error":str(exc)},400); return
        self.reply({"status":"saved",**result})
    def import_cover(self,query):
        relative=(query.get("path") or [""])[0].strip()
        try: folder=(BOOKS_ROOT/relative).resolve(); folder.relative_to(BOOKS_ROOT.resolve())
        except Exception: self.send_error(400); return
        pdfs=sorted(folder.glob("*.pdf"))
        if not pdfs:
            data=(READER/"shiyue-mark.svg").read_bytes();self.send_response(200);self.send_header("Content-Type","image/svg+xml")
            self.send_header("Cache-Control","public, max-age=3600");self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data);return
        digest=hashlib.sha1(relative.encode()).hexdigest()[:16]; target=COVER_CACHE/f"{digest}.png"
        try:
            with COVER_LOCK:
                if not target.exists():
                    with tempfile.TemporaryDirectory(prefix="shiyue-cover-") as tmp:
                        subprocess.run(["qlmanage","-t","-s","420","-o",tmp,str(pdfs[0])],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
                        produced=next(Path(tmp).glob("*.png")); shutil.copy2(produced,target)
            data=target.read_bytes(); self.send_response(200); self.send_header("Content-Type","image/png")
            self.send_header("Cache-Control","public, max-age=31536000, immutable"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
        except Exception: self.send_error(500)
    def word_dictionary(self,query):
        word=(query.get("word") or [""])[0].strip()
        pos=(query.get("pos") or [""])[0].strip()
        if not word or len(word)>80: self.reply({"error":"invalid word"},400); return
        key=f"{word.lower()}|{pos}"; cached=cache_path("dictionary",key)
        try:
            if cached.exists(): result=json.loads(cached.read_text())
            else:
                raw=upstream_json("/base_dict_getFullDict_8",{"form":word,"lemma":"","sl":"en","tl":"zh-CN","pos":pos,"pow":"n","fetchExampleTranslationsSeparately":"true"})
                render=raw.get("data",{}).get("renderData",{})
                entries=render.get("fullDictRenderData",{}).get("entries",[])
                groups=[]
                for entry in entries:
                    for group in entry.get("posGroups",[]):
                        translations=[x for x in group.get("translations",[]) if x]
                        if translations: groups.append({"pos":group.get("pos","") or "其他","translations":translations})
                examples=[]
                for rows in raw.get("data",{}).get("tatoebaExamples",{}).values():
                    for item in rows[:3]:
                        if item.get("text") and item["text"] not in examples: examples.append(item["text"])
                result={"word":word,"hover":render.get("hoverDictEntries",[]),"groups":groups,"examples":examples[:5],"source":"Dioco"}
            local_dictionary=dictionary();local=local_dictionary.get(word.casefold()) or local_dictionary.get(infer_lemma(word).casefold()) or {}
            phonetic=str(local.get("phonetic","")or"").strip()
            formatted=f"/{phonetic.strip('/')}/" if phonetic else ""
            if result.get("phonetic")!=formatted:result["phonetic"]=formatted;cached.write_text(json.dumps(result,ensure_ascii=False))
            self.reply(result)
        except Exception as exc: self.reply({"error":f"dictionary upstream failed: {exc}"},502)
    def word_hover(self,query):
        word=(query.get("word") or query.get("form") or [""])[0].strip()
        lemma=(query.get("lemma") or [""])[0].strip() or infer_lemma(word)
        pos=(query.get("pos") or [""])[0].strip().upper()
        if not word or len(word)>80:self.reply({"error":"invalid word"},400);return
        key=f"{word.casefold()}|{lemma.casefold()}|{pos}";cached=cache_path("hover-dictionary",key)
        try:
            if cached.exists():result=json.loads(cached.read_text())
            else:
                raw=upstream_json("/base_dict_getHoverDict_8",{"form":word,"lemma":lemma,"sl":"en","tl":"zh-CN","pos":pos,"pow":"n"})
                entries=[]
                for value in raw.get("data",{}).get("hoverDictEntries",[]):
                    value=str(value).strip()
                    if value and value not in entries:entries.append(value)
                result={"word":word,"entries":entries[:6],"source":"Dioco Hover Dictionary"}
                cached.write_text(json.dumps(result,ensure_ascii=False))
            self.reply(result)
        except Exception as exc:self.reply({"error":f"hover dictionary upstream failed: {exc}"},502)
    def word_tts(self,query):
        word=(query.get("word") or [""])[0].strip()
        if not word or len(word)>80: self.reply({"error":"invalid word"},400); return
        cached=cache_path("tts",word.lower(),"mp3")
        try:
            if not cached.exists():
                raw=upstream_json("/base_dict_getDictTTS_3",{"lang":"en","text":word})
                value=raw.get("data","")
                if not value.startswith("data:audio/") or "," not in value: raise ValueError("invalid TTS response")
                cached.write_bytes(base64.b64decode(value.split(",",1)[1]))
            data=cached.read_bytes(); self.send_response(200); self.send_header("Content-Type","audio/mpeg")
            self.send_header("Cache-Control","public, max-age=31536000, immutable"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
        except Exception as exc: self.reply({"error":f"tts upstream failed: {exc}"},502)
    def word_context(self):
        length=int(self.headers.get("Content-Length","0"))
        if length<=0 or length>100000: self.reply({"error":"invalid payload"},400); return
        try: incoming=json.loads(self.rfile.read(length))
        except Exception: self.reply({"error":"invalid json"},400); return
        word=str(incoming.get("word","")).strip(); sentence=str(incoming.get("contextSentence","")).strip(); expanded=str(incoming.get("expandedContext",sentence)).strip()
        if not word or not sentence: self.reply({"error":"word and contextSentence are required"},400); return
        key=json.dumps([word,sentence,expanded],ensure_ascii=False); cached=cache_path("context",key)
        try:
            if cached.exists(): result=json.loads(cached.read_text())
            else:
                config=private_config()
                if not config.get("diocoToken") or not config.get("userEmail"): raise ValueError("Dioco credentials are not configured")
                payload={"promptWithPlaceHolders_translated":"请解释一下这句话中这个词的用法<WORD>： <CONTEXT>","contextSentence":sentence,
                         "expandedContext":expanded,"word":word,"userLanguage_G":"zh-CN","studyLanguage_G":"en",
                         "diocoToken":config["diocoToken"],"userEmail":config["userEmail"]}
                raw=upstream_json("/base_lexa_generate",payload=payload,timeout=40)
                generation=raw.get("data",{}).get("generation","")
                result={"word":word,"explanation":plain_html(generation),"source":"Dioco Lexa"}
                cached.write_text(json.dumps(result,ensure_ascii=False))
            self.reply(result)
        except Exception as exc: self.reply({"error":f"context upstream failed: {exc}"},502)
    def sentence_grammar(self):
        try:incoming=self.json_body()
        except Exception:self.reply({"error":"invalid json"},400);return
        book_id=str(incoming.get("bookId","")).strip();sentence_id=str(incoming.get("sentenceId","")).strip();enhance=bool(incoming.get("enhance",False))
        record=get_book(book_id) if book_id else None
        sentence=next((item for item in (record or {}).get("book",{}).get("sentences",[]) if str(item.get("id"))==sentence_id),None)
        if not sentence:self.reply({"error":"sentence not found"},404);return
        text=str(sentence.get("text","")).strip();result=get_sentence_grammar(book_id,sentence_id,text)
        if not result and RUNTIME_MODE!="reader":
            try:
                subprocess.run([str(GRAMMAR_PYTHON),str(ROOT/"tools/analyze_grammar.py"),"--book-id",book_id,"--sentence-id",sentence_id],cwd=ROOT,env={**os.environ,"PYTHONPATH":str(ROOT/"tools")},check=True,timeout=180,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                result=get_sentence_grammar(book_id,sentence_id,text)
            except Exception as exc:self.reply({"error":f"本地语法模型分析失败：{exc}"},503);return
        if not result:self.reply({"error":"该句尚未生成语法数据，请先在本机补充分析"},404);return
        result["translation"]=str(sentence.get("translation","")).strip();result["translationSource"]=sentence.get("translationSource","");result["translationMissing"]=not bool(result["translation"]) and (record or {}).get("source_type")=="youtube"
        explanation_version=2
        if enhance and result.get("explanationVersion")!=explanation_version and RUNTIME_MODE!="reader":
            try:
                config=private_config()
                if config.get("diocoToken") and config.get("userEmail"):
                    structure=json.dumps({key:result.get(key) for key in ("sentenceType","pattern","subject","predicate","object","clauses","grammarPoints")},ensure_ascii=False)
                    prompt=f"请用简洁准确的中文讲解这句英文的句型、主干、从句、时态语态和学习重点。必须以以下Stanza句法结构为准，不得把已经识别出的从句说成不存在；如果原句疑似缺词、转写错误或结构不完整，要直接指出，不要擅自补词。Stanza结构：{structure}。原句：<CONTEXT>"
                    payload={"promptWithPlaceHolders_translated":prompt,"contextSentence":text,"expandedContext":text,"word":"sentence grammar","userLanguage_G":"zh-CN","studyLanguage_G":"en","diocoToken":config["diocoToken"],"userEmail":config["userEmail"]}
                    raw=upstream_json("/base_lexa_generate",payload=payload,timeout=40);generation=plain_html(raw.get("data",{}).get("generation",""))
                    if generation:result["aiExplanation"]=generation;result["explanationSource"]="Dioco Lexa + Stanza";result["explanationVersion"]=explanation_version;save_sentence_grammar(book_id,sentence_id,text,{key:value for key,value in result.items() if key not in {"bookId","sentenceId","model","updatedAt"}},result.get("model","stanza-en"))
            except Exception:pass
        self.reply(result)
    def reply(self,data,status=200,cache_control="no-store",extra_headers=()):
        body=json.dumps(data,ensure_ascii=False,separators=(",",":")).encode();etag='"'+hashlib.sha256(body).hexdigest()[:24]+'"'
        if self.command=="GET" and self.headers.get("If-None-Match")==etag:
            self.send_response(304);self.send_header("ETag",etag);self.send_header("Cache-Control",cache_control)
            for key,value in extra_headers:self.send_header(key,value)
            self.end_headers();return
        encoded="gzip" in self.headers.get("Accept-Encoding","").lower() and len(body)>1024
        if encoded:body=gzip.compress(body,compresslevel=6)
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Cache-Control",cache_control);self.send_header("ETag",etag)
        if encoded:self.send_header("Content-Encoding","gzip");self.send_header("Vary","Accept-Encoding")
        for key,value in extra_headers:self.send_header(key,value)
        self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def reply_text(self,value,status=200):
        body=str(value).encode("utf-8")
        self.send_response(status);self.send_header("Content-Type","text/plain; charset=utf-8");self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
    def can_manage_platform(self):
        return DEPLOYMENT_MODE=="local" and RUNTIME_MODE!="reader" and SAAS.enabled and self.client_address[0] in {"127.0.0.1","::1"} and bool(getattr(self,"_saas_session",{}).get("is_admin"))

    def deployment_allowed(self):
        if DEPLOYMENT_MODE!="local" or RUNTIME_MODE=="reader":
            self.reply({"code":"local_mode_required","error":"平台与部署仅在本地模式开放。"},403);return False
        address=self.client_address[0]
        if address not in {"127.0.0.1","::1"}:self.reply({"error":"部署操作仅允许从服务器本机访问"},403);return False
        if not SAAS.enabled or not getattr(self,"_saas_session",{}).get("is_admin"):
            self.reply({"code":"admin_required","error":"部署管理仅允许管理员访问。"},403);return False
        return True

class ReaderHTTPServer(ThreadingHTTPServer):
    def handle_error(self,request,client_address):
        error=sys.exc_info()[1]
        if isinstance(error,(BrokenPipeError,ConnectionResetError,ConnectionAbortedError)):return
        super().handle_error(request,client_address)

if __name__ == "__main__":
    if SAAS.enabled:
        try:
            SAAS.assert_runtime_configured()
            CACHE_SERVICE.assert_ready()
            if os.environ.get("SHIYUE_SAAS_AUTO_MIGRATE","").strip().lower() in {"1","true","yes","on"}:
                applied=SAAS.migrate()
                if applied: print("SaaS migration 已应用："+", ".join(applied),flush=True)
            else:
                SAAS.ensure_migrated()
            if os.environ.get("BOOTSTRAP_ADMIN_EMAIL","").strip():
                SAAS.bootstrap_admin()
        except SaaSConfigurationError as exc:
            print(f"SaaS 启动配置错误：{exc}",file=sys.stderr,flush=True)
            raise SystemExit(2)
    certificate=os.environ.get("READER_TLS_CERT","").strip();private_key=os.environ.get("READER_TLS_KEY","").strip()
    if certificate:certificate=str(Path(certificate).expanduser().resolve())
    if private_key:private_key=str(Path(private_key).expanduser().resolve())
    os.chdir(READER)
    existing=[job for job in active_import_jobs() if job["status"]=="running"]
    if existing:
        IMPORT_LOCK.acquire()
        def release_import_lock():
            while any(job["status"]=="running" for job in active_import_jobs()):time.sleep(2)
            IMPORT_LOCK.release()
        threading.Thread(target=release_import_lock,daemon=True).start()
    host=os.environ.get("READER_HOST","0.0.0.0")
    port=int(os.environ.get("READER_PORT","8765"))
    server=ReaderHTTPServer((host,port),Handler)
    secure=bool(certificate and private_key)
    if secure:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(certificate,private_key);server.socket=context.wrap_socket(server.socket,server_side=True)
    addresses=[]
    try:
        for info in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
            address=info[4][0]
            if not address.startswith("127.") and address not in addresses: addresses.append(address)
    except OSError: pass
    scheme="https" if secure else "http"
    print(f"拾页已启动：{scheme}://localhost:{port}",flush=True)
    for address in addresses: print(f"局域网访问：{scheme}://{address}:{port}",flush=True)
    print(f"监听地址：{host}:{port}",flush=True)
    server.serve_forever()
