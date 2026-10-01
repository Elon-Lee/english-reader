#!/usr/bin/env python3
import unittest

from timed_segmentation import dedupe_caption_words,segment_timed_words

class TimedSegmentationTests(unittest.TestCase):
    def test_rolling_captions_are_deduplicated(self):
        entries=[
          {"start":0,"end":2,"text":"hate being alone this time of year"},
          {"start":1.5,"end":3.5,"text":"being alone this time of year next"},
          {"start":3.2,"end":5,"text":"time of year next thing you know"},
        ]
        words,report=dedupe_caption_words(entries,automatic=True)
        text=" ".join(item["text"] for item in words).lower()
        self.assertEqual(text,"hate being alone this time of year next thing you know")
        self.assertGreaterEqual(report["deduplicatedWords"],7)

    def test_long_pause_is_always_a_sentence_boundary(self):
        words=[
          {"text":"increase","start":0,"end":.5},
          {"text":"your","start":.55,"end":.9},
          {"text":"vocabulary","start":.95,"end":1.5},
          {"text":"one","start":4.2,"end":4.5},
          {"text":"challenge","start":4.55,"end":5.1},
        ]
        sentences,report=segment_timed_words(words)
        self.assertEqual([item["text"] for item in sentences],["increase your vocabulary","one challenge"])
        self.assertEqual(report["internalPausesOver08"],0)
        self.assertEqual(report["sentenceOverlaps"],0)

    def test_word_and_sentence_timeline_is_monotonic(self):
        words=[
          {"text":"hello","start":0,"end":1.2},
          {"text":"world","start":.7,"end":1.5,"breakAfter":True},
          {"text":"again","start":1.4,"end":2},
        ]
        sentences,report=segment_timed_words(words)
        flattened=[word for sentence in sentences for word in sentence["words"]]
        self.assertTrue(all(right["start"]>=left["end"] for left,right in zip(flattened,flattened[1:])))
        self.assertEqual(report["sentenceOverlaps"],0)

    def test_clause_starter_moves_to_next_sentence(self):
        words=[];time=0
        for text in "you want to read at the right level to learn if it is too easy you will learn little".split():
            words.append({"text":text,"start":time,"end":time+.18,"satBoundaryProbability":.25 if text=="learn" else .01});time+=.24
        sentences,_=segment_timed_words(words,profile="youtube-auto")
        text=[item["text"] for item in sentences]
        self.assertTrue(any(item.endswith("learn") for item in text),text)
        self.assertTrue(any(item.startswith("if ") for item in text),text)
        self.assertFalse(any(item.endswith(" if") for item in text),text)

    def test_preposition_object_phrase_is_not_split(self):
        words=[];time=0
        for text in "or another system that works for you this is also useful".split():
            end=time+.18;words.append({"text":text,"start":time,"end":end,"satBoundaryProbability":.7 if text=="you" else .01});time=end+(.95 if text=="for" else .06)
        sentences,_=segment_timed_words(words,profile="youtube-auto")
        text=[item["text"] for item in sentences]
        self.assertTrue(any("works for you" in item for item in text),text)
        self.assertFalse(any(item.endswith("works for") for item in text),text)

if __name__=="__main__":unittest.main()
