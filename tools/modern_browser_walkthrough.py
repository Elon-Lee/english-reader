#!/usr/bin/env python3
"""Authenticated desktop/mobile walkthrough for the React commercial workspace."""
from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

import psycopg

from browser_walkthrough import screenshot
from saas_auth import ROOT


SCREENS = ("workspace", "catalog", "library", "stats", "vocab", "rewards", "membership", "admin", "platform", "settings")


def stop(process):
    if process and process.poll() is None:
        try: os.killpg(process.pid, signal.SIGTERM); process.wait(timeout=5)
        except Exception:
            try: os.killpg(process.pid, signal.SIGKILL)
            except Exception: pass


def main() -> int:
    database_url = str(os.environ.get("DATABASE_URL", "")).strip()
    email = str(os.environ.get("SHIYUE_BROWSER_AUDIT_EMAIL", "")).strip()
    password = str(os.environ.get("SHIYUE_BROWSER_AUDIT_PASSWORD", ""))
    if not urlsplit(database_url).path.rsplit("/", 1)[-1].endswith("_test"):
        raise SystemExit("DATABASE_URL must point to a database ending in _test")
    if not email or not password:
        raise SystemExit("SHIYUE_BROWSER_AUDIT_EMAIL and SHIYUE_BROWSER_AUDIT_PASSWORD are required")
    private_book_id = ""
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE email=%s", (email,)); row = cursor.fetchone()
            if not row: raise SystemExit("browser audit user not found")
            # Browser acceptance always uses the disposable *_test database.
            # Revoke stale walkthrough devices so repeated local runs do not
            # fail before the UI is reached on single-device plans.
            cursor.execute("UPDATE user_sessions SET revoked_at=NOW() WHERE user_id=%s AND revoked_at IS NULL", (row[0],))
            cursor.execute("UPDATE devices SET revoked_at=NOW() WHERE user_id=%s AND revoked_at IS NULL", (row[0],))
            cursor.execute("SELECT id FROM roles WHERE name='admin'")
            role = cursor.fetchone()
            if not role:
                cursor.execute("INSERT INTO roles(id,name,description) VALUES('admin','admin','temporary browser walkthrough admin role') RETURNING id")
                role = cursor.fetchone()
            cursor.execute("INSERT INTO user_roles(user_id,role_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (row[0], role[0]))
            cursor.execute("SELECT id FROM content_books WHERE owner_id=%s AND visibility IN ('private','draft') ORDER BY updated_at DESC LIMIT 1", (row[0],))
            private = cursor.fetchone(); private_book_id = private[0] if private else ""
    port = int(os.environ.get("READER_PORT", "8794")); base = f"http://127.0.0.1:{port}"; secret = secrets.token_urlsafe(32)
    output = ROOT / ".local/debug/modern-walkthrough" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); output.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "SHIYUE_SAAS_ENABLED": "1", "BOOTSTRAP_ADMIN_EMAIL": "", "BOOTSTRAP_ADMIN_PASSWORD": "", "READER_HOST": "127.0.0.1", "READER_PORT": str(port), "SHIYUE_BROWSER_AUDIT_SECRET": secret, "SHIYUE_BROWSER_AUDIT_EMAIL": email, "SHIYUE_BROWSER_AUDIT_PASSWORD": password}
    process = subprocess.Popen([sys.executable, str(ROOT / "tools/reader_server.py")], cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    report = {"status": "ok", "baseUrl": base, "output": str(output), "screens": []}
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            if process.poll() is not None: raise RuntimeError("modern walkthrough server exited")
            try:
                if json.loads(urlopen(base + "/api/health", timeout=2).read()).get("saasEnabled"): break
            except Exception: time.sleep(.1)
        else: raise RuntimeError("modern walkthrough server did not become healthy")
        device_key = f"browser-audit-{secrets.token_hex(12)}"
        desktop_only = str(os.environ.get("SHIYUE_WALKTHROUGH_DESKTOP_ONLY", "")).strip().lower() in {"1", "true", "yes", "on"}
        requested = [item.strip() for item in str(os.environ.get("SHIYUE_WALKTHROUGH_ONLY", "")).split(",") if item.strip()]
        screens = tuple(item for item in requested if item in SCREENS) or SCREENS
        for screen_name in screens:
            url = base + "/api/auth/debug-browser-login?" + urlencode({"token": secret, "screen": screen_name, "modern": "1", "device": device_key})
            desktop = output / f"desktop-{screen_name}.png"
            screenshot(url, desktop, "1440,1000")
            entry={"screen": screen_name, "desktop": {"path": str(desktop), "bytes": desktop.stat().st_size}}
            if not desktop_only:
                mobile = output / f"mobile-{screen_name}.png"; screenshot(url, mobile, "390,844"); entry["mobile"]={"path": str(mobile), "bytes": mobile.stat().st_size}
            report["screens"].append(entry)
            print(f"captured modern {screen_name}", flush=True)
        if private_book_id and (not requested or "reader" in requested):
            url = base + "/api/auth/debug-browser-login?" + urlencode({"token": secret, "screen": "reader", "modern": "1", "reader": "workspace", "id": private_book_id, "device": device_key})
            desktop = output / "desktop-reader.png"
            screenshot(url, desktop, "1440,1000")
            entry={"screen": "reader", "desktop": {"path": str(desktop), "bytes": desktop.stat().st_size}}
            if not desktop_only:
                mobile = output / "mobile-reader.png"; screenshot(url, mobile, "390,844"); entry["mobile"]={"path": str(mobile), "bytes": mobile.stat().st_size}
            report["screens"].append(entry)
            print("captured modern reader", flush=True)
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2)); return 0
    except Exception as exc:
        report["status"] = "failed"; report["error"] = str(exc); (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"); print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr); return 1
    finally: stop(process)


if __name__ == "__main__": raise SystemExit(main())
