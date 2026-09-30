#!/usr/bin/env python3
"""Safely roll remote point-reading content back to a retained snapshot."""
import argparse,json,shutil,sqlite3,sys
from pathlib import Path

def read_json(path):return json.loads(Path(path).read_text(encoding="utf-8"))
def file_map(payload):return {item["path"]:item for item in payload.get("files",[]) if item.get("path")}
def copy_tree_files(source,destination):
    if not source.exists():return []
    copied=[]
    for path in source.rglob("*"):
        if path.is_file():
            relative=path.relative_to(source);target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target);copied.append(str(relative))
    return copied
def safe_relative(value):
    path=Path(value)
    if path.is_absolute() or ".." in path.parts:raise ValueError(f"非法资源路径：{value}")
    return path
def checkpoint_database(path):
    db=sqlite3.connect(path);db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.close()
def replace_database(source,destination):
    for suffix in ("-wal","-shm"):
        sidecar=Path(str(destination)+suffix)
        if sidecar.exists():sidecar.unlink()
    shutil.copy2(source,destination)

def restore_operation(operation,books,manifests,backups,db_path):
    root=backups/"content-rollbacks"/operation;meta=read_json(root/"restore.json")
    for value in meta["affected"]:
        path=books/safe_relative(value)
        if path.exists():path.unlink()
    copy_tree_files(root/"files",books);replace_database(root/"database.sqlite3",db_path);shutil.copy2(root/"current-content.json",manifests/"current-content.json")
    return {"status":"restored","operation":operation,"revision":meta["fromRevision"]}

def rollback(target,operation,books,manifests,backups,db_path):
    history=manifests/"history";target_manifest=history/f"{target}.json";target_bundle=history/f"{target}.json.gz";current_manifest=manifests/"current-content.json"
    if not target_manifest.is_file() or not target_bundle.is_file():raise ValueError("目标内容版本缺少完整快照，无法安全回滚")
    current=read_json(current_manifest).get("revision","");revisions=sorted(path.stem for path in history.glob("content-*.json") if path.is_file())
    if target not in revisions or current not in revisions:raise ValueError("内容版本链不完整")
    target_index=revisions.index(target);current_index=revisions.index(current)
    if target_index>current_index:raise ValueError("内容回滚只能选择当前版本之前的版本；如需恢复最新本地内容，请执行同步数据")
    if target==current:return {"status":"unchanged","revision":target,"operation":operation}
    affected=set()
    for index in range(target_index+1,current_index+1):
        revision=revisions[index];after=file_map(read_json(history/f"{revision}.json"));before=file_map(read_json(history/f"{revisions[index-1]}.json"));affected.update(set(after)-set(before))
        backup_root=backups/"resources"/revision
        if backup_root.exists():affected.update(str(path.relative_to(backup_root)) for path in backup_root.rglob("*") if path.is_file())
    restore_root=backups/"content-rollbacks"/operation;restore_root.mkdir(parents=True,exist_ok=False);files_backup=restore_root/"files"
    for value in sorted(affected):
        source=books/safe_relative(value)
        if source.is_file():target_path=files_backup/safe_relative(value);target_path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target_path)
    checkpoint_database(db_path);shutil.copy2(db_path,restore_root/"database.sqlite3");shutil.copy2(current_manifest,restore_root/"current-content.json")
    (restore_root/"restore.json").write_text(json.dumps({"operation":operation,"fromRevision":current,"toRevision":target,"affected":sorted(affected)},ensure_ascii=False,indent=2),encoding="utf-8")
    try:
        for index in range(current_index,target_index,-1):
            revision=revisions[index];after=file_map(read_json(history/f"{revision}.json"));before=file_map(read_json(history/f"{revisions[index-1]}.json"))
            for value in set(after)-set(before):
                path=books/safe_relative(value)
                if path.exists():path.unlink()
            copy_tree_files(backups/"resources"/revision,books)
        sys.path.insert(0,str(Path(__file__).resolve().parent));from remote_apply import apply_bundle
        apply_bundle(target_bundle,db_path,True);checkpoint_database(db_path);shutil.copy2(target_manifest,current_manifest)
    except Exception:
        restore_operation(operation,books,manifests,backups,db_path);raise
    return {"status":"ok","revision":target,"fromRevision":current,"operation":operation,"affectedFiles":len(affected)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--target");parser.add_argument("--operation",required=True);parser.add_argument("--restore",action="store_true");parser.add_argument("--books",required=True);parser.add_argument("--manifests",required=True);parser.add_argument("--backups",required=True);parser.add_argument("--database",required=True);args=parser.parse_args()
    books=Path(args.books);manifests=Path(args.manifests);backups=Path(args.backups);db_path=Path(args.database)
    result=restore_operation(args.operation,books,manifests,backups,db_path) if args.restore else rollback(args.target,args.operation,books,manifests,backups,db_path)
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
