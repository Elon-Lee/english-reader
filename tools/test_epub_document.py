import tempfile
import unittest
import zipfile
from pathlib import Path
from epub_document import read_epub


class EpubDocumentTests(unittest.TestCase):
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
