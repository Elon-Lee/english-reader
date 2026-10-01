#!/usr/bin/env python3
"""Rebuild YouTube captions into pause-aware sentences and preserve study records."""
import argparse,json,os,re,shutil,sqlite3,subprocess,sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import unquote

from align_whisper import norm
from library_db import BOOKS_ROOT,DB_PATH,ROOT
from sat_integration import annotate_sat_boundaries
from timed_segmentation import detect_silences,resegment_timed_book

ALIGNER=ROOT/".local/forced-aligner/venv/bin/python"
WORK=ROOT/".local/youtube-realign"

def run(command):
    print("$ "+" ".join(str(item) for item in command),flush=True);subprocess.run([str(item) for item in command],check=True,cwd=ROOT,env={**os.environ,"PYTHONPATH":str(ROOT/"tools")})

def url_path(url):
    prefix="/books/"
    if not str(url).startswith(prefix):raise ValueError(f"Unsupported books URL: {url}")
    path=(BOOKS_ROOT/unquote(str(url)[len(prefix):])).resolve();path.relative_to(BOOKS_ROOT.resolve());return path

def backup_database():
    stamp=datetime.now().strftime("%Y-%m-%d-%H%M%S-before-youtube-realign");target=ROOT/".local/backups"/stamp/"library.sqlite3";target.parent.mkdir(parents=True,exist_ok=True)
    source=sqlite3.connect(DB_PATH);destination=sqlite3.connect(target);source.backup(destination);destination.close();source.close();print(f"Database backup: {target}",flush=True);return target

def flat_words(book):
    output=[]
    for sentence in book.get("sentences",[]):
        words=sentence.get("words",[])
        if not words:
            words=[{"text":match.group(),"start":sentence.get("start",0),"end":sentence.get("end",0)} for match in re.finditer(r"[A-Za-z]+(?:['’][A-Za-z]+)?|\d+",sentence.get("text",""))]
        for index,word in enumerate(words):output.append({"sentenceId":sentence.get("id"),"wordIndex":index,"text":word.get("text",""),"norm":norm(word.get("text","")),"start":float(word.get("start",sentence.get("start",0))),"sentence":sentence})
    return output

def record_mapping(old_book,new_book):
    old=flat_words(old_book);new=flat_words(new_book);matcher=SequenceMatcher(None,[x["norm"] for x in old],[x["norm"] for x in new],autojunk=False);mapping={}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):mapping[block.a+offset]=block.b+offset
    new_by_norm={}
    for index,item in enumerate(new):new_by_norm.setdefault(item["norm"],[]).append((item["start"],index))
    old_positions={(item["sentenceId"],item["wordIndex"]):index for index,item in enumerate(old)}
    def resolve(sentence_id,word_index):
        old_index=old_positions.get((sentence_id,word_index))
        if old_index is None:return None
        new_index=mapping.get(old_index)
        if new_index is None:
            item=old[old_index];candidates=new_by_norm.get(item["norm"],[])
            if candidates:new_index=min(candidates,key=lambda pair:abs(pair[0]-item["start"]))[1]
        if new_index is None:return None
        target=new[new_index];return target["sentenceId"],target["wordIndex"]
    return resolve,len(old),len(new),len(mapping)

def metrics(book):
    sentences=book.get("sentences",[]);segmentation=book.get("segmentation",{});overlaps=sum(1 for left,right in zip(sentences,sentences[1:]) if float(right["start"])<float(left["end"])-.001);raw_internal=0;short=0;maximum=0
    for sentence in sentences:
        words=sentence.get("words",[]);short+=len(words)<3;maximum=max(maximum,float(sentence["end"])-float(sentence["start"]));raw_internal+=sum(1 for left,right in zip(words,words[1:]) if float(right["start"])-float(left["end"])>=.8)
    return {"sentences":len(sentences),"words":sum(len(item.get("words",[])) for item in sentences),"sentenceOverlaps":overlaps,"internalPausesOver08":segmentation.get("internalPausesOver08",raw_internal),"bridgedLongPauses":segmentation.get("bridgedLongPauses",0),"shortSentences":short,"maxSentenceSeconds":round(maximum,3),"ctcCoverage":book.get("forcedAlignment",{}).get("coverage",0)}

def build_candidate(row,artifact):
    old=json.loads(row["data_json"]);source=(BOOKS_ROOT/row["source_path"]).resolve();metadata=json.loads((source/".video-import.json").read_text());subtitle=source/"subtitles.srt";audio=url_path(old["audio"]);video=url_path(old["video"]);page_base=old.get("pageBase","");work=WORK/row["id"];work.mkdir(parents=True,exist_ok=True)
    whisper=work/"whisper.json";whisper.write_text(artifact["data_json"]);stage=work/"stage.json";aligned=work/"aligned.json";final=work/"final.json"
    command=[sys.executable,ROOT/"tools/build_video_book.py","--audio",audio,"--subtitle",subtitle,"--whisper",whisper,"--output",stage,"--id",row["id"],"--title",old["title"],"--english-title",old.get("englishTitle",old["title"]),"--level",old.get("level",""),"--audio-url",old["audio"],"--video-url",old["video"],"--page-base",page_base,"--subtitle-type",old.get("subtitleType","external"),"--subtitle-source",old.get("subtitleSource",metadata.get("youtubeSubtitleSource",""))]
    run(command)
    candidate=json.loads(stage.read_text());candidate.update({key:value for key,value in old.items() if key not in {"sentences","alignment","segmentation","whisper","forcedAlignment","subtitleAlignment"}});candidate["sourceType"]="youtube";stage.write_text(json.dumps(candidate,ensure_ascii=False,indent=2))
    run([sys.executable,ROOT/"tools/align_whisper.py","--book",stage,"--whisper",whisper,"--audio",audio,"--output",aligned,"--report",work/"whisper-report.json","--min-match","0.2"])
    if not ALIGNER.exists():raise ValueError("Forced-aligner environment is missing")
    run([ALIGNER,ROOT/"tools/ctc_forced_align.py","--book-id",row["id"],"--input",aligned,"--output",final])
    result=json.loads(final.read_text());result.update({key:value for key,value in old.items() if key not in {"sentences","alignment","segmentation","whisper","forcedAlignment","subtitleAlignment"}});result.update({key:value for key,value in json.loads(final.read_text()).items() if key in {"sentences","alignment","segmentation","whisper","forcedAlignment","subtitleAlignment"}});result["sourceType"]="youtube";final.write_text(json.dumps(result,ensure_ascii=False,indent=2));report=metrics(result)
    if report["sentenceOverlaps"] or report["internalPausesOver08"]:raise ValueError(f"Timing quality rejected: {report}")
    if report["ctcCoverage"]<.75:raise ValueError(f"CTC coverage too low: {report['ctcCoverage']:.1%}")
    print(json.dumps({"book":row["title"],"metrics":report},ensure_ascii=False,indent=2),flush=True);return old,result,report

