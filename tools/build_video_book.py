#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
from pathlib import Path

from align_whisper import WORD_RE, normalize_words, whisper_words
from timed_segmentation import dedupe_caption_words,detect_silences,segment_timed_words

TIME_RE=re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")

def seconds(value):
    match=TIME_RE.search(value.strip())
    if not match:return 0
    hours,minutes,secs,millis=map(int,match.groups())
    return hours*3600+minutes*60+secs+millis/(1000 if len(match.group(4))==3 else 100)

def duration(path):
    return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nk=1:nw=1",path],text=True).strip())

def subtitle_entries(path):
    text=path.read_text(encoding="utf-8-sig",errors="replace").replace("\r\n","\n")
    blocks=re.split(r"\n\s*\n",text); result=[]
    for block in blocks:
        lines=[line.strip() for line in block.splitlines() if line.strip()]
        time_index=next((i for i,line in enumerate(lines) if "-->" in line),None)
        if time_index is None:continue
        start_text,end_text=lines[time_index].split("-->",1)
        body=" ".join(lines[time_index+1:]); body=re.sub(r"<[^>]+>","",body); body=re.sub(r"\s+"," ",body).strip()
        if body and WORD_RE.search(body): result.append({"start":seconds(start_text),"end":seconds(end_text),"text":body})
    return result

def subtitle_book(entries,automatic=False,silences=None):
    words,caption_report=dedupe_caption_words(entries,automatic=automatic);sentences,segmentation=segment_timed_words(words,"yt",silences=silences)
    return sentences,{**caption_report,**segmentation,"automaticCaptions":automatic}

def whisper_book(data,silences=None):
    return segment_timed_words(whisper_words(data),"yt",silences=silences)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--whisper",type=Path); parser.add_argument("--audio",required=True,type=Path)
    parser.add_argument("--subtitle",type=Path); parser.add_argument("--output",required=True,type=Path); parser.add_argument("--id",required=True); parser.add_argument("--title",required=True)
    parser.add_argument("--english-title",default=""); parser.add_argument("--level",default=""); parser.add_argument("--audio-url",required=True); parser.add_argument("--video-url",required=True); parser.add_argument("--page-base",required=True); parser.add_argument("--subtitle-type",default="whisper");parser.add_argument("--subtitle-source",default="")
    args=parser.parse_args();whisper=json.loads(args.whisper.read_text()) if args.whisper and args.whisper.exists() else None
    subtitle=subtitle_entries(args.subtitle) if args.subtitle and args.subtitle.exists() else [];silences=detect_silences(args.audio)
    if subtitle:sentences,segmentation=subtitle_book(subtitle,args.subtitle_source=="automatic",silences)
    elif whisper:sentences,segmentation=whisper_book(whisper,silences)
    else:raise ValueError("没有可用字幕，也没有 Whisper 转写结果")
    alignment="whisper-dtw-normalized" if whisper else "subtitle-timing"
    book={"id":args.id,"title":args.title,"englishTitle":args.english_title,"level":args.level,"sourceType":"video","video":args.video_url,"audio":args.audio_url,
      "pageBase":args.page_base,"subtitleType":args.subtitle_type,"duration":duration(args.audio),"alignment":alignment,"sentences":sentences}
    book["segmentation"]=segmentation
    if whisper:book["whisper"]={"engine":"whisper.cpp","model":"base.en","timestampMethod":"dtw","transcribedWords":sum(len(s["words"]) for s in sentences)}
    else:book["subtitleAlignment"]={"method":"subtitle-cues","cues":len(subtitle),"sentences":len(sentences),"whisperSkipped":True}
    args.output.write_text(json.dumps(book,ensure_ascii=False,indent=2)); print(f"Built video book: {len(sentences)} sentences")

if __name__=="__main__":main()
