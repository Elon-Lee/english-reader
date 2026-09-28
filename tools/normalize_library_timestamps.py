#!/usr/bin/env python3
import json
import sqlite3

from align_whisper import normalize_words
from library_db import DB_PATH, now

db=sqlite3.connect(DB_PATH); db.row_factory=sqlite3.Row
rows=db.execute("SELECT id,data_json FROM books").fetchall()
for row in rows:
    book=json.loads(row["data_json"]); totals={"overlapsFixed":0,"durationsCapped":0}
    for sentence in book["sentences"]:
        words=sentence.get("words",[]); result=normalize_words(words)
        for key,value in result.items(): totals[key]+=value
        if words: sentence["start"]=words[0]["start"]; sentence["end"]=words[-1]["end"]
    book.setdefault("whisper",{})["postNormalization"]=totals
    db.execute("UPDATE books SET data_json=?,updated_at=? WHERE id=?",(json.dumps(book,ensure_ascii=False),now(),row["id"]))
    print(row["id"],totals)
db.commit(); db.close()