def apply_candidates(candidates,backup):
    db=sqlite3.connect(DB_PATH);db.row_factory=sqlite3.Row;stamp=datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        db.execute("BEGIN")
        for row,old,new,report in candidates:
            resolve,old_words,new_words,direct=record_mapping(old,new);unmapped=0
            for table in ("vocabulary","word_annotations"):
                records=db.execute(f"SELECT rowid AS _rowid,sentence_id,word_index FROM {table} WHERE book_id=?",(row["id"],)).fetchall();updates=[]
                for record in records:
                    target=resolve(record["sentence_id"],record["word_index"])
                    if target:updates.append((record["_rowid"],target[0],target[1]))
                    else:unmapped+=1
                for rowid,_,_ in updates:db.execute(f"UPDATE {table} SET sentence_id=? WHERE rowid=?",(f"__youtube_realign__{row['id']}__{table}__{rowid}",rowid))
                for rowid,sentence_id,word_index in updates:db.execute(f"UPDATE {table} SET sentence_id=?,word_index=? WHERE rowid=?",(sentence_id,word_index,rowid))
            if unmapped:raise ValueError(f"{row['title']} has {unmapped} study records that could not be migrated")
            quality=json.loads(row["quality_json"] or "{}");quality.update({"status":"ready","sentences":report["sentences"],"timingSource":"subtitle-dedup+whisper-dtw+wav2vec2+pause-segmentation","segmentation":new.get("segmentation",{}),"alignmentAudit":report})
            db.execute("UPDATE books SET alignment=?,data_json=?,quality_json=?,updated_at=? WHERE id=?",(new.get("alignment","wav2vec2-ctc-forced-alignment"),json.dumps(new,ensure_ascii=False),json.dumps(quality,ensure_ascii=False),stamp,row["id"]))
            for kind,data in (("alignment-ctc",new.get("forcedAlignment",{})),("segmentation",new.get("segmentation",{})),("alignment-rebuild",{"backup":str(backup),"oldWords":old_words,"newWords":new_words,"directWordMap":direct,"unmappedStudyRecords":unmapped,"metrics":report})):
                db.execute("INSERT INTO book_artifacts(book_id,kind,data_json,created_at) VALUES(?,?,?,?) ON CONFLICT(book_id,kind) DO UPDATE SET data_json=excluded.data_json,created_at=excluded.created_at",(row["id"],kind,json.dumps(data,ensure_ascii=False),stamp))
        db.commit()
    except Exception:db.rollback();raise
    finally:db.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--book-id",action="append");parser.add_argument("--all",action="store_true");parser.add_argument("--dry-run",action="store_true");parser.add_argument("--reuse-final",action="store_true");args=parser.parse_args();db=sqlite3.connect(DB_PATH);db.row_factory=sqlite3.Row
    if args.all:rows=db.execute("SELECT * FROM books WHERE source_type='youtube' ORDER BY created_at").fetchall()
    else:
        ids=args.book_id or [];rows=[db.execute("SELECT * FROM books WHERE id=?",(book_id,)).fetchone() for book_id in ids];rows=[row for row in rows if row]
    candidates=[]
    for row in rows:
        artifact=db.execute("SELECT data_json FROM book_artifacts WHERE book_id=? AND kind='whisper-dtw'",(row["id"],)).fetchone()
        if not artifact:raise ValueError(f"{row['title']} has no retained Whisper artifact")
        final=WORK/row["id"]/"final.json"
        if args.reuse_final and final.exists():
            old=json.loads(row["data_json"]);new=json.loads(final.read_text());audio=url_path(old["audio"]);sat=annotate_sat_boundaries(new,"youtube-auto",True);segmentation=resegment_timed_book(new,"yt",detect_silences(audio),profile="youtube-auto");segmentation["sat"]=sat;new["segmentation"]=segmentation;final.write_text(json.dumps(new,ensure_ascii=False,indent=2));report=metrics(new)
            if report["sentenceOverlaps"] or report["internalPausesOver08"]:raise ValueError(f"Timing quality rejected: {report}")
            print(json.dumps({"book":row["title"],"reusedCtc":True,"metrics":report},ensure_ascii=False,indent=2),flush=True)
        else:old,new,report=build_candidate(row,artifact)
        candidates.append((row,old,new,report))
    db.close()
    if args.dry_run:print("Dry run complete; database unchanged",flush=True);return
    backup=backup_database();apply_candidates(candidates,backup);print(json.dumps({"status":"ok","books":len(candidates),"backup":str(backup)},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
