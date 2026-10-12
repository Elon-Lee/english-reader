#!/usr/bin/env python3
"""Static smoke checks for the React + Ant Design production entrypoint."""
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / "reader"
MODERN = READER / "modern.html"
ASSETS = READER / "modern-assets" / "assets"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    check(MODERN.is_file(), "reader/modern.html missing")
    html = MODERN.read_text(encoding="utf-8")
    check('/modern-assets/assets/index.js' in html, "modern.html must use the fixed production entry")
    check('/modern-assets/assets/index.css' in html, "modern.html must load the production stylesheet")
    check((ASSETS / "index.js").is_file(), "modern entry chunk missing")
    entry = (ASSETS / "index.js").read_text(encoding="utf-8")
    imports = re.findall(r"(?:from|import\()\s*['\"]([^'\"]+\.js)['\"]", entry)
    check(imports, "modern entry has no vendor chunk imports")
    for relative in imports:
        target = (ASSETS / Path(relative).name).resolve()
        check(target.is_file() and ASSETS.resolve() in target.parents, f"missing or unsafe chunk reference: {relative}")
    check((ASSETS / "antd.js").is_file(), "antd vendor chunk missing")
    check((ASSETS / "react.js").is_file(), "react vendor chunk missing")
    check((ASSETS / "icons.js").is_file(), "icons vendor chunk missing")
    check("/api/preferences" in entry, "reading preferences API integration missing")
    check("/api/auth/login" in entry and "/api/auth/register" in entry, "modern authentication integration missing")
    check("/api/workspace/activity" in entry and "/reader" in entry, "modern reader integration missing")
    check("/api/workspace/annotations" in entry and "MediaRecorder" in entry, "desktop reader parity controls missing")
    check("/api/word-tts" in entry and "controlsList" in entry, "reader pronunciation or protected media controls missing")
    check("/api/admin/catalog/sources" in entry and "/api/deployment/config" in entry, "platform operations migration missing")
    check("/api/workspace/books/" in entry and "confirmTitle" in entry, "private book lifecycle integration missing")
    print(f"modern frontend smoke ok: {len(imports)} entry chunk imports")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError) as error:
        print(f"modern frontend smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1)
