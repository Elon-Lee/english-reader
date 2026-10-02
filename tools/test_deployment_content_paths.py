#!/usr/bin/env python3
import tempfile,unittest
from pathlib import Path

from deployment.manager import content_file_entry

class DeploymentContentPathTests(unittest.TestCase):
    def test_symlink_keeps_logical_reader_url(self):
        with tempfile.TemporaryDirectory() as temp:
            books=Path(temp)/"books";book=books/"series"/"title";reader=book/".reader";reader.mkdir(parents=True)
            original=book/"chapter.mp3";original.write_bytes(b"audio")
            logical=reader/"audio.mp3";logical.symlink_to(original)
            relative,actual=content_file_entry(logical,books)
            self.assertEqual(str(relative),"series/title/.reader/audio.mp3")
            self.assertEqual(actual,original.resolve())

    def test_regular_file_keeps_its_path(self):
        with tempfile.TemporaryDirectory() as temp:
            books=Path(temp)/"books";path=books/"series"/"title"/"source.mp4";path.parent.mkdir(parents=True);path.write_bytes(b"video")
            relative,actual=content_file_entry(path,books)
            self.assertEqual(str(relative),"series/title/source.mp4")
            self.assertEqual(actual,path.resolve())

if __name__=="__main__":unittest.main()
