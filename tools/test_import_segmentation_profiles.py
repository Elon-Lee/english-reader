#!/usr/bin/env python3
import unittest

from sat_integration import should_use_sat

class ImportSegmentationProfileTests(unittest.TestCase):
    def test_youtube_auto_always_uses_sat(self):
        self.assertEqual(should_use_sat("youtube-auto",[{"text":"hello"}])[0],True)

    def test_speech_asr_always_uses_sat(self):
        self.assertEqual(should_use_sat("speech-asr",[{"text":"hello"}])[0],True)

    def test_trusted_local_subtitle_skips_sat(self):
        words=[{"text":"Hello","punctuationAfter":"."},{"text":"Next","punctuationAfter":"."}]
        self.assertEqual(should_use_sat("local-subtitle",words)[0],False)

    def test_sparse_local_subtitle_uses_sat(self):
        words=[{"text":f"word{i}"} for i in range(100)]
        self.assertEqual(should_use_sat("local-subtitle",words)[0],True)

if __name__=="__main__":unittest.main()
