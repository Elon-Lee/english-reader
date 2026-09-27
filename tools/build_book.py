#!/usr/bin/env python3
"""Turn OCR output plus an MP3 into the local reader's book.json format."""
import argparse, json, re, subprocess
from pathlib import Path

WORD_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")

def duration(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nokey=1:noprint_wrappers=1", str(path)
    ], text=True)
    return float(out.strip())

def silences(path: Path):
    run=subprocess.run(["ffmpeg","-v","info","-i",str(path),"-af","silencedetect=noise=-38dB:d=0.45","-f","null","-"],
                       text=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    starts=[float(x) for x in re.findall(r"silence_start: ([0-9.]+)",run.stderr)]
    ends=[float(x) for x in re.findall(r"silence_end: ([0-9.]+)",run.stderr)]
    return list(zip(starts,ends))

def clean_page(page):
    text = " ".join(x["text"] for x in page["lines"])
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\bto\s*([0-9]+)\b", r"to \1", text, flags=re.I)
    text = re.sub(r"\btol\b", "to 1", text, flags=re.I)
    text = text.replace("•", " ◆ ")
    return text

def sentences_for_page(text):
    # Keep numbered game sections and choices readable while avoiding tiny fragments.
    parts = re.split(r"(?<=[.!?])\s+(?=[◆A-Z0-9])|\s+(?=◆)", text)
    output=[]
    for part in parts:
        part=part.strip(" ◆")
        if not part or part == "Survive!": continue
        if output and len(WORD_RE.findall(part)) < 3:
            output[-1] += " " + part
        else: output.append(part)
    return output

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ocr", required=True, type=Path)
    ap.add_argument("--audio", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--title", required=True)
    ap.add_argument("--id", default="book")
    ap.add_argument("--english-title", default="")
    ap.add_argument("--level", default="0")
    ap.add_argument("--page-start", type=int, default=1)
    ap.add_argument("--page-end", type=int)
    ap.add_argument("--audio-url", default="audio.mp3")
    ap.add_argument("--pdf-url", default="book.pdf")
    ap.add_argument("--audio-start", type=float, default=0.0)
    ap.add_argument("--section-fixes", type=Path)
    args=ap.parse_args()
    pages=json.loads(args.ocr.read_text())
    page_end=args.page_end or len(pages)
    rows=[]
    current_section=None
    for page in pages[args.page_start-1:page_end]:
        for text in sentences_for_page(clean_page(page)):
            if not WORD_RE.search(text): continue
            section_match=re.match(r"^(40|[1-3][0-9]|[1-9])\s+(?=[A-Z])",text)
            if section_match: current_section=int(section_match.group(1))
            targets=[int(n) for n in re.findall(r"\bGo (?:back )?to\s+(40|[1-3][0-9]|[1-9])\b",text,re.I)]
            rows.append({"page":page["page"],"text":text,"section":current_section,"targets":targets})
    if args.section_fixes and args.section_fixes.exists():
        fixes=json.loads(args.section_fixes.read_text())
        for fix in fixes:
            start_index=next((i for i,r in enumerate(rows) if r["text"].startswith(fix["startsWith"])),None)
            end_index=next((i for i,r in enumerate(rows[start_index+1:],start_index+1)
                            if r["text"].startswith(fix.get("untilStartsWith","\0"))),len(rows)) if start_index is not None else None
            if start_index is not None:
                for row in rows[start_index:end_index]: row["section"]=fix["section"]
    total=duration(args.audio)
    weights=[max(2.0, len(WORD_RE.findall(r["text"]))*0.42 + 0.7) for r in rows]
    start=args.audio_start
    usable=max(1,total-start)
    cumulative=[]; c=0
    for w in weights[:-1]: c+=w; cumulative.append(start+usable*c/sum(weights))
    candidates=[p for p in silences(args.audio) if p[0]>start+0.2 and p[1]<total-.2]
    chosen=[]; floor=start
    for idx,target in enumerate(cumulative):
        remaining=len(cumulative)-idx-1
        allowed=[p for p in candidates if p[0]>floor+.12]
        if len(allowed)>remaining:
            pool=allowed[:len(allowed)-remaining]
            pick=min(pool,key=lambda p:abs(p[0]-target))
            # A distant pause may be a chapter break, music, or illustration cue;
            # snapping to it would make one sentence absorb many seconds.
            next_target=cumulative[idx+1] if idx+1<len(cumulative) else total
            min_span=max(1.2, min(3.0, weights[idx]*0.3))
            if abs(pick[0]-target) <= 2.0 and pick[0]-floor >= min_span and next_target-pick[1] >= 1.0:
                chosen.append(pick); floor=pick[1]
            else:
                chosen.append((target,target)); floor=target
        else: chosen.append((target,target)); floor=target
    cursor=start
    for i,row in enumerate(rows):
        end=chosen[i][0] if i<len(chosen) else total
        row.update(id=f"s{i+1}", start=round(cursor,2), end=round(end,2))
        cursor=chosen[i][1] if i<len(chosen) else total
    book={"id":args.id,"title":args.title,"englishTitle":args.english_title,"level":args.level,
          "audio":args.audio_url,"pdf":args.pdf_url,"duration":total,"alignment":"silence-assisted-estimate",
          "sentences":rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(book,ensure_ascii=False,indent=2))
    report_path=args.output.with_name("quality-report.json")
    selected=pages[args.page_start-1:page_end]
    low_conf=[]
    for page in selected:
        for line in page["lines"]:
            if line.get("confidence",1)<0.65:
                low_conf.append({"page":page["page"],"text":line["text"],"confidence":round(line["confidence"],2)})
    durations=[round(r["end"]-r["start"],2) for r in rows]
    sections=sorted({r["section"] for r in rows if r["section"] is not None})
    referenced=sorted({n for r in rows for n in r["targets"]})
    report={
        "generatedAt":__import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        "status":"needs-review" if low_conf else "ready",
        "summary":{"pages":len(selected),"sentences":len(rows),"sections":len(sections),
                   "lowConfidenceLines":len(low_conf),"alignment":book["alignment"]},
        "checks":{"emptyPages":[p["page"] for p in selected if not p["lines"]],
                  "missingSections":[n for n in range(1,41) if n not in sections],
                  "brokenTargets":[n for n in referenced if n not in sections],
                  "shortTimings":[rows[i]["id"] for i,d in enumerate(durations) if d<1.0],
                  "longTimings":[rows[i]["id"] for i,d in enumerate(durations) if d>15.0]},
        "lowConfidenceLines":low_conf[:100],
        "recommendations":["人工抽查低置信度 OCR 行","试听句子边界并校准正文起始秒数","安装 Whisper 后升级为词级时间戳"]
    }
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(f"Built {len(rows)} sentences, {total:.1f}s -> {args.output}")
if __name__ == "__main__": main()
