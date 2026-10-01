#!/usr/bin/env python3
"""Build natural, non-overlapping sentences from a timed English word stream."""
import re,subprocess

WORD_RE=re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|\d+")
PUNCTUATION_RE=re.compile(r"[.!?]")
CONTINUATIONS={"a","an","the","to","of","for","with","in","on","at","from","by","and","or","but","is","are","was","were","be","been","being","that","this","these","those","my","your","his","her","our","their"}
CLAUSE_STARTERS={"if","when","because","although","unless","while","whether","since","once","where","which","who","whom","whose","after","before","until","though","whereas"}
BAD_ENDINGS=CONTINUATIONS|CLAUSE_STARTERS|{"as","than","then","so","not","no"}
OBJECT_PRONOUNS={"me","you","him","her","it","us","them"}
DETERMINER_LIKE={"most","many","some","all","each","every","another","other","few","several","both","either","neither"}
PROTECTED_PAIRS={
    ("out","loud"),("works","for"),("for","you"),("look","up"),("write","down"),("pay","attention"),("go","back"),
    ("too","easy"),("too","hard"),("one","of"),("a","word"),("word","that"),("such","as"),("rather","than"),
}

def protected_boundary(words,index):
    left=normalized(words[index].get("text"));right=normalized(words[index+1].get("text"));sat_probability=float(words[index].get("satBoundaryProbability",0));pair=(left,right)
    pause=max(words[index+1]["start"]-words[index]["end"],float(words[index].get("acousticPause",0)))
    return (left in BAD_ENDINGS or pair in PROTECTED_PAIRS or left in DETERMINER_LIKE or
            (right in OBJECT_PRONOUNS and sat_probability<.08) or
            (right=="too" and sat_probability<.08) or
            (sat_probability<.03 and pause<1.25) or
            (left in {"for","to","of","with","in","on","at","from","by"} and right not in CLAUSE_STARTERS))

def normalized(value):return re.sub(r"[^a-z0-9']","",str(value).lower().replace("’","'"))

def text_words(text):
    matches=list(WORD_RE.finditer(text or ""));output=[]
    for index,match in enumerate(matches):
        tail=(text or "")[match.end():(matches[index+1].start() if index+1<len(matches) else len(text or ""))]
        punctuation="".join(re.findall(r"[,.;:!?]",tail))
        output.append({"text":match.group(),"punctuationAfter":punctuation,"breakAfter":bool(PUNCTUATION_RE.search(tail))})
    return output

def dedupe_caption_words(entries,automatic=False):
    """Turn display-oriented subtitle cues into one monotonic, de-duplicated word stream."""
    output=[];duplicates=0
    for cue_index,cue in enumerate(entries):
        cue_words=text_words(cue.get("text",""))
        if not cue_words:continue
        norms=[normalized(item["text"]) for item in cue_words]
        skip=0
        if automatic and output:
            existing=[normalized(item["text"]) for item in output]
            limit=min(len(norms),len(existing),24)
            for count in range(limit,0,-1):
                if existing[-count:]==norms[:count]:skip=count;break
            duplicates+=skip
        new=cue_words[skip:]
        if not new:continue
        cue_start=float(cue.get("start",0));cue_end=max(cue_start+.08,float(cue.get("end",cue_start+.08)))
        span=cue_end-cue_start;word_span=max(.04,span/max(1,len(cue_words)))
        for local,item in enumerate(new,skip):
            start=cue_start+span*local/max(1,len(cue_words));end=cue_start+span*(local+1)/max(1,len(cue_words))
            if output and start<output[-1]["start"]+.04:start=output[-1]["start"]+.04
            end=max(start+.04,min(end,start+max(.12,word_span)))
            output.append({**item,"start":round(start,3),"end":round(end,3),"confidence":1,"aligned":False,"cue":cue_index})
    return output,{"inputCues":len(entries),"deduplicatedWords":duplicates,"words":len(output)}

