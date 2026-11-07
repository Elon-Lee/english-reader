import tempfile
import unittest
import zipfile
from pathlib import Path
from epub_document import read_epub, BodyText


class EpubDocumentTests(unittest.TestCase):
    def test_source_index_keeps_fixed_layout_overrides_and_empty_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixed.epub'
            with zipfile.ZipFile(path,'w') as archive:
                archive.writestr('META-INF/container.xml','<container><rootfile full-path="OPS/book.opf"/></container>')
                archive.writestr('OPS/book.opf','<package><metadata><meta property="rendition:layout"> pre-paginated </meta></metadata><manifest><item id="a" href="blank.xhtml"/><item id="b" href="text.xhtml"/></manifest><spine><itemref idref="a"/><itemref idref="b" properties="rendition:layout-reflowable"/></spine></package>')
                archive.writestr('OPS/blank.xhtml','<html><body><img src="original.png"/></body></html>')
                archive.writestr('OPS/text.xhtml','<html><body><p>Original source text.</p></body></html>')
            index={}
            _,_,blocks=read_epub(path,structured=True,source_index=index)
            self.assertEqual(index['layout'],'fixed')
            self.assertEqual(index['spine'],[{'href':'OPS/blank.xhtml','section':'section-1','layout':'fixed'},{'href':'OPS/text.xhtml','section':'section-2','layout':'reflow'}])
            self.assertEqual(blocks[0]['section'],'section-2')

    def test_structured_paragraphs_headings_breaks_and_original_page_labels(self):
        parser=BodyText()
        parser.feed('<head><title>Hidden</title></head><h1>Chapter One</h1><p>“First,” <em>original</em> line.<br/>Second line.</p><span epub:type="pagebreak" title="17"></span><p>Next page.</p><script>secret()</script>')
        parser.flush_block()
        self.assertEqual([block['type'] for block in parser.blocks],['heading','paragraph','paragraph'])
        self.assertEqual(parser.blocks[1]['text'],'“First,” original line.\nSecond line.')
        self.assertEqual(parser.blocks[2]['pageLabel'],'17')
        self.assertNotIn('secret',str(parser.blocks))
        self.assertNotIn('Hidden',str(parser.blocks))

    def test_manifest_attribute_order_cover_type_and_spine_order(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);book=root/'book.epub'
            with zipfile.ZipFile(book,'w') as z:
                z.writestr('META-INF/container.xml','<container><rootfile full-path="OPS/content.opf"/></container>')
                z.writestr('OPS/content.opf','''<package><metadata><meta content="cover" name="cover"/></metadata><manifest>
                <item href="images/front.png" media-type="image/png" id="cover"/>
                <item id="a" href="z.xhtml"/><item id="b" href="a.xhtml"/></manifest>
                <spine><itemref idref="a"/><itemref idref="b"/></spine></package>''')
                z.writestr('OPS/images/front.png',b'\x89PNG\r\n\x1a\nfixture')
                z.writestr('OPS/z.xhtml','<html><head><title>Hidden title</title><style>hidden</style></head><body><p>First <em>natural</em> sentence.</p></body></html>')
                z.writestr('OPS/a.xhtml','<p>Second chapter.</p>')
                z.writestr('OPS/nav.xhtml','Navigation must not appear.')
            text,cover=read_epub(book,root/'cover.jpg')
            self.assertEqual(text,'First natural sentence.\n\nSecond chapter.')
            self.assertEqual(Path(cover).suffix,'.png')
            self.assertTrue(Path(cover).read_bytes().startswith(b'\x89PNG'))
            _,_,blocks=read_epub(book,structured=True)
            self.assertEqual([block['text'] for block in blocks],['First natural sentence.','Second chapter.'])
            self.assertEqual([block['section'] for block in blocks],['section-1','section-2'])

    def test_epub3_cover_image_properties_before_or_after_href(self):
        for item in ['<item href="cover.jpg" properties="cover-image" id="c"/>','<item properties="cover-image" id="c" href="cover.jpg"/>']:
            with self.subTest(item=item), tempfile.TemporaryDirectory() as d:
                root=Path(d);book=root/'book.epub'
                with zipfile.ZipFile(book,'w') as z:
                    z.writestr('META-INF/container.xml','<container><rootfile full-path="book.opf"/></container>')
                    z.writestr('book.opf','<package><manifest>'+item+'</manifest><spine/></package>')
                    z.writestr('cover.jpg',b'\xff\xd8\xfffixture')
                _,cover=read_epub(book,root/'cover.png')
                self.assertEqual(Path(cover).suffix,'.jpg')


if __name__=='__main__':unittest.main()
