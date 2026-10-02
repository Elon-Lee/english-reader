#!/usr/bin/env python3
"""Replace legacy YouTube/Whisper processing with native YouTube caption alignment."""
import json,os,shutil,sqlite3,subprocess,sys,tempfile
from datetime import datetime
from pathlib import Path

from import_youtube_worker import NODE,YTDLP
from library_db import BOOKS_ROOT,DB_PATH,ROOT
from reprocess_youtube_alignment import backup_database,metrics,record_mapping,url_path
from youtube_subtitles import has_translated_english_track,select_native_english_track

ALIGNER=ROOT/".local/forced-aligner/venv/bin/python"
WORK=ROOT/".local/youtube-subtitle-repair"

def run(command,quiet=False):
    print("$ "+" ".join(str(item) for item in command),flush=True)
    subprocess.run([str(item) for item in command],check=True,cwd=ROOT,env={**os.environ,"PYTHONPATH":str(ROOT/"tools")},stdout=subprocess.DEVNULL if quiet else None)

def download_track(metadata,track,target):
    directory=target.parent;directory.mkdir(parents=True,exist_ok=True)
    for path in directory.glob("source.*.srt"):path.unlink()
    flag="--write-subs" if track["source"]=="manual" else "--write-auto-subs"
    command=[YTDLP,"--js-runtimes",f"node:{NODE}","--no-playlist","--skip-download",flag,"--sub-langs",track["code"],"--sub-format","srt","--convert-subs","srt","-o",str(directory/"source.%(ext)s"),metadata["sourceUrl"]]
    run(command,True);subtitle=next(iter(sorted(directory.glob("source.*.srt"))),None)
    if not subtitle:raise ValueError(f"Subtitle download produced no SRT: {track}")
    shutil.copy2(subtitle,target)

def subtitle_metadata(track,translated_rejected):
    return {"youtubeSubtitleSource":track["source"],"youtubeSubtitleTrack":track["code"],"youtubeSubtitleLanguage":"en","youtubeSubtitleTranslated":False,"translatedEnglishRejected":bool(translated_rejected),"localTranscriptionUsed":False}

def candidate_for(row,track,subtitle,metadata):
    old=json.loads(row["data_json"]);source=BOOKS_ROOT/row["source_path"];audio=url_path(old["audio"]);video=url_path(old["video"]);work=WORK/row["id"];work.mkdir(parents=True,exist_ok=True)
    stage=work/"stage.json";aligned=work/"aligned.json";profile="youtube-auto" if track["source"]=="automatic" else "youtube-manual"
    run([sys.executable,ROOT/"tools/build_video_book.py","--audio",audio,"--subtitle",subtitle,"--output",stage,"--id",row["id"],"--title",old["title"],"--english-title",old.get("englishTitle",old["title"]),"--level",old.get("level",""),"--audio-url",old["audio"],"--video-url",old["video"],"--page-base",old.get("pageBase",""),"--subtitle-type","external","--subtitle-source",track["source"]])
    candidate=json.loads(stage.read_text());candidate.update({key:value for key,value in old.items() if key not in {"sentences","alignment","segmentation","whisper","forcedAlignment","subtitleAlignment","subtitleSource","subtitleType"}});candidate.update({"sourceType":"youtube","subtitleType":"external","subtitleSource":track["source"],"channel":old.get("channel",metadata.get("channel","")),**subtitle_metadata(track,metadata.get("translatedEnglishRejected",False))});stage.write_text(json.dumps(candidate,ensure_ascii=False,indent=2))
    run([sys.executable,ROOT/"tools/apply_sat_segmentation.py","--book",stage,"--audio",audio,"--output",stage,"--profile",profile])
    run([ALIGNER,ROOT/"tools/ctc_forced_align.py","--book-id",row["id"],"--input",stage,"--output",aligned,"--segmentation-profile",profile])
    result=json.loads(aligned.read_text());result.update({key:value for key,value in old.items() if key not in {"sentences","alignment","segmentation","whisper","forcedAlignment","subtitleAlignment","subtitleSource","subtitleType"}});result.update({key:value for key,value in json.loads(aligned.read_text()).items() if key in {"sentences","alignment","segmentation","forcedAlignment","subtitleAlignment"}});result.update({"sourceType":"youtube","subtitleType":"external","subtitleSource":track["source"],**subtitle_metadata(track,metadata.get("translatedEnglishRejected",False))});aligned.write_text(json.dumps(result,ensure_ascii=False,indent=2));report=metrics(result)
    if report["sentenceOverlaps"] or report["internalPausesOver08"]:raise ValueError(f"Timing quality rejected: {report}")
    if report["ctcCoverage"]<.75:raise ValueError(f"CTC coverage too low: {report['ctcCoverage']:.1%}")
    print(json.dumps({"book":row["title"],"track":{k:track[k] for k in ("source","code","translated")},"metrics":report},ensure_ascii=False,indent=2),flush=True)
    return old,result,report,metadata,profile

