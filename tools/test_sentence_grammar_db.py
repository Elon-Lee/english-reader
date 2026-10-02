#!/usr/bin/env python3
import tempfile,unittest
from pathlib import Path

import library_db

class SentenceGrammarDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old_db=library_db.DB_PATH;self.old_local=library_db.LOCAL_ROOT
        library_db.LOCAL_ROOT=Path(self.temp.name);library_db.DB_PATH=library_db.LOCAL_ROOT/"library.sqlite3";library_db.connect().close()

    def tearDown(self):
        library_db.DB_PATH=self.old_db;library_db.LOCAL_ROOT=self.old_local;self.temp.cleanup()

    def test_analysis_is_invalidated_when_sentence_text_changes(self):
        saved=library_db.save_sentence_grammar("book","sentence","She reads.",{"sentenceType":"简单句"},"test-model")
        self.assertEqual(saved["sentenceType"],"简单句")
        self.assertIsNotNone(library_db.get_sentence_grammar("book","sentence","She reads."))
        self.assertIsNone(library_db.get_sentence_grammar("book","sentence","She read."))

if __name__=="__main__":unittest.main()
