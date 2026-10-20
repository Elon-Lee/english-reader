#!/usr/bin/env python3
"""Align whisper.cpp word timestamps to the authoritative OCR/book text."""
import argparse
import json
import math
import re
from difflib import SequenceMatcher
from pathlib import Path
from timed_segmentation import detect_silences,normalize_word_timeline,resegment_timed_book

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

def finite_time(value):
    try:
        value=float(value)
        return value if math.isfinite(value) and value>=0 else None
    except (TypeError,ValueError):
        return None

def whisper_timing_report(words):
    counts={}
    for word in words:
        source=word.get("timingSource","segment-estimate")
        counts[source]=counts.get(source,0)+1
    methods={"whisper-dtw":"dtw","whisper-token":"token-offsets","segment-estimate":"segment-estimate"}
    return {"timestampMethod":methods.get(next(iter(counts)),"mixed") if len(counts)==1 else "mixed",
            "timingVersion":3,"wordTimingSources":counts}

def whisper_words(data):
    words=[]
    # DTW is a token onset in centiseconds. Keep punctuation tokens: their
    # onsets provide the spoken word's end without absorbing the following pause.
    tokens=[];segments=[]
    for segment in data.get("transcription", []):
        text=segment.get("text", "")
        if re.fullmatch(r"\s*[\[(](?:music|applause|silence)[\])]\s*",text,re.I):continue
        lexical=[t for t in segment.get("tokens",[]) if not t.get("text","").startswith(("[_","<|"))]
        joined="".join(t.get("text","") for t in lexical)
        spans=[]
        if joined.strip()==text.strip():
            cursor=len(text)-len(text.lstrip())-(len(joined)-len(joined.lstrip()))
            for token in lexical:
                spans.append((cursor,cursor+len(token.get("text","")),len(tokens)))
                tokens.append(token);cursor+=len(token.get("text",""))
        segments.append((segment,spans))
    for segment,spans in segments:
        text=segment.get("text", "")
        found=list(WORD_RE.finditer(text))
        if not found: continue
        offsets=segment.get("offsets", {})
        start=(finite_time(offsets.get("from")) or 0)/1000
        end=max(start,(finite_time(offsets.get("to")) or 0)/1000)
        confidence=[]
        for token in segment.get("tokens", []):
            token_text=token.get("text", "")
            if token_text.startswith("[_"): continue
            confidence.append(float(token.get("p", 0)))
        p=sum(confidence)/len(confidence) if confidence else 0
        span=max(.04,end-start)
        sentence_break=bool(re.search(r"[.!?][\"']?$",text.strip()))
        for i,match in enumerate(found):
            word_start=start+span*i/len(found);word_end=start+span*(i+1)/len(found)
            source="segment-estimate";probability=p;fallback=(word_start,word_end,source)
            selected=[(a,b,n) for a,b,n in spans if a<match.end() and b>match.start()]
            # A token shared by several words has no measured word boundary.
            unshared=selected and all(sum(a<m.end() and b>m.start() for m in found)==1 for a,b,_ in selected)
            if unshared:
                first=tokens[selected[0][2]];last=tokens[selected[-1][2]]
                onset=finite_time(first.get("t_dtw"))
                next_index=selected[-1][2]+1
                following=finite_time(tokens[next_index].get("t_dtw")) if next_index<len(tokens) else None
                last_onset=finite_time(last.get("t_dtw"))
                # Punctuation can share the word's last DTW anchor. It has no
                # speech duration of its own; use the next lexical boundary
                # instead of discarding a valid word onset and cascading back
                # to heuristic offsets for the whole preceding sentence.
                boundary_index=next_index
                while boundary_index<len(tokens) and not WORD_RE.search(tokens[boundary_index].get("text","")) and finite_time(tokens[boundary_index].get("t_dtw"))==last_onset:
                    boundary_index+=1
                if boundary_index<len(tokens):following=finite_time(tokens[boundary_index].get("t_dtw"))
                left=finite_time(first.get("offsets",{}).get("from"))
                right=finite_time(last.get("offsets",{}).get("to"))
                # Older parallel outputs contain chunk-local token offsets.
                if left is not None and right is not None and start-.001<=left/1000<=right/1000<=end+.001 and right>left:
                    fallback=(left/1000,right/1000,"whisper-token")
                # Repeated DTW anchors have no usable word duration. Fall back
                # to token bounds rather than creating a one-millisecond word.
                # Segment/token offsets are heuristic and can drift several
                # seconds across a pause. They cannot validate DTW: rejecting
                # DTW by distance from those offsets restores the known drift.
                if onset is not None and last_onset is not None and last_onset>=onset and (following is None or following>last_onset):
                    word_start=onset/100
                    word_end=max(word_start+.001,following/100 if following is not None else max(last_onset/100+.03,end))
                    source="whisper-dtw"
                else:
                    word_start,word_end,source=fallback
                probability=sum(float(tokens[n].get("p",0)) for _,_,n in selected)/len(selected)
            punctuation="".join(re.findall(r"[,.;:!?]",text[match.end():(found[i+1].start() if i+1<len(found) else len(text))]))
            words.append({"text":match.group(),"norm":norm(match.group()),"punctuationAfter":punctuation,"speechBreakAfter":sentence_break and i==len(found)-1,
                          "start":round(word_start,3),"end":round(word_end,3),"confidence":round(probability,3),
                          "timingSource":source,"estimated":source=="segment-estimate","_timingFallback":fallback})
    # A collapsed DTW region may fall back earlier than the previous DTW onset.
    # Revert the conflicting region too, retaining the original token timeline.
    for index in range(1,len(words)):
        cursor=index
        while cursor and words[cursor]["start"]<words[cursor-1]["start"]:
            changed=False
            for word in words[cursor-1:cursor+1]:
                if word["timingSource"]=="whisper-dtw":
                    word["start"],word["end"],word["timingSource"]=word["_timingFallback"]
                    word["estimated"]=word["timingSource"]=="segment-estimate";changed=True
            if not changed:break
            cursor-=1
    for word in words:word.pop("_timingFallback",None)
    return [w for w in words if w["norm"]]

