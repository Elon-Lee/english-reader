#!/usr/bin/env python3
import unittest
from pathlib import Path

from import_source_plan import exact_title_match_level,select_pdf_ocr_fallback_text,title_match_score

class ImportSourcePlanTests(unittest.TestCase):
    def test_exact_pdf_name_beats_bilingual_edition(self):
        book="3.01.上.01.弗兰肯斯坦"
        self.assertEqual(exact_title_match_level(book,"弗兰肯斯坦.pdf"),3)
        self.assertEqual(exact_title_match_level(book,"3A_01.弗兰肯斯坦中英对照.pdf"),0)

    def test_chinese_and_english_exact_aliases(self):
        book="3.02.上.02.野性的呼唤.The.Call.Of.The.Wild"
        self.assertEqual(exact_title_match_level(book,"野性的呼唤.pdf"),3)
        self.assertEqual(exact_title_match_level(book,"The Call of the Wild.docx"),2)

    def test_one_character_translation_variant_is_relaxed_match(self):
        self.assertEqual(exact_title_match_level("3.08.上.08.铁道少年","铁路少年.pdf"),0)
        self.assertGreaterEqual(title_match_score("3.08.上.08.铁道少年","铁路少年.pdf"),75)

    def test_pdf_ocr_failure_prefers_exact_doc(self):
        source=Path("books/牛津书虫全系列7级（3）/3.01.上.01.弗兰肯斯坦")
        path,paragraphs,words,reason=select_pdf_ocr_fallback_text(source,5206.534*2.4)
        self.assertEqual(path.name,"弗兰肯斯坦.docx")
        self.assertEqual(reason,"书名完全一致 DOC/DOCX")
        self.assertGreater(words,9000)
        self.assertGreater(len(paragraphs),200)

if __name__=="__main__":unittest.main()
