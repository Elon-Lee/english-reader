#!/usr/bin/env python3
"""Populate sentence grammar analysis for imported books."""
import argparse,json,sqlite3,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"tools"))
from grammar_analysis import ANALYSIS_VERSION,GrammarAnalyzer,MODEL_NAME
from library_db import DB_PATH,connect,now,sentence_hash

def targets(db,book_id="",sentence_id="",force=False,shard_count=1,shard_index=0):
    params=[];where="WHERE status='ready'"
    if book_id:where+=" AND id=?";params.append(book_id)
    rows=db.execute(f"SELECT id,title,data_json FROM books {where} ORDER BY created_at",params).fetchall();result=[]
    for row_index,row in enumerate(rows):
        if not book_id and row_index%shard_count!=shard_index:continue
        book=json.loads(row["data_json"])
        for sentence in book.get("sentences",[]):
            if sentence_id and sentence.get("id")!=sentence_id:continue
            text=str(sentence.get("text","")).strip()
            if not text:continue
            existing=db.execute("SELECT sentence_hash,json_extract(analysis_json,'$.analysisVersion') FROM sentence_grammar WHERE book_id=? AND sentence_id=?",(row["id"],sentence["id"])).fetchone()
            if force or not existing or existing[0]!=sentence_hash(text) or existing[1]!=ANALYSIS_VERSION:result.append((row["id"],row["title"],sentence["id"],text))
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--book-id",default="");parser.add_argument("--sentence-id",default="");parser.add_argument("--force",action="store_true");parser.add_argument("--limit",type=int,default=0);parser.add_argument("--shard-count",type=int,default=1);parser.add_argument("--shard-index",type=int,default=0);args=parser.parse_args()
    if args.shard_count<1 or args.shard_index<0 or args.shard_index>=args.shard_count:raise SystemExit("invalid shard")
    db=connect();items=targets(db,args.book_id,args.sentence_id,args.force,args.shard_count,args.shard_index);total=len(items)
    if args.limit>0:items=items[:args.limit];total=len(items)
    if not items:print(json.dumps({"status":"ok","analyzed":0,"remaining":0},ensure_ascii=False));db.close();return
    analyzer=GrammarAnalyzer();analyzed=0;failed=[];batch_size=64
    db.execute("BEGIN")
    for offset in range(0,len(items),batch_size):
        batch=items[offset:offset+batch_size]
        try:analyses=analyzer.analyze_many([item[3] for item in batch])
        except Exception:
            analyses=[]
            for item in batch:
                try:analyses.append(analyzer.analyze(item[3]))
                except Exception as exc:analyses.append(exc)
        for (book_id,title,sentence_id,text),analysis in zip(batch,analyses):
            if isinstance(analysis,Exception):failed.append({"bookId":book_id,"sentenceId":sentence_id,"error":str(analysis)});continue
            db.execute("INSERT INTO sentence_grammar(book_id,sentence_id,sentence_hash,analysis_json,model,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(book_id,sentence_id) DO UPDATE SET sentence_hash=excluded.sentence_hash,analysis_json=excluded.analysis_json,model=excluded.model,updated_at=excluded.updated_at",(book_id,sentence_id,sentence_hash(text),json.dumps(analysis,ensure_ascii=False),MODEL_NAME,now()));analyzed+=1
        db.commit();db.execute("BEGIN");print(f"[{min(offset+len(batch),total)}/{total}] {batch[-1][1]}",flush=True)
    db.commit();remaining=db.execute("SELECT COUNT(*) FROM books b,json_each(b.data_json,'$.sentences') s WHERE b.status='ready' AND NOT EXISTS(SELECT 1 FROM sentence_grammar g WHERE g.book_id=b.id AND g.sentence_id=json_extract(s.value,'$.id'))").fetchone()[0];db.close()
    print(json.dumps({"status":"ok" if not failed else "partial","analyzed":analyzed,"failed":len(failed),"remaining":remaining,"failures":failed[:20]},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
