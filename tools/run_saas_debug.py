#!/usr/bin/env python3
"""Run migrations, phases 1–9, formal DB smoke, backup and verification."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql

from saas_auth import ROOT, SaaSService


def database_url(base:str,name:str)->str:
    parsed=urlsplit(base);return urlunsplit((parsed.scheme,parsed.netloc,"/"+name,parsed.query,parsed.fragment))


def database_name(url:str)->str:return urlsplit(url).path.rsplit("/",1)[-1]


def ensure_database(url:str)->None:
    name=database_name(url);admin_url=database_url(url,"postgres")
    with psycopg.connect(admin_url,autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname=%s",(name,))
            if not cursor.fetchone():cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def run(command:list[str],environment:dict[str,str])->str:
    completed=subprocess.run(command,cwd=ROOT,env=environment,text=True,capture_output=True)
    if completed.returncode:
        if completed.stdout:print(completed.stdout,file=sys.stderr)
        if completed.stderr:print(completed.stderr,file=sys.stderr)
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}")
    if completed.stdout:print(completed.stdout,end="")
    return completed.stdout.strip()


def main()->int:
    formal_url=str(os.environ.get("DATABASE_URL","")).strip()
    if not formal_url:raise SystemExit("DATABASE_URL is required")
    formal_name=database_name(formal_url);test_name=str(os.environ.get("SHIYUE_SAAS_TEST_DATABASE_NAME","shiyue_phase1_test")).strip()
    if not test_name.endswith("_test"):raise SystemExit("test database name must end with _test")
    test_url=database_url(formal_url,test_name);ensure_database(formal_url);ensure_database(test_url)
    service=SaaSService(formal_url,{**os.environ,"DATABASE_URL":formal_url,"SHIYUE_SAAS_ENABLED":"1"});applied=service.migrate();print(json.dumps({"formalDatabase":formal_name,"appliedMigrations":applied},ensure_ascii=False))
    test_environment={**os.environ,"SHIYUE_SAAS_TEST_DATABASE_URL":test_url,"SHIYUE_SAAS_ENABLED":"1"};phase_results=[]
    for phase in range(1,10):
        script=ROOT/f"tools/test_saas_phase{phase}_integration.py";print(f"\n=== SaaS phase {phase} ===",flush=True);run([sys.executable,str(script)],test_environment);phase_results.append(phase)
    with service.transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version FROM schema_migrations ORDER BY version");migrations=[row["version"] for row in service._many(cursor)]
            counts={}
            for table in ("users","content_books","media_assets","workspace_import_tasks","workspace_ai_results"):
                cursor.execute(sql.SQL("SELECT COUNT(*) AS total FROM {}").format(sql.Identifier(table)));counts[table]=int((service._one(cursor)or{"total":0})["total"])
    media_root=Path(os.environ.get("MEDIA_ROOT",str(ROOT/"books"))).expanduser().resolve();backup_root=Path(os.environ.get("SAAS_BACKUP_ROOT","") or ROOT/".local/saas-backups").expanduser();backup_output=run([sys.executable,str(ROOT/"tools/saas_backup.py"),"--database-url",formal_url,"--media-root",str(media_root),"--output-root",str(backup_root)],os.environ.copy());backup=json.loads(backup_output.splitlines()[-1]);run([sys.executable,str(ROOT/"tools/saas_backup_verify.py"),backup["backup"],"--media-root",str(media_root)],os.environ.copy())
    print(json.dumps({"status":"ok","formalDatabase":formal_name,"testDatabase":test_name,"phases":phase_results,"migrations":migrations,"counts":counts,"backup":backup["backup"]},ensure_ascii=False,indent=2));return 0


if __name__=="__main__":raise SystemExit(main())
