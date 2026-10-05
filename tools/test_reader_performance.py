#!/usr/bin/env python3
import json,tempfile,unittest
from pathlib import Path

import library_db

class ReaderPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old_db=library_db.DB_PATH;self.old_local=library_db.LOCAL_ROOT
        library_db.LOCAL_ROOT=Path(self.temp.name);library_db.DB_PATH=library_db.LOCAL_ROOT/"library.sqlite3";db=library_db.connect()
        sentences=[{"id":f"s-{i}","text":f"Sentence {i}.","start":i,"end":i+.8,"page":1,"words":[{"text":"Sentence","start":i,"end":i+.4},{"text":str(i),"start":i+.4,"end":i+.8}]} for i in range(205)]
        book={"id":"book","title":"Book","duration":205,"audio":"/books/a.mp3","sentences":sentences}
        db.execute("INSERT INTO books(id,title,series,source_path,data_json,quality_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",("book","Book","S","S/B",json.dumps(book),"{}","x","x"));db.commit();db.close()

    def tearDown(self):library_db.DB_PATH=self.old_db;library_db.LOCAL_ROOT=self.old_local;self.temp.cleanup()

    def test_manifest_excludes_word_timings(self):
        result=library_db.get_book_manifest("book");self.assertEqual(result["book"]["sentenceCount"],205);self.assertEqual(result["book"]["chunkCount"],3);self.assertNotIn("words",result["book"]["sentences"][0]);self.assertEqual(result["book"]["sentences"][0]["wordCount"],2)

    def test_chunks_return_bounded_full_sentences(self):
        first=library_db.get_book_chunk("book",0);last=library_db.get_book_chunk("book",2)
        self.assertEqual(len(first["sentences"]),library_db.BOOK_CHUNK_SIZE);self.assertIn("words",first["sentences"][0]);self.assertEqual(len(last["sentences"]),45)

if __name__=="__main__":unittest.main()
