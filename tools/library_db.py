#!/usr/bin/env python3
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BOOKS_ROOT=ROOT/"books"
LOCAL_ROOT=ROOT/".local"
DB_PATH=LOCAL_ROOT/"library.sqlite3"

def now(): return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def connect():
    LOCAL_ROOT.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DB_PATH,timeout=30)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS books (
      id TEXT PRIMARY KEY, title TEXT NOT NULL, english_title TEXT DEFAULT '',
      series TEXT NOT NULL, level TEXT DEFAULT '', source_path TEXT UNIQUE NOT NULL,
      status TEXT NOT NULL DEFAULT 'ready', cover_url TEXT DEFAULT '', page_base_url TEXT DEFAULT '',
      audio_url TEXT DEFAULT '', pdf_url TEXT DEFAULT '', duration REAL DEFAULT 0,
      alignment TEXT DEFAULT '', data_json TEXT NOT NULL, quality_json TEXT DEFAULT '{}',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS import_jobs (
      id INTEGER PRIMARY KEY AUTOINCREMENT, source_path TEXT NOT NULL, book_id TEXT,
      status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0, step TEXT DEFAULT '',
      error TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS book_artifacts (
      book_id TEXT NOT NULL, kind TEXT NOT NULL, data_json TEXT NOT NULL,
      created_at TEXT NOT NULL, PRIMARY KEY(book_id,kind), FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS dictionary_entries (
      surface TEXT PRIMARY KEY, entry_json TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    """)
    return db

def slug_for(relative):
    import hashlib
    name=Path(relative).name
    prefix=re.match(r"([0-9]+(?:\.[0-9]+)*)",name)
    readable=(prefix.group(1).replace(".","-") if prefix else "book")
    return f"{readable}-{hashlib.sha1(relative.encode()).hexdigest()[:8]}"

def display_title(folder_name):
    title=re.sub(r"^[0-9]+(?:\.[0-9]+)*(?:\.(?:上|中|下))?(?:\.[0-9]+)?[. ]*","",folder_name).strip()
    return title or folder_name

def scan_catalog():
    db=connect(); imported={row["source_path"]:{"id":row["id"],"cover":row["cover_url"]} for row in db.execute("SELECT source_path,id,cover_url FROM books")}; db.close()
    series=[]
    for series_dir in sorted(p for p in BOOKS_ROOT.iterdir() if p.is_dir() and not p.name.startswith(".")):
        books=[]
        for folder in sorted(p for p in series_dir.iterdir() if p.is_dir()):
            relative=str(folder.relative_to(BOOKS_ROOT))
            pdfs=sorted(folder.glob("*.pdf")); audios=sorted(folder.glob("*.mp3"))
            found=imported.get(relative)
            books.append({"path":relative,"name":folder.name,"title":display_title(folder.name),
                          "pdfCount":len(pdfs),"audioCount":len(audios),"ready":bool(pdfs and audios),
                          "importedId":found["id"] if found else None,
                          "coverUrl":found["cover"] if found else "/api/import/cover?path="+__import__("urllib.parse").parse.quote(relative)})
        series.append({"name":series_dir.name,"books":books})
    return series

def upsert_book(book,quality,source_path,series,page_base_url,cover_url):
    stamp=now(); db=connect()
    db.execute("""INSERT INTO books(id,title,english_title,series,level,source_path,status,cover_url,page_base_url,audio_url,pdf_url,duration,alignment,data_json,quality_json,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(id) DO UPDATE SET title=excluded.title,english_title=excluded.english_title,series=excluded.series,level=excluded.level,
      source_path=excluded.source_path,status='ready',cover_url=excluded.cover_url,page_base_url=excluded.page_base_url,audio_url=excluded.audio_url,
      pdf_url=excluded.pdf_url,duration=excluded.duration,alignment=excluded.alignment,data_json=excluded.data_json,quality_json=excluded.quality_json,updated_at=excluded.updated_at""",
      (book["id"],book["title"],book.get("englishTitle",""),series,str(book.get("level","")),source_path,"ready",cover_url,page_base_url,
       book.get("audio",""),book.get("pdf",""),book.get("duration",0),book.get("alignment",""),json.dumps(book,ensure_ascii=False),
       json.dumps(quality,ensure_ascii=False),stamp,stamp))
    db.commit(); db.close()

def save_artifact(book_id,kind,data):
    db=connect(); db.execute("INSERT INTO book_artifacts(book_id,kind,data_json,created_at) VALUES(?,?,?,?) ON CONFLICT(book_id,kind) DO UPDATE SET data_json=excluded.data_json,created_at=excluded.created_at",
        (book_id,kind,json.dumps(data,ensure_ascii=False),now())); db.commit(); db.close()

def save_dictionary(entries):
    stamp=now(); db=connect()
    db.executemany("INSERT INTO dictionary_entries(surface,entry_json,updated_at) VALUES(?,?,?) ON CONFLICT(surface) DO UPDATE SET entry_json=excluded.entry_json,updated_at=excluded.updated_at",
        [(surface,json.dumps(entry,ensure_ascii=False),stamp) for surface,entry in entries.items()])
    db.commit(); db.close()

def dictionary():
    db=connect(); rows=db.execute("SELECT surface,entry_json FROM dictionary_entries").fetchall(); db.close()
    return {row["surface"]:json.loads(row["entry_json"]) for row in rows}

def get_settings(defaults=None):
    db=connect(); rows=db.execute("SELECT key,value FROM app_settings").fetchall(); db.close()
    result=dict(defaults or {})
    for row in rows:
        try: result[row["key"]]=json.loads(row["value"])
        except json.JSONDecodeError: result[row["key"]]=row["value"]
    return result

def set_settings(values):
    db=connect()
    db.executemany("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   [(key,json.dumps(value,ensure_ascii=False)) for key,value in values.items()])
    db.commit(); db.close()

def library():
    db=connect(); rows=db.execute("SELECT id,title,english_title,series,level,status,cover_url,duration,alignment,updated_at FROM books ORDER BY series,title").fetchall(); db.close()
    return [dict(row) for row in rows]

def get_book(book_id):
    db=connect(); row=db.execute("SELECT * FROM books WHERE id=?",(book_id,)).fetchone(); db.close()
    if not row: return None
    result=dict(row); result["book"]=json.loads(result.pop("data_json")); result["quality"]=json.loads(result.pop("quality_json") or "{}")
    return result

def create_job(source_path):
    stamp=now(); db=connect(); cur=db.execute("INSERT INTO import_jobs(source_path,status,progress,step,created_at,updated_at) VALUES(?,?,?,?,?,?)",
        (source_path,"queued",0,"等待开始",stamp,stamp)); db.commit(); job_id=cur.lastrowid; db.close(); return job_id

def update_job(job_id,**values):
    values["updated_at"]=now(); fields=",".join(f"{key}=?" for key in values); params=list(values.values())+[job_id]
    db=connect(); db.execute(f"UPDATE import_jobs SET {fields} WHERE id=?",params); db.commit(); db.close()

def get_job(job_id):
    db=connect(); row=db.execute("SELECT * FROM import_jobs WHERE id=?",(job_id,)).fetchone(); db.close(); return dict(row) if row else None
