#!/usr/bin/env python3
"""English sentence segmentation for OCR, DOC/CHM text and timed books."""
import re

WORD_RE=re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|\d+")
ABBREVIATIONS={"mr","mrs","ms","dr","prof","sr","jr","st","vs","etc","e.g","i.e","no","vol","fig","rev","hon","capt","lt","col","gen"}
CLOSERS='"\'”’)]}'
OPENERS='"\'“‘('

def word_count(text):return len(WORD_RE.findall(text))

def sentence_boundaries(text):
    boundaries=[];length=len(text);index=0
    while index<length:
        char=text[index]
        if char not in ".!?":index+=1;continue
        end=index+1
        while end<length and text[end] in ".!?":end+=1
        while end<length and text[end] in CLOSERS:end+=1
        if char==".":
            left=text[:index]
            token_match=re.search(r"([A-Za-z](?:[A-Za-z.]*)?)$",left)
            token=(token_match.group(1).rstrip(".").casefold() if token_match else "")
            if (index>0 and end<length and text[index-1].isdigit() and text[end].isdigit()) or token in ABBREVIATIONS or len(token)==1:
                index=end;continue
        next_index=end
        while next_index<length and text[next_index].isspace():next_index+=1
        while next_index<length and text[next_index] in OPENERS:next_index+=1
        if next_index>=length or text[next_index].isupper() or text[next_index].isdigit():boundaries.append(end)
        index=end
    return boundaries

def split_long(text,max_words=60,target_words=42):
    if word_count(text)<=max_words:return [text]
    output=[];remaining=text.strip()
    while word_count(remaining)>max_words:
        words=list(WORD_RE.finditer(remaining));target=min(target_words,len(words)-1);low=max(12,target-12);high=min(len(words)-1,target+12)
        left=words[low].start();right=words[high].start();window=remaining[left:right]
        candidates=[]
        for match in re.finditer(r"[;:—–]|,(?=\s|[A-Z'\"])",window):candidates.append(left+match.end())
        cut=min(candidates,key=lambda value:abs(value-words[target].start())) if candidates else words[target].start()
        first=remaining[:cut].strip(" \t,;:")
        if not first:cut=words[target].start();first=remaining[:cut].strip()
        output.append(first);remaining=remaining[cut:].strip()
    if remaining:output.append(remaining)
    return output

def split_sentences(text,max_words=60):
    text=re.sub(r"[ \t]+"," ",text).strip()
    if not text:return []
    starts=[0];ends=sentence_boundaries(text)
    parts=[]
    for end in ends:
        start=starts[-1];part=text[start:end].strip()
        if part:parts.append(part)
        next_start=end
        while next_start<len(text) and text[next_start].isspace():next_start+=1
        starts.append(next_start)
    tail=text[starts[-1]:].strip()
    if tail:parts.append(tail)
    expanded=[]
    for part in parts:expanded.extend(split_long(part,max_words=max_words))
    output=[]
    for part in expanded:
        count=word_count(part)
        if output and count<3 and not re.match(r"^\d+\s+[A-Z]",part):output[-1]+=" "+part
        else:output.append(part)
    return output