def apply_repairs(candidates,metadata_only,backup):
    db=sqlite3.connect(DB_PATH);db.row_factory=sqlite3.Row;stamp=datetime.now().astimezone().isoformat(timespec="seconds");file_backups=[]
    try:
        db.execute("BEGIN")
        for row,track,subtitle,old,new,report,metadata,profile in candidates:
            source=BOOKS_ROOT/row["source_path"];current=source/"subtitles.srt";saved=Path(backup).parent/"subtitles"/f"{row['id']}.srt";saved.parent.mkdir(parents=True,exist_ok=True)
            if current.exists():shutil.copy2(current,saved);file_backups.append((saved,current))
            shutil.copy2(subtitle,current)
            resolve,old_words,new_words,direct=record_mapping(old,new);unmapped=0
            for table in ("vocabulary","word_annotations"):
                records=db.execute(f"SELECT rowid AS _rowid,sentence_id,word_index FROM {table} WHERE book_id=?",(row["id"],)).fetchall();updates=[]
                for record in records:
                    target=resolve(record["sentence_id"],record["word_index"])
                    if target:updates.append((record["_rowid"],target[0],target[1]))
                    else:unmapped+=1
                for rowid,_,_ in updates:db.execute(f"UPDATE {table} SET sentence_id=? WHERE rowid=?",(f"__subtitle_repair__{row['id']}__{table}__{rowid}",rowid))
                for rowid,sentence_id,word_index in updates:db.execute(f"UPDATE {table} SET sentence_id=?,word_index=? WHERE rowid=?",(sentence_id,word_index,rowid))
            if unmapped:raise ValueError(f"{row['title']} has {unmapped} study records that could not be migrated")
            quality=json.loads(row["quality_json"] or "{}");quality.update({"status":"ready","subtitleType":"external","subtitleSource":track["source"],"whisperSkipped":True,"localTranscriptionUsed":False,"timingSource":f"youtube-{track['source']}-caption+sat+pause+wav2vec2","sentences":report["sentences"],"segmentation":new.get("segmentation",{}),"alignmentAudit":report})
            db.execute("UPDATE books SET subtitle_type='external',alignment=?,data_json=?,quality_json=?,updated_at=? WHERE id=?",(new.get("alignment","wav2vec2-ctc-forced-alignment"),json.dumps(new,ensure_ascii=False),json.dumps(quality,ensure_ascii=False),stamp,row["id"]))
            db.execute("DELETE FROM sentence_grammar WHERE book_id=?",(row["id"],))
            db.execute("DELETE FROM book_artifacts WHERE book_id=? AND kind='whisper-dtw'",(row["id"],));db.execute("INSERT INTO book_artifacts(book_id,kind,data_json,created_at) VALUES(?,?,?,?) ON CONFLICT(book_id,kind) DO UPDATE SET data_json=excluded.data_json,created_at=excluded.created_at",(row["id"],"subtitle",json.dumps({"type":"external","source":track["source"],"track":track["code"],"translated":False,"text":current.read_text(errors="replace")},ensure_ascii=False),stamp));db.execute("INSERT INTO book_artifacts(book_id,kind,data_json,created_at) VALUES(?,?,?,?) ON CONFLICT(book_id,kind) DO UPDATE SET data_json=excluded.data_json,created_at=excluded.created_at",(row["id"],"alignment-ctc",json.dumps(new.get("forcedAlignment",{}),ensure_ascii=False),stamp))
            metadata.update(subtitle_metadata(track,metadata.get("translatedEnglishRejected",False)));(source/".video-import.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
        for row,track,metadata in metadata_only:
            source=BOOKS_ROOT/row["source_path"];metadata.update(subtitle_metadata(track,metadata.get("translatedEnglishRejected",False)));(source/".video-import.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2));quality=json.loads(row["quality_json"] or "{}");quality.update({"whisperSkipped":True,"localTranscriptionUsed":False,"subtitleSource":track["source"]});data=json.loads(row["data_json"]);data.update({"subtitleSource":track["source"],**subtitle_metadata(track,metadata.get("translatedEnglishRejected",False))});db.execute("UPDATE books SET data_json=?,quality_json=?,updated_at=? WHERE id=?",(json.dumps(data,ensure_ascii=False),json.dumps(quality,ensure_ascii=False),stamp,row["id"]))
        for item in [*candidates,*metadata_only]:
            row=item[0]
            source=BOOKS_ROOT/row["source_path"]
            for stale in (source/".reader"/"whisper.json",source/".reader"/"alignment.json"):
                if stale.exists():
                    saved=Path(backup).parent/"legacy-whisper"/row["id"]/stale.name;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(stale,saved);file_backups.append((saved,stale));stale.unlink()
        db.commit()
    except Exception:
        db.rollback()
        for saved,current in file_backups:
            if saved.exists():shutil.copy2(saved,current)
        raise
    finally:db.close()

def main():
    WORK.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(DB_PATH);db.row_factory=sqlite3.Row;rows=db.execute("SELECT * FROM books WHERE source_type='youtube' ORDER BY created_at").fetchall();candidates=[];metadata_only=[]
    for row in rows:
        source=BOOKS_ROOT/row["source_path"];info=json.loads((source/"source.info.json").read_text());track=select_native_english_track(info);metadata=json.loads((source/".video-import.json").read_text());metadata["translatedEnglishRejected"]=has_translated_english_track(info)
        if not track:continue
        quality=json.loads(row["quality_json"] or "{}");whisper_artifact=db.execute("SELECT 1 FROM book_artifacts WHERE book_id=? AND kind='whisper-dtw'",(row["id"],)).fetchone()
        already_clean=bool(quality.get("whisperSkipped") and not whisper_artifact and metadata.get("youtubeSubtitleSource")==track["source"])
        if already_clean:metadata_only.append((row,track,metadata));continue
        work=WORK/row["id"];subtitle=work/"subtitles.srt";download_track(metadata,track,subtitle);old,new,report,metadata,profile=candidate_for(row,track,subtitle,metadata);candidates.append((row,track,subtitle,old,new,report,metadata,profile))
    db.close();backup=backup_database();apply_repairs(candidates,metadata_only,backup)
    for row,*_ in candidates:
        if ALIGNER.exists():subprocess.run([str(ALIGNER),str(ROOT/"tools/analyze_grammar.py"),"--book-id",row["id"]],cwd=ROOT,env={**os.environ,"PYTHONPATH":str(ROOT/"tools")},check=False)
    print(json.dumps({"status":"ok","rebuilt":len(candidates),"metadataOnly":len(metadata_only),"backup":str(backup)},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
