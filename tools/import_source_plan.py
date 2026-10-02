#!/usr/bin/env python3
"""Select coherent book sources before expensive OCR/ASR work begins."""
import json
import math
import re
import shutil
import subprocess
import tempfile
import zipfile
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

WORD_RE=re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")
CHAPTER_RE=re.compile(r"^\s*(\d{1,3})\s+(.+?)\s*$")
PUNCT=str.maketrans({"．":".","。":".","，":",","？":"?","！":"!","：":":","；":";","“":'"',"”":'"',"‘":"'","’":"'","—":"-","－":"-","…":"...","　":" "})
TITLE_NOISE=("中英文对照版","中英对照版","英汉对照版","英文对照版","中英文对照","中英对照","英汉对照","英文版","中文版","完整版","有声书","电子书")

def natural_key(path):
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)",path.name)]

def normalize_paragraph(value):
    return re.sub(r"\s+"," ",value.translate(PUNCT)).strip()

def strip_catalog_prefix(value):
    value=str(value)
    if Path(value).suffix.lower() in {".pdf",".doc",".docx",".txt",".chm"}:value=Path(value).stem
    value=re.sub(r"^\s*\d+(?:\.\d+)*(?:\.(?:上|中|下))?(?:\.\d+)?[. _-]*","",value,flags=re.I)
    value=re.sub(r"^\s*\d+[A-Za-z]?[_ .-]+\d+[. _-]*","",value,flags=re.I)
    return value.strip(" ._-—–")

def title_aliases(value):
    value=strip_catalog_prefix(value)
    for noise in TITLE_NOISE:value=value.replace(noise,"")
    value=re.sub(r"\([^)]*\)|（[^）]*）|\[[^]]*]"," ",value)
    runs=re.findall(r"[\u3400-\u9fff]+|[A-Za-z]+(?:\s+[A-Za-z]+)*",value)
    cjk_compact="".join(re.findall(r"[\u3400-\u9fff]+",value))
    latin_compact="".join(re.findall(r"[A-Za-z]+",value))
    if cjk_compact:runs.append(cjk_compact)
    if latin_compact:runs.append(latin_compact)
    aliases=[]
    for item in [value,*runs]:
        item=item.casefold().replace("&","and")
        item=re.sub(r"\bthe\b", "", item)
        item=item.replace("与","和").replace("及","和")
        item=re.sub(r"[^a-z0-9\u3400-\u9fff]","",item)
        if len(item)>=2 and item not in aliases:aliases.append(item)
    return aliases

def strict_title_aliases(value):
    """Aliases for the exact-name tier; edition labels are intentionally retained."""
    value=strip_catalog_prefix(value)
    value=re.sub(r"\([^)]*\)|（[^）]*）|\[[^]]*]"," ",value)
    cjk="".join(re.findall(r"[\u3400-\u9fff]+",value))
    latin="".join(re.findall(r"[A-Za-z]+",value)).casefold()
    latin_without_the=re.sub(r"^the", "", latin)
    aliases=[]
    for kind,item in (("cjk",cjk),("latin",latin_without_the),("latin",latin)):
        item=re.sub(r"[^a-z0-9\u3400-\u9fff]","",item.casefold())
        if len(item)>=2 and (kind,item) not in aliases:aliases.append((kind,item))
    return aliases

def exact_title_match_level(book_name,candidate_name):
    book_aliases=strict_title_aliases(book_name);candidate_aliases=strict_title_aliases(candidate_name);best=0
    for book_kind,book in book_aliases:
        for candidate_kind,candidate in candidate_aliases:
            if book==candidate:
                best=max(best,3 if book_kind==candidate_kind=="cjk" else 2)
    return best

def edition_noise_count(path):
    name=path.stem.casefold();return sum(noise.casefold() in name for noise in TITLE_NOISE)

def exact_path_key(source,path):
    level=exact_title_match_level(source.name,path.stem)
    stripped=strip_catalog_prefix(path.stem);prefix_removed=int(stripped!=path.stem)
    return (-level,edition_noise_count(path),prefix_removed,len(path.stem),natural_key(path))

