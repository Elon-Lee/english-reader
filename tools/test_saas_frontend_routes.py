"""Production SPA deep links must work without a prior visit to the homepage."""
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import saas_frontend_server as frontend


class FrontendRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.old_root = frontend.ROOT
        frontend.ROOT = Path(cls.directory.name).resolve()
        (frontend.ROOT / 'index.html').write_text('<main id="root">SPA entry</main>')
        cls.server = frontend.ThreadingHTTPServer(('127.0.0.1', 0), frontend.FrontendHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        frontend.ROOT = cls.old_root
        cls.directory.cleanup()

    def test_public_deep_links_serve_react_entry(self):
        for path in ('/pricing', '/purchase/pro-30', '/purchase/advanced-30?purchase=advanced-30', '/terms', '/privacy', '/content-policy', '/refunds', '/copyright'):
            with self.subTest(path=path), urlopen(self.base + path) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers['Cache-Control'], 'no-cache')
                self.assertIn(b'id="root"', response.read())

    def test_missing_assets_do_not_serve_html(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + '/assets/missing.js')
        self.assertEqual(error.exception.code, 404)
        error.exception.close()


if __name__ == '__main__':
    unittest.main()
