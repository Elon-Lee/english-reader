#!/usr/bin/env python3
"""PostgreSQL-backed account and invitation service for the SaaS rollout.

The existing reader intentionally remains usable without this module's optional
PostgreSQL dependency.  Set SHIYUE_SAAS_ENABLED=1 only after running the
migration command in ``tools/saas_migrate.py``.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = Path(__file__).with_name("saas_migrations")
SESSION_TTL_DAYS = 30
VERIFY_TTL_HOURS = 24
RESET_TTL_HOURS = 2
PASSWORD_MIN_LENGTH = 10
INVITATION_VERIFICATION_EMAIL_LIMIT = 3
PASSWORD_RESET_EMAIL_LIMIT = 3


class SaaSError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}

    def payload(self) -> dict[str, Any]:
        return {"code": self.code, "error": self.message, **self.details}


class SaaSConfigurationError(RuntimeError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None = None) -> str:
    return (value or utcnow()).isoformat(timespec="seconds")


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_id() -> str:
    return uuid.uuid4().hex


def random_token() -> str:
    return secrets.token_urlsafe(48)


def normalize_email(value: Any) -> str:
    email = str(value or "").strip().casefold()
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise SaaSError("invalid_email", "请输入有效的邮箱地址。")
    return email


def validate_password(value: Any) -> str:
    password = str(value or "")
    if len(password) < PASSWORD_MIN_LENGTH:
        raise SaaSError("weak_password", f"密码至少需要 {PASSWORD_MIN_LENGTH} 个字符。")
    if len(password) > 1024:
        raise SaaSError("weak_password", "密码过长。")
    return password


def hash_password(password: str) -> str:
    """Use a self-describing salted scrypt encoding suitable for DB storage."""
    salt = secrets.token_bytes(16)
    n, r, p = 16384, 8, 1
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=64)
    return "scrypt$n={n},r={r},p={p}${salt}${digest}".format(
        n=n,
        r=r,
        p=p,
        salt=base64.urlsafe_b64encode(salt).decode("ascii"),
        digest=base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, options, encoded_salt, encoded_digest = encoded.split("$", 3)
        if algorithm != "scrypt":
            return False
        values = dict(part.split("=", 1) for part in options.split(","))
        salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
        expected = base64.urlsafe_b64decode(encoded_digest.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(values["n"]), r=int(values["r"]), p=int(values["p"]), dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (KeyError, ValueError, TypeError, binascii.Error):
        return False


def device_limit(plan_version: str) -> int:
    value = str(plan_version or "free-v2").casefold()
    if value.startswith("pro-"):
        return 5
    if value.startswith("advanced-") or value.startswith("advance-"):
        return 2
    return 1


class SaaSService:
    """Small DB-API layer that uses PostgreSQL only; no SQLite fallback exists."""

    def __init__(self, database_url: str | None = None, environment: dict[str, str] | None = None):
        self.environment = environment if environment is not None else os.environ
        self.database_url = (database_url if database_url is not None else self.environment.get("DATABASE_URL", "")).strip()
        self.enabled = self.environment.get("SHIYUE_SAAS_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}

    @classmethod
    def from_env(cls) -> "SaaSService":
        return cls()

    def assert_configured(self) -> None:
        if not self.database_url:
            raise SaaSConfigurationError("SHIYUE_SAAS_ENABLED=1 requires DATABASE_URL.")

    def assert_runtime_configured(self) -> None:
        """Check secret material required when the HTTP SaaS surface is live."""
        self.assert_configured()
        secret = self.environment.get("SESSION_SECRET", "")
        if len(secret) < 32:
            raise SaaSConfigurationError("SHIYUE_SAAS_ENABLED=1 requires a SESSION_SECRET of at least 32 characters.")

    def _connect(self):
        self.assert_configured()
        try:
            import psycopg  # type: ignore
        except ImportError as exc:
            raise SaaSConfigurationError("缺少 psycopg；请先执行 `python3 -m pip install -r requirements-saas.txt`。") from exc
        return psycopg.connect(self.database_url)

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _one(cursor: Any) -> dict[str, Any] | None:
        row = cursor.fetchone()
        if row is None:
            return None
        return {column.name: value for column, value in zip(cursor.description, row)}

    @staticmethod
    def _many(cursor: Any) -> list[dict[str, Any]]:
        rows = cursor.fetchall()
        return [{column.name: value for column, value in zip(cursor.description, row)} for row in rows]

    def migrate(self) -> list[str]:
        """Apply each SQL migration once, recording it transactionally."""
        applied: list[str] = []
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""
                )
                for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                    version = path.name
                    cursor.execute("SELECT 1 FROM schema_migrations WHERE version=%s", (version,))
                    if cursor.fetchone():
                        continue
                    cursor.execute(path.read_text(encoding="utf-8"))
                    cursor.execute("INSERT INTO schema_migrations(version) VALUES(%s)", (version,))
                    applied.append(version)
        return applied

    def ensure_migrated(self) -> None:
        """Fail fast when a SaaS server is pointed at an unmigrated database."""
        expected = [path.name for path in sorted(MIGRATIONS_DIR.glob("*.sql"))]
        try:
            with self.transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT to_regclass('public.schema_migrations') AS table_name")
                    found = self._one(cursor)
                    if not found or not found["table_name"]:
                        raise SaaSConfigurationError("数据库尚未迁移；请先执行 `python3 tools/saas_migrate.py --migrate`。")
                    cursor.execute("SELECT version FROM schema_migrations")
                    present = {str(row["version"]) for row in self._many(cursor)}
        except SaaSConfigurationError:
            raise
        missing = [version for version in expected if version not in present]
        if missing:
            raise SaaSConfigurationError("数据库缺少 migration：" + ", ".join(missing))

    def _ensure_role(self, cursor: Any, name: str, description: str = "") -> str:
        role_id = f"role-{name}"
        cursor.execute(
            """INSERT INTO roles(id,name,description) VALUES(%s,%s,%s)
            ON CONFLICT (name) DO UPDATE SET description=EXCLUDED.description RETURNING id""",
            (role_id, name, description),
        )
        row = self._one(cursor)
        return str(row["id"])

    def bootstrap_admin(self, email: str | None = None, password: str | None = None) -> dict[str, Any] | None:
        """Create the designated administrator once, never logging a password."""
        configured_email = email or self.environment.get("BOOTSTRAP_ADMIN_EMAIL", "")
        if not configured_email:
            return None
        admin_email = normalize_email(configured_email)
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                admin_role = self._ensure_role(cursor, "admin", "平台管理员")
                cursor.execute("SELECT id,email,email_verified_at FROM users WHERE email=%s FOR UPDATE", (admin_email,))
                existing = self._one(cursor)
                if existing:
                    user_id = str(existing["id"])
                    cursor.execute("UPDATE users SET email_verified_at=COALESCE(email_verified_at,NOW()),updated_at=NOW() WHERE id=%s", (user_id,))
                else:
                    configured_password = password or self.environment.get("BOOTSTRAP_ADMIN_PASSWORD", "")
                    if not configured_password:
                        raise SaaSConfigurationError("首次创建管理员需要 BOOTSTRAP_ADMIN_PASSWORD（创建后应立即从环境中移除）。")
                    password_value = validate_password(configured_password)
                    user_id = new_id()
                    cursor.execute(
                        """INSERT INTO users(id,email,password_hash,display_name,email_verified_at,plan_version)
                        VALUES(%s,%s,%s,%s,NOW(),'pro-v1')""",
                        (user_id, admin_email, hash_password(password_value), "管理员"),
                    )
                cursor.execute(
                    "INSERT INTO user_roles(user_id,role_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                    (user_id, admin_role),
                )
                cursor.execute("SELECT id,email,display_name,plan_version,email_verified_at FROM users WHERE id=%s", (user_id,))
                return self._one(cursor)

    def reset_admin_password(self, email: str | None = None, password: str | None = None) -> None:
        """Operational recovery for the local bootstrap admin.

        The password deliberately comes from an environment variable or caller
        memory rather than a command-line argument, so it is not retained in
        shell history or process listings.
        """
        configured_email = email or self.environment.get("BOOTSTRAP_ADMIN_EMAIL", "")
        configured_password = password or self.environment.get("BOOTSTRAP_ADMIN_PASSWORD", "")
        if not configured_email or not configured_password:
            raise SaaSConfigurationError("重设管理员密码需要 BOOTSTRAP_ADMIN_EMAIL 和 BOOTSTRAP_ADMIN_PASSWORD。")
        admin_email, password_value = normalize_email(configured_email), validate_password(configured_password)
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT u.id FROM users u JOIN user_roles ur ON ur.user_id=u.id JOIN roles r ON r.id=ur.role_id
                    WHERE u.email=%s AND r.name='admin' FOR UPDATE""",
                    (admin_email,),
                )
                administrator = self._one(cursor)
                if not administrator:
                    raise SaaSConfigurationError("指定邮箱不是现有管理员。")
                cursor.execute("UPDATE users SET password_hash=%s,updated_at=NOW() WHERE id=%s", (hash_password(password_value), administrator["id"]))
                cursor.execute("UPDATE user_sessions SET revoked_at=NOW() WHERE user_id=%s AND revoked_at IS NULL", (administrator["id"],))

    def create_invitation(self, code: str, max_uses: int = 1, expires_at: datetime | None = None, created_by: str | None = None, note: str = "", channel: str = "") -> dict[str, Any]:
        normalized = re.sub(r"\s+", "", str(code or "").upper())
        if not re.fullmatch(r"[A-Z0-9_-]{4,64}", normalized):
            raise SaaSError("invalid_invitation", "邀请码需为 4～64 位的大写字母、数字、下划线或连字符。")
        if not isinstance(max_uses, int) or max_uses < 1 or max_uses > 1_000_000:
            raise SaaSError("invalid_invitation", "邀请码使用次数无效。")
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                batch_id="invite-batch-"+new_id()
                cursor.execute("""INSERT INTO invitation_batches(id,requested_count,max_uses,expires_at,created_by,note,channel)
                VALUES(%s,1,%s,%s,%s,%s,%s)""",(batch_id,max_uses,expires_at,created_by,str(note or "")[:1000],str(channel or "")[:100]))
                cursor.execute(
                    """INSERT INTO invitations(id,code,max_uses,expires_at,created_by,note,channel,batch_id)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (new_id(), normalized, max_uses, expires_at, created_by, str(note or "")[:1000], str(channel or "")[:100],batch_id),
                )
                return self._one(cursor) or {}

    def _new_verification(self, cursor: Any, user_id: str) -> str:
        raw = random_token()
        cursor.execute("UPDATE email_verifications SET consumed_at=NOW() WHERE user_id=%s AND consumed_at IS NULL", (user_id,))
        cursor.execute(
            "INSERT INTO email_verifications(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",
            (new_id(), user_id, token_hash(raw), utcnow() + timedelta(hours=VERIFY_TTL_HOURS)),
        )
        return raw

    def register(self, email: Any, password: Any, invitation_code: Any, display_name: Any = "", ip_address: str = "") -> dict[str, Any]:
        normalized_email = normalize_email(email)
        password_value = validate_password(password)
        code = re.sub(r"\s+", "", str(invitation_code or "").upper())
        if not code:
            raise SaaSError("invitation_required", "注册需要有效邀请码。", 400)
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM invitations WHERE code=%s FOR UPDATE", (code,))
                invitation = self._one(cursor)
                if not invitation or invitation["status"] != "active":
                    raise SaaSError("invalid_invitation", "邀请码不存在或已停用。", 400)
                if invitation["expires_at"] and invitation["expires_at"] <= utcnow():
                    raise SaaSError("invalid_invitation", "邀请码已过期。", 400)
                if int(invitation["used_count"]) >= int(invitation["max_uses"]):
                    raise SaaSError("invitation_exhausted", "邀请码使用次数已满。", 400)
                if int(invitation.get("verification_email_count", 0)) >= INVITATION_VERIFICATION_EMAIL_LIMIT:
                    raise SaaSError("invitation_email_limit", "该邀请码的激活邮件发送次数已达上限。", 429)
                cursor.execute("SELECT 1 FROM users WHERE email=%s", (normalized_email,))
                if cursor.fetchone():
                    raise SaaSError("email_exists", "该邮箱已注册，请直接登录。", 409)
                user_id = new_id()
                cursor.execute(
                    """INSERT INTO users(id,email,password_hash,display_name,plan_version)
                    VALUES(%s,%s,%s,%s,'free-v2')""",
                    (user_id, normalized_email, hash_password(password_value), str(display_name or "").strip()[:100]),
                )
                cursor.execute(
                    "INSERT INTO invitation_uses(id,invitation_id,user_id,email,ip_address) VALUES(%s,%s,%s,%s,%s)",
                    (new_id(), invitation["id"], user_id, normalized_email, str(ip_address or "")[:128]),
                )
                cursor.execute("UPDATE invitations SET used_count=used_count+1 WHERE id=%s", (invitation["id"],))
                # Only invitations explicitly issued as member invites can
                # create referral rewards; administrator/channel invitation
                # codes never silently become referral relationships.
                cursor.execute("SELECT id,inviter_id,invitee_id FROM member_invites WHERE invitation_id=%s FOR UPDATE", (invitation["id"],))
                member_invite = self._one(cursor)
                if member_invite and not member_invite["invitee_id"] and member_invite["inviter_id"] != user_id:
                    cursor.execute("UPDATE member_invites SET invitee_id=%s,status='registered',registered_at=NOW() WHERE id=%s", (user_id, member_invite["id"]))
                verification_token = self._new_verification(cursor, user_id)
                cursor.execute("UPDATE invitations SET verification_email_count=verification_email_count+1 WHERE id=%s", (invitation["id"],))
                cursor.execute("SELECT id,email,display_name,plan_version,email_verified_at FROM users WHERE id=%s", (user_id,))
                user = self._one(cursor) or {}
        delivered = self._send_verification(normalized_email, verification_token)
        return {"user": self.public_user(user), "verificationRequired": True, "emailDelivery": delivered}

    def verify_email(self, raw_token: Any) -> dict[str, Any]:
        supplied = str(raw_token or "").strip()
        if not supplied:
            raise SaaSError("invalid_verification", "验证链接无效或已过期。", 400)
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM email_verifications WHERE token_hash=%s AND consumed_at IS NULL
                    ORDER BY created_at DESC LIMIT 1 FOR UPDATE""",
                    (token_hash(supplied),),
                )
                record = self._one(cursor)
                if not record or record["expires_at"] <= utcnow():
                    raise SaaSError("invalid_verification", "验证链接无效或已过期。", 400)
                cursor.execute("UPDATE email_verifications SET consumed_at=NOW() WHERE id=%s", (record["id"],))
                cursor.execute("UPDATE users SET email_verified_at=NOW(),updated_at=NOW() WHERE id=%s", (record["user_id"],))
                cursor.execute("SELECT id,email,display_name,plan_version,email_verified_at FROM users WHERE id=%s", (record["user_id"],))
                return {"user": self.public_user(self._one(cursor) or {})}

    def login(self, email: Any, password: Any, device_key: Any, user_agent: str = "", ip_address: str = "", replace_device_id: Any = "") -> dict[str, Any]:
        normalized_email = normalize_email(email)
        key = str(device_key or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._:-]{16,200}", key):
            raise SaaSError("invalid_device", "设备标识无效，请刷新页面后重试。")
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE email=%s FOR UPDATE", (normalized_email,))
                user = self._one(cursor)
                if not user or not verify_password(str(password or ""), str(user.get("password_hash", ""))):
                    raise SaaSError("invalid_credentials", "邮箱或密码不正确。", 401)
                if user["status"] != "active":
                    raise SaaSError("account_unavailable", "该账号当前不可登录。", 403)
                if not user.get("email_verified_at"):
                    raise SaaSError("email_unverified", "邮箱尚未激活，请先前往邮箱完成验证。", 403)
                cursor.execute(
                    """SELECT EXISTS(SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id
                    WHERE ur.user_id=%s AND r.name='admin') AS is_admin""",
                    (user["id"],),
                )
                user["is_admin"] = bool((self._one(cursor) or {}).get("is_admin"))
                # Membership expiry must also take effect for device limits,
                # even if the member has not opened the membership screen.
                cursor.execute("UPDATE subscriptions SET status='expired',updated_at=NOW() WHERE user_id=%s AND status IN ('active','grace_period') AND ends_at<=NOW()", (user["id"],))
                cursor.execute(
                    """SELECT pv.id,pv.quotas_json FROM subscriptions s JOIN plan_versions pv ON pv.id=s.plan_version_id
                    WHERE s.user_id=%s AND s.status IN ('active','grace_period') AND s.starts_at<=NOW() AND s.ends_at>NOW()
                    ORDER BY pv.rank DESC,s.ends_at DESC,s.created_at DESC LIMIT 1""",
                    (user["id"],),
                )
                effective = self._one(cursor)
                if not effective:
                    cursor.execute("SELECT id,quotas_json FROM plan_versions WHERE id='free-v2'")
                    effective = self._one(cursor)
                if not effective:
                    raise SaaSConfigurationError("会员套餐 migration 缺失；请先执行 `python3 tools/saas_migrate.py --migrate`。")
                user["plan_version"] = effective["id"]
                cursor.execute("UPDATE users SET plan_version=%s,updated_at=NOW() WHERE id=%s", (effective["id"], user["id"]))
                quotas = effective["quotas_json"] if isinstance(effective["quotas_json"], dict) else json.loads(effective["quotas_json"])
                limit = max(1, int(quotas.get("devices", device_limit(str(user["plan_version"])))) )
                cursor.execute("SELECT * FROM devices WHERE user_id=%s AND device_key=%s FOR UPDATE", (user["id"], key))
                device = self._one(cursor)
                if not device or device["revoked_at"]:
                    cursor.execute("SELECT COUNT(*) AS count FROM devices WHERE user_id=%s AND revoked_at IS NULL", (user["id"],))
                    count = int((self._one(cursor) or {"count": 0})["count"])
                    if count >= limit and not user["is_admin"] and not replace_device_id:
                        cursor.execute(
                            """SELECT id,label,user_agent,first_seen_at,last_seen_at FROM devices
                            WHERE user_id=%s AND revoked_at IS NULL ORDER BY last_seen_at DESC""",
                            (user["id"],),
                        )
                        active_devices = [{"id": row["id"], "label": row["label"], "userAgent": row["user_agent"], "firstSeenAt": iso(row["first_seen_at"]), "lastSeenAt": iso(row["last_seen_at"])} for row in self._many(cursor)]
                        raise SaaSError(
                            "device_limit_exceeded",
                            "已达到当前套餐的同时登录设备上限，请先在已登录设备中移除旧设备。",
                            409,
                            {"limit": limit, "activeDevices": count, "devices": active_devices},
                        )
                    if replace_device_id:
                        cursor.execute("SELECT id FROM devices WHERE id=%s AND user_id=%s AND revoked_at IS NULL FOR UPDATE", (str(replace_device_id), user["id"]))
                        replaced = self._one(cursor)
                        if not replaced or str(replaced["id"]) == str(device["id"] if device else ""):
                            raise SaaSError("device_not_found", "所选设备已下线或不可替换，请重新登录后选择。", 409)
                        cursor.execute("UPDATE devices SET revoked_at=NOW() WHERE id=%s", (replaced["id"],))
                        cursor.execute("UPDATE user_sessions SET revoked_at=NOW() WHERE device_id=%s AND revoked_at IS NULL", (replaced["id"],))
                    if device:
                        cursor.execute("UPDATE devices SET revoked_at=NULL,last_seen_at=NOW(),user_agent=%s WHERE id=%s", (user_agent[:1000], device["id"]))
                        device_id = str(device["id"])
                    else:
                        device_id = new_id()
                        cursor.execute(
                            "INSERT INTO devices(id,user_id,device_key,label,user_agent) VALUES(%s,%s,%s,%s,%s)",
                            (device_id, user["id"], key, "", user_agent[:1000]),
                        )
                else:
                    device_id = str(device["id"])
                    cursor.execute("UPDATE devices SET last_seen_at=NOW(),user_agent=%s WHERE id=%s", (user_agent[:1000], device_id))
                raw_session, raw_csrf = random_token(), random_token()
                session_id = new_id()
                cursor.execute(
                    """INSERT INTO user_sessions(id,user_id,device_id,token_hash,csrf_hash,expires_at,ip_address,user_agent)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (session_id, user["id"], device_id, token_hash(raw_session), token_hash(raw_csrf), utcnow() + timedelta(days=SESSION_TTL_DAYS), ip_address[:128], user_agent[:1000]),
                )
                cursor.execute("UPDATE users SET last_login_at=NOW(),updated_at=NOW() WHERE id=%s", (user["id"],))
                if user["is_admin"]:
                    cursor.execute(
                        """DELETE FROM user_sessions WHERE id IN (
                        SELECT id FROM user_sessions WHERE user_id=%s AND id<>%s
                        AND id NOT IN (SELECT id FROM user_sessions WHERE user_id=%s AND id<>%s ORDER BY created_at DESC,id DESC LIMIT 4)
                        )""",
                        (user["id"], session_id, user["id"], session_id),
                    )
                return {"user": self.public_user(user), "sessionToken": raw_session, "csrfToken": raw_csrf}

    def authenticate(self, raw_session_token: str | None) -> dict[str, Any] | None:
        if not raw_session_token:
            return None
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT s.id AS session_id,s.csrf_hash,s.device_id,u.id,u.email,u.display_name,u.status,u.plan_version,u.email_verified_at,
                    EXISTS(SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id WHERE ur.user_id=u.id AND r.name='admin') AS is_admin
                    FROM user_sessions s JOIN users u ON u.id=s.user_id JOIN devices d ON d.id=s.device_id
                    WHERE s.token_hash=%s AND s.revoked_at IS NULL AND s.expires_at>NOW() AND d.revoked_at IS NULL""",
                    (token_hash(raw_session_token),),
                )
                session = self._one(cursor)
                if not session or session["status"] != "active":
                    return None
                cursor.execute("UPDATE user_sessions SET last_seen_at=NOW() WHERE id=%s", (session["session_id"],))
                cursor.execute("UPDATE devices SET last_seen_at=NOW() WHERE id=%s", (session["device_id"],))
                return session

    def assert_csrf(self, session: dict[str, Any], supplied: str | None) -> None:
        if not supplied or not hmac.compare_digest(str(session.get("csrf_hash", "")), token_hash(supplied)):
            raise SaaSError("csrf_failed", "请求验证失败，请刷新页面后重试。", 403)

    def recover_csrf(self, session_id: str, raw_session_token: str) -> tuple[str, str]:
        """Rotate a session with a missing CSRF cookie and return its cookie pair."""
        rotated_session = random_token()
        recovered = hmac.new(rotated_session.encode("utf-8"), b"shiyue-csrf-recovery-v1", hashlib.sha256).hexdigest()
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE user_sessions SET token_hash=%s,csrf_hash=%s
                    WHERE id=%s AND token_hash=%s AND revoked_at IS NULL AND expires_at>NOW()""",
                    (token_hash(rotated_session), token_hash(recovered), session_id, token_hash(raw_session_token)),
                )
                if cursor.rowcount != 1:
                    raise SaaSError("authentication_required", "请先登录。", 401)
        return rotated_session, recovered

    def logout(self, session: dict[str, Any]) -> None:
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE user_sessions SET revoked_at=NOW() WHERE id=%s", (session["session_id"],))

    def devices(self, user_id: str, current_device_id: str = "") -> list[dict[str, Any]]:
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT id,label,user_agent,first_seen_at,last_seen_at FROM devices
                    WHERE user_id=%s AND revoked_at IS NULL ORDER BY last_seen_at DESC""",
                    (user_id,),
                )
                return [{"id":row["id"],"label":row["label"],"userAgent":row["user_agent"],"firstSeenAt":iso(row["first_seen_at"]) if row["first_seen_at"] else "","lastSeenAt":iso(row["last_seen_at"]) if row["last_seen_at"] else "","current":str(row["id"]) == current_device_id} for row in self._many(cursor)]

    def preferences(self, user_id: str) -> dict[str, Any]:
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT preferences_json FROM user_preferences WHERE user_id=%s", (user_id,))
                row = self._one(cursor)
                if not row:
                    return {}
                value = row.get("preferences_json", {})
                value = value if isinstance(value, dict) else json.loads(value or "{}")
                return {key: item for key, item in value.items() if key != "highlightLeadMs"} if isinstance(value, dict) else {}

    def update_preferences(self, user_id: str, incoming: Any) -> dict[str, Any]:
        if not isinstance(incoming, dict):
            raise SaaSError("invalid_preferences", "阅读偏好数据无效。", 400)
        enum_fields = {
            "theme": {"pine", "mist", "iris"},
            "density": {"comfortable", "compact"},
            "readerLayout": {"side", "stack"},
            "shortcutPrevious": {"a", "s", "d", "space", "arrowleft", "arrowright", "enter"},
            "shortcutRepeat": {"a", "s", "d", "space", "arrowleft", "arrowright", "enter"},
            "shortcutNext": {"a", "s", "d", "space", "arrowleft", "arrowright", "enter"},
            "shortcutPlay": {"a", "s", "d", "space", "arrowleft", "arrowright", "enter"},
        }
        boolean_fields = {"eyeComfort", "focusMode", "sentenceAutoPause", "readerToolsPinned", "wordAutoPronounce", "wordHoverPause"}
        number_fields = {
            "playbackRate": (0.5, 2.0),
            "readerFontSize": (16, 28),
            "readerLineHeight": (1.4, 2.4),
            "readerContentWidth": (560, 1040),
        }
        current = self.preferences(user_id)
        changed = False
        for key, values in enum_fields.items():
            if key in incoming:
                value = str(incoming[key]).strip()
                if value not in values:
                    raise SaaSError("invalid_preferences", f"阅读偏好 {key} 无效。", 400)
                current[key] = value
                changed = True
        for key in boolean_fields:
            if key in incoming:
                if not isinstance(incoming[key], bool):
                    raise SaaSError("invalid_preferences", f"阅读偏好 {key} 无效。", 400)
                current[key] = incoming[key]
                changed = True
        for key, (minimum, maximum) in number_fields.items():
            if key in incoming:
                try:
                    value = float(incoming[key])
                except (TypeError, ValueError) as exc:
                    raise SaaSError("invalid_preferences", f"阅读偏好 {key} 无效。", 400) from exc
                if not minimum <= value <= maximum or isinstance(incoming[key], bool):
                    raise SaaSError("invalid_preferences", f"阅读偏好 {key} 超出允许范围。", 400)
                current[key] = value
                changed = True
        shortcut_values = [current.get(key) for key in ("shortcutPrevious", "shortcutRepeat", "shortcutNext", "shortcutPlay") if current.get(key)]
        if len(shortcut_values) != len(set(shortcut_values)):
            raise SaaSError("invalid_preferences", "四个阅读快捷键不能重复。", 400)
        if not changed:
            raise SaaSError("invalid_preferences", "没有可保存的阅读偏好。", 400)
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO user_preferences(user_id,preferences_json) VALUES(%s,%s::jsonb)
                ON CONFLICT(user_id) DO UPDATE SET preferences_json=EXCLUDED.preferences_json,updated_at=NOW()""", (user_id, json.dumps(current, ensure_ascii=False)))
        return current

    def revoke_device(self, user_id: str, device_id: str) -> None:
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM devices WHERE id=%s AND user_id=%s AND revoked_at IS NULL FOR UPDATE", (device_id, user_id))
                if not cursor.fetchone():
                    raise SaaSError("device_not_found", "设备不存在或已下线。", 404)
                cursor.execute("UPDATE devices SET revoked_at=NOW() WHERE id=%s", (device_id,))
                cursor.execute("UPDATE user_sessions SET revoked_at=NOW() WHERE device_id=%s AND revoked_at IS NULL", (device_id,))

    def forgot_password(self, email: Any) -> bool:
        try:
            normalized_email = normalize_email(email)
        except SaaSError:
            return False
        raw = ""
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id,email,password_reset_request_count,password_reset_locked_at FROM users WHERE email=%s AND status='active' FOR UPDATE",
                    (normalized_email,),
                )
                user = self._one(cursor)
                if not user:
                    return False
                if int(user.get("password_reset_request_count", 0)) >= PASSWORD_RESET_EMAIL_LIMIT:
                    return False
                raw = random_token()
                cursor.execute("UPDATE password_reset_tokens SET consumed_at=NOW() WHERE user_id=%s AND consumed_at IS NULL", (user["id"],))
                cursor.execute(
                    "INSERT INTO password_reset_tokens(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",
                    (new_id(), user["id"], token_hash(raw), utcnow() + timedelta(hours=RESET_TTL_HOURS)),
                )
                cursor.execute(
                    """UPDATE users SET password_reset_request_count=password_reset_request_count+1,
                    password_reset_locked_at=CASE WHEN password_reset_request_count+1 >= %s THEN NOW() ELSE NULL END,
                    updated_at=NOW() WHERE id=%s""",
                    (PASSWORD_RESET_EMAIL_LIMIT, user["id"]),
                )
        delivered = self._send_password_reset(normalized_email, raw)
        if delivered:
            return True
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE password_reset_tokens SET consumed_at=NOW() WHERE token_hash=%s AND consumed_at IS NULL", (token_hash(raw),))
                cursor.execute(
                    """UPDATE users SET password_reset_request_count=GREATEST(password_reset_request_count-1,0),
                    password_reset_locked_at=CASE WHEN password_reset_request_count-1 >= %s THEN password_reset_locked_at ELSE NULL END,
                    updated_at=NOW() WHERE id=%s""",
                    (PASSWORD_RESET_EMAIL_LIMIT, user["id"]),
                )
        return False

    def reset_password(self, raw_token: Any, password: Any) -> None:
        supplied = str(raw_token or "").strip()
        password_value = validate_password(password)
        if not supplied:
            raise SaaSError("invalid_reset", "重置链接无效或已过期。", 400)
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM password_reset_tokens WHERE token_hash=%s AND consumed_at IS NULL
                    ORDER BY created_at DESC LIMIT 1 FOR UPDATE""",
                    (token_hash(supplied),),
                )
                record = self._one(cursor)
                if not record or record["expires_at"] <= utcnow():
                    raise SaaSError("invalid_reset", "重置链接无效或已过期。", 400)
                cursor.execute("UPDATE password_reset_tokens SET consumed_at=NOW() WHERE id=%s", (record["id"],))
                cursor.execute(
                    """UPDATE users SET password_hash=%s,password_reset_request_count=0,
                    password_reset_locked_at=NULL,updated_at=NOW() WHERE id=%s""",
                    (hash_password(password_value), record["user_id"]),
                )
                cursor.execute("UPDATE user_sessions SET revoked_at=NOW() WHERE user_id=%s AND revoked_at IS NULL", (record["user_id"],))

    @staticmethod
    def public_user(user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": user.get("id"),
            "email": user.get("email"),
            "displayName": user.get("display_name", ""),
            "planVersion": user.get("plan_version", "free-v2"),
            "emailVerified": bool(user.get("email_verified_at")),
            "isAdmin": bool(user.get("is_admin", False)),
        }

    def _send_verification(self, email: str, raw_token: str) -> bool:
        url = self._app_url("/verify-email?token=" + quote(raw_token))
        return self._send_mail(email, "验证你的拾页邮箱", f"请在 24 小时内打开以下链接验证邮箱：\n{url}\n")

    def _send_password_reset(self, email: str, raw_token: str) -> bool:
        url = self._app_url("/reset-password?token=" + quote(raw_token))
        return self._send_mail(email, "重置拾页密码", f"请在 2 小时内打开以下链接重置密码：\n{url}\n")

    def _app_url(self, path: str) -> str:
        base = self.environment.get("APP_BASE_URL", "").strip().rstrip("/")
        return (base or "http://localhost:8765") + path

    def _send_mail(self, recipient: str, subject: str, text: str) -> bool:
        host = self.environment.get("SMTP_HOST", "").strip()
        sender = self.environment.get("SMTP_FROM", "").strip()
        if not host or not sender:
            return False
        try:
            port = int(self.environment.get("SMTP_PORT", "587"))
            message = EmailMessage()
            message["From"], message["To"], message["Subject"] = sender, recipient, subject
            message.set_content(text)
            with smtplib.SMTP(host, port, timeout=15) as client:
                client.ehlo()
                if port in {25, 587}:
                    client.starttls()
                    client.ehlo()
                username = self.environment.get("SMTP_USER", "")
                if username:
                    client.login(username, self.environment.get("SMTP_PASSWORD", ""))
                client.send_message(message)
            return True
        except (OSError, ValueError, smtplib.SMTPException):
            return False

    def import_legacy_sqlite(self, sqlite_path: Path, admin_user_id: str) -> dict[str, int]:
        """Copy current single-user records into PostgreSQL as administrator-private data.

        Source SQLite is opened read-only.  Re-running is safe because each
        insertion is an upsert keyed by the legacy primary key.
        """
        if not sqlite_path.is_file():
            raise SaaSConfigurationError(f"找不到 SQLite 源库：{sqlite_path}")
        source = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
        source.row_factory = sqlite3.Row
        result = {"books": 0, "vocabulary": 0, "annotations": 0, "learningDays": 0, "grammar": 0}
        try:
            with self.transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM users WHERE id=%s", (admin_user_id,))
                    if not cursor.fetchone():
                        raise SaaSConfigurationError("管理员账号不存在；请先 bootstrap 管理员。")
                    for row in source.execute("SELECT * FROM books"):
                        item = dict(row)
                        cursor.execute(
                            """INSERT INTO content_books(
                            id,owner_id,title,english_title,series,level,source_type,source_path,status,visibility,
                            cover_url,page_base_url,audio_url,pdf_url,video_url,duration,alignment,data_json,quality_json,created_at,updated_at)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'private',%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
                            ON CONFLICT (id) DO UPDATE SET owner_id=EXCLUDED.owner_id,title=EXCLUDED.title,english_title=EXCLUDED.english_title,
                            series=EXCLUDED.series,level=EXCLUDED.level,source_type=EXCLUDED.source_type,source_path=EXCLUDED.source_path,
                            status=EXCLUDED.status,visibility='private',cover_url=EXCLUDED.cover_url,page_base_url=EXCLUDED.page_base_url,
                            audio_url=EXCLUDED.audio_url,pdf_url=EXCLUDED.pdf_url,video_url=EXCLUDED.video_url,duration=EXCLUDED.duration,
                            alignment=EXCLUDED.alignment,data_json=EXCLUDED.data_json,quality_json=EXCLUDED.quality_json,updated_at=EXCLUDED.updated_at""",
                            (
                                item["id"], admin_user_id, item["title"], item.get("english_title", ""), item.get("series", ""), item.get("level", ""),
                                item.get("source_type", "book"), item["source_path"], item.get("status", "ready"), item.get("cover_url", ""),
                                item.get("page_base_url", ""), item.get("audio_url", ""), item.get("pdf_url", ""), item.get("video_url", ""),
                                item.get("duration", 0), item.get("alignment", ""), item["data_json"], item.get("quality_json", "{}"), item["created_at"], item["updated_at"],
                            ),
                        )
                        result["books"] += 1
                    for table, key in (("vocabulary", "vocabulary"), ("word_annotations", "annotations"), ("learning_daily", "learningDays"), ("sentence_grammar", "grammar")):
                        rows = source.execute(f"SELECT * FROM {table}")
                        for row in rows:
                            item = dict(row)
                            if table == "vocabulary":
                                cursor.execute(
                                    """INSERT INTO content_vocabulary(legacy_id,owner_id,book_id,sentence_id,word_index,payload)
                                    VALUES(%s,%s,%s,%s,%s,%s::jsonb)
                                    ON CONFLICT (legacy_id) DO UPDATE SET owner_id=EXCLUDED.owner_id,book_id=EXCLUDED.book_id,
                                    sentence_id=EXCLUDED.sentence_id,word_index=EXCLUDED.word_index,payload=EXCLUDED.payload""",
                                    (item["id"], admin_user_id, item["book_id"], item["sentence_id"], item["word_index"], json.dumps(item, ensure_ascii=False)),
                                )
                            elif table == "word_annotations":
                                cursor.execute(
                                    """INSERT INTO content_word_annotations(owner_id,book_id,sentence_id,word_index,payload)
                                    VALUES(%s,%s,%s,%s,%s::jsonb)
                                    ON CONFLICT (owner_id,book_id,sentence_id,word_index) DO UPDATE SET payload=EXCLUDED.payload""",
                                    (admin_user_id, item["book_id"], item["sentence_id"], item["word_index"], json.dumps(item, ensure_ascii=False)),
                                )
                            elif table == "learning_daily":
                                cursor.execute(
                                    """INSERT INTO content_learning_daily(owner_id,day,payload) VALUES(%s,%s,%s::jsonb)
                                    ON CONFLICT (owner_id,day) DO UPDATE SET payload=EXCLUDED.payload""",
                                    (admin_user_id, item["day"], json.dumps(item, ensure_ascii=False)),
                                )
                            else:
                                cursor.execute(
                                    """INSERT INTO content_sentence_grammar(book_id,sentence_id,payload) VALUES(%s,%s,%s::jsonb)
                                    ON CONFLICT (book_id,sentence_id) DO UPDATE SET payload=EXCLUDED.payload""",
                                    (item["book_id"], item["sentence_id"], json.dumps(item, ensure_ascii=False)),
                                )
                            result[key] += 1
        finally:
            source.close()
        return result
