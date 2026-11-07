import copy
import unittest

from book_audio_alignment import apply_timings, match_anchors, validate_coverage


class BookAlignmentTests(unittest.TestCase):
    def test_truncated_audio_must_not_be_accepted_as_verified_excerpt(self):
        anchors={i:i-3 for i in range(3,903)}
        timings={i:{'start':i/2,'end':i/2+.2} for i in anchors}
        with self.assertRaisesRegex(ValueError,'incomplete'):
            validate_coverage(2098,927,anchors,timings)

    def test_incomplete_second_half_is_also_rejected(self):
        with self.assertRaisesRegex(ValueError,'incomplete'):
            validate_coverage(1000,600,{i:i for i in range(600)},{i:{} for i in range(600)})

    def test_missing_intro_or_ending_is_rejected_even_above_coverage_threshold(self):
        for indices in (range(900),range(100,1000)):
            with self.subTest(indices=indices),self.assertRaisesRegex(ValueError,'incomplete'):
                validate_coverage(1000,900,{i:i for i in indices},{i:{} for i in indices})

    def test_complete_narration_may_leave_isolated_recognition_errors_untimed(self):
        indices=[i for i in range(1000) if i%10!=5]
        self.assertEqual(validate_coverage(1000,950,{i:i for i in indices},{i:{} for i in indices})['validation'],'full-text-coverage')

    def test_short_unspoken_publisher_footer_does_not_reject_complete_original(self):
        indices=range(2075)
        self.assertFalse(validate_coverage(2098,2100,{i:i for i in indices},{i:{} for i in indices})['partialAudio'])

    def test_excerpt_rejects_wrong_sparse_short_or_unmeasured_matches(self):
        cases=[(1000,500,{},{}),
            (1000,20,{i:i for i in range(20)},{i:{} for i in range(20)}),
            (2000,400,{i*4:i for i in range(400)},{i*4:{} for i in range(400)}),
            (1000,100,{i:i for i in range(100)},{i:{} for i in range(30)}),
            (1000,500,{i:i for i in range(100)},{i:{} for i in range(100)})]
        for expected,heard,anchors,timings in cases:
            with self.subTest(expected=expected,heard=heard),self.assertRaises(ValueError):
                validate_coverage(expected,heard,anchors,timings)

    def test_full_book_validation_preserves_existing_short_document_rule(self):
        report=validate_coverage(10,9,{i:i for i in range(8)},{i:{} for i in range(8)})
        self.assertFalse(report['partialAudio'])
        self.assertEqual(report['validation'],'full-text-coverage')

    def test_intro_and_omission_preserve_monotonic_canonical_indices(self):
        expected='CHAPTER ONE THE CITY HEAT WHEN WE GET HOME WE CAN REST'.split()
        heard='A PUBLISHER PRESENTS CHAPTER ONE WHEN WE GET HOME WE CAN REST'.split()
        anchors=match_anchors(expected,heard)
        self.assertEqual([expected[i] for i in anchors],[heard[j] for j in anchors.values()])
        self.assertEqual(list(anchors.values()),sorted(anchors.values()))
        self.assertNotIn(2,anchors)
        self.assertEqual(anchors[5],5)

    def test_single_common_word_cannot_anchor_mismatched_audio(self):
        self.assertEqual(match_anchors(['THE','CAT','SLEPT'],['THE','SUN','ROSE']),{})

    def test_short_documents_require_their_whole_phrase_to_match(self):
        self.assertEqual(match_anchors(['HELLO'],['HELLO']),{0:0})
        self.assertEqual(match_anchors(['HELLO','WORLD'],['HELLO','WORLD']),{0:0,1:1})
        self.assertEqual(match_anchors(['HELLO','WORLD'],['HELLO','THERE']),{})

    def test_canonical_text_ids_and_learning_metadata_are_preserved(self):
        book={'id':'book','sentences':[{'id':'original-id','text':'First missing last.',
            'translation':'译文','words':[{'text':'First'},{'text':'missing','start':99},
                                         {'text':'last'}]},
            {'id':'heading','text':'Unspoken','words':[{'text':'Unspoken'}]}]}
        original=copy.deepcopy(book)
        result=apply_timings(book,[(0,0),(0,1),(0,2),(1,0)],
            {0:{'start':3,'end':4},2:{'start':5,'end':6}})
        self.assertEqual(result['id'],original['id'])
        self.assertEqual(result['sentences'][0]['text'],original['sentences'][0]['text'])
        self.assertEqual(result['sentences'][0]['translation'],'译文')
        self.assertEqual(result['sentences'][0]['start'],3)
        self.assertEqual(result['sentences'][0]['end'],6)
        self.assertNotIn('start',result['sentences'][0]['words'][1])
        self.assertNotIn('start',result['sentences'][1])
        self.assertEqual(result['audioAlignment']['coverage'],.5)
        self.assertTrue(all(not w['estimated'] for s in result['sentences'] for w in s['words']))


if __name__=='__main__':unittest.main()
