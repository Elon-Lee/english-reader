#!/usr/bin/env python3
import gzip,json,sqlite3,tempfile,unittest
from pathlib import Path

from deployment.remote_apply import apply_bundle

class DeploymentGrammarContentTests(unittest.TestCase):
    def test_content_bundle_replaces_sentence_grammar(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);database=root/"library.sqlite3";bundle=root/"content.json.gz"
            payload={"revision":"content-test","books":[],"book_artifacts":[],"dictionary_entries":[],"sentence_grammar":[{"book_id":"book-1","sentence_id":"sentence-1","sentence_hash":"hash","analysis_json":json.dumps({"sentenceType":"简单句"},ensure_ascii=False),"model":"test","updated_at":"2026-10-02T00:00:00+08:00"}]}
            with gzip.open(bundle,"wt",encoding="utf-8") as output:json.dump(payload,output,ensure_ascii=False)
            result=apply_bundle(bundle,database)
            db=sqlite3.connect(database);row=db.execute("SELECT sentence_id,model FROM sentence_grammar").fetchone();db.close()
            self.assertEqual(result["revision"],"content-test")
            self.assertEqual(row,("sentence-1","test"))

if __name__=="__main__":unittest.main()
