import copy
import unittest

from book_audio_alignment import apply_timings, match_anchors


class BookAlignmentTests(unittest.TestCase):
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
