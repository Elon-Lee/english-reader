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

def probe_video(path,url,label):
    data=json.loads(subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=codec_name,width,height,bit_rate:format=bit_rate,duration","-of","json",path],text=True));stream=(data.get("streams") or [{}])[0];fmt=data.get("format") or {}
    return {"label":label,"url":url,"status":"ready","codec":stream.get("codec_name","") or "","width":int(stream.get("width",0) or 0),"height":int(stream.get("height",0) or 0),"bitrate":int(stream.get("bit_rate") or fmt.get("bit_rate") or 0),"bytes":path.stat().st_size,"duration":float(fmt.get("duration",0) or 0)}

def optimize_video(data):
    source=local_path(data.get("video",""))
    if not source or not source.is_file():return data.get("video",""),data.get("videoVariants",{}),False
    book_dir=next((parent for parent in [source.parent,*source.parents] if (parent/"source.mp4").is_file()),source.parent)
    original=book_dir/"source.mp4";target=book_dir/".reader"/"video-muted.mp4";target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists() or target.stat().st_mtime_ns<original.stat().st_mtime_ns:
        subprocess.run(["ffmpeg","-y","-v","error","-i",str(original),"-map","0:v:0","-c:v","copy","-an","-movflags","+faststart",str(target)],check=True)
    low=book_dir/".reader"/"video-low.mp4";created=False
    if not low.exists() or low.stat().st_mtime_ns<original.stat().st_mtime_ns:
        subprocess.run(["ffmpeg","-y","-v","error","-i",str(original),"-map","0:v:0","-an","-vf","scale=640:360:force_original_aspect_ratio=decrease:force_divisible_by=2","-c:v","libx264","-preset","veryfast","-crf","27","-maxrate","380k","-bufsize","760k","-g","50","-keyint_min","50","-pix_fmt","yuv420p","-threads","2","-movflags","+faststart",str(low)],check=True);created=True
    high_url="/books/"+str(target.relative_to(BOOKS_ROOT));low_url="/books/"+str(low.relative_to(BOOKS_ROOT));variants={"high":probe_video(target,high_url,"高清"),"low":probe_video(low,low_url,"流畅")}
    return high_url,variants,created

def main():
    db=sqlite3.connect(DB_PATH);db.row_factory=sqlite3.Row;rows=db.execute("SELECT id,cover_url,video_url,data_json,quality_json FROM books WHERE status='ready'").fetchall();covers=videos=low_videos=0
    for row in rows:
        cover=optimize_cover_url(row["cover_url"]);data=json.loads(row["data_json"]);video=row["video_url"]
        if cover!=row["cover_url"]:covers+=1
        if data.get("video"):
            optimized,variants,created=optimize_video(data)
            if optimized and optimized!=data.get("video"):
                data["video"]=optimized;video=optimized;videos+=1
            data["videoDefaultQuality"]="high";data["videoVariants"]=variants;low_videos+=1 if created else 0
        quality=json.loads(row["quality_json"] or "{}");quality["videoVariants"]=data.get("videoVariants",{})
        db.execute("UPDATE books SET cover_url=?,video_url=?,data_json=?,quality_json=?,updated_at=datetime('now') WHERE id=?",(cover,video,json.dumps(data,ensure_ascii=False),json.dumps(quality,ensure_ascii=False),row["id"]))
    db.commit();db.close();print(json.dumps({"covers":covers,"videos":videos,"lowVideosGenerated":low_videos},ensure_ascii=False))
if __name__=="__main__":main()
