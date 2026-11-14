"""Narration boundaries must remain truthful and independent of model installation."""
import copy
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kokoro_speech import attach_timing, options, reader_speech, validate_request
from kokoro_worker import word_timing
from saas_auth import SaaSError


class KokoroSpeechTests(unittest.TestCase):
    def test_only_explicit_document_requests_are_accepted(self):
        self.assertIsNone(validate_request(None, 'document', 'a.epub', {}))
        self.assertEqual(validate_request({'engine': 'kokoro'}, 'document', 'a.pdf', {}),
                         {'engine': 'kokoro', 'voice': 'af_heart', 'speed': 1})
        for value, kind, filename, metadata in [
            ({'engine': 'browser'}, 'document', 'a.epub', {}),
            ({'engine': 'kokoro'}, 'text', 'a.txt', {}),
            ({'engine': 'kokoro'}, 'document', 'a.exe', {}),
            ({'engine': 'kokoro'}, 'document', 'a.pdf', {'awaitingAudioUpload': True}),
            ({'engine': 'kokoro'}, 'document', 'a.epub', {'matchedAudioAssetId': 'other'}),
        ]:
            with self.subTest(value=value, kind=kind, filename=filename, metadata=metadata), self.assertRaises(SaaSError):
                validate_request(value, kind, filename, metadata)

    def test_voice_and_speed_are_bounded(self):
        for field, values in {'voice': ['../voice', 'zf_xiaobei', [], None],
                              'speed': [0, 3, True, None, [], 'nan', 'inf']}.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(SaaSError):
                    validate_request({'engine': 'kokoro', field: value}, 'document', 'a.epub', {})

    def test_missing_or_broken_runtime_is_unavailable(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SHIYUE_KOKORO_HOME': folder}):
            self.assertFalse(options()['available'])
            Path(folder, 'ready.json').write_text('null')
            self.assertFalse(options()['available'])

    def test_native_word_prediction_requires_exact_text_and_valid_times(self):
        sentence = {'start': 0, 'end': 2, 'words': [{'text': 'Hello'}, {'text': 'world'}]}
        tokens = [('Hello', .1, .5), (',', None, None), ('world', .6, 1.8)]
        self.assertEqual(len(word_timing(sentence, tokens)), 2)
        for bad in [[('Hello world', .1, 1.8)], [('Hello', .1, .5)],
                    [('Hello', .1, .5), ('world', .4, 1.8)],
                    [('Hello', .1, .5), ('world', .6, math.nan)]]:
            self.assertEqual(word_timing(sentence, bad), [])

    def test_attach_preserves_document_and_marks_predictions(self):
        original = {'sentences': [{'id': 's-1', 'text': 'Hello.', 'words': [{'text': 'Hello'}]}],
                    'readingDocument': {'version': 1, 'blocks': [{'text': 'Hello.'}]}}
        result = {'duration': 1, 'sentences': [{'id': 's-1', 'start': 0, 'end': 1,
                                              'words': [{'text': 'Hello', 'start': .1, 'end': .9}]}]}
        data = attach_timing(copy.deepcopy(original), result, {'voice': 'af_heart', 'speed': 1})
        self.assertEqual(data['readingDocument'], original['readingDocument'])
        self.assertTrue(data['sentences'][0]['words'][0]['estimated'])
        self.assertEqual(reader_speech(data)['language'], 'en-US')
        self.assertIsNone(reader_speech(original))
        for start, end in [(0, 2), (-1, 1), (0, math.nan)]:
            broken = copy.deepcopy(result);broken['sentences'][0].update(start=start, end=end)
            with self.assertRaises(ValueError):
                attach_timing(copy.deepcopy(original), broken, {'voice': 'af_heart', 'speed': 1})


if __name__ == '__main__':
    unittest.main()
