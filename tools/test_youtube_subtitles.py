#!/usr/bin/env python3
import unittest

from build_video_book import attach_chinese
from youtube_subtitles import has_translated_english_track,json3_to_srt,preferred_json3_entry,select_chinese_track,select_native_english_track

class YoutubeSubtitleTests(unittest.TestCase):
    def test_manual_nonstandard_english_code_is_selected(self):
        info={"subtitles":{"en-owner-id":[{"url":"https://x.test/t?lang=en"}]},"automatic_captions":{"en":[{"url":"https://x.test/t?kind=asr&lang=en"}]}}
        track=select_native_english_track(info);self.assertEqual(track["source"],"manual");self.assertEqual(track["code"],"en-owner-id")

    def test_native_auto_en_orig_beats_translated_en(self):
        info={"automatic_captions":{"en":[{"url":"https://x.test/t?kind=asr&lang=ar&tlang=en"}],"en-orig":[{"url":"https://x.test/t?kind=asr&lang=en"}]}}
        track=select_native_english_track(info);self.assertEqual(track["source"],"automatic");self.assertEqual(track["code"],"en-orig");self.assertTrue(has_translated_english_track(info))

    def test_only_translated_english_is_rejected(self):
        info={"automatic_captions":{"en":[{"url":"https://x.test/t?kind=asr&lang=ja&tlang=en"}]}}
        self.assertIsNone(select_native_english_track(info));self.assertTrue(has_translated_english_track(info))

    def test_native_manual_en_is_accepted(self):
        info={"subtitles":{"en":[{"url":"https://x.test/t?lang=en"}]}}
        self.assertEqual(select_native_english_track(info)["source"],"manual")

    def test_manual_simplified_chinese_is_preferred(self):
        info={"subtitles":{"zh-CN":[{"url":"https://x.test/t?lang=zh-CN"}]},"automatic_captions":{"zh-Hans":[{"url":"https://x.test/t?lang=en&tlang=zh-Hans"}]}}
        track=select_chinese_track(info);self.assertEqual(track["source"],"manual");self.assertEqual(track["code"],"zh-CN");self.assertFalse(track["translated"])

    def test_translated_chinese_is_last_resort(self):
        info={"automatic_captions":{"zh-Hans":[{"url":"https://x.test/t?lang=en&tlang=zh-Hans"}]}}
        track=select_chinese_track(info);self.assertEqual(track["source"],"translated");self.assertTrue(track["translated"])

    def test_preferred_translation_entry_uses_english_json3(self):
        track={"entries":[{"ext":"srv1","url":"https://x.test/t?lang=en&tlang=zh-Hans"},{"ext":"json3","url":"https://x.test/t?lang=ar&tlang=zh-Hans"},{"ext":"json3","url":"https://x.test/t?lang=en&tlang=zh-Hans"}]}
        entry=preferred_json3_entry(track);self.assertIn("lang=en",entry["url"])

    def test_json3_translation_is_converted_to_srt(self):
        payload={"events":[{"tStartMs":250,"dDurationMs":1500,"segs":[{"utf8":"你好"},{"utf8":"，世界"}]},{"tStartMs":2000,"dDurationMs":900,"segs":[{"utf8":"下一句"}]}]}
        result=json3_to_srt(payload);self.assertIn("00:00:00,250 --> 00:00:01,750",result);self.assertIn("你好，世界",result);self.assertIn("下一句",result)

    def test_original_youtube_cues_use_one_exact_translation_each(self):
        sentences=[{"id":"a","start":.2,"end":2.8,"cueStart":0,"cueEnd":6.2},{"id":"b","start":3,"end":6,"cueStart":3.12,"cueEnd":9.68},{"id":"c","start":6.3,"end":9,"cueStart":6.2,"cueEnd":13.84}]
        translations=[{"start":0,"end":6.2,"text":"第一句"},{"start":3.12,"end":9.68,"text":"第二句"},{"start":6.2,"end":13.84,"text":"第三句"}]
        report=attach_chinese(sentences,translations)
        self.assertEqual([item["translation"] for item in sentences],["第一句","第二句","第三句"]);self.assertEqual(report["method"],"youtube-original-cue-start")

if __name__=="__main__":unittest.main()
