#!/usr/bin/env python3
"""Apply an exported content bundle while preserving remote learning data."""
import gzip,json,sys
from pathlib import Path

def apply_bundle(bundle,db_path,preserve_removed_learning=False):
    bundle=Path(bundle);db_path=Path(db_path);db_path.parent.mkdir(parents=True,exist_ok=True)
    tools_root=Path(__file__).resolve().parents[1]
    if str(tools_root) not in sys.path:sys.path.insert(0,str(tools_root))
    import library_db
    library_db.DB_PATH=db_path;library_db.LOCAL_ROOT=db_path.parent
    db=library_db.connect();payload=json.loads(gzip.open(bundle,"rt",encoding="utf-8").read());book_ids=[row["id"] for row in payload["books"]]
    db.execute("BEGIN")
    try:
        for row in payload["books"]:
            columns=list(row);marks=",".join("?" for _ in columns);updates=",".join(f"{c}=excluded.{c}" for c in columns if c!="id")
            db.execute(f"INSERT INTO books({','.join(columns)}) VALUES({marks}) ON CONFLICT(id) DO UPDATE SET {updates}",[row[c] for c in columns])
        if book_ids:
            marks=",".join("?" for _ in book_ids);removed=[row[0] for row in db.execute(f"SELECT id FROM books WHERE id NOT IN ({marks})",book_ids)]
        else:removed=[row[0] for row in db.execute("SELECT id FROM books")]
        for book_id in removed:
            if not preserve_removed_learning:
                db.execute("DELETE FROM vocabulary WHERE book_id=?",(book_id,));db.execute("DELETE FROM word_annotations WHERE book_id=?",(book_id,))
            db.execute("DELETE FROM book_artifacts WHERE book_id=?",(book_id,));db.execute("DELETE FROM books WHERE id=?",(book_id,))
        db.execute("DELETE FROM book_artifacts")
        for row in payload["book_artifacts"]:db.execute("INSERT INTO book_artifacts(book_id,kind,data_json,created_at) VALUES(?,?,?,?)",(row["book_id"],row["kind"],row["data_json"],row["created_at"]))
        db.execute("DELETE FROM dictionary_entries")
        for row in payload["dictionary_entries"]:db.execute("INSERT INTO dictionary_entries(surface,entry_json,updated_at) VALUES(?,?,?)",(row["surface"],row["entry_json"],row["updated_at"]))
        db.commit()
    except Exception:
        db.rollback();raise
    finally:db.close()
    return {"status":"ok","books":len(book_ids),"revision":payload["revision"]}

if __name__=="__main__":
    result=apply_bundle(sys.argv[1],sys.argv[2],"--preserve-learning" in sys.argv[3:])
    print(json.dumps(result,ensure_ascii=False))
