#!/usr/bin/env python3
import gzip,json,sqlite3,tempfile,unittest
from pathlib import Path

from deployment.remote_apply import apply_bundle

class DeploymentGrammarContentTests(unittest.TestCase):
    def test_content_bundle_replaces_sentence_grammar(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);database=root/"library.sqlite3";bundle=root/"content.json.gz"
            book={"id":"book-1","title":"Book","english_title":"","series":"Test","level":"","source_path":"Test/Book","status":"ready","cover_url":"","page_base_url":"","audio_url":"","pdf_url":"","duration":1,"alignment":"","data_json":json.dumps({"id":"book-1","title":"Book","sentences":[]}),"quality_json":"{}","created_at":"2026-10-02T00:00:00+08:00","updated_at":"2026-10-02T00:00:00+08:00","last_read_at":None,"source_type":"book","video_url":"","subtitle_type":""}
            payload={"revision":"content-test","books":[book],"book_artifacts":[],"dictionary_entries":[],"sentence_grammar":[{"book_id":"book-1","sentence_id":"sentence-1","sentence_hash":"hash","analysis_json":json.dumps({"sentenceType":"简单句"},ensure_ascii=False),"model":"test","updated_at":"2026-10-02T00:00:00+08:00"}]}
            with gzip.open(bundle,"wt",encoding="utf-8") as output:json.dump(payload,output,ensure_ascii=False)
            result=apply_bundle(bundle,database)
            db=sqlite3.connect(database);row=db.execute("SELECT sentence_id,model FROM sentence_grammar").fetchone();db.close()
            self.assertEqual(result["revision"],"content-test")
            self.assertEqual(row,("sentence-1","test"))

if __name__=="__main__":unittest.main()
