#!/usr/bin/env python3
"""Sequentially rebuild every imported book with base.en DTW timestamps."""
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote

from library_db import BOOKS_ROOT, DB_PATH, ROOT, now, save_artifact

WHISPER=ROOT/"tools/vendor/whisper.cpp/build/bin/whisper-cli"
MODEL=ROOT/"tools/vendor/whisper.cpp/models/ggml-base.en.bin"

def audio_path(url):
    prefix="/books/"
    if not url.startswith(prefix): raise ValueError(f"unsupported audio URL: {url}")
    path=(BOOKS_ROOT/unquote(url[len(prefix):])).resolve()
    path.relative_to(BOOKS_ROOT.resolve())
    return path

def main():
    connection=sqlite3.connect(DB_PATH); connection.row_factory=sqlite3.Row
    rows=connection.execute("SELECT id,title,data_json,quality_json FROM books ORDER BY series,title").fetchall(); connection.close()
    print(f"DTW realignment queue: {len(rows)} books",flush=True)
    for number,row in enumerate(rows,1):
        book=json.loads(row["data_json"]); quality=json.loads(row["quality_json"] or "{}")
        audio=audio_path(book["audio"])
        print(f"[{number}/{len(rows)}] {row['title']}: Whisper base.en + DTW",flush=True)
        with tempfile.TemporaryDirectory(prefix="shiyue-dtw-") as tmp:
            directory=Path(tmp); book_file=directory/"book.json"; quality_file=directory/"quality-report.json"; prefix=directory/"whisper"
            book_file.write_text(json.dumps(book,ensure_ascii=False)); quality_file.write_text(json.dumps(quality,ensure_ascii=False))
            log=ROOT/".local"/f"dtw-{row['id']}.log"
            with log.open("w") as output:
                subprocess.run([WHISPER,"-m",MODEL,"-f",audio,"-l","en","-t","4","-p","2","-ng","-dtw","base.en",
                                "-ml","1","-sow","-ojf","-of",prefix,"-np"],check=True,stdout=subprocess.DEVNULL,stderr=output)
            report=directory/"alignment.json"
            subprocess.run([sys.executable,ROOT/"tools/align_whisper.py","--book",book_file,"--whisper",str(prefix)+".json",
                            "--report",report,"--min-match","0.25"],check=True)
            updated=json.loads(book_file.read_text()); updated_quality=json.loads(quality_file.read_text())
            connection=sqlite3.connect(DB_PATH)
            connection.execute("UPDATE books SET alignment=?,data_json=?,quality_json=?,updated_at=? WHERE id=?",
                (updated["alignment"],json.dumps(updated,ensure_ascii=False),json.dumps(updated_quality,ensure_ascii=False),now(),row["id"]))
            connection.commit(); connection.close()
            save_artifact(row["id"],"whisper-dtw",json.loads(Path(str(prefix)+".json").read_text()))
            save_artifact(row["id"],"alignment-dtw",json.loads(report.read_text()))
            info=updated["whisper"]
            print(f"  match={info['directWordMatch']:.1%}, normalized={info['normalization']}",flush=True)
    print("DTW realignment complete",flush=True)

if __name__=="__main__": main()
