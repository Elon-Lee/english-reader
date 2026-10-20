#!/usr/bin/env python3
"""Align native English manual captions. No database writes or model downloads."""
import argparse
import json
import math
import os
import re
import sys
import wave
from difflib import SequenceMatcher
from pathlib import Path

from build_video_book import subtitle_entries
from timed_segmentation import text_words

ROOT=Path(__file__).resolve().parents[1]
MODEL_FILE="wav2vec2_fairseq_base_ls960_asr_ls960.pth"


def caption_cues(path,duration):
    cues=[]
    for entry in subtitle_entries(path):
        text=re.sub(r"\[[^\]]*\]|\([^)]*(?:music|applause)[^)]*\)","",entry["text"],flags=re.I).strip()
        words=text_words(text)
        if not words:continue
        start=float(entry["start"]);end=min(float(entry["end"]),duration)
        if not math.isfinite(start) or not math.isfinite(end) or start<0 or end<=start:continue
        if cues and start<cues[-1]["end"]-.02:
            raise ValueError("overlapping manual caption cues")
        cues.append({"index":len(cues),"start":start,"end":end,"text":text,"words":words})
    if not cues:raise ValueError("no usable manual English captions")
    return cues


def fallback_windows(cues,failed,duration,padding=.3):
    windows=[]
    for cue in cues:
        if cue["index"] not in failed:continue
        start=max(0,cue["start"]-padding);end=min(duration,cue["end"]+padding)
        if windows and start<=windows[-1]["end"]+.3 and end-windows[-1]["start"]<=30:
            windows[-1]["end"]=end;windows[-1]["indices"].append(cue["index"])
        else:windows.append({"start":start,"end":end,"indices":[cue["index"]]})
    return windows


def align_cue(model,waveform,sample_rate,cue,dictionary):
    import torch
    import torchaudio
    from ctc_forced_align import word_char_ranges
    transcript,ranges=word_char_ranges(cue["words"])
    if not transcript or any(c not in dictionary for c in transcript):return None,"unsupported caption characters"
    if cue["end"]-cue["start"]>25:return None,"caption window too long"
    # Native cues are a coarse search window; retain absolute media offsets.
    clip_start=max(0,cue["start"]-.25);clip_end=min(waveform.shape[-1]/sample_rate,cue["end"]+.25)
    clip=waveform[:,int(clip_start*sample_rate):int(clip_end*sample_rate)]
    if clip.shape[-1]<sample_rate*.12:return None,"audio window too short"
    with torch.inference_mode():
        emissions,_=model(clip);log_probs=torch.log_softmax(emissions,dim=-1)
        ids=log_probs.argmax(-1)[0].tolist();collapsed=[];last=None
        for value in ids:
            if value!=last and value:collapsed.append(value)
            last=value
        labels={value:key for key,value in dictionary.items()}
        heard="".join(labels[i] for i in collapsed)
        expected=re.sub(r"[^A-Z']","",transcript);heard=re.sub(r"[^A-Z']","",heard)
        agreement=SequenceMatcher(None,expected,heard,autojunk=False).ratio()
        if agreement<.6:return None,"caption does not match acoustic decoding"
        targets=torch.tensor([[dictionary[c] for c in transcript]],dtype=torch.int32)
        if log_probs.shape[1]<len(transcript)+sum(a==b for a,b in zip(transcript,transcript[1:])):
            return None,"insufficient acoustic frames"
        path,scores=torchaudio.functional.forced_align(log_probs,targets,blank=0)
        spans=torchaudio.functional.merge_tokens(path[0],scores[0],blank=0)
    if len(spans)!=len(transcript):return None,"incomplete character alignment"
    frame_seconds=(clip.shape[-1]/sample_rate)/log_probs.shape[1];result=[]
    for word,(left,right) in zip(cue["words"],ranges):
        selected=spans[left:right]
        start=clip_start+selected[0].start*frame_seconds;end=clip_start+selected[-1].end*frame_seconds
        confidence=sum(math.exp(float(span.score)) for span in selected)/len(selected)
        if end<=start or end-start>2.5 or confidence<.15:return None,"weak or implausible word alignment"
        result.append({**word,"start":round(start,3),"end":round(end,3),"confidence":round(confidence,4),
                       "timingSource":"manual-caption-ctc","estimated":False,"aligned":True,"cue":cue["index"]})
    if sum(w["confidence"] for w in result)/len(result)<.45:return None,"low acoustic confidence"
    return result,None


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--audio",required=True,type=Path);parser.add_argument("--subtitle",required=True,type=Path)
    parser.add_argument("--model-home",required=True,type=Path);parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    checkpoint=args.model_home/"hub/checkpoints"/MODEL_FILE
    if not checkpoint.is_file():raise ValueError("local CTC model missing")
    os.environ["TORCH_HOME"]=str(args.model_home)
    import numpy as np
    import torch
    import torchaudio
    torch.set_num_threads(max(1,min(3,int(os.environ.get("SHIYUE_CTC_THREADS","2")))))
    torch.set_num_interop_threads(1)
    with wave.open(str(args.audio),"rb") as audio:
        if (audio.getframerate(),audio.getnchannels(),audio.getsampwidth())!=(16000,1,2):raise ValueError("expected mono 16kHz PCM16 WAV")
        waveform=torch.from_numpy(np.frombuffer(audio.readframes(audio.getnframes()),dtype=np.int16).copy()).float().unsqueeze(0)/32768
    sample_rate=16000;duration=waveform.shape[-1]/sample_rate;cues=caption_cues(args.subtitle,duration)
    bundle=torchaudio.pipelines.WAV2VEC2_ASR_BASE_960H
    model=bundle.get_model().eval();dictionary={char:i for i,char in enumerate(bundle.get_labels())}
    aligned=[];rejected=[]
    for index,cue in enumerate(cues):
        words,error=align_cue(model,waveform,sample_rate,cue,dictionary)
        if words:aligned.append({"index":cue["index"],"words":words})
        else:rejected.append({"index":cue["index"],"reason":error})
        print(f"caption_progress={round((index+1)/len(cues)*100)}",file=sys.stderr,flush=True)
    args.output.write_text(json.dumps({"model":"WAV2VEC2_ASR_BASE_960H","cues":cues,"aligned":aligned,"rejected":rejected},ensure_ascii=False))


if __name__=="__main__":main()
