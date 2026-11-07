import copy
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from reading_document import build_reading_document, reader_document
from saas_auth import SaaSError
from saas_imports import WorkspaceImportService
from saas_workspace import WorkspaceService
from saas_catalog import CatalogService
from book_audio_alignment import apply_timings


class ReadingDocumentTests(unittest.TestCase):
    def test_epub_paragraphs_punctuation_and_word_addresses_survive_segmentation(self):
        text = '🌿 “Hello,” she said.\nAnd then, the original paragraph continues!'
        sentences, document = build_reading_document([{'type': 'heading', 'text': 'Chapter One', 'section': 'a'}, {'type': 'paragraph', 'text': text, 'section': 'a'}], 'epub')
        self.assertEqual(document['pagination'], 'reflow')
        self.assertEqual(document['blocks'][1]['text'], text)
        by_id = {sentence['id']: sentence for sentence in sentences}
        for block in document['blocks']:
            for word in block['words']:
                self.assertEqual(block['text'][word['start']:word['end']], by_id[word['sentenceId']]['words'][word['wordIndex']]['text'])

    def test_long_paragraphs_keep_original_punctuation_after_learning_sentence_splits(self):
        text = ', '.join(['natural wording and punctuation'] * 40) + '!'
        sentences, document = build_reading_document([{'type': 'paragraph', 'text': text}], 'epub')
        self.assertGreater(len(sentences), 1)
        self.assertEqual(document['blocks'][0]['text'], text)
        self.assertEqual(len(document['blocks'][0]['words']), sum(len(s['words']) for s in sentences))

    def test_pdf_page_numbers_are_independent_of_reflow_and_empty_pages(self):
        sentences, document = build_reading_document([{'type': 'paragraph', 'text': 'First original page.', 'page': 1}, {'type': 'paragraph', 'text': 'Third original page.', 'page': 3}], 'pdf')
        self.assertEqual(document['pagination'], 'original')
        self.assertEqual([s['page'] for s in sentences], [1, 3])
        self.assertEqual([b['page'] for b in document['blocks']], [1, 3])

    def test_trial_trims_partial_paragraph_and_never_exposes_later_chapters(self):
        sentences, document = build_reading_document([{'type': 'paragraph', 'text': 'Allowed sentence for preview. Secret words must remain hidden.', 'section': 'a'}, {'type': 'heading', 'text': 'Secret Chapter Title', 'section': 'b'}], 'epub')
        original = copy.deepcopy(document)
        document['source']={'version':1,'spine':[{'href':'secret.xhtml'}]}
        visible = reader_document({'readingDocument': document}, sentences[:1], True)
        self.assertEqual(len(visible['blocks']), 1)
        self.assertEqual(visible['blocks'][0]['text'], 'Allowed sentence for preview.')
        self.assertNotIn('Secret', str(visible))
        self.assertNotIn('source',visible)
        self.assertEqual(document['blocks'], original['blocks'])
        self.assertEqual(reader_document({'readingDocument': document}, sentences)['blocks'], document['blocks'])

    def test_old_books_have_no_structure_generated_or_written_on_read(self):
        data = {'sentences': [{'id': 'old', 'text': 'Existing original sentence.'}]}
        original = copy.deepcopy(data)
        self.assertIsNone(reader_document(data, data['sentences']))
        self.assertEqual(data, original)

    def test_paired_original_audio_alignment_preserves_document_blocks_and_addresses(self):
        sentences,document=build_reading_document([{'type':'paragraph','text':'Original audio document.'}],'epub')
        original=copy.deepcopy(document)
        book={'sentences':sentences,'readingDocument':document}
        result=apply_timings(book,[(0,0),(0,1),(0,2)],{0:{'start':0,'end':.3},1:{'start':.4,'end':.7},2:{'start':.8,'end':1.2}})
        self.assertEqual(result['readingDocument'],original)
        self.assertEqual(result['sentences'][0]['end'],1.2)

    def test_pdf_extractor_keeps_empty_page_number_and_text_strategy_is_unchanged(self):
        service=WorkspaceImportService.__new__(WorkspaceImportService)
        service.pdf_ocr=Path(__file__)
        def fake_ocr(command, **kwargs):
            Path(command[2]).write_text(json.dumps([{'lines':[{'text':'First page.'}]},{'lines':[]},{'lines':[{'text':'Third page.'}]}]))
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'original.pdf'
            with patch('saas_imports.subprocess.run',side_effect=fake_ocr):
                _,metadata=service._document_text(source,'document')
            self.assertEqual([b['page'] for b in metadata['documentBlocks']],[1,3])
            text=Path(directory)/'original.txt';text.write_text('Existing text.\n\nNext paragraph.')
            extracted,metadata=service._document_text(text,'text')
            self.assertEqual(extracted,text.read_text())
            self.assertNotIn('documentBlocks',metadata)
            self.assertEqual(service._sentences(extracted),service._sentences(text.read_text()))

    def test_private_reader_forwards_structure_only_after_owner_authorization(self):
        sentences,document=build_reading_document([{'type':'paragraph','text':'Original private paragraph.'}],'epub')
        accounts=MagicMock();accounts._one.return_value={}
        service=WorkspaceService(accounts)
        book={'id':'private','title':'Private','english_title':'Private','series':'','level':'','source_type':'document','duration':0,'data_json':{'sentences':sentences,'readingDocument':document}}
        with patch.object(service,'_book',return_value=book), patch.object(service,'_asset_summaries',return_value=[]), patch('saas_media.MediaService.attach_reader_captions'), patch('saas_workspace.can_watch_hd_video',return_value=False):
            result=service.reader('owner','private')
        self.assertEqual(result['book']['readingDocument']['blocks'],document['blocks'])
        with patch.object(service,'_book',side_effect=SaaSError('book_not_found','Denied',404)),patch('reading_document.reader_document') as serialize:
            with self.assertRaises(SaaSError):service.reader('other','private')
            serialize.assert_not_called()

    def test_catalog_reader_trial_filters_document_at_the_same_authorized_sentence_limit(self):
        sentences,document=build_reading_document([{'type':'paragraph','text':'Allowed sample sentence. Hidden sentence after preview.'}],'epub')
        accounts=MagicMock();accounts._many.return_value=[]
        row={'id':'catalog','source_content_book_id':'source','title':'Public','english_title':'Public','level':'','resource_type':'document','duration':0,'estimated_minutes':1,'library_book_id':None,'data_json':{'sentences':sentences,'readingDocument':document}}
        accounts._one.side_effect=[row,{}]
        service=CatalogService(accounts,MagicMock())
        with patch('saas_media.MediaService.attach_reader_captions'),patch('saas_catalog.can_watch_hd_video',return_value=False):
            result=service.reader('reader','catalog',trial=True)['book']
        self.assertEqual(len(result['sentences']),1)
        self.assertNotIn('Hidden',str(result['readingDocument']))
        self.assertEqual(document['blocks'][0]['text'],'Allowed sample sentence. Hidden sentence after preview.')


if __name__ == '__main__':
    unittest.main()
