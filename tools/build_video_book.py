#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
from pathlib import Path

from align_whisper import WORD_RE, normalize_words, whisper_words
from text_segmentation import split_sentences

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

def subtitle_book(entries):
    sentences=[]
    for item in entries:
        parts=split_sentences(item["text"],max_words=60);total=max(1,sum(len(WORD_RE.findall(part)) for part in parts));cursor=0
        for part in parts:
            matches=list(WORD_RE.finditer(part));span=max(.1,item["end"]-item["start"]);start=item["start"]+span*cursor/total;cursor+=len(matches);end=item["start"]+span*cursor/total
            words=[{"text":match.group(),"start":round(start+(end-start)*i/max(1,len(matches)),3),"end":round(start+(end-start)*(i+1)/max(1,len(matches)),3),"confidence":1,"aligned":False} for i,match in enumerate(matches)]
            index=len(sentences)+1;sentences.append({"id":f"s{index}","page":int(start//15)+1,"text":part,"start":start,"end":end,"section":None,"targets":[],"words":words})
    return sentences

def whisper_book(data):
    timed=whisper_words(data); transcription=data.get("transcription",[]); punctuation=[]
    for segment in transcription:
        raw=segment.get("text","").strip(); punctuation.append(bool(re.search(r"[.!?][\"']?$",raw)))
    groups=[]; current=[]; last_end=None
    for index,word in enumerate(timed):
        gap=word["start"]-(last_end if last_end is not None else word["start"])
        if current and (gap>1.1 or len(current)>=22): groups.append(current); current=[]
        current.append(word); last_end=word["end"]
        if index<len(punctuation) and punctuation[index]: groups.append(current); current=[]
    if current:groups.append(current)
    sentences=[]
    for index,words in enumerate(groups,1):
        normalize_words(words); text=" ".join(word["text"] for word in words)
        sentences.append({"id":f"s{index}","page":int(words[0]["start"]//15)+1,"text":text,"start":words[0]["start"],"end":words[-1]["end"],"section":None,"targets":[],
          "words":[{"text":word["text"],"start":word["start"],"end":word["end"],"confidence":word.get("confidence",0),"aligned":True} for word in words]})
    return sentences

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--whisper",required=True,type=Path); parser.add_argument("--audio",required=True,type=Path)
    parser.add_argument("--subtitle",type=Path); parser.add_argument("--output",required=True,type=Path); parser.add_argument("--id",required=True); parser.add_argument("--title",required=True)
    parser.add_argument("--english-title",default=""); parser.add_argument("--level",default=""); parser.add_argument("--audio-url",required=True); parser.add_argument("--video-url",required=True); parser.add_argument("--page-base",required=True); parser.add_argument("--subtitle-type",default="whisper")
    args=parser.parse_args(); whisper=json.loads(args.whisper.read_text())
    sentences=subtitle_book(subtitle_entries(args.subtitle)) if args.subtitle and args.subtitle.exists() else whisper_book(whisper)
    book={"id":args.id,"title":args.title,"englishTitle":args.english_title,"level":args.level,"sourceType":"video","video":args.video_url,"audio":args.audio_url,
      "pageBase":args.page_base,"subtitleType":args.subtitle_type,"duration":duration(args.audio),"alignment":"whisper-dtw-normalized","sentences":sentences,
      "whisper":{"engine":"whisper.cpp","model":"base.en","timestampMethod":"dtw","transcribedWords":sum(len(s["words"]) for s in sentences)}}
    args.output.write_text(json.dumps(book,ensure_ascii=False,indent=2)); print(f"Built video book: {len(sentences)} sentences")

if __name__=="__main__":main()
