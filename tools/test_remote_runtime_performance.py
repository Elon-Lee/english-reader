#!/usr/bin/env python3
import inspect,unittest
from reader_server import Handler

class RemoteRuntimePerformanceTests(unittest.TestCase):
    def test_reader_uses_gzip_etag_and_cache_headers(self):
        source=inspect.getsource(Handler.reply)+inspect.getsource(Handler.serve_reader_asset)+inspect.getsource(Handler.serve_books_file)
        self.assertIn("gzip.compress",source);self.assertIn("ETag",source);self.assertIn("Cache-Control",source)

    def test_media_supports_range_and_connection_abort(self):
        source=inspect.getsource(Handler.send_path_range)+inspect.getsource(Handler.send_file_content)
        self.assertIn("Content-Range",source);self.assertIn("sendfile",source);self.assertIn("ConnectionResetError",source)

if __name__=="__main__":unittest.main()