def canonical_words(book):
    output=[]
    for sentence_index,sentence in enumerate(book["sentences"]):
        source_words=sentence.get("words",[])
        for word_index,match in enumerate(WORD_RE.finditer(sentence["text"])):
            source=source_words[word_index] if word_index<len(source_words) else {}
            output.append({"text":match.group(),"norm":norm(match.group()),"punctuationAfter":source.get("punctuationAfter",""),"breakAfter":bool(source.get("breakAfter")),"speechBreakAfter":bool(source.get("speechBreakAfter")),
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

def max_word_duration(text):
    letters=len(re.sub(r"[^A-Za-z0-9]","",text))
    return min(1.35,max(.38,.28+letters*.095))

def normalize_words(words):
    """Remove overlaps and prevent timestamp tokens from absorbing long pauses."""
    if not words: return {"overlapsFixed":0,"durationsCapped":0}
    overlaps=0; capped=0
    for word in words:
        word["start"]=max(0,float(word["start"])); word["end"]=max(word["start"]+.04,float(word["end"]))
    for index in range(1,len(words)):
        words[index]["start"]=max(words[index]["start"],words[index-1]["start"]+.04)
        words[index]["end"]=max(words[index]["end"],words[index]["start"]+.04)
    for left,right in zip(words,words[1:]):
        if right["start"] < left["end"]:
            low=left["start"]+.04; high=right["end"]-.04
            boundary=(left["end"]+right["start"])/2
            boundary=max(low,min(high,boundary)) if high>=low else max(low,right["start"])
            left["end"]=boundary; right["start"]=boundary; overlaps+=1
    for index,word in enumerate(words):
        maximum=max_word_duration(word["text"])
        original_end=word["end"]
        ceiling=word["start"]+maximum
        if index+1<len(words): ceiling=min(ceiling,words[index+1]["start"])
        word["end"]=max(word["start"]+.03,min(original_end,ceiling))
        if original_end-word["start"] > maximum: capped+=1
        word["start"]=round(word["start"],3); word["end"]=round(word["end"],3)
    return {"overlapsFixed":overlaps,"durationsCapped":capped}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--book",required=True,type=Path)
    parser.add_argument("--whisper",required=True,type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--report",type=Path)
    parser.add_argument("--model",default="base.en")
    parser.add_argument("--min-match",type=float,default=.5)
    parser.add_argument("--audio",type=Path)
    args=parser.parse_args()
    book=json.loads(args.book.read_text())
    transcript=json.loads(args.whisper.read_text())
    canonical=canonical_words(book); heard=whisper_words(transcript)
    maximum_possible=min(len(canonical),len(heard))/max(1,len(canonical))
    if maximum_possible < args.min_match:
        raise SystemExit(f"Alignment rejected before matching: {len(canonical)} canonical words vs {len(heard)} transcribed words; maximum possible match {maximum_possible:.1%} is below {args.min_match:.0%}")
    # Disabling autojunk on book-length token sequences makes common words create
    # near-quadratic candidate sets. Long books use anchor-oriented matching;
    # matching blocks still include common words once rarer anchors are found.
    use_autojunk=max(len(canonical),len(heard))>=12000
    matcher=SequenceMatcher(None,[x["norm"] for x in canonical],[x["norm"] for x in heard],autojunk=use_autojunk)
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
    per_sentence=[[] for _ in book["sentences"]];all_aligned=[]
    for ci,item in enumerate(canonical):
        timing=mapping[ci]
        aligned={"text":item["text"],"start":round(timing["start"],3),
            "end":round(max(timing["start"]+.001,timing["end"]),3),"timingSource":timing.get("timingSource","segment-estimate"),"estimated":timing.get("estimated",False),
            "confidence":round(timing.get("confidence",0),3),"aligned":not timing.get("estimated",False),
            "punctuationAfter":item.get("punctuationAfter",timing.get("punctuationAfter","")),"breakAfter":bool(item.get("breakAfter")),"speechBreakAfter":bool(item.get("speechBreakAfter") or timing.get("speechBreakAfter"))}
        per_sentence[item["sentence"]].append(aligned);all_aligned.append(aligned)
    normalization=normalize_word_timeline(all_aligned)
    for sentence,words in zip(book["sentences"],per_sentence):
        sentence["words"]=words
        if words:
            sentence["start"]=round(words[0]["start"],3)
            sentence["end"]=round(words[-1]["end"],3)
    ratio=direct/max(1,len(canonical))
    if ratio < args.min_match:
        raise SystemExit(f"Alignment rejected: direct word match {ratio:.1%} is below {args.min_match:.0%}")
    timing_report=whisper_timing_report(all_aligned)
    book["alignment"]=f"whisper-{timing_report['timestampMethod']}-normalized"
    segmentation=resegment_timed_book(book,"yt",detect_silences(args.audio) if args.audio else None)
    book["whisper"]={"engine":"whisper.cpp","model":args.model,"directWordMatch":round(ratio,4),
                     **timing_report,"normalization":normalization,"segmentation":segmentation,
                     "canonicalWords":len(canonical),"matchedWords":direct,"transcribedWords":len(heard)}
    output=args.output or args.book
    output.write_text(json.dumps(book,ensure_ascii=False,indent=2))
    report={"engine":"whisper.cpp","model":args.model,"canonicalWords":len(canonical),
            "transcribedWords":len(heard),"directMatches":direct,"directMatchRate":round(ratio,4),
            "estimatedWords":sum(word.get("estimated",False) for word in all_aligned),**timing_report,"normalization":normalization,
            "largeBookOptimization":use_autojunk,
            "firstSpeechWord":heard[0] if heard else None,"lastSpeechWord":heard[-1] if heard else None}
    if args.report: args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    quality_path=output.with_name("quality-report.json")
    if quality_path.exists():
        quality=json.loads(quality_path.read_text())
        quality["summary"]["alignment"]=book["alignment"]
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
