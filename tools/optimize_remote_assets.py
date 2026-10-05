#!/usr/bin/env python3
"""Generate low-bandwidth covers and mute/faststart video display copies."""
import json,sqlite3,subprocess,sys
from pathlib import Path
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"tools"))
from library_db import BOOKS_ROOT,DB_PATH,optimize_cover_url

def local_path(url):
    if not isinstance(url,str) or not url.startswith("/books/"):return None
    path=(BOOKS_ROOT/unquote(url[len("/books/"):])).resolve()
    try:path.relative_to(BOOKS_ROOT.resolve())
    except ValueError:return None
    return path

def optimize_video(data):
    source=local_path(data.get("video",""))
    if not source or not source.is_file():return data.get("video","")
    book_dir=next((parent for parent in [source.parent,*source.parents] if (parent/"source.mp4").is_file()),source.parent)
    original=book_dir/"source.mp4";target=book_dir/".reader"/"video-muted.mp4";target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists() or target.stat().st_mtime_ns<original.stat().st_mtime_ns:
        subprocess.run(["ffmpeg","-y","-v","error","-i",str(original),"-map","0:v:0","-c:v","copy","-an","-movflags","+faststart",str(target)],check=True)
    return "/books/"+str(target.relative_to(BOOKS_ROOT))

def main():
    db=sqlite3.connect(DB_PATH);db.row_factory=sqlite3.Row;rows=db.execute("SELECT id,cover_url,video_url,data_json FROM books WHERE status='ready'").fetchall();covers=videos=0
    for row in rows:
        cover=optimize_cover_url(row["cover_url"]);data=json.loads(row["data_json"]);video=row["video_url"]
        if cover!=row["cover_url"]:covers+=1
        if data.get("video"):
            optimized=optimize_video(data)
            if optimized and optimized!=data.get("video"):
                data["video"]=optimized;video=optimized;videos+=1
        db.execute("UPDATE books SET cover_url=?,video_url=?,data_json=? WHERE id=?",(cover,video,json.dumps(data,ensure_ascii=False),row["id"]))
    db.commit();db.close();print(json.dumps({"covers":covers,"videos":videos},ensure_ascii=False))
if __name__=="__main__":main()
