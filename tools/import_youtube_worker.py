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
from youtube_subtitles import has_translated_english_track,select_chinese_track,select_native_english_track

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

def download_caption_track(url,destination,log,job_id,track,prefix,label):
    if not track:return None
    for stale in destination.glob(f"{prefix}.*.srt"):stale.unlink()
    target=destination/("subtitles.en.srt" if prefix=="english" else "subtitles.zh-CN.srt");target.unlink(missing_ok=True)
    update_job(job_id,progress=4,step=f"下载 YouTube {label}")
    flag="--write-subs" if track["source"]=="manual" else "--write-auto-subs"
    command=[YTDLP,"--js-runtimes",f"node:{NODE}","--no-playlist","--skip-download",flag,"--sub-langs",track["code"],"--sub-format","srt","--convert-subs","srt","-o",str(destination/f"{prefix}.%(ext)s"),url]
    code,_=run_ytdlp(command,log,job_id);subtitle=next(iter(sorted(destination.glob(f"{prefix}.*.srt"))),None)
    if code!=0 or not subtitle:return None
    shutil.move(subtitle,target)
    for stale in destination.glob(f"{prefix}.*.srt"):stale.unlink()
    return target

def download_bilingual_subtitles(url,destination,log,job_id,info):
    english_track=select_native_english_track(info);chinese_track=select_chinese_track(info)
    english_label="人工英文字幕" if english_track and english_track["source"]=="manual" else "原生自动英文字幕"
    chinese_label=("人工中文字幕" if chinese_track and chinese_track["source"]=="manual" else "原生自动中文字幕" if chinese_track and chinese_track["source"]=="automatic" else "自动翻译中文字幕")
    english=download_caption_track(url,destination,log,job_id,english_track,"english",english_label)
    chinese=download_caption_track(url,destination,log,job_id,chinese_track,"chinese",chinese_label)
    return english,english_track,chinese,chinese_track

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
        info=probe_info(url);subtitle,subtitle_track,chinese_subtitle,chinese_track=download_bilingual_subtitles(url,destination,log,job_id,info);subtitle_source=subtitle_track["source"] if subtitle and subtitle_track else "none"
        code,recent=run_ytdlp(command,log,job_id,progress=True)
        if code!=0:
            reason=next((line for line in reversed(recent) if line.startswith("ERROR:") or "HTTP Error" in line),"")
            raise RuntimeError(reason or "yt-dlp 视频下载失败，请检查地址、网络或登录权限")
        video=next(iter(sorted(destination.glob("source.mp4"))+sorted(destination.glob("source.mkv"))+sorted(destination.glob("source.webm"))),None)
        if not video: raise RuntimeError("下载完成但没有找到视频文件")
        if video.suffix.lower()!=".mp4":
            converted=destination/"source.mp4"; subprocess.run(["ffmpeg","-y","-v","error","-i",video,"-c","copy",converted],check=True); video.unlink()
        metadata={"title":title,"englishTitle":request.get("englishTitle",title),"series":series,"level":request.get("level",""),"sourceType":"youtube",
          "subtitleStrategy":"auto","youtubeSubtitleSource":subtitle_source,"youtubeSubtitleTrack":subtitle_track["code"] if subtitle_track else "","youtubeSubtitleLanguage":"en" if subtitle_track else "","youtubeSubtitleTranslated":False,
          "youtubeChineseSubtitleSource":chinese_track["source"] if chinese_subtitle and chinese_track else "none","youtubeChineseSubtitleTrack":chinese_track["code"] if chinese_track else "","youtubeChineseSubtitleLanguage":"zh-CN" if chinese_track else "","youtubeChineseSubtitleTranslated":bool(chinese_track and chinese_track.get("translated")),
          "translatedEnglishRejected":has_translated_english_track(info),"sourceUrl":url,"youtubeId":video_id,"channel":request.get("channel","")}
        (destination/".video-import.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
        update_job(job_id,source_path=relative,progress=25,step="YouTube 下载完成，开始视频处理")
        import_video(job_id,relative,progress_base=25,progress_span=75)
    except Exception as exc:
        update_job(job_id,status="failed",step="YouTube 导入失败",error=str(exc)); raise
    finally:
        request_file.unlink(missing_ok=True)

if __name__=="__main__": main()
