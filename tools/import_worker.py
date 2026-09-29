#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from library_db import BOOKS_ROOT, ROOT, display_title, save_artifact, save_dictionary, slug_for, update_job, upsert_book
from import_source_plan import WORD_RE, authoritative_ocr, build_source_plan, write_plan

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

def media_duration(path):
    return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",path],text=True).strip())

def reset_generated(generated):
    for name in ("audio.mp3","audio.concat.txt","ocr.json","text-ocr.json","book.json","quality-report.json","whisper.json","whisper-alignment.json"):
        path=generated/name
        if path.exists():path.unlink()
    for name in ("pages","whisper-parts"):
        path=generated/name
        if path.exists():shutil.rmtree(path)

def offset_whisper(data,seconds):
    shift=round(seconds*1000)
    for segment in data.get("transcription",[]):
        offsets=segment.get("offsets",{})
        if "from" in offsets:offsets["from"]+=shift
        if "to" in offsets:offsets["to"]+=shift
    return data

def transcribe_parts(job_id,audios,generated,output):
    if len(audios)==1:
        log=ROOT/".local"/f"whisper-{job_id}.log"
        run([WHISPER,"-m",MODEL,"-f",audios[0],"-l","en","-t","4","-p","2","-ng","-dtw","base.en","-ml","1","-sow","-ojf","-of",output.with_suffix(""),"-np"],
            stdout=subprocess.DEVNULL,stderr=log.open("w"));return
    parts=generated/"whisper-parts";parts.mkdir(parents=True,exist_ok=True);combined=None;transcription=[];offset=0.0
    for index,audio in enumerate(audios,1):
        progress=63+round((index-1)/len(audios)*24);set_job(job_id,progress,f"Whisper DTW {index}/{len(audios)}：{audio.stem}")
        prefix=parts/f"part-{index:03d}";part_json=prefix.with_suffix(".json")
        if not part_json.exists():
            log=ROOT/".local"/f"whisper-{job_id}-{index:03d}.log"
            run([WHISPER,"-m",MODEL,"-f",audio,"-l","en","-t","4","-p","2","-ng","-dtw","base.en","-ml","1","-sow","-ojf","-of",prefix,"-np"],
                stdout=subprocess.DEVNULL,stderr=log.open("w"))
        data=offset_whisper(json.loads(part_json.read_text()),offset)
        if combined is None:combined={key:value for key,value in data.items() if key!="transcription"}
        transcription.extend(data.get("transcription",[]));offset+=media_duration(audio)
    combined["transcription"]=transcription;combined["result"]={"language":"en"};output.write_text(json.dumps(combined,ensure_ascii=False))

def validate_source_match(book,has_authoritative_text):
    words=sum(len(WORD_RE.findall(sentence.get("text",""))) for sentence in book.get("sentences",[]))
    expected=max(1,float(book.get("duration",0))*2.4);ratio=words/expected
    low,high=(.55,1.8) if has_authoritative_text else (.25,3.0)
    if words>=800 and book.get("duration",0)>=300 and not low<=ratio<=high:
        raise ValueError(f"正文与音频规模明显不一致：正文约 {words} 词，按音频时长预计约 {round(expected)} 词（比例 {ratio:.2f}，允许 {low:.2f}-{high:.2f}）")
    return {"textWords":words,"estimatedSpokenWords":round(expected),"ratio":round(ratio,3),"authoritativeText":has_authoritative_text}

