#!/usr/bin/env python3
import json
import shutil
from pathlib import Path
from library_db import BOOKS_ROOT, ROOT, upsert_book

source=BOOKS_ROOT/"牛津书虫全系列7级（0）/0.01.生存游戏"
generated=BOOKS_ROOT/".reader/survival-game"
(generated/"pages").mkdir(parents=True,exist_ok=True)
old_pages=ROOT/"reader/assets/survival-game/pages"
for page in old_pages.glob("*.jpg"):
    target=generated/"pages"/page.name
    if not target.exists(): shutil.copy2(page,target)
book=json.loads((ROOT/"reader/data/survival-game/book.json").read_text())
quality=json.loads((ROOT/"reader/data/survival-game/quality-report.json").read_text())
audio=next(source.glob("*.mp3")); pdf=next(source.glob("*.pdf"))
book.update({"audio":"/books/"+str(audio.relative_to(BOOKS_ROOT)),"pdf":"/books/"+str(pdf.relative_to(BOOKS_ROOT)),
             "pageBase":"/books/.reader/survival-game/pages"})
upsert_book(book,quality,str(source.relative_to(BOOKS_ROOT)),"牛津书虫全系列7级（0）",book["pageBase"],book["pageBase"]+"/page-001.jpg")
print("Migrated survival-game to SQLite")