def normalize_word_timeline(words):
    """Make textual word order globally monotonic without stretching words over pauses."""
    fixed=0;capped=0
    for index,word in enumerate(words):
        word["start"]=max(0,float(word.get("start",0)));word["end"]=max(word["start"]+.03,float(word.get("end",word["start"]+.03)))
        maximum=min(1.35,max(.32,.24+len(re.sub(r"[^A-Za-z0-9]","",word.get("text","")))*.09))
        if word["end"]-word["start"]>maximum:word["end"]=word["start"]+maximum;capped+=1
        if index:
            previous=words[index-1]
            if word["start"]<previous["end"]:
                boundary=max(previous["start"]+.03,min(word["end"]-.03,(previous["end"]+word["start"])/2))
                previous["end"]=boundary;word["start"]=boundary;fixed+=1
            if word["start"]<previous["start"]+.03:word["start"]=previous["start"]+.03;fixed+=1
            word["end"]=max(word["start"]+.03,word["end"])
        word["start"]=round(word["start"],3);word["end"]=round(word["end"],3)
    return {"wordOverlapsFixed":fixed,"wordDurationsCapped":capped}

def detect_silences(path,noise="-35dB",duration=.35):
    process=subprocess.run(["ffmpeg","-hide_banner","-nostats","-i",str(path),"-af",f"silencedetect=noise={noise}:d={duration}","-f","null","-"],text=True,capture_output=True)
    starts=[float(value) for value in re.findall(r"silence_start: ([0-9.]+)",process.stderr)];ends=[float(value) for value in re.findall(r"silence_end: ([0-9.]+)",process.stderr)]
    return list(zip(starts,ends))

def mark_silence_boundaries(words,silences):
    marked=0
    for silence_start,silence_end in silences:
        midpoint=(silence_start+silence_end)/2;left=None;right=None
        for index,word in enumerate(words):
            if word["end"]<=midpoint:left=index
            if word["start"]>=midpoint:right=index;break
        if left is None or right is None or right<=left:continue
        gap=words[right]["start"]-words[left]["end"]
        pause=max(gap,silence_end-silence_start)
        if gap>=.28:
            words[left]["acousticPause"]=round(pause,3);marked+=1
    return marked

def boundary_score(words,index,start,profile="speech-asr"):
    left=words[index];right=words[index+1];gap=max(0,right["start"]-left["end"]);count=index-start+1;duration=left["end"]-words[start]["start"]
    left_word=normalized(left.get("text"));right_word=normalized(right.get("text"));punctuation_weight=13 if profile in {"youtube-manual","local-subtitle"} else 10;sat_weight=22 if profile in {"youtube-auto","speech-asr"} else 14
    pause=max(gap,float(left.get("acousticPause",0)));score=min(10,pause*5)
    if left.get("breakAfter") or left.get("speechBreakAfter"):score+=punctuation_weight
    sat_probability=float(left.get("satBoundaryProbability",0));sat_evidence=max(0,(sat_probability-.08)/.92)
    score+=sat_weight*sat_evidence
    if pause>=.78:score+=6
    elif pause>=.48:score+=2
    if right_word in CLAUSE_STARTERS:score+=6
    if left_word in BAD_ENDINGS:score-=15
    if (left_word,right_word) in PROTECTED_PAIRS:score-=18
    if left_word in {"for","to","of","with","in","on","at","from","by","a","an","the"}:score-=5
    if count<3:score-=5
    if count>=7:score+=1
    if duration>=4:score+=1
    return score,gap

def internal_bridge_penalty(words,start,end,hard_pause=.78):
    penalty=0;bridges=0
    for index in range(start,end-1):
        left=normalized(words[index].get("text"));right=normalized(words[index+1].get("text"));pause=max(words[index+1]["start"]-words[index]["end"],float(words[index].get("acousticPause",0)))
        if pause<hard_pause:continue
        protected=protected_boundary(words,index)
        if protected:penalty-=1.5;bridges+=1
        else:penalty-=min(30,8+pause*5)
    return penalty,bridges

def segment_score(words,start,end,max_words,max_seconds,hard_pause,profile):
    count=end-start;duration=words[end-1]["end"]-words[start]["start"]
    if count<=0 or count>max_words+5 or duration>max_seconds+2:return None
    # Each new segment has a cost. Boundary evidence must justify creating it;
    # this prevents SaT/short pauses from producing subtitle-like fragments.
    quality=-6
    if count==1:quality-=14
    elif count==2:quality-=8
    elif count<5:quality-=3
    elif 7<=count<=18:quality+=2
    if duration<.45:quality-=8
    if duration>max_seconds:quality-=5+(duration-max_seconds)*2
    ending=normalized(words[end-1].get("text"))
    if ending in BAD_ENDINGS:quality-=12
    bridge_penalty,protected_bridges=internal_bridge_penalty(words,start,end,hard_pause)
    all_long_pauses=sum(1 for index in range(start,end-1) if max(words[index+1]["start"]-words[index]["end"],float(words[index].get("acousticPause",0)))>=hard_pause)
    if all_long_pauses>protected_bridges:return None
    quality+=bridge_penalty
    if end<len(words):quality+=boundary_score(words,end-1,start,profile)[0]
    else:quality+=8
    return quality

