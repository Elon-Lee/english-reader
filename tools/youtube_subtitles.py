#!/usr/bin/env python3
"""Select native English YouTube captions and reject auto-translated tracks."""
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
