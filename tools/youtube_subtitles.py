#!/usr/bin/env python3
"""Select and convert native/translated YouTube caption tracks."""
import json
import re
from urllib.parse import parse_qs,urlsplit

def track_url_language(entry):
    query=parse_qs(urlsplit(str(entry.get("url","") or "")).query);lang=(query.get("lang") or [""])[0];translated=(query.get("tlang") or [""])[0]
    return lang.strip(),translated.strip()

def native_english_entries(entries):
    output=[]
    for entry in entries or []:
        lang,translated=track_url_language(entry)
        if translated:continue
        if lang and not lang.casefold().startswith("en"):continue
        output.append(entry)
    return output

def english_code_priority(code,source):
    folded=str(code).casefold()
    if source=="automatic":
        order={"en-orig":0,"en":1,"en-us":2,"en-gb":3}
    else:order={"en":0,"en-us":1,"en-gb":2,"en-orig":3}
    return order.get(folded,10 if folded.startswith("en-") else 20),len(folded),folded

def select_native_english_track(info):
    for source,key in (("manual","subtitles"),("automatic","automatic_captions")):
        candidates=[]
        for code,entries in (info.get(key) or {}).items():
            if not str(code).casefold().startswith("en"):continue
            native=native_english_entries(entries)
            if native:candidates.append((english_code_priority(code,source),str(code),native))
        if candidates:
            _,code,entries=min(candidates,key=lambda item:item[0]);return {"source":source,"code":code,"language":"en","translated":False,"entries":entries}
    return None

def has_translated_english_track(info):
    for key in ("subtitles","automatic_captions"):
        for code,entries in (info.get(key) or {}).items():
            if not str(code).casefold().startswith("en"):continue
            for entry in entries or []:
                lang,translated=track_url_language(entry)
                if translated.casefold().startswith("en") and not lang.casefold().startswith("en"):return True
    return False

def chinese_code_priority(code):
    folded=str(code).casefold();order={"zh-cn":0,"zh-hans":1,"zh":2,"cmn-hans":3,"zh-tw":10,"zh-hant":11}
    return order.get(folded,5 if "hans" in folded else 20),len(folded),folded

def select_chinese_track(info):
    """Prefer native simplified Chinese captions, then YouTube translation to Chinese."""
    for source,key in (("manual","subtitles"),("automatic","automatic_captions")):
        candidates=[]
        for code,entries in (info.get(key) or {}).items():
            folded=str(code).casefold()
            if not (folded.startswith("zh") or folded.startswith("cmn")):continue
            native=[]
            for entry in entries or []:
                lang,translated=track_url_language(entry)
                if translated:continue
                if lang and not (lang.casefold().startswith("zh") or lang.casefold().startswith("cmn")):continue
                native.append(entry)
            if native:candidates.append((chinese_code_priority(code),str(code),native))
        if candidates:
            _,code,entries=min(candidates,key=lambda item:item[0]);return {"source":source,"code":code,"language":"zh-CN","translated":False,"entries":entries}
    candidates=[]
    for code,entries in (info.get("automatic_captions") or {}).items():
        folded=str(code).casefold()
        if not (folded.startswith("zh") or folded.startswith("cmn")):continue
        translated_entries=[]
        for entry in entries or []:
            lang,translated=track_url_language(entry)
            if (lang.casefold().startswith("en") and (translated.casefold().startswith("zh") or translated.casefold().startswith("cmn"))):translated_entries.append(entry)
        if translated_entries:candidates.append((chinese_code_priority(code),str(code),translated_entries))
    if candidates:
        _,code,entries=min(candidates,key=lambda item:item[0]);return {"source":"translated","code":code,"language":"zh-CN","translated":True,"entries":entries}
    return None

def preferred_json3_entry(track,source_language="en"):
    if not track:return None
    entries=track.get("entries") or []
    matching=[entry for entry in entries if str(entry.get("ext","")).casefold()=="json3" and track_url_language(entry)[0].casefold().startswith(source_language.casefold())]
    if matching:return matching[0]
    return next((entry for entry in entries if str(entry.get("ext","")).casefold()=="json3"),None)

def srt_timestamp(seconds):
    millis=max(0,round(float(seconds)*1000));hours,millis=divmod(millis,3600000);minutes,millis=divmod(millis,60000);secs,millis=divmod(millis,1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def json3_to_srt(payload):
    if isinstance(payload,(str,bytes)):payload=json.loads(payload)
    cues=[]
    for event in payload.get("events",[]):
        text="".join(str(segment.get("utf8","") or "") for segment in event.get("segs",[]))
        text=re.sub(r"\s+"," ",text.replace("\u200b","").replace("\n"," ")).strip()
        if not text:continue
        start=max(0,float(event.get("tStartMs",0) or 0)/1000)
        duration=max(.08,float(event.get("dDurationMs",0) or 0)/1000)
        cues.append({"start":start,"end":start+duration,"text":text})
    blocks=[]
    for index,cue in enumerate(cues,1):
        blocks.append(f"{index}\n{srt_timestamp(cue['start'])} --> {srt_timestamp(cue['end'])}\n{cue['text']}")
    return "\n\n".join(blocks)+( "\n" if blocks else "")