def split_ranges(words,max_words=22,max_seconds=11.0,hard_pause=.78,soft_pause=.48,profile="speech-asr"):
    if not words:return []
    total=len(words);negative=-10**18;best=[negative]*(total+1);previous=[None]*(total+1);best[0]=0
    for end in range(1,total+1):
        low=max(0,end-(max_words+5))
        for start in range(low,end):
            if best[start]==negative:continue
            score=segment_score(words,start,end,max_words,max_seconds,hard_pause,profile)
            if score is None:continue
            candidate=best[start]+score
            if candidate>best[end]:best[end]=candidate;previous[end]=start
    if previous[total] is None:
        return [(index,min(total,index+max_words)) for index in range(0,total,max_words)]
    ranges=[];cursor=total
    while cursor:
        start=previous[cursor];ranges.append((start,cursor));cursor=start
    return list(reversed(ranges))

def sentence_text(words):
    text=" ".join((str(word.get("text","")).strip()+str(word.get("punctuationAfter","")).strip()) for word in words if str(word.get("text","")).strip())
    return re.sub(r"\s+([,.;:!?])",r"\1",text).strip()

def segment_timed_words(words,id_prefix="yt",max_words=22,max_seconds=11.0,hard_pause=.78,soft_pause=.48,silences=None,profile="speech-asr"):
    words=[dict(word) for word in words if normalized(word.get("text",""))]
    for word in words:word.pop("acousticBreakAfter",None);word.pop("acousticPause",None)
    normalization=normalize_word_timeline(words);ranges=split_ranges(words,max_words,max_seconds,hard_pause,soft_pause,profile);sentences=[]
    silence_boundaries=mark_silence_boundaries(words,silences or [])
    if silence_boundaries:ranges=split_ranges(words,max_words,max_seconds,hard_pause,soft_pause,profile)
    for index,(left,right) in enumerate(ranges,1):
        selected=words[left:right];sentences.append({"id":f"{id_prefix}-{index:06d}","page":int(selected[0]["start"]//15)+1,"text":sentence_text(selected),"start":selected[0]["start"],"end":selected[-1]["end"],"section":None,"targets":[],"words":selected})
    gaps=[words[i+1]["start"]-words[i]["end"] for i in range(len(words)-1)]
    report={**normalization,"method":"sat-fused-dynamic-programming" if any("satBoundaryProbability" in word for word in words) else "timed-pause-punctuation-dynamic-programming","profile":profile,"words":len(words),"sentences":len(sentences),"acousticSilenceBoundaries":silence_boundaries,"hardPause":hard_pause,"softPause":soft_pause,"maxWords":max_words,"maxSeconds":max_seconds,"internalPausesOver08":0,"bridgedLongPauses":0,"sentenceOverlaps":0,"maxSentenceSeconds":round(max((s["end"]-s["start"] for s in sentences),default=0),3)}
    for sentence in sentences:
        for index,(a,b) in enumerate(zip(sentence["words"],sentence["words"][1:])):
            pause=max(b["start"]-a["end"],float(a.get("acousticPause",0)))
            if pause>=.8:
                if protected_boundary(sentence["words"],index):report["bridgedLongPauses"]+=1
                else:report["internalPausesOver08"]+=1
    report["sentenceOverlaps"]=sum(1 for a,b in zip(sentences,sentences[1:]) if b["start"]<a["end"]-.001)
    return sentences,report

def flatten_book_words(book):return [dict(word) for sentence in book.get("sentences",[]) for word in sentence.get("words",[])]

def resegment_timed_book(book,id_prefix="yt",silences=None,profile="speech-asr"):
    sentences,report=segment_timed_words(flatten_book_words(book),id_prefix=id_prefix,silences=silences,profile=profile)
    book["sentences"]=sentences;book["segmentation"]=report;return report
