#!/usr/bin/env python3
import json
import re
import sqlite3
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

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
    CREATE TABLE IF NOT EXISTS vocabulary (
      id INTEGER PRIMARY KEY AUTOINCREMENT, book_id TEXT NOT NULL, sentence_id TEXT NOT NULL,
      word_index INTEGER NOT NULL, word TEXT NOT NULL, root TEXT NOT NULL, phonetic TEXT DEFAULT '',
      meaning TEXT DEFAULT '', context TEXT DEFAULT '', note TEXT DEFAULT '', rating TEXT DEFAULT 'unknown',
      interval_days INTEGER NOT NULL DEFAULT 1, due_at TEXT NOT NULL, reviews INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      UNIQUE(book_id,sentence_id,word_index)
    );
    CREATE TABLE IF NOT EXISTS word_annotations (
      book_id TEXT NOT NULL, sentence_id TEXT NOT NULL, word_index INTEGER NOT NULL,
      original_word TEXT NOT NULL, corrected_word TEXT DEFAULT '', note TEXT DEFAULT '', updated_at TEXT NOT NULL,
      PRIMARY KEY(book_id,sentence_id,word_index)
    );
    CREATE TABLE IF NOT EXISTS learning_daily (
      day TEXT PRIMARY KEY, reading_seconds REAL NOT NULL DEFAULT 0, sentences INTEGER NOT NULL DEFAULT 0,
      lookups INTEGER NOT NULL DEFAULT 0, reviews INTEGER NOT NULL DEFAULT 0,
      shadow_attempts INTEGER NOT NULL DEFAULT 0, sessions INTEGER NOT NULL DEFAULT 0,
      updated_at TEXT NOT NULL
    );
    """)
    columns={row[1] for row in db.execute("PRAGMA table_info(books)")}
    if "last_read_at" not in columns: db.execute("ALTER TABLE books ADD COLUMN last_read_at TEXT")
    if "source_type" not in columns: db.execute("ALTER TABLE books ADD COLUMN source_type TEXT NOT NULL DEFAULT 'book'")
    if "video_url" not in columns: db.execute("ALTER TABLE books ADD COLUMN video_url TEXT DEFAULT ''")
    if "subtitle_type" not in columns: db.execute("ALTER TABLE books ADD COLUMN subtitle_type TEXT DEFAULT ''")
    db.commit()
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
    db=connect(); db.execute("UPDATE books SET source_type=?,video_url=?,subtitle_type=? WHERE id=?",
      (book.get("sourceType","book"),book.get("video",""),book.get("subtitleType",""),book["id"])); db.commit(); db.close()

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
    db=connect(); rows=db.execute("SELECT id,title,english_title,series,level,status,cover_url,duration,alignment,updated_at,last_read_at,source_type,video_url,subtitle_type FROM books ORDER BY (last_read_at IS NULL),last_read_at DESC,created_at ASC").fetchall(); db.close()
    return [dict(row) for row in rows]

def touch_book(book_id):
    db=connect(); db.execute("UPDATE books SET last_read_at=? WHERE id=?",(now(),book_id)); db.commit(); db.close()

def add_daily(reading_seconds=0,sentences=0,lookups=0,reviews=0,shadow_attempts=0,sessions=0):
    day=datetime.now().astimezone().date().isoformat(); stamp=now(); db=connect()
    db.execute("""INSERT INTO learning_daily(day,reading_seconds,sentences,lookups,reviews,shadow_attempts,sessions,updated_at)
      VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(day) DO UPDATE SET
      reading_seconds=reading_seconds+excluded.reading_seconds,sentences=sentences+excluded.sentences,
      lookups=lookups+excluded.lookups,reviews=reviews+excluded.reviews,
      shadow_attempts=shadow_attempts+excluded.shadow_attempts,sessions=sessions+excluded.sessions,updated_at=excluded.updated_at""",
      (day,reading_seconds,sentences,lookups,reviews,shadow_attempts,sessions,stamp)); db.commit(); db.close()

def learning_days(limit=365):
    db=connect(); rows=db.execute("SELECT * FROM learning_daily ORDER BY day DESC LIMIT ?",(limit,)).fetchall(); db.close(); return [dict(row) for row in rows]

def vocabulary_list():
    db=connect(); rows=db.execute("SELECT * FROM vocabulary ORDER BY due_at,updated_at DESC").fetchall(); db.close(); return [dict(row) for row in rows]

def save_vocab(item):
    stamp=now(); due=item.get("due_at") or stamp; db=connect()
    db.execute("""INSERT INTO vocabulary(book_id,sentence_id,word_index,word,root,phonetic,meaning,context,note,rating,interval_days,due_at,reviews,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(book_id,sentence_id,word_index) DO UPDATE SET
      word=excluded.word,root=excluded.root,phonetic=excluded.phonetic,meaning=excluded.meaning,context=excluded.context,
      note=CASE WHEN excluded.note='' THEN vocabulary.note ELSE excluded.note END,rating=excluded.rating,
      interval_days=excluded.interval_days,due_at=excluded.due_at,reviews=vocabulary.reviews+1,updated_at=excluded.updated_at""",
      (item["book_id"],item["sentence_id"],int(item["word_index"]),item["word"],item.get("root",item["word"].lower()),item.get("phonetic",""),
       item.get("meaning",""),item.get("context",""),item.get("note",""),item.get("rating","unknown"),int(item.get("interval_days",1)),due,
       int(item.get("reviews",0)),stamp,stamp)); db.commit(); db.close()

def update_vocab(vocab_id,values):
    allowed={k:v for k,v in values.items() if k in {"note","rating","interval_days","due_at","word","meaning"}}
    if not allowed:return
    allowed["updated_at"]=now(); fields=",".join(f"{key}=?" for key in allowed); db=connect()
    db.execute(f"UPDATE vocabulary SET {fields},reviews=reviews+1 WHERE id=?",[*allowed.values(),vocab_id]); db.commit(); db.close()

def annotate_word(book_id,sentence_id,word_index,corrected_word=None,note=None):
    db=connect(); row=db.execute("SELECT data_json FROM books WHERE id=?",(book_id,)).fetchone()
    if not row: db.close(); raise ValueError("book not found")
    book=json.loads(row[0]); sentence=next((s for s in book["sentences"] if s["id"]==sentence_id),None)
    if not sentence or word_index<0 or word_index>=len(sentence.get("words",[])): db.close(); raise ValueError("word not found")
    original=sentence["words"][word_index]["text"]
    if corrected_word:
        matches=list(re.finditer(r"[A-Za-z]+(?:['’][A-Za-z]+)?|\d+",sentence["text"]))
        if word_index<len(matches):
            match=matches[word_index]; sentence["text"]=sentence["text"][:match.start()]+corrected_word+sentence["text"][match.end():]
        sentence["words"][word_index]["text"]=corrected_word
        db.execute("UPDATE books SET data_json=?,updated_at=? WHERE id=?",(json.dumps(book,ensure_ascii=False),now(),book_id))
    previous=db.execute("SELECT corrected_word,note FROM word_annotations WHERE book_id=? AND sentence_id=? AND word_index=?",(book_id,sentence_id,word_index)).fetchone()
    corrected=corrected_word if corrected_word is not None else (previous[0] if previous else "")
    saved_note=note if note is not None else (previous[1] if previous else "")
    db.execute("INSERT INTO word_annotations(book_id,sentence_id,word_index,original_word,corrected_word,note,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(book_id,sentence_id,word_index) DO UPDATE SET corrected_word=excluded.corrected_word,note=excluded.note,updated_at=excluded.updated_at",
      (book_id,sentence_id,word_index,original,corrected,saved_note,now())); db.commit(); db.close()
    if note is not None:
        db=connect(); db.execute("UPDATE vocabulary SET note=?,updated_at=? WHERE book_id=? AND sentence_id=? AND word_index=?",(saved_note,now(),book_id,sentence_id,word_index)); db.commit(); db.close()
    return {"originalWord":original,"correctedWord":corrected,"note":saved_note}

def get_book(book_id):
    db=connect(); row=db.execute("SELECT * FROM books WHERE id=?",(book_id,)).fetchone()
    annotations=[dict(item) for item in db.execute("SELECT * FROM word_annotations WHERE book_id=?",(book_id,)).fetchall()]; db.close()
    if not row: return None
    result=dict(row); result["book"]=json.loads(result.pop("data_json")); result["quality"]=json.loads(result.pop("quality_json") or "{}"); result["annotations"]=annotations
    return result

def delete_book(book_id,confirmed_title):
    """Delete one imported title and its private media tree with rollback protection."""
    db=connect(); row=db.execute("SELECT * FROM books WHERE id=?",(book_id,)).fetchone()
    if not row: db.close(); raise ValueError("book not found")
    if str(confirmed_title).strip()!=row["title"]: db.close(); raise ValueError("书名确认不匹配")
    source=(BOOKS_ROOT/row["source_path"]).resolve()
    try: source.relative_to(BOOKS_ROOT.resolve())
    except ValueError: db.close(); raise ValueError("资源路径越界，拒绝删除")
    if source==BOOKS_ROOT.resolve() or len(source.relative_to(BOOKS_ROOT.resolve()).parts)<2:
        db.close(); raise ValueError("资源目录范围过大，拒绝删除")
    if not source.is_dir():
        db.close(); raise ValueError("资源目录不存在；请先人工核对数据库路径")
    book=json.loads(row["data_json"])
    candidates={source}
    urls=[row["cover_url"],row["page_base_url"],row["audio_url"],row["pdf_url"],row["video_url"],
          book.get("pageBase",""),book.get("audio",""),book.get("pdf",""),book.get("video","")]
    for url in urls:
        if not isinstance(url,str) or not url.startswith("/books/"): continue
        target=(BOOKS_ROOT/unquote(url[len("/books/"):])).resolve()
        try: relative=target.relative_to(BOOKS_ROOT.resolve())
        except ValueError: db.close(); raise ValueError("关联资源路径越界，拒绝删除")
        if not relative.parts or len(relative.parts)<2: continue
        if target==source or source in target.parents: continue
        # Migrated books may keep generated pages in books/.reader/<book-id>/.
        if relative.parts[0]==".reader" and len(relative.parts)>=2:
            candidates.add((BOOKS_ROOT/relative.parts[0]/relative.parts[1]).resolve())
        elif target.exists(): candidates.add(target)
    # Remove descendants when their parent is already staged.
    targets=[]
    for candidate in sorted(candidates,key=lambda path:len(path.parts)):
        if not any(parent==candidate or parent in candidate.parents for parent in targets): targets.append(candidate)
    job_ids=[item[0] for item in db.execute("SELECT id FROM import_jobs WHERE book_id=? OR source_path=?",(book_id,row["source_path"])).fetchall()]
    trash_root=LOCAL_ROOT/"delete-staging"; trash_root.mkdir(parents=True,exist_ok=True)
    staging=trash_root/f"{book_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    staging.mkdir(); moved=[]
    for index,target in enumerate(targets):
        if not target.exists() and not target.is_symlink(): continue
        destination=staging/str(index); shutil.move(str(target),str(destination)); moved.append((destination,target))
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM vocabulary WHERE book_id=?",(book_id,))
        db.execute("DELETE FROM word_annotations WHERE book_id=?",(book_id,))
        db.execute("DELETE FROM book_artifacts WHERE book_id=?",(book_id,))
        db.execute("DELETE FROM import_jobs WHERE book_id=? OR source_path=?",(book_id,row["source_path"]))
        db.execute("DELETE FROM books WHERE id=?",(book_id,))
        db.commit()
    except Exception:
        db.rollback()
        for staged,original in reversed(moved):
            if staged.exists() and not original.exists(): original.parent.mkdir(parents=True,exist_ok=True); shutil.move(str(staged),str(original))
        db.close(); raise
    db.close()
    shutil.rmtree(staging)
    log_names=[]
    for job_id in job_ids:
        log_names += [f"import-{job_id}.log",f"whisper-{job_id}.log",f"video-import-{job_id}.log",f"video-whisper-{job_id}.log",
                      f"youtube-{job_id}.log",f"youtube-import-{job_id}.log"]
    log_names += [f"ctc-{book_id}.log",f"dtw-{book_id}.log"]
    for name in log_names:
        path=LOCAL_ROOT/name
        try: path.unlink(missing_ok=True)
        except OSError: pass
    # Remove now-empty series directory, but never the books root.
    try:
        parent=source.parent
        if parent!=BOOKS_ROOT.resolve() and not any(parent.iterdir()): parent.rmdir()
    except OSError: pass
    return {"id":row["id"],"title":row["title"],"sourcePath":row["source_path"],"removedTargets":len(moved)}

def create_job(source_path):
    stamp=now(); db=connect(); cur=db.execute("INSERT INTO import_jobs(source_path,status,progress,step,created_at,updated_at) VALUES(?,?,?,?,?,?)",
        (source_path,"queued",0,"等待开始",stamp,stamp)); db.commit(); job_id=cur.lastrowid; db.close(); return job_id

def update_job(job_id,**values):
    values["updated_at"]=now(); fields=",".join(f"{key}=?" for key in values); params=list(values.values())+[job_id]
    db=connect(); db.execute(f"UPDATE import_jobs SET {fields} WHERE id=?",params); db.commit(); db.close()

def get_job(job_id):
    db=connect(); row=db.execute("SELECT * FROM import_jobs WHERE id=?",(job_id,)).fetchone(); db.close(); return dict(row) if row else None