def select_exact_files(source,extensions):
    return sorted([path for path in source.iterdir() if path.is_file() and path.suffix.lower() in extensions and exact_title_match_level(source.name,path.stem)],key=lambda path:exact_path_key(source,path))

def title_match_score(book_name,candidate_name):
    book_aliases=title_aliases(book_name);candidate_aliases=title_aliases(candidate_name);best=0
    for book in book_aliases:
        for candidate in candidate_aliases:
            if book==candidate:best=max(best,100)
            elif min(len(book),len(candidate))>=4 and (book in candidate or candidate in book):best=max(best,82)
            elif min(len(book),len(candidate))>=5:
                ratio=SequenceMatcher(None,book,candidate).ratio()
                if ratio>=.78:best=max(best,round(ratio*75))
            elif re.fullmatch(r"[\u3400-\u9fff]+",book) and re.fullmatch(r"[\u3400-\u9fff]+",candidate) and min(len(book),len(candidate))>=4:
                ratio=SequenceMatcher(None,book,candidate).ratio()
                if ratio>=.75:best=max(best,78)
    return best

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

def doc_paragraphs(path):
    output=subprocess.check_output(["textutil","-convert","txt","-stdout",path],stderr=subprocess.DEVNULL)
    text=output.decode("utf-8",errors="replace")
    return [line for line in (normalize_paragraph(line) for line in text.splitlines()) if line]

class ChmHtmlText(HTMLParser):
    BLOCKS={"p","div","li","br","h1","h2","h3","h4","h5","h6","tr","td","blockquote"}
    def __init__(self):super().__init__();self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in {"script","style","noscript"}:self.hidden+=1
        elif tag in self.BLOCKS:self.parts.append("\n")
    def handle_endtag(self,tag):
        if tag in {"script","style","noscript"}:self.hidden=max(0,self.hidden-1)
        elif tag in self.BLOCKS:self.parts.append("\n")
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)
    def paragraphs(self):
        output=[]
        for line in "".join(self.parts).splitlines():
            line=normalize_paragraph(line)
            if len(WORD_RE.findall(line))>=2:output.append(line)
        return output

def decoded_html(path):
    raw=path.read_bytes();head=raw[:4096].decode("ascii",errors="ignore")
    match=re.search(r"charset\s*=\s*['\"]?([\w.-]+)",head,re.I);encodings=[]
    if match:encodings.append(match.group(1))
    encodings.extend(["utf-8-sig","gb18030","utf-16","windows-1252"])
    for encoding in encodings:
        try:return raw.decode(encoding)
        except (UnicodeError,LookupError):pass
    return raw.decode("utf-8",errors="replace")

def chm_tool():
    for name in ("7zz","7z","extract_chmLib"):
        found=shutil.which(name)
        if found:return found
    return None

