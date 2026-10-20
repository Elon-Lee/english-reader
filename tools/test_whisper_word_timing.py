#!/usr/bin/env python3
"""Regression coverage for imported media word timing (no model/database needed)."""
import unittest
from pathlib import Path

from align_whisper import whisper_words
from build_video_book import whisper_book
from saas_imports import WorkspaceImportService
from import_worker import offset_whisper
from timed_segmentation import normalize_word_timeline


def token(text,start,end,dtw=-1,p=.9):
    return {"text":text,"offsets":{"from":start,"to":end},"t_dtw":dtw,"p":p}


def segment(text,tokens,start=0,end=2000):
    return {"text":text,"offsets":{"from":start,"to":end},"tokens":tokens}


class WhisperWordTimingTests(unittest.TestCase):
    def test_real_sentence_eleven_keeps_dtw_despite_six_seconds_of_offset_drift(self):
        # Actual whisper.cpp output from the 2026-10-20 import. The source
        # subtitle places this complete sentence at 44.18-49.74s, followed by
        # silence until 55.70s. Heuristic offsets stretch into that silence.
        rows=[
            (" These",44640,45540,45190,45540,4456),
            (" videos",45540,46630,45540,46630,4498),
            (" build",46630,47530,46630,47530,4534),
            (" one",47530,48140,47530,47740,4582),
            (" on",48140,48430,48140,48430,4608),
            (" top",48430,48970,48430,48970,4628),
            (" of",48970,49330,48970,49330,4644),
            (" the",49330,49870,49330,49870,4656),
            (" next,",49870,50980,49870,50300,4674),
            (" so",50980,51310,50980,51310,4728),
            (" click",51310,52210,51310,52210,4756),
            (" here",52210,52930,52210,52930,4778),
            (" to",52930,53290,52930,53290,4800),
            (" watch",53290,54220,53290,54110,4824),
            (" video",54220,55090,54220,55090,4874),
            (" 1.",55090,56280,55090,55580,4932),
        ]
        segments=[]
        for text,start,end,left,right,dtw in rows:
            tokens=[token(text.rstrip(",."),left,right,dtw)]
            if text.endswith(","):tokens.append(token(",",50930,50950,4716))
            if text.endswith("."):tokens.append(token(".",55620,56130,4988))
            segments.append(segment(text,tokens,start,end))
        sentences,report=whisper_book({"transcription":segments})
        self.assertEqual(len(sentences),1)
        self.assertEqual(sentences[0]["text"],"These videos build one on top of the next, so click here to watch video 1.")
        self.assertEqual((sentences[0]["start"],sentences[0]["end"]),(44.56,49.88))
        words=sentences[0]["words"]
        self.assertEqual(next(w["start"] for w in words if w["text"]=="on"),46.08)
        self.assertEqual(next(w["start"] for w in words if w["text"]=="click"),47.56)
        self.assertEqual(report["wordTimingSources"],{"whisper-dtw":16})
        self.assertEqual(report["timingVersion"],3)

    def test_dtw_centiseconds_group_contractions_subwords_and_punctuation(self):
        data={"transcription":[segment(" It's professional.",[
            token(" It",0,200,20),token("'s",200,300,28),
            token(" pro",300,600,38),token("fessional",600,1200,60),
            token(".",1200,2000,124)])]}
        words=whisper_words(data)
        self.assertEqual([(w["text"],w["start"],w["end"]) for w in words],[("It's",.2,.38),("professional",.38,1.24)])
        self.assertTrue(all(w["timingSource"]=="whisper-dtw" and not w["estimated"] for w in words))

    def test_token_offsets_are_used_when_dtw_disabled(self):
        words=whisper_words({"transcription":[segment("a professional.",[
            token("a",100,180),token(" professional",200,1300),token(".",1300,2000)])]})
        self.assertEqual([(w["start"],w["end"]) for w in words],[(.1,.18),(.2,1.3)])
        self.assertEqual(words[0]["timingSource"],"whisper-token")

    def test_real_shared_punctuation_anchor_does_not_revert_preceding_words(self):
        # Another region in the same full video: "words," and the comma have
        # the same DTW point. Reverting the whole word previously propagated
        # backward through this sentence, shifting its first word by 990ms.
        sentences,report=whisper_book({"transcription":[
            segment(" I",[token(" I",814790,814860,81578)],814790,814860),
            segment(" content",[token(" content",818190,818850,81906)],818190,818850),
            segment(" words,",[token(" words",818850,819340,81944),token(",",819530,819530,81944)],818850,819580),
            segment(" but",[token(" but",819580,819820,81990)],819580,819820),
            segment(" let's",[token(" let",819820,820160,82008),token("'s",820220,820320,82030)],819820,820320),
        ]})
        words=[w for s in sentences for w in s["words"]]
        self.assertEqual([w["start"] for w in words],[815.78,819.06,819.44,819.9,820.08])
        self.assertEqual(next(w["end"] for w in words if w["text"]=="words"),819.9)
        self.assertEqual(report["wordTimingSources"],{"whisper-dtw":5})

    def test_collapsed_dtw_region_falls_back_without_tiny_or_reversed_words(self):
        sentences,report=whisper_book({"transcription":[
            segment(" private",[token(" private",8760,9320,952)],8760,9320),
            segment(" place.",[token(" place",9320,9650,1008),token(".",9820,9920,1008)],9320,10110)]})
        words=[w for s in sentences for w in s["words"]]
        self.assertEqual([(w["start"],w["end"]) for w in words],[(8.76,9.32),(9.32,9.65)])
        self.assertEqual(report["timestampMethod"],"token-offsets")

    def test_missing_tokens_and_shared_tokens_are_explicit_estimates(self):
        for tokens in ([],[token("Hello world",0,2000)]):
            sentences,report=whisper_book({"transcription":[segment("Hello world",tokens)]})
            self.assertEqual(report["timestampMethod"],"segment-estimate")
            self.assertTrue(all(w["estimated"] for s in sentences for w in s["words"]))

    def test_chunk_local_token_offsets_are_not_applied_to_global_segments(self):
        words=whisper_words({"transcription":[segment("Hello",[token("Hello",0,500)],start=10000,end=10500)]})
        self.assertEqual(words[0]["start"],10)
        self.assertTrue(words[0]["estimated"])

    def test_spoken_music_survives_but_noise_label_is_removed(self):
        words=whisper_words({"transcription":[segment("[Music]",[]),segment("I love music.",[])]})
        self.assertEqual([w["text"] for w in words],["I","love","music"])

    def test_tiny_intervals_do_not_accumulate_thirty_ms_drift(self):
        words=[{"text":"a","start":i*.01,"end":i*.01+.1} for i in range(100)]
        normalize_word_timeline(words)
        self.assertEqual(words[-1]["start"],.99)
        self.assertTrue(all(a["end"]<=b["start"] for a,b in zip(words,words[1:])))

    def test_overlap_trimming_preserves_next_onset_and_long_measured_word(self):
        words=[{"text":"slow","start":0,"end":2,"timingSource":"whisper-dtw"},
               {"text":"word","start":1.8,"end":3.5,"timingSource":"whisper-token"}]
        normalize_word_timeline(words)
        self.assertEqual(words[0]["end"],1.8)
        self.assertEqual(words[1]["start"],1.8)
        self.assertEqual(words[1]["end"],3.5)

    def test_equal_reversed_and_zero_intervals_stay_positive_and_do_not_overlap(self):
        words=[{"text":"a","start":s,"end":e} for s,e in [(1,1),(1,1),(0,.1),(1.002,1.002)]]
        normalize_word_timeline(words)
        self.assertTrue(all(w["end"]>w["start"] for w in words))
        self.assertTrue(all(a["end"]<=b["start"] for a,b in zip(words,words[1:])))

    def test_media_duration_excludes_hallucinations_after_end(self):
        sentences,report=whisper_book({"transcription":[segment("Hello",[],0,2000),segment("Ghost",[],3000,4000)]},media_duration=1.5)
        self.assertEqual([s["text"] for s in sentences],["Hello"])
        self.assertLessEqual(sentences[-1]["end"],1.5)
        self.assertEqual(report["wordsOutsideMedia"],1)

    def test_part_merge_offsets_tokens_and_dtw_in_their_own_units(self):
        data={"transcription":[segment("Hi",[token("Hi",100,200,10),token("[_END_]",-1,-1)])]}
        merged=offset_whisper(data,10.25)["transcription"][0]
        self.assertEqual(merged["offsets"]["from"],10250)
        self.assertEqual(merged["tokens"][0]["offsets"],{"from":10350,"to":10450})
        self.assertEqual(merged["tokens"][0]["t_dtw"],1035)
        self.assertEqual(merged["tokens"][1]["t_dtw"],-1)
        self.assertEqual(merged["tokens"][1]["offsets"],{"from":-1,"to":-1})

    def test_import_arguments_enable_dtw_and_preserve_absolute_token_times(self):
        service=object.__new__(WorkspaceImportService);service.whisper_cli=Path("whisper-cli")
        for model,preset in [("ggml-base.en.bin","base.en"),("ggml-small.en-q5_1.bin","small.en"),("ggml-large-v3-turbo.bin","large.v3.turbo"),("custom.bin",None)]:
            service.whisper_model=Path(model)
            command=service._whisper_command(Path("source.wav"),Path("output"),True)
            self.assertEqual(command[command.index("-p")+1],"1")
            self.assertIn("-nfa",command);self.assertIn("-pp",command)
            if preset:self.assertEqual(command[command.index("-dtw")+1],preset)
            else:self.assertNotIn("-dtw",command)


if __name__=="__main__":unittest.main()
