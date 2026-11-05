"""Tianai provider adapter and short-lived, single-use authentication receipts."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from urllib.request import Request, urlopen

from saas_auth import SaaSError, new_id, normalize_email


SCENES = {"login", "register", "login_replace", "forgot"}
CONSUME = "if redis.call('GET',KEYS[1]) == ARGV[1] then redis.call('DEL',KEYS[1]); return 1 else return 0 end"


def unavailable():
    return SaaSError("captcha_unavailable", "验证码服务暂不可用，请稍后重试。", 503)


class CaptchaService:
    def __init__(self, accounts, redis_client, environment=None):
        self.accounts = accounts
        self.redis = redis_client
        self.environment = environment if environment is not None else os.environ

    def config(self):
        # Only a missing setting defaults off. Database errors must fail closed.
        try:
            with self.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT value_json FROM platform_settings WHERE key='auth.captcha'")
                    row = self.accounts._one(cursor)
            value = row["value_json"] if row else {"enabled": False}
            if not isinstance(value, dict) or type(value.get("enabled")) is not bool:
                raise unavailable()
            return {"captchaEnabled": value["enabled"], "captchaType": "ROTATE"}
        except SaaSError:
            raise
        except Exception as exc:
            raise unavailable() from exc

    def update_config(self, actor_id, item):
        if set(item) != {"captchaEnabled"} or type(item["captchaEnabled"]) is not bool:
            raise SaaSError("invalid_auth_config", "请提供有效的验证码开关。")
        enabled = item["captchaEnabled"]
        if enabled:
            self._cache()
            result = self._provider("/gen?type=ROTATE")
            data = result.get("data")
            if result.get("code") != 200 or not isinstance(data, dict) or data.get("type") != "ROTATE" or not data.get("id"):
                raise unavailable()
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO platform_settings(key,value_json,updated_by) VALUES('auth.captcha',%s::jsonb,%s) ON CONFLICT(key) DO UPDATE SET value_json=EXCLUDED.value_json,updated_by=EXCLUDED.updated_by,updated_at=NOW()", (json.dumps({"enabled": enabled}), actor_id))
                cursor.execute("INSERT INTO admin_audit_logs(id,actor_id,action,payload_json) VALUES(%s,%s,'auth_captcha_updated',%s::jsonb)", (new_id(), actor_id, json.dumps({"captchaEnabled": enabled})))
        return {"captchaEnabled": enabled, "captchaType": "ROTATE"}

    def _cache(self):
        try:
            if self.redis is None or not self.redis.ping():
                raise unavailable()
            return self.redis
        except Exception as exc:
            raise unavailable() from exc

    def _get(self, key):
        try:
            return self._cache().get(key)
        except Exception as exc:
            raise unavailable() from exc

    def _set(self, key, value, ttl):
        try:
            if not self._cache().set(key, value, ex=ttl, nx=True):
                raise unavailable()
        except Exception as exc:
            raise unavailable() from exc

    def _consume(self, key, expected):
        try:
            return self._cache().eval(CONSUME, 1, key, expected) == 1
        except Exception as exc:
            raise unavailable() from exc

    def _provider(self, path, payload=None):
        secret = self.environment.get("SHIYUE_CAPTCHA_SECRET", "")
        if len(secret) < 32:
            raise unavailable()
        # Deliberately fixed loopback endpoint: no public demo or arbitrary proxy.
        request = Request("http://127.0.0.1:18080" + path,
                          data=json.dumps(payload).encode() if payload is not None else None,
                          headers={"Content-Type": "application/json", "X-Captcha-Secret": secret})
        try:
            with urlopen(request, timeout=8) as response:
                result = json.loads(response.read(3_000_000))
            if not isinstance(result, dict):
                raise unavailable()
            return result
        except Exception as exc:
            raise unavailable() from exc

    @staticmethod
    def _key(kind, value):
        return "shiyue:captcha:" + kind + ":" + hashlib.sha256(str(value).encode()).hexdigest()

    @staticmethod
    def _binding(scene, email, browser):
        if scene not in SCENES or not re.fullmatch(r"[A-Za-z0-9_-]{10,128}", browser or ""):
            raise SaaSError("invalid_captcha_context", "请重新打开验证码。")
        return json.dumps({"scene": scene, "email": normalize_email(email), "browser": browser}, sort_keys=True)

    def prepare(self, scene, email, browser):
        if not self.config()["captchaEnabled"]:
            raise SaaSError("captcha_disabled", "验证码未开启。")
        binding = self._binding(scene, email, browser)
        context = secrets.token_urlsafe(32)
        self._set(self._key("context", context), binding, 120)
        return {"context": context}

    def generate(self, context, browser):
        key = self._key("context", context)
        binding = self._get(key)
        if not binding or json.loads(binding)["browser"] != browser or not self._consume(key, binding):
            raise SaaSError("captcha_expired", "验证码已过期，请重试。")
        result = self._provider("/gen?type=ROTATE")
        data = result.get("data")
        if result.get("code") != 200 or not isinstance(data, dict) or not data.get("id") or data.get("type") != "ROTATE":
            raise unavailable()
        self._set(self._key("challenge", data["id"]), binding, 60)
        return result

    def check(self, item, browser):
        if not isinstance(item.get("id"), str) or not isinstance(item.get("data"), dict):
            raise SaaSError("invalid_captcha", "验证码数据无效。")
        key = self._key("challenge", item["id"])
        binding = self._get(key)
        if not binding or json.loads(binding)["browser"] != browser or not self._consume(key, binding):
            raise SaaSError("captcha_expired", "验证码已过期，请重新验证。")
        result = self._provider("/check", {"id": item["id"], "data": item["data"]})
        if result.get("code") != 200 or result.get("success") is not True:
            raise SaaSError("captcha_failed", "验证失败，请重新尝试。")
        token = secrets.token_urlsafe(32)
        self._set(self._key("receipt", token), binding, 120)
        return {"code": 200, "data": {"captchaToken": token}}

    def require(self, scene, email, token, browser):
        if not self.config()["captchaEnabled"]:
            return
        self._cache()
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{40,100}", token):
            raise SaaSError("captcha_required", "请先完成验证码验证。")
        binding = self._binding(scene, email, browser)
        if not self._consume(self._key("receipt", token), binding):
            raise SaaSError("captcha_required", "验证码已失效，请重新验证。")
