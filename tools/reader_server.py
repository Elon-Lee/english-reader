#!/usr/bin/env python3
"""Static reader server plus a local-only Whisper endpoint for shadowing."""
import json
import base64
import hashlib
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import uuid
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from library_db import BOOKS_ROOT, add_daily, annotate_word, create_job, dictionary, get_book, get_job, get_settings as db_get_settings, learning_days, library, save_vocab, scan_catalog, set_settings, touch_book, update_vocab, vocabulary_list

ROOT=Path(__file__).resolve().parents[1]
READER=ROOT/"reader"
CLI=ROOT/"tools/vendor/whisper.cpp/build/bin/whisper-cli"
MODEL=ROOT/"tools/vendor/whisper.cpp/models/ggml-base.en.bin"
YTDLP=ROOT/".local/bin/yt-dlp"
NODE=Path(shutil.which("node") or "/usr/local/bin/node")
PRIVATE_CONFIG=ROOT/".dioco.local.json"
CACHE=ROOT/".cache/dioco"
CACHE.mkdir(parents=True,exist_ok=True)
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
        if urlsplit(self.path).path.lower().endswith((".mp3",".wav",".m4a",".ogg")):
            self.send_header("Accept-Ranges","bytes")
        super().end_headers()
    def do_GET(self):
        route=urlsplit(self.path)
        if route.path == "/api/library": self.reply({"books":library()}); return
        if route.path == "/api/vocabulary": self.reply({"items":vocabulary_list()}); return
        if route.path == "/api/learning/days": self.reply({"days":learning_days(365)}); return
        if route.path == "/api/local-dictionary": self.reply(dictionary()); return
        if route.path == "/api/import/catalog": self.reply({"series":scan_catalog()}); return
        if route.path == "/api/import/cover": self.import_cover(parse_qs(route.query)); return
        if route.path.startswith("/api/import/jobs/"):
            try: job=get_job(int(route.path.rsplit("/",1)[1]))
            except ValueError: job=None
            self.reply(job or {"error":"job not found"},200 if job else 404); return
        if route.path.startswith("/api/books/"):
            book_id=unquote(route.path.split("/api/books/",1)[1]); result=get_book(book_id)
            self.reply(result or {"error":"book not found"},200 if result else 404); return
        if route.path == "/api/settings": self.get_settings(); return
        if route.path == "/api/word-dictionary": self.word_dictionary(parse_qs(route.query)); return
        if route.path == "/api/word-tts": self.word_tts(parse_qs(route.query)); return
        if route.path.startswith("/books/"):
            self.serve_books_file(route.path); return
        range_header=self.headers.get("Range")
        if range_header and self.serve_range(range_header): return
        super().do_GET()
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
                except BrokenPipeError: break
                remaining-=len(chunk)
        return True
    def do_POST(self):
        if self.path == "/api/import/youtube/info": self.youtube_info(); return
        if self.path == "/api/import/youtube": self.start_youtube_import(); return
        if self.path == "/api/import/video/init": self.init_video_upload(); return
        if self.path.startswith("/api/import/video/upload/"): self.upload_video_part(); return
        if self.path.startswith("/api/import/video/complete/"): self.complete_video_upload(); return
        if self.path == "/api/activity": self.record_activity(); return
        if self.path == "/api/vocabulary": self.create_vocabulary(); return
        if self.path.startswith("/api/vocabulary/"): self.change_vocabulary(); return
        if self.path == "/api/word-annotation": self.save_annotation(); return
        if self.path == "/api/preferences": self.update_preferences(); return
        if self.path == "/api/import/batch": self.start_batch_import(); return
        if self.path == "/api/import": self.start_import(); return
        if self.path == "/api/settings": self.update_settings(); return
        if self.path == "/api/word-context": self.word_context(); return
        if self.path != "/api/transcribe": self.send_error(404); return
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
    def start_import(self):
        length=int(self.headers.get("Content-Length","0"))
        try: incoming=json.loads(self.rfile.read(length))
        except Exception: self.reply({"error":"invalid json"},400); return
        relative=str(incoming.get("path","")).strip()
        try:
            source=(BOOKS_ROOT/relative).resolve(); source.relative_to(BOOKS_ROOT.resolve())
        except Exception: self.reply({"error":"invalid book path"},400); return
        if not source.is_dir(): self.reply({"error":"book not found"},404); return
        job_id=create_job(relative)
        threading.Thread(target=self.run_import_queue,args=([(job_id,relative)],),daemon=True).start()
        self.reply({"jobId":job_id,"status":"queued"},202)
    def start_batch_import(self):
        length=int(self.headers.get("Content-Length","0"))
        try: incoming=json.loads(self.rfile.read(length)); paths=incoming.get("paths",[])
        except Exception: self.reply({"error":"invalid json"},400); return
        if not isinstance(paths,list) or not paths or len(paths)>151: self.reply({"error":"请选择1至151本书"},400); return
        queue=[]
        for value in paths:
            relative=str(value).strip()
            try: source=(BOOKS_ROOT/relative).resolve(); source.relative_to(BOOKS_ROOT.resolve())
            except Exception: self.reply({"error":f"invalid book path: {relative}"},400); return
            if not source.is_dir(): self.reply({"error":f"book not found: {relative}"},404); return
            queue.append((create_job(relative),relative))
        threading.Thread(target=self.run_import_queue,args=(queue,),daemon=True).start()
        self.reply({"jobIds":[job_id for job_id,_ in queue],"status":"queued","mode":"sequential"},202)
    def init_video_upload(self):
        try:item=self.json_body()
        except Exception:self.reply({"error":"invalid json"},400);return
        title=str(item.get("title","")).strip();series=str(item.get("series","")).strip() or "视频课程"
        if not title:self.reply({"error":"请输入视频标题"},400);return
        upload_id=uuid.uuid4().hex;folder=VIDEO_UPLOADS/upload_id;folder.mkdir(parents=True)
        metadata={"title":title,"englishTitle":str(item.get("englishTitle","")).strip(),"series":series,"level":str(item.get("level","")).strip(),
                  "subtitleStrategy":str(item.get("subtitleStrategy","auto")),"videoFilename":str(item.get("videoFilename","source.mp4")),"subtitleFilename":str(item.get("subtitleFilename",""))}
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
            data=json.loads(output); subtitles=data.get("subtitles") or {}; automatic=data.get("automatic_captions") or {}
            self.reply({"id":data.get("id",""),"title":data.get("title","") or "YouTube Video","channel":data.get("channel") or data.get("uploader","") or "YouTube",
                        "duration":data.get("duration",0),"thumbnail":data.get("thumbnail","") or "","hasEnglishSubtitles":any(key.startswith("en") for key in subtitles),
                        "hasEnglishAutoCaptions":any(key.startswith("en") for key in automatic),"webpageUrl":data.get("webpage_url",url)})
        except subprocess.TimeoutExpired:self.reply({"error":"解析超时，请稍后重试"},504)
        except subprocess.CalledProcessError as exc:self.reply({"error":"无法解析视频，可能需要登录、Cookie或该视频不可访问","detail":exc.output[-800:]},502)
        except Exception as exc:self.reply({"error":str(exc)},502)
    def start_youtube_import(self):
        try:item=self.json_body(); url=str(item.get("url","")).strip(); title=str(item.get("title","")).strip(); series=str(item.get("series","")).strip()
        except Exception:self.reply({"error":"invalid json"},400);return
        if not self.valid_youtube_url(url):self.reply({"error":"请输入有效的 YouTube 地址"},400);return
        if not title or not series:self.reply({"error":"标题和标签不能为空"},400);return
        request_id=uuid.uuid4().hex; request_file=ROOT/".local"/f"youtube-request-{request_id}.json"; request_file.write_text(json.dumps(item,ensure_ascii=False,indent=2))
        job_id=create_job(f"youtube:{item.get('videoId','') or request_id[:8]}")
        def launch():
            with IMPORT_LOCK:
                log=ROOT/".local"/f"youtube-import-{job_id}.log"
                with log.open("w") as output:subprocess.run([sys.executable,str(ROOT/"tools/import_youtube_worker.py"),str(job_id),request_file],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
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
        if kind=="video" and suffix not in {".mp4",".mov",".m4v"}:suffix=".mp4"
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
        metadata=json.loads((folder/"metadata.json").read_text());video=next(iter(folder.glob("source.*")),None)
        if not video:self.reply({"error":"video missing"},400);return
        safe=re.sub(r"[^\w\-\u4e00-\u9fff]+","-",metadata["title"]).strip("-") or "video"
        relative=str(Path(metadata["series"])/f"video.{safe}-{upload_id[:8]}");destination=BOOKS_ROOT/relative;destination.mkdir(parents=True,exist_ok=True)
        shutil.move(str(video),destination/("source"+video.suffix.lower()))
        subtitle=next(iter(folder.glob("subtitles.*")),None)
        if subtitle:shutil.move(str(subtitle),destination/("subtitles"+subtitle.suffix.lower()))
        (destination/".video-import.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2));shutil.rmtree(folder)
        job_id=create_job(relative);threading.Thread(target=self.run_video_import_queue,args=([(job_id,relative)],),daemon=True).start();self.reply({"jobId":job_id,"status":"queued"},202)
    def run_import_queue(self,queue):
        with IMPORT_LOCK:
            for job_id,relative in queue:
                log=ROOT/".local"/f"import-{job_id}.log"; log.parent.mkdir(parents=True,exist_ok=True)
                with log.open("w") as output:
                    subprocess.run([sys.executable,str(ROOT/"tools/import_worker.py"),str(job_id),relative],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
    def run_video_import_queue(self,queue):
        with IMPORT_LOCK:
            for job_id,relative in queue:
                log=ROOT/".local"/f"video-import-{job_id}.log"
                with log.open("w") as output:subprocess.run([sys.executable,str(ROOT/"tools/import_video_worker.py"),str(job_id),relative],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
    def serve_books_file(self,url_path):
        relative=unquote(url_path.split("/books/",1)[1]); path=(BOOKS_ROOT/relative).resolve()
        try: path.relative_to(BOOKS_ROOT.resolve())
        except ValueError: self.send_error(403); return
        if not path.is_file(): self.send_error(404); return
        range_header=self.headers.get("Range")
        if range_header: self.send_path_range(path,range_header); return
        size=path.stat().st_size; self.send_response(200); self.send_header("Content-Type",mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length",str(size)); self.send_header("Accept-Ranges","bytes"); self.end_headers()
        with path.open("rb") as source:
            try: shutil.copyfileobj(source,self.wfile)
            except BrokenPipeError: pass
    def send_path_range(self,path,range_header):
        match=re.fullmatch(r"bytes=(\d*)-(\d*)",range_header.strip()); size=path.stat().st_size
        if not match: self.send_error(416); return
        first,last=match.groups()
        if first: start=int(first); end=min(int(last),size-1) if last else size-1
        else: length=min(int(last),size); start=size-length; end=size-1
        if start<0 or start>=size or end<start:
            self.send_response(416); self.send_header("Content-Range",f"bytes */{size}"); self.end_headers(); return
        length=end-start+1; self.send_response(206); self.send_header("Content-Type",mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges","bytes"); self.send_header("Content-Range",f"bytes {start}-{end}/{size}"); self.send_header("Content-Length",str(length)); self.end_headers()
        with path.open("rb") as source:
            source.seek(start); remaining=length
            while remaining:
                chunk=source.read(min(256*1024,remaining))
                if not chunk: break
                try: self.wfile.write(chunk)
                except BrokenPipeError: break
                remaining-=len(chunk)
    def get_settings(self):
        config=private_config(); token=config.get("diocoToken","")
        shortcuts=db_get_settings({"shortcutPrevious":"a","shortcutRepeat":"s","shortcutNext":"d","shortcutPlay":"space","shelfView":"tile","currentSeries":"","wordTipSeconds":2,"reviewPageSize":10,"manualRepeatCount":3,"manualPauseSeconds":2,"highlightLeadMs":0,"eyeComfort":False,"heatmapRange":"year","sentenceAutoPause":False})
        self.reply({"userEmail":config.get("userEmail",""),"tokenConfigured":bool(token),
                    "tokenMask":("••••••••"+token[-4:]) if token else "",**shortcuts})
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
        if not pdfs: self.send_error(404); return
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
                cached.write_text(json.dumps(result,ensure_ascii=False))
            self.reply(result)
        except Exception as exc: self.reply({"error":f"dictionary upstream failed: {exc}"},502)
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
    def reply(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)

if __name__ == "__main__":
    os.chdir(READER)
    host=os.environ.get("READER_HOST","0.0.0.0")
    port=int(os.environ.get("READER_PORT","8765"))
    server=ThreadingHTTPServer((host,port),Handler)
    addresses=[]
    try:
        for info in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
            address=info[4][0]
            if not address.startswith("127.") and address not in addresses: addresses.append(address)
    except OSError: pass
    print(f"拾页已启动：http://localhost:{port}",flush=True)
    for address in addresses: print(f"局域网访问：http://{address}:{port}",flush=True)
    print(f"监听地址：{host}:{port}",flush=True)
    server.serve_forever()
