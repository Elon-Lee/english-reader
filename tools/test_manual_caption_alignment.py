#!/usr/bin/env python3
"""Manual captions route through acoustic alignment, never uniform word timing."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from manual_caption_alignment import MODEL_FILE,caption_cues,fallback_windows
from saas_imports import WorkspaceImportService


class ManualCaptionTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.subtitle=self.root/"manual.srt"
        self.subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello world.\n\n2\n00:00:02,000 --> 00:00:03,000\nWrong text.\n")
        self.python=self.root/"python";self.python.touch()
        checkpoint=self.root/"hub/checkpoints"/MODEL_FILE;checkpoint.parent.mkdir(parents=True);checkpoint.touch()
        self.service=object.__new__(WorkspaceImportService);self.service.ffmpeg=Path("ffmpeg")
        environment=patch.dict("os.environ",{"SHIYUE_CTC_PYTHON":str(self.python),"SHIYUE_CTC_MODEL_HOME":str(self.root)})
        environment.start();self.addCleanup(environment.stop)

    def result(self,accepted=(0,1)):
        cues=caption_cues(self.subtitle,4)
        return {"cues":cues,"aligned":[{"index":c["index"],"words":[{**w,"start":c["start"]+.1+i*.3,"end":c["start"]+.35+i*.3,"confidence":.9,"timingSource":"manual-caption-ctc","estimated":False} for i,w in enumerate(c["words"])]} for c in cues if c["index"] in accepted],"rejected":[{"index":c["index"],"reason":"mismatch"} for c in cues if c["index"] not in accepted]}

    def write_result(self,data):
        def run(command,*args):
            Path(command[command.index("--output")+1]).write_text(json.dumps(data))
        return run

    def test_verified_manual_captions_skip_whisper_and_keep_acoustic_times(self):
        with patch.object(self.service,"_run_speech_process",side_effect=self.write_result(self.result())),patch.object(self.service,"_transcribe_video_audio") as transcribe:
            result,report=self.service._manual_caption_book(self.root/"audio.wav",self.subtitle,self.root,4,None)
        transcribe.assert_not_called()
        sentences,timing=result
        self.assertEqual([s["text"] for s in sentences],["Hello world.","Wrong text."])
        self.assertEqual(sentences[0]["words"][0]["start"],.1)
        self.assertEqual(timing["wordTimingSources"],{"manual-caption-ctc":4})
        self.assertEqual(report["status"],"aligned");self.assertEqual(report["fallbackMode"],"none")

    def test_mismatched_manual_text_falls_back_without_inserting_unheard_words(self):
        with patch.object(self.service,"_run_speech_process",side_effect=self.write_result(self.result((0,)))):
            result,report=self.service._manual_caption_book(self.root/"audio.wav",self.subtitle,self.root,4,None)
        self.assertIsNone(result);self.assertEqual(report["reason"],"caption_audio_mismatch")

    def test_only_failed_cue_uses_asr_and_absolute_offsets_are_restored(self):
        self.subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello beautiful world.\n\n2\n00:00:02,000 --> 00:00:03,000\nWrong.\n")
        transcript={"transcription":[{"text":"Actual.","offsets":{"from":300,"to":800},"tokens":[]}]}
        with patch.object(self.service,"_run_speech_process",side_effect=self.write_result(self.result((0,)))),patch.object(self.service,"_transcribe_video_audio",return_value=transcript) as transcribe,patch("saas_imports.subprocess.run") as ffmpeg:
            result,report=self.service._manual_caption_book(self.root/"audio.wav",self.subtitle,self.root,10,None)
        self.assertEqual(transcribe.call_count,1);self.assertEqual(ffmpeg.call_count,1)
        words=[w for s in result[0] for w in s["words"]]
        self.assertEqual([w["text"] for w in words],["Hello","beautiful","world","Actual"])
        self.assertEqual(words[-1]["start"],2)
        self.assertEqual(report["fallbackMode"],"windows")
        self.assertEqual(report["fallbackCues"],1)

    def test_missing_runtime_falls_back_instead_of_failing_import(self):
        self.python.unlink()
        with patch.object(self.service,"_run_speech_process") as run:
            result,report=self.service._manual_caption_book(self.root/"audio.wav",self.subtitle,self.root,4,None)
        run.assert_not_called();self.assertIsNone(result)
        self.assertEqual(report["reason"],"aligner_unavailable")

    def test_many_rejected_windows_use_one_asr_pass_and_keep_verified_captions(self):
        entries=["1\n00:00:00,000 --> 00:00:12,000\n"+" ".join(["Hello"]*27)+"."]
        entries.extend(f"{i+2}\n00:00:{20+i*3:02},000 --> 00:00:{21+i*3:02},000\nWrong." for i in range(9))
        self.subtitle.write_text("\n\n".join(entries))
        transcript={"transcription":[{"text":"Actual.","offsets":{"from":20100,"to":20800},"tokens":[]}]}
        with patch.object(self.service,"_run_speech_process",side_effect=self.write_result(self.result((0,)))),patch.object(self.service,"_transcribe_video_audio",return_value=transcript) as transcribe,patch("saas_imports.subprocess.run") as ffmpeg:
            result,report=self.service._manual_caption_book(self.root/"audio.wav",self.subtitle,self.root,100,None)
        self.assertEqual(transcribe.call_count,1);ffmpeg.assert_not_called()
        self.assertEqual(report["fallbackMode"],"full")
        words=[w for s in result[0] for w in s["words"]]
        self.assertEqual(sum(w["text"]=="Hello" for w in words),27)
        self.assertIn("Actual",[w["text"] for w in words]);self.assertNotIn("Wrong",[w["text"] for w in words])

    def test_invalid_or_estimated_caption_times_cannot_bypass_whisper(self):
        for invalid in ({"start":float("nan")},{"start":2,"end":3},{"estimated":True},{"timingSource":"segment-estimate"}):
            with self.subTest(invalid=invalid):
                data=self.result()
                for item in data["aligned"]:item["words"][0].update(invalid)
                with patch.object(self.service,"_run_speech_process",side_effect=self.write_result(data)):
                    result,report=self.service._manual_caption_book(self.root/"audio.wav",self.subtitle,self.root,4,None)
                self.assertIsNone(result);self.assertEqual(report["reason"],"caption_audio_mismatch")

    def test_broken_aligner_falls_back(self):
        with patch.object(self.service,"_run_speech_process",side_effect=OSError("unavailable")):
            result,report=self.service._manual_caption_book(self.root/"audio.wav",self.subtitle,self.root,4,None)
        self.assertIsNone(result);self.assertEqual(report["reason"],"alignment_failed")

    def test_fallback_windows_are_bounded_merged_and_do_not_remove_gaps(self):
        cues=[{"index":0,"start":0,"end":1},{"index":1,"start":1.1,"end":2},{"index":2,"start":50,"end":51}]
        windows=fallback_windows(cues,{0,1,2},51)
        self.assertEqual(windows,[{"start":0,"end":2.3,"indices":[0,1]},{"start":49.7,"end":51,"indices":[2]}])

    def test_overlapping_caption_display_windows_reject_fast_path(self):
        self.subtitle.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello world.\n\n2\n00:00:01,000 --> 00:00:03,000\nRolling captions.\n")
        with self.assertRaisesRegex(ValueError,"overlapping"):caption_cues(self.subtitle,4)


if __name__=="__main__":unittest.main()
