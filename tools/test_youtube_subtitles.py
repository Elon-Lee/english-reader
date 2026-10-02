#!/usr/bin/env python3
import unittest

from youtube_subtitles import has_translated_english_track,select_native_english_track

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

if __name__=="__main__":unittest.main()
