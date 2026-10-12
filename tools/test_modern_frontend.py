#!/usr/bin/env python3
"""Static smoke checks for the React + Ant Design production entrypoint."""
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / "reader"
SITE = READER / "site"
INDEX = SITE / "index.html"
ASSETS = SITE / "assets"
READER_PAGE = ROOT / "frontend" / "src" / "pages" / "ReaderPage.jsx"
MODERN_STYLES = ROOT / "frontend" / "src" / "styles.css"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    check(INDEX.is_file(), "reader/site/index.html missing")
    html = INDEX.read_text(encoding="utf-8")
    check('/assets/index.js' in html, "root site must use the fixed production entry")
    check('/assets/index.css' in html, "root site must load the production stylesheet")
    check('/modern-assets/' not in html, "root site must not depend on the legacy modern-assets path")
    check((ASSETS / "index.js").is_file(), "root entry chunk missing")
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
    reader_page = READER_PAGE.read_text(encoding="utf-8")
    modern_styles = MODERN_STYLES.read_text(encoding="utf-8")
    check('className="reader-media-float"' in reader_page, "stacked reader media must use a dedicated floating wrapper")
    check("grid-template-rows:auto minmax(0,1fr)" in modern_styles, "stacked reader media must reserve a separate row above sentences")
    check(".reader-media-top .reader-media-float" in modern_styles and "justify-content:center" in modern_styles, "stacked reader media must stay centered")
    check(".reader-media-top .reader-story" in modern_styles and "overflow-y:auto" in modern_styles, "stacked reader sentences must scroll below media")
    print(f"modern frontend smoke ok: {len(imports)} entry chunk imports")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError) as error:
        print(f"modern frontend smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1)
