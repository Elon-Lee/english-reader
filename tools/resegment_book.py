#!/usr/bin/env python3
"""Split oversized book paragraphs while preserving existing word timings."""
import argparse
import json
import re
import sqlite3
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from text_segmentation import WORD_RE, split_sentences, word_count

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/".local/library.sqlite3"

def chapter_headings(source_path):
    headings=[]
    if not source_path:return headings
    source=(ROOT/"books"/source_path)
    for path in source.glob("*.mp3"):
        match=re.match(r"^0*(\d+)\s*[. _-]+(.+)$",path.stem)
        if match and not re.fullmatch(r"\d+",match.group(2)):headings.append((int(match.group(1)),match.group(2).strip()))
    return sorted(headings)

def split_heading(text,headings):
    normalized=lambda value:re.sub(r"[^a-z0-9]","",value.casefold())
    for number,title in headings:
        match=re.match(rf"^\s*0*{number}\s+(.+)$",text)
        if not match:continue
        words=list(WORD_RE.finditer(match.group(1)));target=normalized(title);joined=""
        for index,word in enumerate(words):
            joined+=normalized(word.group())
            target_words=len(WORD_RE.findall(title));close_length=index+1==target_words
            if joined==target or (close_length and SequenceMatcher(None,joined,target).ratio()>=.75):
                cut=match.start(1)+word.end();heading=text[:cut].strip();rest=text[cut:].strip()
                if rest:return [heading,rest]
                return [heading]
            if index+1>=target_words:break
    return [text]

def resegment(book,max_words=60,headings=()):
    output=[];mapping={};split_sources=0;sentences=book.get("sentences",[]);position=0
    while position<len(sentences):
        source_group=[sentences[position]];position+=1
        number_match=re.match(r"^\s*0*(\d+)\s+",source_group[0].get("text",""))
        heading=next(((number,title) for number,title in headings if number_match and number==int(number_match.group(1))),None)
        if heading:
            needed=1+len(WORD_RE.findall(heading[1]))
            while sum(len(item.get("words",[])) for item in source_group)<needed and position<len(sentences):
                source_group.append(sentences[position]);position+=1
        sentence={**source_group[0],"text":" ".join(item.get("text","") for item in source_group),"words":[word for item in source_group for word in item.get("words",[])]}
        if source_group[-1].get("end") is not None:sentence["end"]=source_group[-1]["end"]
        coordinates=[(item["id"],index) for item in source_group for index in range(len(item.get("words",[])))]
        parts=[]
        for headed in split_heading(sentence.get("text",""),headings):parts.extend(split_sentences(headed,max_words=max_words))
        if len(parts)>1:split_sources+=1
        words=sentence.get("words",[]);cursor=0
        for part in parts:
            count=word_count(part);selected=words[cursor:cursor+count]
            if count and len(selected)!=count:raise ValueError(f"{sentence.get('id')} 单词数量不一致：正文 {count}，时间轴 {len(selected)}")
            new_id=f"seg-{len(output)+1:06d}"
            item={**sentence,"id":new_id,"text":part,"targets":[int(value) for value in re.findall(r"\bGo (?:back )?to\s+(40|[1-3][0-9]|[1-9])\b",part,re.I)],"words":selected}
            if selected:item["start"]=selected[0]["start"];item["end"]=selected[-1]["end"]
            for index in range(count):mapping[coordinates[cursor+index]]=(new_id,index)
            output.append(item);cursor+=count
        if cursor!=len(words):raise ValueError(f"{sentence.get('id')} 尚有 {len(words)-cursor} 个时间轴单词未映射")
    return output,mapping,split_sources

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--book-id",required=True);parser.add_argument("--max-words",type=int,default=60)
    args=parser.parse_args();db=sqlite3.connect(DB);db.row_factory=sqlite3.Row
    row=db.execute("SELECT data_json,quality_json,source_path FROM books WHERE id=?",(args.book_id,)).fetchone()
    if not row:raise SystemExit("Book not found")
    book=json.loads(row["data_json"]);old_count=len(book.get("sentences",[]));sentences,mapping,split_sources=resegment(book,args.max_words,chapter_headings(row["source_path"]))
    book["sentences"]=sentences;book["segmentation"]={"method":"punctuation-and-length","maxWords":args.max_words,"previousSentences":old_count,"sentences":len(sentences),"splitSources":split_sources}
    if book.get("forcedAlignment"):
        book["forcedAlignment"]["resegmentedSentences"]=len(sentences);book["forcedAlignment"]["wordTimingsPreserved"]=True
    quality=json.loads(row["quality_json"] or "{}");quality.setdefault("summary",{})["sentences"]=len(sentences);quality["segmentation"]=book["segmentation"]
    for table in ("vocabulary","word_annotations"):
        records=db.execute(f"SELECT rowid AS _rowid,sentence_id,word_index FROM {table} WHERE book_id=?",(args.book_id,)).fetchall();updates=[]
        for record in records:
            target=mapping.get((record["sentence_id"],record["word_index"]))
            if target:updates.append((record["_rowid"],target))
        # Move through unique temporary sentence IDs so remapping an already
        # segmented book cannot collide with its current primary keys.
        for rowid,target in updates:db.execute(f"UPDATE {table} SET sentence_id=? WHERE rowid=?",(f"__resegment__{args.book_id}__{rowid}",rowid))
        for rowid,target in updates:db.execute(f"UPDATE {table} SET sentence_id=?,word_index=? WHERE rowid=?",(target[0],target[1],rowid))
    stamp=datetime.now().astimezone().isoformat(timespec="seconds")
    db.execute("UPDATE books SET data_json=?,quality_json=?,updated_at=? WHERE id=?",(json.dumps(book,ensure_ascii=False),json.dumps(quality,ensure_ascii=False),stamp,args.book_id))
    db.execute("INSERT INTO book_artifacts(book_id,kind,data_json,created_at) VALUES(?,?,?,?) ON CONFLICT(book_id,kind) DO UPDATE SET data_json=excluded.data_json,created_at=excluded.created_at",(args.book_id,"segmentation",json.dumps(book["segmentation"],ensure_ascii=False),stamp))
    if book.get("forcedAlignment"):db.execute("INSERT INTO book_artifacts(book_id,kind,data_json,created_at) VALUES(?,?,?,?) ON CONFLICT(book_id,kind) DO UPDATE SET data_json=excluded.data_json,created_at=excluded.created_at",(args.book_id,"alignment-ctc",json.dumps(book["forcedAlignment"],ensure_ascii=False),stamp))
    db.commit();db.close();print(json.dumps(book["segmentation"],ensure_ascii=False,indent=2))

if __name__=="__main__":main()
