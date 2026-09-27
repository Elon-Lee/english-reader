#!/usr/bin/env python3
"""Align whisper.cpp word timestamps to the authoritative OCR/book text."""
import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

WORD_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|\d+")
NUMBERS = {
    0:"zero",1:"one",2:"two",3:"three",4:"four",5:"five",6:"six",7:"seven",8:"eight",9:"nine",10:"ten",
    11:"eleven",12:"twelve",13:"thirteen",14:"fourteen",15:"fifteen",16:"sixteen",17:"seventeen",18:"eighteen",19:"nineteen",20:"twenty",
    21:"twentyone",22:"twentytwo",23:"twentythree",24:"twentyfour",25:"twentyfive",26:"twentysix",27:"twentyseven",28:"twentyeight",29:"twentynine",30:"thirty",
    31:"thirtyone",32:"thirtytwo",33:"thirtythree",34:"thirtyfour",35:"thirtyfive",36:"thirtysix",37:"thirtyseven",38:"thirtyeight",39:"thirtynine",40:"forty"
}

def norm(word):
    if word.isdigit(): return NUMBERS.get(int(word),word)
    return re.sub(r"[^a-z']", "", word.lower().replace("’", "'"))

def whisper_words(data):
    words=[]
    for segment in data.get("transcription", []):
        text=segment.get("text", "")
        found=list(WORD_RE.finditer(text))
        if not found: continue
        offsets=segment.get("offsets", {})
        start=offsets.get("from", 0)/1000
        end=offsets.get("to", 0)/1000
        confidence=[]
        for token in segment.get("tokens", []):
            token_text=token.get("text", "")
            if token_text.startswith("[_"): continue
            confidence.append(float(token.get("p", 0)))
        p=sum(confidence)/len(confidence) if confidence else 0
        span=max(.04,end-start)
        for i,match in enumerate(found):
            words.append({"text":match.group(),"norm":norm(match.group()),
                          "start":round(start+span*i/len(found),3),
                          "end":round(start+span*(i+1)/len(found),3),"confidence":round(p,3)})
    return [w for w in words if w["norm"] and w["norm"] not in {"music"}]

def canonical_words(book):
    output=[]
    for sentence_index,sentence in enumerate(book["sentences"]):
        for word_index,match in enumerate(WORD_RE.finditer(sentence["text"])):
            output.append({"text":match.group(),"norm":norm(match.group()),
                           "sentence":sentence_index,"word":word_index})
    return output

def interpolate(mapping, canonical, whisper, old_book):
    mapped=sorted(mapping)
    for index in range(len(canonical)):
        if index in mapping: continue
        previous=next((p for p in reversed(mapped) if p<index),None)
        following=next((p for p in mapped if p>index),None)
        if previous is not None and following is not None:
            ratio=(index-previous)/(following-previous)
            left=mapping[previous]["end"]
            right=mapping[following]["start"]
            center=left+(right-left)*ratio
            mapping[index]={"start":max(left,center-.09),"end":min(right,center+.09),"confidence":0,"estimated":True}
        elif following is not None:
            right=mapping[following]["start"]
            center=max(0,right-(following-index)*.38)
            mapping[index]={"start":max(0,center-.12),"end":min(right,center+.12),"confidence":0,"estimated":True}
        elif previous is not None:
            left=mapping[previous]["end"]
            center=left+(index-previous)*.38
            mapping[index]={"start":center-.12,"end":center+.12,"confidence":0,"estimated":True}
        else:
            item=canonical[index]; sentence=old_book["sentences"][item["sentence"]]
            count=max(1,len(WORD_RE.findall(sentence["text"])))
            span=max(.2,sentence["end"]-sentence["start"])
            start=sentence["start"]+span*item["word"]/count
            mapping[index]={"start":start,"end":sentence["start"]+span*(item["word"]+1)/count,
                            "confidence":0,"estimated":True}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--book",required=True,type=Path)
    parser.add_argument("--whisper",required=True,type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--report",type=Path)
    parser.add_argument("--model",default="base.en")
    parser.add_argument("--min-match",type=float,default=.5)
    args=parser.parse_args()
    book=json.loads(args.book.read_text())
    transcript=json.loads(args.whisper.read_text())
    canonical=canonical_words(book); heard=whisper_words(transcript)
    matcher=SequenceMatcher(None,[x["norm"] for x in canonical],[x["norm"] for x in heard],autojunk=False)
    mapping={}
    direct=0
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            ci=block.a+offset; wi=block.b+offset
            mapping[ci]=wi; direct+=1
    # Preserve exact Whisper data before filling alignment gaps.
    direct_mapping={ci:heard[wi] for ci,wi in mapping.items()}
    mapping=dict(direct_mapping)
    interpolate(mapping,canonical,heard,book)
    per_sentence=[[] for _ in book["sentences"]]
    for ci,item in enumerate(canonical):
        timing=mapping[ci]
        per_sentence[item["sentence"]].append({"text":item["text"],"start":round(timing["start"],3),
            "end":round(max(timing["start"]+.03,timing["end"]),3),
            "confidence":round(timing.get("confidence",0),3),"aligned":not timing.get("estimated",False)})
    for sentence,words in zip(book["sentences"],per_sentence):
        sentence["words"]=words
        if words:
            sentence["start"]=round(words[0]["start"],3)
            sentence["end"]=round(words[-1]["end"],3)
    ratio=direct/max(1,len(canonical))
    if ratio < args.min_match:
        raise SystemExit(f"Alignment rejected: direct word match {ratio:.1%} is below {args.min_match:.0%}")
    book["alignment"]="whisper-word-timestamps"
    book["whisper"]={"engine":"whisper.cpp","model":args.model,"directWordMatch":round(ratio,4),
                     "canonicalWords":len(canonical),"matchedWords":direct,"transcribedWords":len(heard)}
    output=args.output or args.book
    output.write_text(json.dumps(book,ensure_ascii=False,indent=2))
    report={"engine":"whisper.cpp","model":args.model,"canonicalWords":len(canonical),
            "transcribedWords":len(heard),"directMatches":direct,"directMatchRate":round(ratio,4),
            "estimatedWords":len(canonical)-direct,
            "firstSpeechWord":heard[0] if heard else None,"lastSpeechWord":heard[-1] if heard else None}
    if args.report: args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    quality_path=output.with_name("quality-report.json")
    if quality_path.exists():
        quality=json.loads(quality_path.read_text())
        quality["summary"]["alignment"]="whisper-word-timestamps"
        quality["whisper"]=report
        validated={(book["sentences"][item["sentence"]]["page"],item["text"]) for ci,item in enumerate(canonical) if ci in direct_mapping}
        unresolved=[]; confirmed=[]
        for line in quality.get("lowConfidenceLines",[]):
            (confirmed if (line["page"],line["text"].strip()) in validated else unresolved).append(line)
        quality["whisperValidatedLines"]=confirmed
        quality["lowConfidenceLines"]=unresolved
        quality["summary"]["lowConfidenceLines"]=len(unresolved)
        structural=sum(len(values) for values in quality.get("checks",{}).values())
        quality["status"]="ready" if not unresolved and not structural else "needs-review"
        quality["recommendations"]=[item for item in quality.get("recommendations",[]) if "Whisper" not in item]
        if not unresolved:
            quality["recommendations"]=[item for item in quality["recommendations"] if "低置信度" not in item]
        if book["whisper"]["directWordMatch"]>.98:
            quality["recommendations"]=[item for item in quality["recommendations"] if "起始秒数" not in item]
        quality_path.write_text(json.dumps(quality,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
