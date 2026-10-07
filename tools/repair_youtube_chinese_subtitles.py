#!/usr/bin/env python3
"""Download and attach YouTube Chinese caption tracks without reprocessing media."""
import argparse
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from build_video_book import attach_chinese,subtitle_entries
from import_youtube_worker import download_translated_caption,probe_info
from library_db import BOOKS_ROOT,DB_PATH,ROOT
from youtube_subtitles import select_chinese_track


def now():return datetime.now().astimezone().isoformat(timespec="seconds")

def backup_database():
    stamp=datetime.now().strftime("%Y%m%d-%H%M%S");target=ROOT/".local/backups"/f"library-before-youtube-zh-{stamp}.sqlite3";target.parent.mkdir(parents=True,exist_ok=True)
    source=sqlite3.connect(DB_PATH);backup=sqlite3.connect(target);source.backup(backup);backup.close();source.close();return target

def repair(book_id):
    db=sqlite3.connect(DB_PATH);db.row_factory=sqlite3.Row;row=db.execute("SELECT * FROM books WHERE id=? AND source_type='youtube'",(book_id,)).fetchone()
    if not row:db.close();raise ValueError("YouTube读物不存在")
    source=BOOKS_ROOT/row["source_path"];metadata_path=source/".video-import.json";info_path=source/"source.info.json"
    metadata=json.loads(metadata_path.read_text()) if metadata_path.exists() else {};info=json.loads(info_path.read_text()) if info_path.exists() else {}
    track=select_chinese_track(info)
    if not track:
        source_url=metadata.get("sourceUrl") or json.loads(row["data_json"]).get("sourceUrl")
        if not source_url:db.close();raise ValueError("没有YouTube源地址，无法刷新字幕")
        info=probe_info(source_url);track=select_chinese_track(info);info_path.write_text(json.dumps(info,ensure_ascii=False),encoding="utf-8")
    if not track:db.close();raise ValueError("YouTube没有可用的中文或中文机器翻译字幕")
    target=source/"subtitles.zh-CN.srt";log=ROOT/".local"/f"youtube-zh-repair-{book_id}.log";log.write_text("")
    downloaded=download_translated_caption(track,target,log,attempts=3) if track.get("translated") else None
    if not downloaded:
        db.close();raise RuntimeError("中文字幕下载失败，详情见 "+str(log))
    cues=subtitle_entries(target,False)
    if len(cues)<3:db.close();raise ValueError("中文字幕内容过少")
    data=json.loads(row["data_json"]);sentences=data.get("sentences") or [];alignment=attach_chinese(sentences,cues)
    if alignment["coverage"]<.5:db.close();raise ValueError(f"中文字幕覆盖率过低：{alignment['coverage']:.1%}")
    data.update({"youtubeChineseSubtitleAvailable":True,"youtubeChineseSubtitleDownloaded":True,"youtubeChineseSubtitleSource":track["source"],"youtubeChineseSubtitleTrack":track["code"],"youtubeChineseSubtitleLanguage":"zh-CN","youtubeChineseSubtitleTranslated":bool(track.get("translated")),"translationAlignment":alignment})
    metadata.update({"youtubeChineseSubtitleAvailable":True,"youtubeChineseSubtitleDownloaded":True,"youtubeChineseSubtitleSource":track["source"],"youtubeChineseSubtitleTrack":track["code"],"youtubeChineseSubtitleLanguage":"zh-CN","youtubeChineseSubtitleTranslated":bool(track.get("translated"))})
    quality=json.loads(row["quality_json"] or "{}");quality["translationAlignment"]=alignment;stamp=now();backup=backup_database()
    try:
        db.execute("BEGIN")
        db.execute("UPDATE books SET data_json=?,quality_json=?,updated_at=? WHERE id=?",(json.dumps(data,ensure_ascii=False),json.dumps(quality,ensure_ascii=False),stamp,book_id))
        db.execute("INSERT INTO book_artifacts(book_id,kind,data_json,created_at) VALUES(?,?,?,?) ON CONFLICT(book_id,kind) DO UPDATE SET data_json=excluded.data_json,created_at=excluded.created_at",(book_id,"subtitle-zh",json.dumps({"type":"external","source":track["source"],"track":track["code"],"translated":bool(track.get("translated")),"text":target.read_text(errors="replace")},ensure_ascii=False),stamp))
        db.commit();metadata_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    except Exception:
        db.rollback();shutil.copy2(backup,DB_PATH);raise
    finally:db.close()
    return {"bookId":book_id,"track":track["code"],"source":track["source"],"translated":bool(track.get("translated")),"cues":len(cues),**alignment,"backup":str(backup)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--book-id",required=True);args=parser.parse_args();print(json.dumps(repair(args.book_id),ensure_ascii=False,indent=2))

if __name__=="__main__":main()
