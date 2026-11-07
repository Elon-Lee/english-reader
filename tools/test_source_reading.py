import unittest
from source_reading import validate_source_location
from saas_auth import SaaSError


class SourceLocationTests(unittest.TestCase):
    def test_pdf_accepts_actual_blank_page_and_rejects_out_of_bounds(self):
        data={'readingDocument':{'format':'pdf','blocks':[{'page':1},{'page':3}]},'import':{'extractor':{'pages':4}}}
        self.assertEqual(validate_source_location(data,{'format':'pdf','page':2}),{'format':'pdf','page':2})
        for page in [0,-1,5,'2',True]:
            with self.assertRaises(SaaSError):validate_source_location(data,{'format':'pdf','page':page})

    def test_epub_positions_require_a_valid_source_index_and_bounded_offsets(self):
        data={'readingDocument':{'format':'epub','source':{'spine':[{'href':'original.xhtml'}]}}}
        location={'format':'epub','chapter':0,'offset':18}
        self.assertEqual(validate_source_location(data,location),location)
        for invalid in [None,{}, {'format':'epub','chapter':1,'offset':0},{'format':'epub','chapter':0,'offset':-1},{'format':'epub','chapter':False,'offset':0},{'format':'pdf','page':1}]:
            with self.assertRaises(SaaSError):validate_source_location(data,invalid)
        with self.assertRaises(SaaSError):validate_source_location({'readingDocument':{'format':'epub'}},location)
