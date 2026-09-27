#!/usr/bin/env python3
"""Build a compact offline English-Chinese dictionary for imported books."""
import argparse
import csv
import json
import re
from pathlib import Path

WORD_RE=re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")

def candidates(word):
    word=word.lower().replace("’","'")
    result=[word]
    if word.endswith("ies"): result.append(word[:-3]+"y")
    if word.endswith("ing"):
        stem=word[:-3]; result += [stem,stem+"e"]
        if len(stem)>2 and stem[-1]==stem[-2]: result.append(stem[:-1])
    if word.endswith("ed"):
        stem=word[:-2]; result += [stem,stem+"e"]
        if len(stem)>2 and stem[-1]==stem[-2]: result.append(stem[:-1])
    if word.endswith("es"): result += [word[:-2],word[:-1]]
    if word.endswith("s"): result.append(word[:-1])
    if word.endswith("er"): result += [word[:-2],word[:-1]]
    if word.endswith("est"): result += [word[:-3],word[:-2]]
    return list(dict.fromkeys(x for x in result if x))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--book",action="append",required=True,type=Path)
    parser.add_argument("--ecdict",type=Path,default=Path("tools/vendor/ECDICT/ecdict.csv"))
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    surfaces=set()
    for path in args.book:
        book=json.loads(path.read_text())
        for sentence in book["sentences"]:
            surfaces.update(x.lower().replace("’","'") for x in WORD_RE.findall(sentence["text"]))
    wanted={candidate for word in surfaces for candidate in candidates(word)}
    records={}
    with args.ecdict.open(encoding="utf-8",newline="") as source:
        for row in csv.DictReader(source):
            key=row["word"].lower()
            if key not in wanted: continue
            translation=row.get("translation","").replace("\\n","\n").strip()
            definition=row.get("definition","").replace("\\n","\n").strip()
            if not translation and not definition: continue
            records[key]={"word":row["word"],"phonetic":row.get("phonetic","").strip(),
                          "translation":translation,"definition":definition,"source":"ECDICT"}
    output={}
    for surface in sorted(surfaces):
        options=[records[c] for c in candidates(surface) if c in records]
        if options:
            match=dict(options[0])
            pronunciation=next((item["phonetic"] for item in options if item.get("phonetic")),"")
            match["phonetic"]=pronunciation
            output[surface]=match
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,ensure_ascii=False,separators=(",",":")))
    print(f"Dictionary: {len(output)}/{len(surfaces)} surface forms -> {args.output}")

if __name__=="__main__": main()
