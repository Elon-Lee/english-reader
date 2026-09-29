#!/usr/bin/env python3
"""Select coherent book sources before expensive OCR/ASR work begins."""
import json
import math
import re
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

WORD_RE=re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")
CHAPTER_RE=re.compile(r"^\s*(\d{1,3})\s+(.+?)\s*$")
PUNCT=str.maketrans({"．":".","。":".","，":",","？":"?","！":"!","：":":","；":";","“":'"',"”":'"',"‘":"'","’":"'","—":"-","－":"-","…":"...","　":" "})

def natural_key(path):
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)",path.name)]

def normalize_paragraph(value):
    return re.sub(r"\s+"," ",value.translate(PUNCT)).strip()

def docx_paragraphs(path):
    with zipfile.ZipFile(path) as archive:
        root=ET.fromstring(archive.read("word/document.xml"))
    namespace="{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    output=[]
    for paragraph in root.iter(namespace+"p"):
        text="".join(node.text or "" for node in paragraph.iter(namespace+"t"))
        text=normalize_paragraph(text)
        if text:output.append(text)
    return output

def decoded_text(path):
    raw=path.read_bytes()
    for encoding in ("utf-8-sig","gb18030","utf-16"):
        try:return raw.decode(encoding)
        except UnicodeError:pass
    return raw.decode("latin-1",errors="replace")

def txt_paragraphs(path):
    lines=[normalize_paragraph(line) for line in decoded_text(path).splitlines()]
    headings=[]
    for index,line in enumerate(lines):
        match=CHAPTER_RE.match(line)
        if match:headings.append((index,int(match.group(1)),match.group(2)))
    english_headings=[item for item in headings if len(WORD_RE.findall(item[2]))>=1]
    if len({item[1] for item in english_headings})>=3:
        output=[];active=False
        for line in lines:
            match=CHAPTER_RE.match(line)
            if match:
                active=len(WORD_RE.findall(match.group(2)))>=1
            if active and line:output.append(line)
        return output
    return [line for line in lines if line and len(WORD_RE.findall(line))>=2]

def trim_to_story(paragraphs):
    start=next((index for index,text in enumerate(paragraphs) if re.match(r"^\s*1\s+[A-Za-z]",text)),0)
    result=paragraphs[start:]
    return [text for text in result if text and not re.fullmatch(r"JANE\s+EY(?:RE|ER)",text,re.I)]

def media_duration(path):
    try:return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",path],text=True).strip())
    except Exception:return 0.0

def select_text_source(source,expected_words=0):
    candidates=[]
    for path in sorted(source.glob("*.docx"),key=natural_key):
        try:paragraphs=trim_to_story(docx_paragraphs(path))
        except Exception:continue
        words=sum(len(WORD_RE.findall(text)) for text in paragraphs)
        if words>=500:candidates.append((2,words,path,paragraphs))
    for path in sorted(source.glob("*.txt"),key=natural_key):
        try:paragraphs=trim_to_story(txt_paragraphs(path))
        except Exception:continue
        words=sum(len(WORD_RE.findall(text)) for text in paragraphs)
        if words>=500:candidates.append((1,words,path,paragraphs))
    if not candidates:return None,[],0
    if expected_words:
        # Prefer a transcript whose scale resembles the selected audio. This
        # avoids choosing a full novel when the MP3s contain an abridged reader.
        distances=[(abs(math.log(max(1,item[1])/expected_words)),item) for item in candidates];best=min(value for value,_ in distances)
        near=[item for value,item in distances if value<=best+.03]
        _,words,path,paragraphs=max(near,key=lambda item:(item[0],item[1]))
    else:_,words,path,paragraphs=max(candidates,key=lambda item:(item[0],item[1]))
    return path,paragraphs,words

def pdf_page_count(path):
    try:
        value=subprocess.check_output(["mdls","-raw","-name","kMDItemNumberOfPages",path],text=True,stderr=subprocess.DEVNULL).strip()
        return int(value)
    except Exception:return 0

def select_pdf(pdfs,text_words=0):
    pdfs=sorted(pdfs,key=natural_key)
    if len(pdfs)<=1:return pdfs[0]
    page_counts={path:pdf_page_count(path) for path in pdfs}
    if text_words and any(page_counts.values()):
        expected=max(10,text_words/150)
        return min(pdfs,key=lambda path:abs(math.log(max(1,page_counts[path])/expected)) if page_counts[path] else 99)
    return min(pdfs,key=lambda path:(page_counts[path] or 10**9,path.stat().st_size))

def select_audio(audios):
    audios=sorted(audios,key=natural_key);groups={};ungrouped=[]
    for path in audios:
        match=re.match(r"^\s*(\d{1,3})(?:\D|$)",path.stem)
        if match:groups.setdefault(int(match.group(1)),[]).append(path)
        else:ungrouped.append(path)
    selected=list(ungrouped);excluded=[]
    for chapter in sorted(groups):
        items=groups[chapter]
        bare=[path for path in items if re.fullmatch(r"0*\d+",path.stem.strip())]
        descriptive=[path for path in items if path not in bare]
        if descriptive and bare:
            selected.extend(descriptive);excluded.extend({"file":path.name,"reason":f"章节 {chapter} 已有描述性音频"} for path in bare)
        else:selected.extend(items)
    return sorted(selected,key=natural_key),excluded

def signature(path):
    stat=path.stat();return {"file":path.name,"size":stat.st_size,"mtime":stat.st_mtime_ns}

def build_source_plan(source):
    pdfs=list(source.glob("*.pdf"));audios=list(source.glob("*.mp3"))
    if not pdfs or not audios:raise ValueError("导入需要至少一个 PDF 和一个 MP3")
    selected_audio,excluded_audio=select_audio(audios);audio_duration=sum(media_duration(path) for path in selected_audio)
    text_source,paragraphs,text_words=select_text_source(source,audio_duration*2.4)
    pdf=select_pdf(pdfs,text_words)
    return {
        "version":2,"pdf":signature(pdf),"textSource":signature(text_source) if text_source else None,
        "textWords":text_words,"audioDuration":round(audio_duration,3),"audio":[signature(path) for path in selected_audio],"excludedAudio":excluded_audio,
        "multiplePdfs":[{"file":path.name,"pages":pdf_page_count(path)} for path in sorted(pdfs,key=natural_key)],
    },pdf,text_source,paragraphs,selected_audio

def authoritative_ocr(paragraphs,scanned_pages):
    if not paragraphs:return scanned_pages
    candidates=[]
    for page in scanned_pages:
        text=" ".join(line.get("text","") for line in page.get("lines",[]))
        english=len(re.findall(r"[A-Za-z]",text));cjk=len(re.findall(r"[\u3400-\u9fff]",text))
        if len(WORD_RE.findall(text))>=12 and english>=max(60,cjk*1.25):candidates.append(page["page"])
    if len(candidates)<8:candidates=[page["page"] for page in scanned_pages]
    total=sum(max(1,len(WORD_RE.findall(text))) for text in paragraphs);pages={number:[] for number in candidates};seen=0
    for text in paragraphs:
        center=(seen+max(1,len(WORD_RE.findall(text)))/2)/max(1,total)
        page=candidates[min(len(candidates)-1,int(center*len(candidates)))]
        pages[page].append({"text":text,"confidence":1})
        seen+=max(1,len(WORD_RE.findall(text)))
    return [{"page":number,"width":next((page.get("width",0) for page in scanned_pages if page["page"]==number),0),"lines":lines} for number,lines in pages.items() if lines]

def write_plan(path,plan):path.write_text(json.dumps(plan,ensure_ascii=False,indent=2))
