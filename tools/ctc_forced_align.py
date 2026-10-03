#!/usr/bin/env python3
"""Phoneme/character CTC forced alignment for authoritative English book text."""
import argparse
import json
import math
import os
import re
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote

import torch
import torchaudio
from sat_integration import annotate_sat_boundaries
from timed_segmentation import detect_silences,resegment_timed_book

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/".local/library.sqlite3"
BOOKS=ROOT/"books"
WORD_RE=re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|\d+")

ONES=["ZERO","ONE","TWO","THREE","FOUR","FIVE","SIX","SEVEN","EIGHT","NINE","TEN","ELEVEN","TWELVE","THIRTEEN","FOURTEEN","FIFTEEN","SIXTEEN","SEVENTEEN","EIGHTEEN","NINETEEN"]
TENS=["","","TWENTY","THIRTY","FORTY","FIFTY","SIXTY","SEVENTY","EIGHTY","NINETY"]

def number_words(value):
    try:n=int(value)
    except ValueError:return ""
    if n<20:return ONES[n]
    if n<100:return TENS[n//10]+(("" if n%10==0 else ONES[n%10]))
    if n<1000:return ONES[n//100]+"HUNDRED"+("" if n%100==0 else number_words(str(n%100)))
    if n<10000:return ONES[n//1000]+"THOUSAND"+("" if n%1000==0 else number_words(str(n%1000)))
    return ""

def normalized_word(value):
    if value.isdigit():return number_words(value)
    return re.sub(r"[^A-Z']","",value.upper().replace("’","'"))

def audio_path(url):
    prefix="/books/"
    if not url.startswith(prefix):raise ValueError(f"Unsupported audio URL: {url}")
    path=(BOOKS/unquote(url[len(prefix):])).resolve();path.relative_to(BOOKS.resolve());return path

def load_book(book_id,input_path=None):
    if input_path:return json.loads(Path(input_path).read_text())
    db=sqlite3.connect(DB);row=db.execute("SELECT data_json FROM books WHERE id=?",(book_id,)).fetchone();db.close()
    if not row:raise ValueError("Book not found")
    return json.loads(row[0])

def load_waveform(path):
    with tempfile.NamedTemporaryFile(suffix=".wav") as temp:
        subprocess.run(["ffmpeg","-y","-v","error","-i",path,"-ar","16000","-ac","1","-c:a","pcm_s16le",temp.name],check=True)
        waveform,sample_rate=torchaudio.load(temp.name)
    return waveform,sample_rate

def word_char_ranges(words):
    normalized=[normalized_word(word["text"]) for word in words]
    if any(not word for word in normalized):return None,None
    transcript="|".join(normalized);ranges=[];offset=0
    for word in normalized:
        ranges.append((offset,offset+len(word)));offset+=len(word)+1
    return transcript,ranges

def align_sentence(model,waveform,sample_rate,sentence,labels,dictionary,padding=1.0):
    words=sentence.get("words",[])
    if not words:return None,"no words"
    transcript,ranges=word_char_ranges(words)
    if not transcript:return None,"unsupported characters"
    if any(char not in dictionary for char in transcript):return None,"character not in acoustic alphabet"
    clip_start=max(0,float(sentence["start"])-padding);clip_end=min(waveform.shape[-1]/sample_rate,float(sentence["end"])+padding)
    start_sample=int(clip_start*sample_rate);end_sample=int(clip_end*sample_rate);clip=waveform[:,start_sample:end_sample]
    if clip.shape[-1]<sample_rate*.15:return None,"audio clip too short"
    targets=torch.tensor([[dictionary[char] for char in transcript]],dtype=torch.int32)
    with torch.inference_mode():
        emissions,_=model(clip);log_probs=torch.log_softmax(emissions,dim=-1)
        if log_probs.shape[1] < targets.shape[1]+sum(a==b for a,b in zip(transcript,transcript[1:])):return None,"insufficient acoustic frames"
        path,scores=torchaudio.functional.forced_align(log_probs,targets,blank=0)
        spans=torchaudio.functional.merge_tokens(path[0],scores[0],blank=0)
    if len(spans)!=len(transcript):return None,f"aligned chars {len(spans)} != transcript chars {len(transcript)}"
    frame_seconds=(clip.shape[-1]/sample_rate)/log_probs.shape[1]
    result=[]
    for word,(left,right) in zip(words,ranges):
        selected=spans[left:right]
        start=clip_start+selected[0].start*frame_seconds;end=clip_start+selected[-1].end*frame_seconds
        confidence=sum(math.exp(float(span.score)) for span in selected)/len(selected)
        if end<=start or end-start>2.5:return None,"implausible word duration"
        result.append({**word,"start":round(start,3),"end":round(end,3),"confidence":round(confidence,4),"aligned":True,"alignment":"ctc"})
    average=sum(word["confidence"] for word in result)/len(result)
    if average<.08:return None,f"low acoustic confidence {average:.3f}"
    return result,None

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--book-id",required=True);parser.add_argument("--input",type=Path);parser.add_argument("--job-id",type=int);parser.add_argument("--output",type=Path);parser.add_argument("--sentence",type=int);parser.add_argument("--limit",type=int);parser.add_argument("--padding",type=float,default=1.0);parser.add_argument("--segmentation-profile",choices=["youtube-auto","youtube-manual","local-subtitle","speech-asr"]);parser.add_argument("--preserve-sentences",action="store_true");parser.add_argument("--update-db",action="store_true")
    args=parser.parse_args();torch.set_num_threads(max(1,min(3,int(os.environ.get("SHIYUE_CTC_THREADS","3")))));torch.set_num_interop_threads(1);book=load_book(args.book_id,args.input);audio=audio_path(book["audio"]);waveform,sample_rate=load_waveform(audio)
    bundle=torchaudio.pipelines.WAV2VEC2_ASR_BASE_960H;labels=bundle.get_labels();dictionary={char:index for index,char in enumerate(labels)};model=bundle.get_model().eval()
    selected=range(len(book["sentences"]))
    if args.sentence is not None:selected=[args.sentence]
    elif args.limit:selected=range(min(args.limit,len(book["sentences"])))
    aligned=0;failed=[];total=len(list(selected))
    for number,index in enumerate(selected,1):
        sentence=book["sentences"][index]
        result,error=align_sentence(model,waveform,sample_rate,sentence,labels,dictionary,args.padding)
        if result:
            sentence["words"]=result;sentence["start"]=result[0]["start"];sentence["end"]=result[-1]["end"];sentence["alignment"]="ctc";aligned+=1
        else:failed.append({"index":index,"id":sentence.get("id"),"reason":error})
        print(f"[{number}] {sentence.get('id')} {'aligned' if result else 'fallback: '+error}",flush=True)
        if args.job_id and (number==1 or number%5==0 or number==total):
            db=sqlite3.connect(DB);db.execute("UPDATE import_jobs SET progress=?,step=?,updated_at=datetime('now') WHERE id=?",(98 if number<total/2 else 99,f"wav2vec2 CTC {number}/{total}",args.job_id));db.commit();db.close()
    cue_overlaps_fixed=0
    if args.preserve_sentences:
        for index in range(1,len(book["sentences"])):
            previous,current=book["sentences"][index-1],book["sentences"][index]
            if float(current["start"])>=float(previous["end"]):continue
            left=previous.get("words",[])[-1] if previous.get("words") else None;right=current.get("words",[])[0] if current.get("words") else None
            boundary=(float(previous["end"])+float(current["start"]))/2
            if left:boundary=max(float(left["start"])+.02,boundary)
            if right:boundary=min(float(right["end"])-.02,boundary)
            if left:left["end"]=round(boundary,3)
            if right:right["start"]=round(boundary,3)
            previous["end"]=round(boundary,3);current["start"]=round(boundary,3);cue_overlaps_fixed+=1
    coverage=aligned/max(1,total)
    profile=args.segmentation_profile
    if not profile and book.get("sourceType") in {"video","youtube","audio"}:
        if book.get("sourceType")=="youtube":profile="youtube-auto" if book.get("subtitleSource")=="automatic" else "youtube-manual"
        elif book.get("subtitleType") in {"external","embedded"}:profile="local-subtitle"
        else:profile="speech-asr"
    sat_report=None if args.preserve_sentences else (annotate_sat_boundaries(book,profile) if profile else None)
    segmentation=({"method":"youtube-original-caption-cues","sentences":len(book.get("sentences",[])),"originalCueBoundariesPreserved":True,"cueBoundaryOverlapsFixed":cue_overlaps_fixed,"sentenceOverlaps":sum(1 for index in range(1,len(book.get("sentences",[]))) if book["sentences"][index]["start"]<book["sentences"][index-1]["end"]),"internalPausesOver08":0} if args.preserve_sentences else (resegment_timed_book(book,"yt",detect_silences(audio),profile=profile) if profile else None))
    if segmentation:segmentation["sat"]=sat_report
    if segmentation and (segmentation.get("sentenceOverlaps") or segmentation.get("internalPausesOver08")):
        raise ValueError(f"Timed segmentation quality rejected: {segmentation}")
    summary={"method":"wav2vec2-ctc-forced-alignment","model":"WAV2VEC2_ASR_BASE_960H","alignedSentences":aligned,"failedSentences":len(failed),"coverage":round(coverage,4),"failures":failed}
    if segmentation:summary["segmentation"]=segmentation
    book["forcedAlignment"]=summary
    if coverage>=.35:book["alignment"]="wav2vec2-ctc-forced-alignment"
    if args.output:args.output.write_text(json.dumps(book,ensure_ascii=False,indent=2))
    if args.update_db:
        db=sqlite3.connect(DB);row=db.execute("SELECT quality_json FROM books WHERE id=?",(args.book_id,)).fetchone();quality=json.loads(row[0] or "{}") if row else {}
        timing_sources={"youtube-auto":"youtube-auto-original-cues+wav2vec2" if args.preserve_sentences else "youtube-auto-dedup+sat+pause+wav2vec2","youtube-manual":"youtube-manual-original-cues+wav2vec2" if args.preserve_sentences else "youtube-manual-subtitle+pause+wav2vec2","local-subtitle":"local-subtitle+pause+wav2vec2","speech-asr":"whisper-dtw+sat+pause+wav2vec2"}
        if segmentation:quality.update({"sentences":len(book.get("sentences",[])),"timingSource":timing_sources.get(profile,"whisper-dtw+pause+wav2vec2"),"segmentation":segmentation,"alignmentAudit":{"sentenceOverlaps":segmentation.get("sentenceOverlaps",0),"internalPausesOver08":segmentation.get("internalPausesOver08",0),"maxSentenceSeconds":segmentation.get("maxSentenceSeconds",0),"ctcCoverage":round(coverage,4)}})
        db.execute("UPDATE books SET alignment=?,data_json=?,quality_json=?,updated_at=datetime('now') WHERE id=?",(book["alignment"],json.dumps(book,ensure_ascii=False),json.dumps(quality,ensure_ascii=False),args.book_id));db.execute("INSERT INTO book_artifacts(book_id,kind,data_json,created_at) VALUES(?,?,?,datetime('now')) ON CONFLICT(book_id,kind) DO UPDATE SET data_json=excluded.data_json,created_at=excluded.created_at",(args.book_id,"alignment-ctc",json.dumps(summary,ensure_ascii=False)));db.execute("INSERT INTO book_artifacts(book_id,kind,data_json,created_at) VALUES(?,?,?,datetime('now')) ON CONFLICT(book_id,kind) DO UPDATE SET data_json=excluded.data_json,created_at=excluded.created_at",(args.book_id,"segmentation",json.dumps(segmentation or {},ensure_ascii=False)));db.commit();db.close()
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
