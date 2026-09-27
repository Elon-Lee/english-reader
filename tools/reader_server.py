#!/usr/bin/env python3
"""Static reader server plus a local-only Whisper endpoint for shadowing."""
import json
import base64
import hashlib
import mimetypes
import os
import re
import subprocess
import tempfile
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
READER=ROOT/"reader"
CLI=ROOT/"tools/vendor/whisper.cpp/build/bin/whisper-cli"
MODEL=ROOT/"tools/vendor/whisper.cpp/models/ggml-base.en.bin"
PRIVATE_CONFIG=ROOT/".dioco.local.json"
CACHE=ROOT/".cache/dioco"
CACHE.mkdir(parents=True,exist_ok=True)
UPSTREAM="https://api-cdn-plus.dioco.io"
UPSTREAM_HEADERS={
    "Accept":"application/json, text/plain, */*",
    "Origin":"https://www.youtube.com",
    "Referer":"https://www.youtube.com/",
    "User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/153.0 Safari/537.36",
}

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
        if route.path == "/api/settings": self.get_settings(); return
        if route.path == "/api/word-dictionary": self.word_dictionary(parse_qs(route.query)); return
        if route.path == "/api/word-tts": self.word_tts(parse_qs(route.query)); return
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
    def get_settings(self):
        config=private_config(); token=config.get("diocoToken","")
        self.reply({"userEmail":config.get("userEmail",""),"tokenConfigured":bool(token),
                    "tokenMask":("••••••••"+token[-4:]) if token else ""})
    def update_settings(self):
        length=int(self.headers.get("Content-Length","0"))
        if length<=0 or length>10000: self.reply({"error":"invalid payload"},400); return
        try: incoming=json.loads(self.rfile.read(length))
        except Exception: self.reply({"error":"invalid json"},400); return
        current=private_config(); email=str(incoming.get("userEmail",current.get("userEmail",""))).strip()
        token=str(incoming.get("diocoToken","")).strip() or current.get("diocoToken","")
        if not email or "@" not in email: self.reply({"error":"请输入有效邮箱"},400); return
        if not token: self.reply({"error":"请输入令牌"},400); return
        PRIVATE_CONFIG.write_text(json.dumps({"userEmail":email,"diocoToken":token},ensure_ascii=False,indent=2))
        os.chmod(PRIVATE_CONFIG,0o600)
        self.get_settings()
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
    server=ThreadingHTTPServer(("127.0.0.1",8765),Handler)
    print("拾页已启动：http://localhost:8765",flush=True)
    server.serve_forever()
