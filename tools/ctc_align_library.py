#!/usr/bin/env python3
import sqlite3
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/".local/library.sqlite3"
PYTHON=ROOT/".local/forced-aligner/venv/bin/python"
ALIGNER=ROOT/"tools/ctc_forced_align.py"

db=sqlite3.connect(DB);rows=db.execute("SELECT id,title FROM books ORDER BY created_at").fetchall();db.close()
print(f"CTC queue: {len(rows)} books",flush=True)
for number,(book_id,title) in enumerate(rows,1):
    print(f"[{number}/{len(rows)}] {title}",flush=True)
    log=ROOT/".local"/f"ctc-{book_id}.log"
    with log.open("w") as output:
        result=subprocess.run([PYTHON,ALIGNER,"--book-id",book_id,"--update-db"],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
    if result.returncode: print(f"  failed; kept DTW (see {log})",flush=True)
    else:
        db=sqlite3.connect(DB);row=db.execute("SELECT json_extract(data_json,'$.forcedAlignment.coverage') FROM books WHERE id=?",(book_id,)).fetchone();db.close()
        print(f"  complete; coverage={float(row[0] or 0):.1%}",flush=True)