def validate_source_plan(plan):
    if not plan.get("textSource") or plan.get("textWords",0)<800 or plan.get("audioDuration",0)<300:return
    expected=plan["audioDuration"]*2.4;ratio=plan["textWords"]/max(1,expected)
    if not .55<=ratio<=1.8:
        raise ValueError(f"导入前检查失败：权威正文约 {plan['textWords']} 词，按音频时长预计约 {round(expected)} 词（比例 {ratio:.2f}），可能是完整版/改写版不一致")

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
    book_id=slug_for(relative); generated=source/".reader"; pages=generated/"pages"
    generated.mkdir(parents=True,exist_ok=True)
    plan,pdf,text_source,paragraphs,audios=build_source_plan(source);plan_file=generated/"import-plan.json"
    validate_source_plan(plan)
    previous=json.loads(plan_file.read_text()) if plan_file.exists() else None
    if previous!=plan:reset_generated(generated)
    pages.mkdir(parents=True,exist_ok=True);write_plan(plan_file,plan)
    update_job(job_id,book_id=book_id,status="running")

    excluded=len(plan.get("excludedAudio",[]));set_job(job_id,5,f"准备音频：{len(audios)} 个文件"+(f"，排除 {excluded} 个重复候选" if excluded else ""))
    audio_out=generated/"audio.mp3"
    if not audio_out.exists(): merge_audio(audios,audio_out)
    set_job(job_id,12,"编译本地 OCR")
    ensure_ocr()
    ocr_file=generated/"ocr.json"
    if not ocr_file.exists():
        set_job(job_id,18,f"识别原书页：{pdf.name}")
        run([PDF_OCR,pdf,ocr_file,pages,"1.6"],stdout=subprocess.DEVNULL)
    else:set_job(job_id,54,"复用已完成的 OCR 数据")
    ocr=json.loads(ocr_file.read_text());content_ocr_file=ocr_file
    if paragraphs:
        content_ocr_file=generated/"text-ocr.json"
        if not content_ocr_file.exists():content_ocr_file.write_text(json.dumps(authoritative_ocr(paragraphs,ocr),ensure_ascii=False))
        content_ocr=json.loads(content_ocr_file.read_text());page_start,page_end=1,len(content_ocr)
    else:content_ocr=ocr;page_start,page_end=choose_pages(ocr)

    title=display_title(source.name); series=Path(relative).parts[0]
    level_match=re.search(r"（(\d+)）",series); level=level_match.group(1) if level_match else ""
    page_base="/books/"+str((source/".reader/pages").relative_to(BOOKS_ROOT))
    audio_url="/books/"+str(audio_out.relative_to(BOOKS_ROOT)); pdf_url="/books/"+str(pdf.relative_to(BOOKS_ROOT))
    book_json=generated/"book.json"
    if not book_json.exists() or not (generated/"quality-report.json").exists():
        set_job(job_id,55,"生成正文和初始时间轴")
        run([sys.executable,ROOT/"tools/build_book.py","--ocr",content_ocr_file,"--audio",audio_out,"--output",book_json,
             "--id",book_id,"--title",title,"--level",level,"--page-start",page_start,"--page-end",page_end,
             "--audio-url",audio_url,"--pdf-url",pdf_url])
    else:set_job(job_id,62,"复用已生成的正文数据")
    book=json.loads(book_json.read_text());source_check=validate_source_match(book,bool(text_source))
    quality=json.loads((generated/"quality-report.json").read_text());quality["sourcePlan"]={**plan,"textSource":plan.get("textSource"),"sourceCheck":source_check};(generated/"quality-report.json").write_text(json.dumps(quality,ensure_ascii=False,indent=2))

    whisper_prefix=generated/"whisper"
    whisper_json=Path(str(whisper_prefix)+".json")
    if not whisper_json.exists():
        set_job(job_id,63,"Whisper DTW 正在按章节生成词级时间轴")
        transcribe_parts(job_id,audios,generated,whisper_json)
    else:set_job(job_id,87,"复用已完成的 Whisper 数据")
    set_job(job_id,88,"对齐原文与音频")
    aligned=subprocess.run([sys.executable,ROOT/"tools/align_whisper.py","--book",book_json,"--whisper",str(whisper_prefix)+".json",
         "--report",generated/"whisper-alignment.json","--min-match","0.25"],text=True,capture_output=True)
    if aligned.returncode:
        detail=(aligned.stderr or aligned.stdout or "正文与音频对齐失败").strip().splitlines()[-1]
        raise ValueError(detail)
    book=json.loads(book_json.read_text()); quality=json.loads((generated/"quality-report.json").read_text())
    book["pageBase"]=page_base
    cover=page_base+"/page-001.jpg"
    set_job(job_id,96,"写入本地数据库")
    upsert_book(book,quality,relative,series,page_base,cover)
    save_artifact(book_id,"ocr",ocr)
    save_artifact(book_id,"import-plan",plan)
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
    for artifact in [ocr_file,generated/"text-ocr.json",book_json,generated/"quality-report.json",Path(str(whisper_prefix)+".json"),alignment_file,audio_out.with_suffix(".concat.txt")]:
        if artifact.exists(): artifact.unlink()
    update_job(job_id,status="complete",progress=100,step="导入完成")

def main():
    job_id=int(sys.argv[1]); relative=sys.argv[2]
    try: import_book(job_id,relative)
    except Exception as exc:
        update_job(job_id,status="failed",step="导入失败",error=str(exc))
        raise

if __name__=="__main__": main()
