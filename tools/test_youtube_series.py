#!/usr/bin/env python3
import unittest

from library_db import normalize_youtube_series

class YoutubeSeriesTests(unittest.TestCase):
    def test_ted_uses_existing_display_name(self):
        self.assertEqual(normalize_youtube_series("TED"),"Ted")

    def test_tedx_channels_are_grouped(self):
        self.assertEqual(normalize_youtube_series("TEDx Talks"),"TEDx Talks")
        self.assertEqual(normalize_youtube_series("TEDxStanford"),"TEDx Talks")

    def test_regular_channel_is_preserved(self):
        self.assertEqual(normalize_youtube_series("Rachel's   English"),"Rachel's English")

    def test_empty_channel_falls_back(self):
        self.assertEqual(normalize_youtube_series(""),"YouTube")

if __name__=="__main__":unittest.main()
