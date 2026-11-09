#!/usr/bin/env python3
"""Smoke checks for the invitation-only React production entrypoint."""
from pathlib import Path
import os
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SITE = Path(os.environ.get("READER_TEST_SITE", str(ROOT / "reader/site")))
SOURCE = ROOT / "frontend/src"


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    html = (SITE / "index.html").read_text()
    check('<title>纸间微光' in html and 'og:site_name' in html, "private brand metadata missing")
    mark = "paper-glow-mark.svg"
    check((SITE / "brand" / mark).read_bytes() == (ROOT / "frontend/public/brand" / mark).read_bytes(), "private brand mark missing or stale")
    check(f'/brand/{mark}?v=' in html, "versioned brand icon reference missing")
    for name in ('index.js', 'index.css'):
        check(re.search(r'/assets/' + re.escape(name) + r'\?v=[A-Za-z0-9_-]+', html), f"versioned {name} entry missing")
        check((SITE / 'assets' / name).is_file(), f"{name} missing")
    entry = (SITE / 'assets/index.js').read_text()
    imports = re.findall(r"(?:from|import\()\s*['\"]([^'\"]+\.js)['\"]", entry)
    check(imports, "vendor imports missing")
    for relative in imports:
        path = (SITE / 'assets' / Path(relative).name).resolve()
        check(path.is_file() and (SITE / 'assets').resolve() in path.parents, "missing or unsafe chunk reference")
    for endpoint in ('/api/auth/login', '/api/auth/register', '/api/auth/verify-email', '/api/auth/reset-password', '/api/preferences', '/api/workspace/activity', '/api/workspace/annotations', '/api/admin/invitation-batches', '/api/admin/catalog/sources', '/api/deployment/config'):
        check(endpoint in entry, f"API integration missing: {endpoint}")
    check(re.search(r'/api/(?:admin/)?(?:membership|commerce|billing|payments|payment-config|payment-orders|subscriptions|manual-orders)\b', entry) is None, "commercial API still ships")
    for word in ('会员中心', '云猫', '支付宝', '付费会员', '购买 / 兑换', 'RynEnglish'):
        check(word not in entry, f"retired text still ships: {word}")
    for value in ('受邀注册', '页面不存在', 'MediaRecorder', 'controlsList', '纸间微光'):
        check(value in entry, f"private reader behavior missing: {value}")
    modern = (SOURCE / 'main.jsx').read_text()
    check(modern.index("initialPreferences = await getJson('/api/preferences'") < modern.index("setAuthState('authenticated')", modern.index("initialPreferences = await getJson('/api/preferences'")), "saved theme must load before workspace")
    check('Promise.resolve(initialPreferences || preferences)' in modern, "first preferences snapshot lost")
    check('resolvePrivateRoute' in modern and 'safeNextPath' in modern, "private routes and login return validation missing")
    check('name="invitationCode"' in modern and "required: true, message: '请输入邀请码'" in modern, "invitation input must be required")
    check('fallbackBooks' not in modern and 'Atomic Habits' not in modern, "example books must not ship")
    api = (SOURCE / 'api/client.js').read_text()
    check("error.code === 'csrf_failed'" in api and "fetch('/api/auth/me'" in api, "CSRF recovery missing")
    reader = (SOURCE / 'pages/ReaderPage.jsx').read_text()
    check('availableVideos=media.videos' in reader and 'canWatchHdVideo' not in reader, "video selection must not depend on a paid tier")
    check('className="reader-media-float"' in reader, "stacked reader media wrapper missing")
    check("postJson('/api/workspace/imports/delete-invalid', {})" in (SOURCE / 'pages/LibraryPage.jsx').read_text(), "invalid task deletion endpoint missing")
    styles = (SOURCE / 'styles.css').read_text()
    check('grid-template-rows:auto minmax(0,1fr)' in styles and '.reader-media-top .reader-story' in styles, "reader layout integration missing")
    check('page-skeleton' in styles and 'private-entry' in styles, "loading or private entry styles missing")
    print(f"private frontend smoke ok: {len(imports)} vendor imports")
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (AssertionError, OSError) as error:
        print(f"private frontend smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1)
