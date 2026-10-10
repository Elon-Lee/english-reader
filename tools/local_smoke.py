#!/usr/bin/env python3
"""Start the reader in-process, exercise real HTTP(S), then stop it cleanly."""
from __future__ import annotations

import json
import os
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPSHandler


ROOT=Path(__file__).resolve().parents[1]
HOST=os.environ.get("READER_HOST","127.0.0.1")
if HOST in {"0.0.0.0","::"}:HOST="127.0.0.1"
PORT=int(os.environ.get("READER_PORT","8785"))
SECURE=bool(os.environ.get("READER_TLS_CERT") and os.environ.get("READER_TLS_KEY"))
BASE=f"{'https' if SECURE else 'http'}://{HOST}:{PORT}"


def request(path:str,headers:dict[str,str]|None=None)->tuple[int,dict[str,str],bytes]:
    opener=build_opener(HTTPSHandler(context=ssl._create_unverified_context())) if SECURE else build_opener()
    response=opener.open(Request(BASE+path,headers=headers or {}),timeout=10)
    return response.status,{key.lower():value for key,value in response.headers.items()},response.read()


def main()->int:
    environment={**os.environ,"READER_HOST":HOST,"READER_PORT":str(PORT)};process=subprocess.Popen([sys.executable,str(ROOT/"tools/reader_server.py")],cwd=ROOT,env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    checks=[]
    def check(name:str,condition:bool,detail:str="")->None:
        checks.append({"name":name,"ok":bool(condition),"detail":detail})
        if not condition:raise AssertionError(f"{name}: {detail}")
    try:
        deadline=time.time()+15
        while time.time()<deadline:
            if process.poll() is not None:raise RuntimeError("reader exited during startup")
            try:
                status,_,body=request("/api/health");health=json.loads(body);break
            except Exception:time.sleep(.1)
        else:raise RuntimeError("reader did not become healthy")
        check("health",status==200 and health.get("status")=="ok",json.dumps(health,ensure_ascii=False));check("legacy mode",health.get("saasEnabled") is False,str(health.get("saasEnabled")));check("book count",health.get("books")==39,str(health.get("books")))
        status,headers,index=request("/");html=index.decode("utf-8");check("index",status==200 and "拾页" in html);check("frontend bundle","app.js?v=20261010-6" in html and "styles.css?v=20261010-4" in html);check("security headers",headers.get("x-frame-options")=="DENY" and headers.get("x-content-type-options")=="nosniff",str(headers))
        _,_,library_body=request("/api/library");library=json.loads(library_body).get("books",[]);check("library",len(library)==39,str(len(library)));book_id=str(library[0]["id"])
        _,_,manifest_body=request(f"/api/books/{quote(book_id)}/manifest");manifest=json.loads(manifest_body);book=manifest.get("book",manifest);sentences=book.get("sentences",[]);check("manifest",bool(book.get("title")));check("sentences",bool(sentences),str(len(sentences)))
        audio=str(book.get("audio","") or book.get("audio_url","") or "")
        if audio.startswith("/"):
            status,range_headers,data=request(quote(audio,safe="/?=&"),{"Range":"bytes=0-31"});check("media range",status==206 and len(data)==32,f"status={status}, bytes={len(data)}");check("range header","content-range" in range_headers,str(range_headers))
        _,_,vocabulary=request("/api/vocabulary");check("vocabulary",isinstance(json.loads(vocabulary).get("items"),list))
        _,_,days=request("/api/learning/days");check("learning days",isinstance(json.loads(days).get("days"),list))
        _,_,catalog=request("/api/import/catalog");check("import catalog",isinstance(json.loads(catalog).get("series"),list))
        _,_,settings=request("/api/settings");check("settings",isinstance(json.loads(settings),dict))
        chrome=Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if chrome.is_file() and not SECURE:
            debug_root=ROOT/".local/debug";debug_root.mkdir(parents=True,exist_ok=True);label=("https" if SECURE else "http")
            def chrome_run(extra:list[str],suffix:str,timeout:int=60)->subprocess.CompletedProcess[str]:
                with tempfile.TemporaryDirectory(prefix=f"shiyue-chrome-{suffix}-") as profile:
                    common=[str(chrome),"--headless","--disable-gpu","--no-sandbox","--disable-dev-shm-usage","--disable-background-networking","--disable-sync","--metrics-recording-only","--virtual-time-budget=5000",f"--user-data-dir={profile}","--ignore-certificate-errors"]
                    return subprocess.run([*common,*extra,BASE+"/"],text=True,capture_output=True,timeout=timeout,check=True)
            desktop=debug_root/f"{label}-desktop.png";mobile=debug_root/f"{label}-mobile.png"
            def screenshot(target:Path,size:str,suffix:str)->None:
                target.unlink(missing_ok=True)
                try:chrome_run([f"--window-size={size}",f"--screenshot={target}"],suffix,15)
                except subprocess.TimeoutExpired:
                    if not target.is_file() or target.stat().st_size<=10_000:raise
            screenshot(desktop,"1440,1000","desktop");screenshot(mobile,"390,844","mobile")
            check("browser screenshots",desktop.stat().st_size>10_000 and mobile.stat().st_size>10_000,f"desktop={desktop.stat().st_size}, mobile={mobile.stat().st_size}")
        if not SECURE:
            try:
                context=ssl._create_unverified_context();context.wrap_socket(socket.create_connection((HOST,PORT),timeout=2),server_hostname=HOST).do_handshake()
            except Exception:pass
            time.sleep(.2);check("malformed request resilience",process.poll() is None)
        print(json.dumps({"status":"ok","baseUrl":BASE,"checks":checks},ensure_ascii=False,indent=2));return 0
    except Exception as exc:
        print(json.dumps({"status":"failed","baseUrl":BASE,"error":str(exc),"checks":checks},ensure_ascii=False,indent=2),file=sys.stderr);return 1
    finally:
        if process.poll() is None:
            try:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=5)
            except Exception:
                try:os.killpg(process.pid,signal.SIGKILL)
                except Exception:pass
        stdout=process.stdout.read() if process.stdout else "";stderr=process.stderr.read() if process.stderr else ""
        if "Traceback" in stderr:
            print(stderr,file=sys.stderr)


if __name__=="__main__":raise SystemExit(main())
