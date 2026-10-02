#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from import_video_worker import import_video
from library_db import BOOKS_ROOT, ROOT, update_job
from youtube_subtitles import has_translated_english_track,select_native_english_track

YTDLP=ROOT/".local/bin/yt-dlp"
NODE=Path(shutil.which("node") or "/usr/local/bin/node")

def safe_name(value): return re.sub(r"[^\w\-\u4e00-\u9fff]+","-",value).strip("-") or "youtube-video"

def run_ytdlp(command,log,job_id,progress=False):
    recent=[]
    with log.open("a") as output:
        process=subprocess.Popen([str(item) for item in command],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        for line in process.stdout:
            output.write(line);output.flush();recent.append(line.strip());recent=recent[-30:]
            if progress:
                match=re.search(r"\[download\]\s+([0-9.]+)%",line)
                if match:update_job(job_id,progress=5+round(float(match.group(1))*.20),step="下载 YouTube 视频")
        code=process.wait()
    return code,recent

def probe_info(url):
    output=subprocess.check_output([str(YTDLP),"--js-runtimes",f"node:{NODE}","--dump-single-json","--no-playlist","--skip-download",url],text=True,stderr=subprocess.STDOUT,timeout=120)
    return json.loads(output)

def download_english_subtitle(url,destination,log,job_id,info):
    for stale in destination.glob("source.*.srt"):stale.unlink()
    track=select_native_english_track(info)
    if not track:return None,"none",None
    common=[YTDLP,"--js-runtimes",f"node:{NODE}","--no-playlist","--skip-download","--sub-langs",track["code"],"--sub-format","srt","--convert-subs","srt","-o",str(destination/"source.%(ext)s")]
    label="人工英文字幕" if track["source"]=="manual" else "原生自动英文字幕";update_job(job_id,progress=4,step=f"下载 YouTube {label}")
    flag="--write-subs" if track["source"]=="manual" else "--write-auto-subs";code,_=run_ytdlp(common[:4]+[flag]+common[4:]+[url],log,job_id)
    subtitle=next(iter(sorted(destination.glob("source.*.srt"))),None)
    if code!=0 or not subtitle:return None,"none",track
    return subtitle,track["source"],track

def main():
    try:os.nice(10)
    except OSError:pass
    job_id=int(sys.argv[1]); request_file=Path(sys.argv[2]); request=json.loads(request_file.read_text())
    url=request["url"]; title=request["title"]; series=request["series"]; video_id=request.get("videoId","") or "video"
    relative=str(Path(series)/f"youtube.{safe_name(title)}-{safe_name(video_id)}")
    destination=BOOKS_ROOT/relative; destination.mkdir(parents=True,exist_ok=True)
    update_job(job_id,source_path=relative,status="running",progress=3,step="读取 YouTube 信息")
    command=[YTDLP,"--js-runtimes",f"node:{NODE}","--no-playlist","--newline","--progress","--retries","5","--fragment-retries","5","--write-info-json","--write-thumbnail",
      "-f","bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/b[height<=720]/best[height<=720]",
      "--merge-output-format","mp4","-o",str(destination/"source.%(ext)s"),url]
    log=ROOT/".local"/f"youtube-{job_id}.log"
    try:
        log.write_text("")
        info=probe_info(url);subtitle,subtitle_source,subtitle_track=download_english_subtitle(url,destination,log,job_id,info)
        code,recent=run_ytdlp(command,log,job_id,progress=True)
        if code!=0:
            reason=next((line for line in reversed(recent) if line.startswith("ERROR:") or "HTTP Error" in line),"")
            raise RuntimeError(reason or "yt-dlp 视频下载失败，请检查地址、网络或登录权限")
        video=next(iter(sorted(destination.glob("source.mp4"))+sorted(destination.glob("source.mkv"))+sorted(destination.glob("source.webm"))),None)
        if not video: raise RuntimeError("下载完成但没有找到视频文件")
        if video.suffix.lower()!=".mp4":
            converted=destination/"source.mp4"; subprocess.run(["ffmpeg","-y","-v","error","-i",video,"-c","copy",converted],check=True); video.unlink()
        if subtitle and subtitle.exists() and subtitle.name!="subtitles.srt": shutil.move(subtitle,destination/"subtitles.srt")
        metadata={"title":title,"englishTitle":request.get("englishTitle",title),"series":series,"level":request.get("level",""),"sourceType":"youtube",
          "subtitleStrategy":"auto","youtubeSubtitleSource":subtitle_source,"youtubeSubtitleTrack":subtitle_track["code"] if subtitle_track else "","youtubeSubtitleLanguage":"en" if subtitle_track else "","youtubeSubtitleTranslated":False,"translatedEnglishRejected":has_translated_english_track(info),"sourceUrl":url,"youtubeId":video_id,"channel":request.get("channel","")}
        (destination/".video-import.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
        update_job(job_id,source_path=relative,progress=25,step="YouTube 下载完成，开始视频处理")
        import_video(job_id,relative,progress_base=25,progress_span=75)
    except Exception as exc:
        update_job(job_id,status="failed",step="YouTube 导入失败",error=str(exc)); raise
    finally:
        request_file.unlink(missing_ok=True)

if __name__=="__main__": main()