def chm_paragraphs(path):
    tool=chm_tool()
    if not tool:raise RuntimeError("CHM 导入需要安装 sevenzip（brew install sevenzip）或 chmlib")
    with tempfile.TemporaryDirectory(prefix="shiyue-chm-") as temp:
        root=Path(temp)
        if Path(tool).name=="extract_chmLib":command=[tool,path,root]
        else:command=[tool,"x","-y",f"-o{root}",path]
        subprocess.run([str(item) for item in command],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        html_files=sorted([item for item in root.rglob("*") if item.suffix.lower() in {".htm",".html"}],key=natural_key)
        order=[]
        for toc in root.rglob("*.hhc"):
            text=decoded_html(toc)
            for target in re.findall(r"<param[^>]+name\s*=\s*['\"]?Local['\"]?[^>]+value\s*=\s*['\"]([^'\"]+)",text,re.I):
                candidate=(toc.parent/target.replace("\\","/")).resolve()
                if candidate.is_file() and candidate.suffix.lower() in {".htm",".html"} and candidate not in order:order.append(candidate)
        order.extend(item for item in html_files if item not in order and "introduction" not in item.name.casefold() and item.name.casefold()!="index.htm")
        paragraphs=[];seen=set()
        for html in order:
            parser=ChmHtmlText()
            try:parser.feed(decoded_html(html))
            except Exception:continue
            for paragraph in parser.paragraphs():
                key=re.sub(r"\W+","",paragraph.casefold())
                if len(key)<8 or key in seen:continue
                seen.add(key);paragraphs.append(paragraph)
        return trim_to_story(paragraphs)

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

def text_candidate(path):
    if path.suffix.lower()==".docx":paragraphs=trim_to_story(docx_paragraphs(path));priority=3
    elif path.suffix.lower()==".doc":paragraphs=trim_to_story(doc_paragraphs(path));priority=3
    elif path.suffix.lower()==".chm":paragraphs=chm_paragraphs(path);priority=2
    else:paragraphs=trim_to_story(txt_paragraphs(path));priority=2
    return priority,sum(len(WORD_RE.findall(text)) for text in paragraphs),path,paragraphs

def choose_text_candidate(candidates,expected_words=0):
    candidates=[item for item in candidates if item[1]>=500]
    if not candidates:return None,[],0
    if expected_words:
        distances=[(abs(math.log(max(1,item[1])/expected_words)),item) for item in candidates];best=min(value for value,_ in distances)
        near=[item for value,item in distances if value<=best+.03]
        _,words,path,paragraphs=max(near,key=lambda item:(item[0],item[1]))
    else:_,words,path,paragraphs=max(candidates,key=lambda item:(item[0],item[1]))
    return path,paragraphs,words

def select_text_source(source,expected_words=0,extensions=(".docx",".doc",".chm",".txt")):
    candidates=[]
    for path in sorted(source.iterdir(),key=natural_key):
        if path.suffix.lower() not in extensions:continue
        try:candidates.append(text_candidate(path))
        except Exception:continue
    return choose_text_candidate(candidates,expected_words)

def select_named_text(source,expected_words,extensions):
    candidates=[]
    for path in sorted(source.iterdir(),key=natural_key):
        if path.suffix.lower() not in extensions:continue
        score=title_match_score(source.name,path.stem)
        if score<75:continue
        try:candidates.append((score,text_candidate(path)))
        except Exception:continue
    if not candidates:return None,[],0,0
    top=max(score for score,_ in candidates);near=[item for score,item in candidates if score==top]
    path,paragraphs,words=choose_text_candidate(near,expected_words)
    return path,paragraphs,words,top

def select_pdf_ocr_fallback_text(source,expected_words):
    """Choose authoritative text after a selected PDF cannot provide usable OCR."""
    tiers=[
        ("书名完全一致 DOC/DOCX",select_exact_files(source,{".docx",".doc"})),
        ("书名完全一致 CHM/TXT",select_exact_files(source,{".chm",".txt"})),
    ]
    for reason,paths in tiers:
        candidates=[]
        for path in paths:
            try:candidates.append(text_candidate(path))
            except Exception:continue
        path,paragraphs,words=choose_text_candidate(candidates,expected_words)
        if path:return path,paragraphs,words,reason
    for reason,extensions in (("书名相关 DOC/DOCX",(".docx",".doc")),("书名相关 CHM/TXT",(".chm",".txt"))):
        path,paragraphs,words,_=select_named_text(source,expected_words,extensions)
        if path:return path,paragraphs,words,reason
    return None,[],0,""

def pdf_page_count(path):
    try:
        value=subprocess.check_output(["mdls","-raw","-name","kMDItemNumberOfPages",path],text=True,stderr=subprocess.DEVNULL).strip()
        return int(value)
    except Exception:return 0

def select_pdf(pdfs,text_words=0,expected_words=0):
    pdfs=sorted(pdfs,key=natural_key)
    if len(pdfs)<=1:return pdfs[0]
    page_counts={path:pdf_page_count(path) for path in pdfs}
    reference_words=text_words or expected_words
    if reference_words and any(page_counts.values()):
        expected=max(10,reference_words/150)
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

def available_resources(folder):
    supported=(".mp3",".m4a",".wav",".ogg",".aac",".pdf",".doc",".docx",".txt",".chm")
    counts={ext[1:]:0 for ext in supported}
    for path in folder.iterdir():
        if path.is_file() and path.suffix.lower() in supported:counts[path.suffix.lower()[1:]]+=1
    audio_count=sum(counts[name] for name in ("mp3","m4a","wav","ogg","aac"));text_count=sum(counts[name] for name in ("pdf","doc","docx","txt","chm"))
    if audio_count and counts["chm"] and not sum(counts[name] for name in ("pdf","doc","docx","txt")):mode="CHM + 音频 · 导入时校验"
    elif audio_count and text_count:mode="正文 + 音频"
    elif audio_count:mode="仅音频 · Whisper"
    elif text_count:mode="缺少音频"
    else:mode="未发现可导入资源"
    return counts,audio_count,text_count,mode

def signature(path):
    stat=path.stat();return {"file":path.name,"size":stat.st_size,"mtime":stat.st_mtime_ns}

def build_source_plan(source):
    files=[path for path in source.iterdir() if path.is_file()];pdfs=[path for path in files if path.suffix.lower()==".pdf"]
    audio_extensions={".mp3",".m4a",".wav",".ogg",".aac"};audios=[path for path in files if path.suffix.lower() in audio_extensions]
    if not audios:raise ValueError("导入需要至少一个 MP3、M4A、WAV、OGG 或 AAC 音频")
    selected_audio,excluded_audio=select_audio(audios);audio_duration=sum(media_duration(path) for path in selected_audio);expected_words=audio_duration*2.4
    exact_pdfs=select_exact_files(source,{".pdf"});exact_docs=select_exact_files(source,{".docx",".doc"});exact_chm=select_exact_files(source,{".chm"});exact_txt=select_exact_files(source,{".txt"})
    named_pdfs=[(title_match_score(source.name,path.stem),path) for path in pdfs if path not in exact_pdfs]
    named_pdfs=[(score,path) for score,path in named_pdfs if score>=75]
    selection_reason=""
    if exact_pdfs:
        pdf=exact_pdfs[0];text_source=None;paragraphs=[];text_words=0;selection_reason=f"书名完全一致 PDF：{pdf.name}"
    elif exact_docs:
        candidates=[]
        for path in exact_docs:
            try:candidates.append(text_candidate(path))
            except Exception:continue
        text_source,paragraphs,text_words=choose_text_candidate(candidates,expected_words)
        if text_source:selection_reason=f"书名完全一致 DOC/DOCX：{text_source.name}"
        else:text_source=None;paragraphs=[];text_words=0;selection_reason="完全一致 DOC/DOCX 无法提取有效正文，使用 PDF/OCR 兜底"
        pdf=select_pdf(pdfs,text_words,expected_words) if pdfs else None
    elif exact_chm or exact_txt:
        exact_text=exact_chm or exact_txt;candidates=[]
        for path in exact_text:
            try:candidates.append(text_candidate(path))
            except Exception:continue
        text_source,paragraphs,text_words=choose_text_candidate(candidates,expected_words)
        if text_source:selection_reason=f"书名完全一致 {text_source.suffix.upper().lstrip('.')}：{text_source.name}"
        else:text_source=None;paragraphs=[];text_words=0;selection_reason="完全一致 CHM/TXT 无法提取有效正文，使用 PDF/OCR 兜底"
        pdf=select_pdf(pdfs,text_words,expected_words) if pdfs else None
    elif named_pdfs:
        top=max(score for score,_ in named_pdfs);pdf=select_pdf([path for score,path in named_pdfs if score==top],expected_words=expected_words)
        text_source=None;paragraphs=[];text_words=0;selection_reason=f"书名相关 PDF：{pdf.name}"
    else:
        text_source,paragraphs,text_words,score=select_named_text(source,expected_words,(".docx",".doc"))
        if text_source:selection_reason="书名匹配 DOC/DOCX"
        else:
            text_source,paragraphs,text_words,score=select_named_text(source,expected_words,(".chm",))
            if text_source:selection_reason="书名匹配 CHM"
            else:
                text_source,paragraphs,text_words,score=select_named_text(source,expected_words,(".txt",))
                if text_source:selection_reason="书名匹配 TXT"
                else:
                    text_source,paragraphs,text_words=select_text_source(source,expected_words);selection_reason="正文规模与音频时长匹配" if text_source else "仅音频：Whisper 自动生成正文"
        pdf=select_pdf(pdfs,text_words,expected_words) if pdfs else None
    rejected_text_source=None
    if text_source and text_words>=800 and expected_words>=800:
        ratio=text_words/expected_words
        if not .5<=ratio<=2.0:
            rejected_text_source={**signature(text_source),"words":text_words,"ratio":round(ratio,3),"reason":"正文规模与音频时长明显不匹配"}
            fallback="PDF OCR" if pdf else "仅音频 Whisper"
            selection_reason=f"{text_source.suffix.upper().lstrip('.')} 正文与音频规模不匹配，改用{fallback}"
            text_source=None;paragraphs=[];text_words=0
    content_mode="pdf" if pdf and not text_source else (text_source.suffix.lower().lstrip(".") if text_source else "audio")
    return {
        "version":5,"pdf":signature(pdf) if pdf else None,"textSource":signature(text_source) if text_source else None,"selectionReason":selection_reason,"contentMode":content_mode,
        "matchPolicy":"exact-pdf > exact-doc/docx > exact-chm/txt > related-pdf > related-doc/docx > related-chm/txt > duration-scale fallback",
        "exactMatches":{"pdf":[path.name for path in exact_pdfs],"doc":[path.name for path in exact_docs],"chm":[path.name for path in exact_chm],"txt":[path.name for path in exact_txt]},
        "textWords":text_words,"audioDuration":round(audio_duration,3),"audio":[signature(path) for path in selected_audio],"excludedAudio":excluded_audio,
        "rejectedTextSource":rejected_text_source,
        "multiplePdfs":[{"file":path.name,"pages":pdf_page_count(path),"exactLevel":exact_title_match_level(source.name,path.stem),"titleScore":title_match_score(source.name,path.stem)} for path in sorted(pdfs,key=natural_key)],
    },pdf,text_source,paragraphs,selected_audio

def authoritative_ocr(paragraphs,scanned_pages):
    if not paragraphs:return scanned_pages
    candidates=[]
    for page in scanned_pages:
        text=" ".join(line.get("text","") for line in page.get("lines",[]))
        english=len(re.findall(r"[A-Za-z]",text));cjk=len(re.findall(r"[\u3400-\u9fff]",text))
        if len(WORD_RE.findall(text))>=12 and english>=max(60,cjk*1.25):candidates.append(page["page"])
    total=sum(max(1,len(WORD_RE.findall(text))) for text in paragraphs)
    if len(candidates)<8:candidates=[page["page"] for page in scanned_pages]
    if not candidates:candidates=list(range(1,max(2,math.ceil(total/320)+1)))
    pages={number:[] for number in candidates};seen=0
    for text in paragraphs:
        center=(seen+max(1,len(WORD_RE.findall(text)))/2)/max(1,total)
        page=candidates[min(len(candidates)-1,int(center*len(candidates)))]
        pages[page].append({"text":text,"confidence":1,"paragraph":True})
        seen+=max(1,len(WORD_RE.findall(text)))
    return [{"page":number,"width":next((page.get("width",0) for page in scanned_pages if page["page"]==number),0),"lines":lines} for number,lines in pages.items() if lines]

def write_plan(path,plan):path.write_text(json.dumps(plan,ensure_ascii=False,indent=2))
