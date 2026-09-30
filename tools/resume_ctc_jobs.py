#!/usr/bin/env python3
"""Resume failed import jobs that already reached the CTC stage."""
import argparse
import json
import os
import sqlite3
import subprocess
from pathlib import Path

from library_db import DB_PATH, ROOT, get_job, update_job

ALIGNER=ROOT/".local/forced-aligner/venv/bin/python"
CTC=ROOT/"tools/ctc_forced_align.py"

def book_info(book_id):
    db=sqlite3.connect(DB_PATH);row=db.execute("SELECT title,data_json FROM books WHERE id=?",(book_id,)).fetchone();db.close()
    if not row:return None
    book=json.loads(row[1]);return {"title":row[0],"sentences":len(book.get("sentences",[])),"duration":float(book.get("duration",0))}

def resume(job_id):
    job=get_job(job_id)
    if not job:raise ValueError(f"任务 {job_id} 不存在")
    book_id=job.get("book_id")
    info=book_info(book_id)
    if not book_id or not info:raise ValueError(f"任务 {job_id} 没有可恢复的书籍数据")
    log=ROOT/".local"/f"ctc-{book_id}.log"
    update_job(job_id,status="running",progress=98,step=f"恢复 wav2vec2 CTC 0/{info['sentences']}",error="",pid=os.getpid())
    try:
        with log.open("w") as output:
            subprocess.run([str(ALIGNER),str(CTC),"--book-id",str(book_id),"--job-id",str(job_id),"--update-db"],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,check=True)
        complete_step="YouTube 导入完成" if job.get("kind")=="youtube" else "视频导入完成" if job.get("kind")=="video" else "导入完成"
        update_job(job_id,status="complete",progress=100,step=complete_step,error="",pid=None)
        print(f"[{job_id}] {info['title']} CTC恢复完成",flush=True)
    except Exception as exc:
        update_job(job_id,status="failed",step="CTC恢复失败",error=f"{exc}；日志：{log.name}",pid=None)
        print(f"[{job_id}] {info['title']} CTC恢复失败：{exc}",flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument("job_ids",nargs="+",type=int);args=parser.parse_args()
    if not ALIGNER.exists():raise SystemExit("未安装 wav2vec2 CTC 环境")
    try:os.nice(10)
    except OSError:pass
    jobs=[]
    for job_id in args.job_ids:
        job=get_job(job_id);info=book_info(job.get("book_id")) if job else None
        if job and info:jobs.append((info["duration"],info["sentences"],job_id))
    for _,__,job_id in sorted(jobs):resume(job_id)

if __name__=="__main__":main()
