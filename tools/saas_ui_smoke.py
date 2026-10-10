#!/usr/bin/env python3
"""Render the formal SaaS login surface in real Chrome and capture screenshots."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen


ROOT=Path(__file__).resolve().parents[1];PORT=int(os.environ.get("READER_PORT","8792"));BASE=f"http://127.0.0.1:{PORT}"


def chrome_screenshot(chrome:Path,target:Path,size:str)->None:
    target.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="shiyue-saas-ui-") as profile:
        command=[str(chrome),"--headless","--disable-gpu","--no-sandbox","--disable-dev-shm-usage","--disable-background-networking","--disable-sync","--metrics-recording-only","--virtual-time-budget=5000",f"--user-data-dir={profile}",f"--window-size={size}",f"--screenshot={target}",BASE+"/"]
        try:subprocess.run(command,text=True,capture_output=True,timeout=30,check=True)
        except subprocess.TimeoutExpired:
            if not target.is_file() or target.stat().st_size<=10_000:raise


def main()->int:
    process=subprocess.Popen([sys.executable,str(ROOT/"tools/reader_server.py")],cwd=ROOT,env=os.environ.copy(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    try:
        deadline=time.time()+15
        while time.time()<deadline:
            if process.poll() is not None:raise RuntimeError("SaaS UI server exited during startup")
            try:
                health=json.loads(urlopen(BASE+"/api/health",timeout=2).read());break
            except Exception:time.sleep(.1)
        else:raise RuntimeError("SaaS UI server did not become healthy")
        if not health.get("saasEnabled"):raise AssertionError("SaaS mode is not enabled")
        html=urlopen(BASE+"/",timeout=5).read().decode();required=['id="saasAuth"','id="saasLoginForm"','id="saasRegisterForm"','id="saasForgotForm"','app.js?v=20261010-6','styles.css?v=20261010-4']
        missing=[item for item in required if item not in html]
        if missing:raise AssertionError("missing SaaS UI markers: "+", ".join(missing))
        chrome=Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome");debug=ROOT/".local/debug";debug.mkdir(parents=True,exist_ok=True);desktop=debug/"saas-login-desktop.png";mobile=debug/"saas-login-mobile.png"
        chrome_screenshot(chrome,desktop,"1440,1000");chrome_screenshot(chrome,mobile,"390,844")
        print(json.dumps({"status":"ok","baseUrl":BASE,"health":health,"screenshots":{"desktop":{"path":str(desktop),"bytes":desktop.stat().st_size},"mobile":{"path":str(mobile),"bytes":mobile.stat().st_size}}},ensure_ascii=False,indent=2));return 0
    finally:
        if process.poll() is None:
            try:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=5)
            except Exception:
                try:os.killpg(process.pid,signal.SIGKILL)
                except Exception:pass


if __name__=="__main__":raise SystemExit(main())
