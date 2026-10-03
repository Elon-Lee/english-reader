#!/usr/bin/env python3
import tempfile,unittest
from pathlib import Path

from build_video_book import attach_chinese,original_cue_book,subtitle_entries

SRT_EN="""1
00:00:00,000 --> 00:00:02,000
First English cue.

2
00:00:02,000 --> 00:00:04,000
Second cue stays separate.
"""
SRT_ZH="""1
00:00:00,000 --> 00:00:02,000
第一条中文字幕。

2
00:00:02,000 --> 00:00:04,000
第二条中文字幕。
"""

class YoutubeOriginalCueTests(unittest.TestCase):
    def test_preserves_english_cues_and_attaches_chinese(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);english=root/"en.srt";chinese=root/"zh.srt";english.write_text(SRT_EN);chinese.write_text(SRT_ZH)
            en=subtitle_entries(english);zh=subtitle_entries(chinese,False);sentences,report=original_cue_book(en);translation=attach_chinese(sentences,zh)
            self.assertEqual(len(sentences),2);self.assertEqual(report["inputCues"],2);self.assertTrue(report["originalCueBoundariesPreserved"])
            self.assertEqual([item["text"] for item in sentences],["First English cue.","Second cue stays separate."])
            self.assertEqual([item["translation"] for item in sentences],["第一条中文字幕。","第二条中文字幕。"])
            self.assertEqual(translation["coverage"],1.0)

if __name__=="__main__":unittest.main()
