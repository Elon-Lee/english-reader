#!/usr/bin/env python3
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from library_db import BOOKS_ROOT, ROOT, save_artifact, save_dictionary, slug_for, update_job, upsert_book

WHISPER=ROOT/"tools/vendor/whisper.cpp/build/bin/whisper-cli"
MODEL=ROOT/"tools/vendor/whisper.cpp/models/ggml-base.en.bin"

def run(command,**kwargs):return subprocess.run([str(item) for item in command],check=True,**kwargs)
def set_job(job_id,progress,step,**extra):update_job(job_id,progress=progress,step=step,**extra)

def embedded_subtitle(video,target):
    probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-select_streams","s","-show_entries","stream=index,codec_name:stream_tags=language,title","-of","json",video],text=True))
    streams=probe.get("streams",[])
    if not streams:return False
    selected=next((item for item in streams if item.get("tags",{}).get("language","").lower().startswith("en")),streams[0])
    try:run(["ffmpeg","-y","-v","error","-i",video,"-map",f"0:{selected['index']}",target]);return True
    except subprocess.CalledProcessError:return False

def import_video(job_id,relative,progress_base=0,progress_span=100):
    def progress(raw,step): set_job(job_id,progress_base+round(raw*progress_span/100),step)
    source=(BOOKS_ROOT/relative).resolve();source.relative_to(BOOKS_ROOT.resolve())
    metadata=json.loads((source/".video-import.json").read_text()); videos=sorted(source.glob("*.mp4"))+sorted(source.glob("*.mov"))+sorted(source.glob("*.m4v"))
    if not videos:raise ValueError("没有找到视频文件")
    video=videos[0];generated=source/".reader";pages=generated/"pages";generated.mkdir(parents=True,exist_ok=True);pages.mkdir(parents=True,exist_ok=True)
    book_id=slug_for(relative);update_job(job_id,book_id=book_id,status="running")
    progress(8,"提取视频音频")
    audio=generated/"audio.mp3";run(["ffmpeg","-y","-v","error","-i",video,"-vn","-ac","1","-ar","16000","-b:a","64k",audio])
    progress(18,"生成视频关键帧")
    for old in pages.glob("page-*.jpg"):old.unlink()
    run(["ffmpeg","-y","-v","error","-i",video,"-vf","fps=1/15,scale=960:-2","-q:v","3",pages/"page-%03d.jpg"])
    if not any(pages.glob("*.jpg")):run(["ffmpeg","-y","-v","error","-ss","0","-i",video,"-frames:v","1","-vf","scale=960:-2",pages/"page-001.jpg"])

    strategy=metadata.get("subtitleStrategy","auto");subtitle=None;subtitle_type="whisper"
    external=next(iter(sorted(source.glob("*.srt"))+sorted(source.glob("*.vtt"))),None)
    if strategy!="whisper" and external:subtitle=external;subtitle_type="external"
    elif strategy!="whisper":
        extracted=generated/"embedded.srt"
        if embedded_subtitle(video,extracted):subtitle=extracted;subtitle_type="embedded"
    progress(35,"Whisper DTW 正在转写视频")
    prefix=generated/"whisper";log=ROOT/".local"/f"video-whisper-{job_id}.log"
    with log.open("w") as output:
        run([WHISPER,"-m",MODEL,"-f",audio,"-l","en","-t","4","-p","2","-ng","-dtw","base.en","-ml","1","-sow","-ojf","-of",prefix,"-np"],stdout=subprocess.DEVNULL,stderr=output)
    progress(72,"构建视频正文与词级时间轴")
    page_base="/books/"+str(pages.relative_to(BOOKS_ROOT));audio_url="/books/"+str(audio.relative_to(BOOKS_ROOT));video_url="/books/"+str(video.relative_to(BOOKS_ROOT))
    book_file=generated/"book.json"
    command=[sys.executable,ROOT/"tools/build_video_book.py","--whisper",str(prefix)+".json","--audio",audio,"--output",book_file,"--id",book_id,
      "--title",metadata["title"],"--english-title",metadata.get("englishTitle",""),"--level",metadata.get("level",""),"--audio-url",audio_url,
      "--video-url",video_url,"--page-base",page_base,"--subtitle-type",subtitle_type]
    if subtitle:command += ["--subtitle",subtitle]
    run(command)
    if subtitle:
        progress(82,"对齐字幕与视频音频")
        run([sys.executable,ROOT/"tools/align_whisper.py","--book",book_file,"--whisper",str(prefix)+".json","--output",book_file,"--report",generated/"alignment.json","--min-match","0.2"])
        book=json.loads(book_file.read_text());book.update({"sourceType":metadata.get("sourceType","video"),"sourceUrl":metadata.get("sourceUrl",""),"channel":metadata.get("channel",""),"externalId":metadata.get("youtubeId",""),"video":video_url,"subtitleType":subtitle_type,"pageBase":page_base})
        for sentence in book["sentences"]:sentence["page"]=int(sentence["start"]//15)+1
        book_file.write_text(json.dumps(book,ensure_ascii=False,indent=2))
    book=json.loads(book_file.read_text());book.update({"sourceType":metadata.get("sourceType","video"),"sourceUrl":metadata.get("sourceUrl",""),"channel":metadata.get("channel",""),"externalId":metadata.get("youtubeId",""),"video":video_url,"subtitleType":subtitle_type,"pageBase":page_base});book_file.write_text(json.dumps(book,ensure_ascii=False,indent=2));quality={"status":"ready","sourceType":book["sourceType"],"subtitleType":subtitle_type,"sentences":len(book["sentences"])}
    progress(94,"写入视频书籍数据库")
    cover=page_base+"/page-001.jpg";upsert_book(book,quality,relative,metadata["series"],page_base,cover)
    save_artifact(book_id,"whisper-dtw",json.loads(Path(str(prefix)+".json").read_text()))
    if subtitle:save_artifact(book_id,"subtitle",{"type":subtitle_type,"text":subtitle.read_text(errors="replace")})
    dictionary_file=ROOT/".local"/f"video-dictionary-{job_id}.json";run([sys.executable,ROOT/"tools/build_local_dictionary.py","--book",book_file,"--output",dictionary_file]);save_dictionary(json.loads(dictionary_file.read_text()));dictionary_file.unlink()
    aligner_python=ROOT/".local/forced-aligner/venv/bin/python"
    if aligner_python.exists():
        progress(98,"wav2vec2 CTC 强制对齐")
        subprocess.run([aligner_python,ROOT/"tools/ctc_forced_align.py","--book-id",book_id,"--update-db"],cwd=ROOT,stdout=(ROOT/".local"/f"ctc-{book_id}.log").open("w"),stderr=subprocess.STDOUT)
    for item in [book_file,Path(str(prefix)+".json"),generated/"alignment.json",generated/"embedded.srt"]:
        if item.exists():item.unlink()
    update_job(job_id,status="complete",progress=100,step="视频导入完成")

def main():
    job_id=int(sys.argv[1]);relative=sys.argv[2]
    try:import_video(job_id,relative)
    except Exception as exc:update_job(job_id,status="failed",step="视频导入失败",error=str(exc));raise

if __name__=="__main__":main()
