#!/usr/bin/env python3
"""Read-only SaaS launch readiness audit that never prints secret values."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from saas_auth import SaaSService


ROOT=Path(__file__).resolve().parents[1]


def env_file(path:Path)->dict[str,str]:
    values={}
    if not path.is_file():return values
    for line in path.read_text(encoding="utf-8",errors="replace").splitlines():
        line=line.strip()
        if not line or line.startswith("#") or "=" not in line:continue
        key,value=line.split("=",1);values[key.strip()]=value.strip().strip('"').strip("'")
    return values


def configured(environment:dict[str,str],key:str)->bool:return bool(str(environment.get(key,"")).strip())


def executable(environment:dict[str,str],key:str,default:str)->bool:
    value=str(environment.get(key,default) or default);path=Path(value).expanduser()
    return path.is_file() or bool(shutil.which(value))


def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument("--env-file",type=Path,default=ROOT/".env");parser.add_argument("--json",action="store_true");args=parser.parse_args()
    environment={**env_file(args.env_file),**os.environ};checks=[]
    def add(name:str,ok:bool,detail:str,required:bool=True)->None:checks.append({"name":name,"ok":bool(ok),"required":required,"detail":detail})

    for key in ("DATABASE_URL","SESSION_SECRET","APP_BASE_URL","MEDIA_ROOT"):
        add(key,configured(environment,key),"已配置" if configured(environment,key) else "缺失")
    smtp=all(configured(environment,key) for key in ("SMTP_HOST","SMTP_PORT","SMTP_USER","SMTP_PASSWORD","SMTP_FROM"));add("SMTP",smtp,"注册验证和找回密码所需" if not smtp else "已配置")
    ai=all(configured(environment,key) for key in ("SHIYUE_DIOCO_TOKEN","SHIYUE_DIOCO_EMAIL"));add("平台 AI",ai,"语境精讲和句法分析所需" if not ai else "已配置")
    backup_root=Path(environment.get("SAAS_BACKUP_ROOT","")).expanduser() if configured(environment,"SAAS_BACKUP_ROOT") else None
    external=bool(backup_root and backup_root.is_absolute() and ROOT not in backup_root.parents and backup_root!=ROOT);add("外部备份目录",external,"请将 SAAS_BACKUP_ROOT 指向项目目录之外的绝对路径" if not external else str(backup_root))
    add("FFmpeg",executable(environment,"SHIYUE_FFMPEG","ffmpeg"),"本地视频和 YouTube 处理器")
    add("Node.js",executable(environment,"SHIYUE_NODE","node"),"yt-dlp JavaScript 运行时")
    add("yt-dlp",executable(environment,"SHIYUE_YTDLP",str(ROOT/".local/bin/yt-dlp")),"YouTube 下载器")
    add("Whisper",executable(environment,"SHIYUE_WHISPER_CLI",str(ROOT/"tools/vendor/whisper.cpp/build/bin/whisper-cli")),"音视频转写")
    add("PDF OCR",executable(environment,"SHIYUE_PDF_OCR",str(ROOT/".local/bin/pdf_ocr")),"PDF 导入")
    migration_files=sorted((ROOT/"tools/saas_migrations").glob("*.sql"));latest=migration_files[-1].name if migration_files else "none";add("迁移文件",latest=="0013_workspace_ai.sql",f"{len(migration_files)} 个，最新 {latest}")
    database_ok=False;applied=[]
    if configured(environment,"DATABASE_URL"):
        try:
            service=SaaSService(environment["DATABASE_URL"],environment)
            with service.transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT version FROM schema_migrations ORDER BY version");applied=[row["version"] for row in service._many(cursor)]
            database_ok=latest in applied
            add("PostgreSQL",database_ok,f"可连接，已应用 {len(applied)} 个迁移，最新 {applied[-1] if applied else 'none'}")
        except Exception as exc:add("PostgreSQL",False,f"不可连接或迁移未完成：{type(exc).__name__}")
    else:add("PostgreSQL",False,"DATABASE_URL 缺失")
    local_backups=sorted((ROOT/".local/saas-backups").glob("*/backup.json"));latest_backup=local_backups[-1].parent.name if local_backups else "none";add("本机备份",bool(local_backups),f"最新 {latest_backup}",required=False)
    enabled=str(environment.get("SHIYUE_SAAS_ENABLED","0")).strip()=="1";add("SaaS 开关",not enabled,"验收完成前应保持关闭" if not enabled else "当前已开启；请确认所有必需项已通过",required=False)
    blockers=[item for item in checks if item["required"] and not item["ok"]];result={"checkedAt":datetime.now(timezone.utc).isoformat(),"ready":not blockers,"blockers":[item["name"] for item in blockers],"checks":checks}
    if args.json:print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        for item in checks:print(f"{'PASS' if item['ok'] else 'BLOCK' if item['required'] else 'INFO'}  {item['name']}: {item['detail']}")
        print("READY" if result["ready"] else "NOT READY: "+", ".join(result["blockers"]))
    return 0 if result["ready"] else 2


if __name__=="__main__":raise SystemExit(main())
