#!/usr/bin/env python3
"""Optional Redis dependency used by the production SaaS runtime."""
from __future__ import annotations

import os


class SaaSCache:
    def __init__(self,url:str|None=None):
        self.url=str(url if url is not None else os.environ.get("REDIS_URL","")).strip();self.client=None
        if self.url:
            import redis
            self.client=redis.Redis.from_url(self.url,decode_responses=True,socket_connect_timeout=3,socket_timeout=3,health_check_interval=30)

    @property
    def enabled(self)->bool:return bool(self.client)

    def assert_ready(self)->None:
        if self.client and not self.client.ping():raise RuntimeError("Redis ping failed")

    def status(self)->dict[str,bool]:
        if not self.client:return {"enabled":False,"ready":False}
        try:return {"enabled":True,"ready":bool(self.client.ping())}
        except Exception:return {"enabled":True,"ready":False}
