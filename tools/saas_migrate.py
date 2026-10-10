#!/usr/bin/env python3
"""Controlled PostgreSQL migration and legacy SQLite import entry point."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from saas_auth import ROOT, SaaSConfigurationError, SaaSService


def parse_expiry(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("请使用 ISO-8601 时间，例如 2026-12-31T23:59:59+08:00") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("过期时间必须带时区，例如 +08:00")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="拾页 SaaS PostgreSQL migration utility")
    parser.add_argument("--migrate", action="store_true", help="应用尚未执行的 PostgreSQL migration")
    parser.add_argument("--bootstrap-admin", action="store_true", help="按环境变量创建或确认管理员")
    parser.add_argument("--reset-admin-password", action="store_true", help="用 BOOTSTRAP_ADMIN_PASSWORD 重设已有管理员密码")
    parser.add_argument("--import-legacy", action="store_true", help="把当前 SQLite 数据作为管理员私人数据导入")
    parser.add_argument("--legacy-db", type=Path, default=ROOT / ".local/library.sqlite3", help="只读 SQLite 源库路径")
    parser.add_argument("--create-invitation", metavar="CODE", help="创建一个邀请码（需已有管理员）")
    parser.add_argument("--max-uses", type=int, default=1, help="邀请码最大使用次数")
    parser.add_argument("--expires-at", type=parse_expiry, default=None, help="邀请码 ISO-8601 过期时间")
    parser.add_argument("--note", default="", help="邀请码后台备注")
    args = parser.parse_args()
    if not any((args.migrate, args.bootstrap_admin, args.reset_admin_password, args.import_legacy, args.create_invitation)):
        parser.error("至少指定一个操作；通常先执行 --migrate --bootstrap-admin --import-legacy")

    service = SaaSService(os.environ.get("DATABASE_URL", ""))
    try:
        output: dict[str, object] = {}
        if args.migrate:
            output["appliedMigrations"] = service.migrate()
        admin = None
        if args.bootstrap_admin:
            admin = service.bootstrap_admin()
            if not admin:
                raise SaaSConfigurationError("需要设置 BOOTSTRAP_ADMIN_EMAIL 和 BOOTSTRAP_ADMIN_PASSWORD。")
            output["admin"] = {"id": admin["id"], "email": admin["email"]}
        if args.reset_admin_password:
            service.reset_admin_password()
            output["adminPassword"] = "reset"
        if args.import_legacy:
            if admin is None:
                admin = service.bootstrap_admin()
            if not admin:
                raise SaaSConfigurationError("导入旧数据前需要已有管理员；请设置 bootstrap 环境变量并先执行 --bootstrap-admin。")
            output["legacyImport"] = service.import_legacy_sqlite(args.legacy_db, str(admin["id"]))
        if args.create_invitation:
            if admin is None:
                admin = service.bootstrap_admin()
            if not admin:
                raise SaaSConfigurationError("创建邀请码需要已有管理员。")
            invitation = service.create_invitation(args.create_invitation, args.max_uses, args.expires_at, str(admin["id"]), args.note)
            output["invitation"] = {key: invitation[key] for key in ("id", "code", "status", "max_uses", "used_count", "expires_at")}
        print(json.dumps(output, ensure_ascii=False, default=str, indent=2))
        return 0
    except (SaaSConfigurationError, ValueError) as exc:
        parser.exit(2, f"配置错误：{exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
