#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from library_db import BOOKS_ROOT, ROOT, display_title, save_artifact, save_dictionary, slug_for, update_job, upsert_book

PDF_OCR=ROOT/".local/bin/pdf_ocr"
WHISPER=ROOT/"tools/vendor/whisper.cpp/build/bin/whisper-cli"
MODEL=ROOT/"tools/vendor/whisper.cpp/models/ggml-base.en.bin"

def run(command,**kwargs): return subprocess.run([str(x) for x in command],check=True,**kwargs)
def set_job(job_id,progress,step,**extra): update_job(job_id,progress=progress,step=step,**extra)

def ensure_ocr():
    if PDF_OCR.exists(): return
    PDF_OCR.parent.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,SWIFT_MODULECACHE_PATH="/tmp/english-swift-cache",CLANG_MODULE_CACHE_PATH="/tmp/english-clang-cache")
    run(["swiftc",ROOT/"tools/pdf_ocr.swift","-o",PDF_OCR,"-framework","PDFKit","-framework","Vision","-framework","AppKit"],env=env)

def merge_audio(files,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    if len(files)==1:
        if target.exists(): target.unlink()
        try: os.symlink(files[0],target)
        except OSError: shutil.copy2(files[0],target)
        return
    manifest=target.with_suffix(".concat.txt")
    manifest.write_text("".join("file '"+str(path).replace("'","'\\''")+"'\n" for path in files))
    run(["ffmpeg","-y","-v","error","-f","concat","-safe","0","-i",manifest,"-c","copy",target])

def choose_pages(ocr):
    texts=[" ".join(line["text"] for line in page["lines"]) for page in ocr]
    contents=next((i for i,text in enumerate(texts) if re.search(r"\bCONTENTS\b",text,re.I)),None)
    start=(contents+1) if contents is not None else 0
    if contents is None:
        for i,text in enumerate(texts):
            english=len(re.findall(r"\b[A-Za-z]{2,}\b",text))
            if english>=18 and not re.search(r"copyright|isbn|published by|activities before reading",text,re.I): start=i; break
    end=len(ocr)
    for i in range(start+10,len(texts)):
        if re.search(r"^\s*ACTIVITIES\b|\bACTIVITIES\s+(?:Before|While|After)\s+Reading",texts[i],re.I): end=i; break
    return start+1,max(start+1,end)

def import_book(job_id,relative):
    source=(BOOKS_ROOT/relative).resolve(); source.relative_to(BOOKS_ROOT.resolve())
    if not source.is_dir(): raise ValueError("书籍目录不存在")
    pdfs=sorted(source.glob("*.pdf")); audios=sorted(source.glob("*.mp3"))
    if not pdfs or not audios: raise ValueError("导入需要至少一个 PDF 和一个 MP3")
    book_id=slug_for(relative); generated=source/".reader"; pages=generated/"pages"
    generated.mkdir(parents=True,exist_ok=True); pages.mkdir(parents=True,exist_ok=True)
    update_job(job_id,book_id=book_id,status="running")

    set_job(job_id,5,"准备音频")
    audio_out=generated/"audio.mp3"; merge_audio(audios,audio_out)
    set_job(job_id,12,"编译本地 OCR")
    ensure_ocr()
    ocr_file=generated/"ocr.json"
    set_job(job_id,18,"识别 PDF 页面文字")
    run([PDF_OCR,pdfs[0],ocr_file,pages,"1.6"],stdout=subprocess.DEVNULL)
    ocr=json.loads(ocr_file.read_text()); page_start,page_end=choose_pages(ocr)

    title=display_title(source.name); series=Path(relative).parts[0]
    level_match=re.search(r"（(\d+)）",series); level=level_match.group(1) if level_match else ""
    page_base="/books/"+str((source/".reader/pages").relative_to(BOOKS_ROOT))
    audio_url="/books/"+str(audio_out.relative_to(BOOKS_ROOT)); pdf_url="/books/"+str(pdfs[0].relative_to(BOOKS_ROOT))
    book_json=generated/"book.json"
    set_job(job_id,55,"生成正文和初始时间轴")
    run([sys.executable,ROOT/"tools/build_book.py","--ocr",ocr_file,"--audio",audio_out,"--output",book_json,
         "--id",book_id,"--title",title,"--level",level,"--page-start",page_start,"--page-end",page_end,
         "--audio-url",audio_url,"--pdf-url",pdf_url])

    whisper_prefix=generated/"whisper"
    set_job(job_id,63,"Whisper DTW 正在生成词级时间轴")
    whisper_log=ROOT/".local"/f"whisper-{job_id}.log"
    run([WHISPER,"-m",MODEL,"-f",audio_out,"-l","en","-t","4","-p","2","-ng","-dtw","base.en","-ml","1","-sow","-ojf","-of",whisper_prefix,"-np"],
        stdout=subprocess.DEVNULL,stderr=whisper_log.open("w"))
    set_job(job_id,88,"对齐原文与音频")
    run([sys.executable,ROOT/"tools/align_whisper.py","--book",book_json,"--whisper",str(whisper_prefix)+".json",
         "--report",generated/"whisper-alignment.json","--min-match","0.25"])
    book=json.loads(book_json.read_text()); quality=json.loads((generated/"quality-report.json").read_text())
    book["pageBase"]=page_base
    cover=page_base+"/page-001.jpg"
    set_job(job_id,96,"写入本地数据库")
    upsert_book(book,quality,relative,series,page_base,cover)
    save_artifact(book_id,"ocr",ocr)
    save_artifact(book_id,"whisper",json.loads((Path(str(whisper_prefix)+".json")).read_text()))
    alignment_file=generated/"whisper-alignment.json"
    if alignment_file.exists(): save_artifact(book_id,"alignment",json.loads(alignment_file.read_text()))
    dictionary_file=ROOT/".local"/f"dictionary-{job_id}.json"
    run([sys.executable,ROOT/"tools/build_local_dictionary.py","--book",book_json,"--output",dictionary_file])
    save_dictionary(json.loads(dictionary_file.read_text())); dictionary_file.unlink()
    aligner_python=ROOT/".local/forced-aligner/venv/bin/python"
    if aligner_python.exists():
        set_job(job_id,98,"wav2vec2 CTC 强制对齐")
        subprocess.run([aligner_python,ROOT/"tools/ctc_forced_align.py","--book-id",book_id,"--update-db"],cwd=ROOT,stdout=(ROOT/".local"/f"ctc-{book_id}.log").open("w"),stderr=subprocess.STDOUT)
    for artifact in [ocr_file,book_json,generated/"quality-report.json",Path(str(whisper_prefix)+".json"),alignment_file,audio_out.with_suffix(".concat.txt")]:
        if artifact.exists(): artifact.unlink()
    update_job(job_id,status="complete",progress=100,step="导入完成")

def main():
    job_id=int(sys.argv[1]); relative=sys.argv[2]
    try: import_book(job_id,relative)
    except Exception as exc:
        update_job(job_id,status="failed",step="导入失败",error=str(exc))
        raise

if __name__=="__main__": main()
