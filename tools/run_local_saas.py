#!/usr/bin/env python3
"""Run the formal local SaaS server with a file-backed debug SMTP sink."""
from __future__ import annotations

import os
import signal
import socketserver
import subprocess
import sys
import threading
import time
import uuid
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from saas_auth import ROOT, SaaSService


class SMTPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b"220 shiyue-debug ESMTP\r\n");self.wfile.flush();message=[];data_mode=False
        while True:
            line=self.rfile.readline()
            if not line:break
            text=line.decode("utf-8",errors="replace").rstrip("\r\n")
            if data_mode:
                if text==".":
                    path=self.server.outbox/(time.strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex+".eml");path.write_text("\n".join(message)+"\n",encoding="utf-8");message=[];data_mode=False;self.wfile.write(b"250 2.0.0 queued\r\n");self.wfile.flush();continue
                if text.startswith(".."):text=text[1:]
                message.append(text);continue
            command=text.split(" ",1)[0].upper()
            if command in {"EHLO","HELO"}:self.wfile.write(b"250-shiyue-debug\r\n250 SIZE 10485760\r\n")
            elif command in {"MAIL","RCPT","RSET","NOOP"}:self.wfile.write(b"250 2.0.0 ok\r\n")
            elif command=="DATA":data_mode=True;self.wfile.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
            elif command=="QUIT":self.wfile.write(b"221 2.0.0 bye\r\n");self.wfile.flush();break
            else:self.wfile.write(b"250 2.0.0 ok\r\n")
            self.wfile.flush()


class SMTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address=True
    daemon_threads=True
    def __init__(self,address,handler,outbox):self.outbox=outbox;super().__init__(address,handler)


def main()->int:
    port=int(os.environ.get("READER_PORT","8790"));smtp_port=int(os.environ.get("SHIYUE_DEBUG_SMTP_PORT","1025"));outbox=ROOT/".local/smtp-outbox";outbox.mkdir(parents=True,exist_ok=True)
    smtp=SMTPServer(("127.0.0.1",smtp_port),SMTPHandler,outbox);threading.Thread(target=smtp.serve_forever,daemon=True).start()
    walkthrough=os.environ.get("SHIYUE_RUN_WALKTHROUGH","").strip().lower() in {"1","true","yes","on"};secret=secrets.token_urlsafe(32) if walkthrough else ""
    environment={**os.environ,"SHIYUE_DEPLOYMENT_MODE":"local","SHIYUE_SAAS_ENABLED":"1","READER_HOST":"0.0.0.0","READER_PORT":str(port),"APP_BASE_URL":f"http://localhost:{port}","SMTP_HOST":"127.0.0.1","SMTP_PORT":str(smtp_port),"SMTP_USER":"","SMTP_PASSWORD":"","SMTP_FROM":"debug@shiyue.local"}
    if walkthrough:environment.update({"SHIYUE_BROWSER_AUDIT_SECRET":secret,"SHIYUE_BROWSER_AUDIT_EMAIL":str(os.environ.get("BOOTSTRAP_ADMIN_EMAIL","")).strip(),"SHIYUE_BROWSER_AUDIT_PASSWORD":str(os.environ.get("SHIYUE_BROWSER_PASSWORD",""))})
    before=set(outbox.glob("*.eml"));sent=SaaSService(environment=environment)._send_mail("debug-recipient@local.test","拾页本地 SMTP 自检","本邮件只保存到本机调试目录。")
    after=set(outbox.glob("*.eml"));
    if not sent or not after-before:raise SystemExit("debug SMTP self-test failed")
    process=subprocess.Popen([sys.executable,str(ROOT/"tools/reader_server.py")],cwd=ROOT,env=environment,start_new_session=True)
    def stop(*_):
        if process.poll() is None:
            try:os.killpg(process.pid,signal.SIGTERM)
            except Exception:pass
        smtp.shutdown();smtp.server_close()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        deadline=time.time()+15
        while time.time()<deadline:
            if process.poll() is not None:raise RuntimeError("SaaS reader exited during startup")
            try:
                with urlopen(f"http://127.0.0.1:{port}/api/health",timeout=2) as response:
                    if response.status==200:break
            except Exception:time.sleep(.1)
        else:raise RuntimeError("SaaS reader did not become healthy")
        print(f"拾页 SaaS 本地调试：http://localhost:{port}",flush=True);print(f"SMTP 调试捕获：127.0.0.1:{smtp_port} → {outbox}",flush=True);print("平台 AI 未配置时会返回受控提示；SaaS 总开关仅在本进程内临时开启。",flush=True)
        if walkthrough:
            from browser_walkthrough import capture_existing
            output=ROOT/".local/debug/walkthrough"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");report=capture_existing(f"http://127.0.0.1:{port}",secret,output);return 0 if report.get("status")=="ok" else 1
        return process.wait()
    finally:stop()


if __name__=="__main__":raise SystemExit(main())
