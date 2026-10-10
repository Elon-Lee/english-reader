#!/usr/bin/env python3
"""Capture every authenticated SaaS screen in desktop and mobile Chrome."""
from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import urlopen

from saas_auth import ROOT
from saas_auth import SaaSService


CHROME=Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SCREENS=("catalog","my-library","workspace","stats","vocab","rewards","membership","admin","settings")


def stop(process):
    if process and process.poll() is None:
        try:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=5)
        except Exception:
            try:os.killpg(process.pid,signal.SIGKILL)
            except Exception:pass


def screenshot(url:str,target:Path,size:str)->None:
    target.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="shiyue-walkthrough-") as profile:
        command=[str(CHROME),"--headless","--disable-gpu","--no-sandbox","--disable-dev-shm-usage","--disable-background-networking","--disable-sync","--metrics-recording-only","--virtual-time-budget=8000",f"--user-data-dir={profile}",f"--window-size={size}",f"--screenshot={target}",url]
        try:subprocess.run(command,text=True,capture_output=True,timeout=12,check=True)
        except subprocess.TimeoutExpired:
            if not target.is_file() or target.stat().st_size<10_000:raise
    if not target.is_file() or target.stat().st_size<10_000:raise RuntimeError(f"invalid screenshot: {target}")


def contact_sheet(files:list[Path],target:Path,width:int,height:int)->None:
    command=["ffmpeg","-y","-v","error"]
    for file in files:command.extend(["-i",str(file)])
    filters=[]
    for index in range(len(files)):filters.append(f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:white[s{index}]")
    inputs="".join(f"[s{index}]" for index in range(len(files)));filters.append(f"{inputs}xstack=inputs={len(files)}:layout=0_0|{width}_0|{width*2}_0|0_{height}|{width}_{height}|{width*2}_{height}|0_{height*2}|{width}_{height*2}|{width*2}_{height*2}[out]")
    subprocess.run([*command,"-filter_complex",";".join(filters),"-map","[out]","-frames:v","1",str(target)],check=True,timeout=60)


def capture_existing(base:str,secret:str,output:Path)->dict:
    output.mkdir(parents=True,exist_ok=True)
    report={"status":"ok","baseUrl":base,"output":str(output),"screens":[]}
    try:
        desktop=[];mobile=[];only=str(os.environ.get("SHIYUE_WALKTHROUGH_ONLY","")).strip();screens=(only,) if only in SCREENS else (() if only in {"workspace-reader","official-reader"} else SCREENS)
        for screen in screens:
            url=base+"/api/auth/debug-browser-login?"+urlencode({"token":secret,"screen":screen});desktop_file=output/f"desktop-{screen}.png";mobile_file=output/f"mobile-{screen}.png"
            screenshot(url,desktop_file,"1440,1000");screenshot(url,mobile_file,"390,844");desktop.append(desktop_file);mobile.append(mobile_file);report["screens"].append({"screen":screen,"desktop":{"path":str(desktop_file),"bytes":desktop_file.stat().st_size},"mobile":{"path":str(mobile_file),"bytes":mobile_file.stat().st_size}});print(f"captured {screen}",flush=True)
        service=SaaSService.from_env()
        with service.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM content_books WHERE visibility IN ('private','draft') ORDER BY updated_at DESC LIMIT 1");private=(service._one(cursor)or{}).get("id")
                cursor.execute("SELECT id FROM catalog_books WHERE publication_status='published' AND rights_status IN ('public_domain','licensed') ORDER BY updated_at DESC LIMIT 1");official=(service._one(cursor)or{}).get("id")
        for label,kind,identifier in (("workspace-reader","workspace",private),("official-reader","official",official)):
            if only and only!=label:continue
            if not identifier:continue
            url=base+"/api/auth/debug-browser-login?"+urlencode({"token":secret,"screen":"reader","reader":kind,"id":identifier});desktop_file=output/f"desktop-{label}.png";mobile_file=output/f"mobile-{label}.png";screenshot(url,desktop_file,"1440,1000");screenshot(url,mobile_file,"390,844");report["screens"].append({"screen":label,"desktop":{"path":str(desktop_file),"bytes":desktop_file.stat().st_size},"mobile":{"path":str(mobile_file),"bytes":mobile_file.stat().st_size}});print(f"captured {label}",flush=True)
        if only:(output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(report,ensure_ascii=False,indent=2));return report
        contact_sheet(desktop,output/"desktop-contact-sheet.png",480,333);contact_sheet(mobile,output/"mobile-contact-sheet.png",260,563);(output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(report,ensure_ascii=False,indent=2));return report
    except Exception as exc:
        report["status"]="failed";report["error"]=str(exc);(output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(report,ensure_ascii=False,indent=2),file=sys.stderr);return report


def main()->int:
    port=int(os.environ.get("READER_PORT","8794"));base=f"http://127.0.0.1:{port}";email=str(os.environ.get("BOOTSTRAP_ADMIN_EMAIL","")).strip();password=str(os.environ.get("SHIYUE_BROWSER_PASSWORD",""));secret=secrets.token_urlsafe(32)
    if not email or not password:raise SystemExit("BOOTSTRAP_ADMIN_EMAIL and SHIYUE_BROWSER_PASSWORD are required")
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");output=ROOT/".local/debug/walkthrough"/stamp;log=(output/"reader.log");output.mkdir(parents=True,exist_ok=True)
    with log.open("w") as stream:
        environment={**os.environ,"SHIYUE_SAAS_ENABLED":"1","READER_HOST":"127.0.0.1","READER_PORT":str(port),"BOOTSTRAP_ADMIN_EMAIL":"","BOOTSTRAP_ADMIN_PASSWORD":"","SHIYUE_BROWSER_AUDIT_SECRET":secret,"SHIYUE_BROWSER_AUDIT_EMAIL":email,"SHIYUE_BROWSER_AUDIT_PASSWORD":password};reader=subprocess.Popen([sys.executable,str(ROOT/"tools/reader_server.py")],cwd=ROOT,env=environment,stdout=stream,stderr=stream,start_new_session=True)
        try:
            deadline=time.time()+20
            while time.time()<deadline:
                if reader.poll() is not None:raise RuntimeError("reader exited during startup")
                try:
                    if json.loads(urlopen(base+"/api/health",timeout=2).read()).get("saasEnabled"):break
                except Exception:time.sleep(.1)
            else:raise RuntimeError("reader did not become healthy")
            return 0 if capture_existing(base,secret,output).get("status")=="ok" else 1
        finally:stop(reader)


if __name__=="__main__":raise SystemExit(main())
