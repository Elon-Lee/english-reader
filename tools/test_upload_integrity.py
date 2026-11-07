"""A closed/short upload must never be rewritten into a successful shorter file."""
import ast
import http.client
import io
import socket
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import saas_frontend_server as frontend


class UploadIntegrityTests(unittest.TestCase):
    def test_proxy_rejects_short_body_and_changed_length_before_forwarding(self):
        server = frontend.ThreadingHTTPServer(('127.0.0.1', 0), frontend.FrontendHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for length, declared, data in ((100, None, b'partial'), (7, 100, b'partial')):
                with self.subTest(length=length), patch.object(frontend.http.client, 'HTTPConnection') as upstream:
                    with socket.create_connection(server.server_address, timeout=5) as client:
                        headers = f'POST /api/workspace/imports/test/upload-audio HTTP/1.1\r\nHost: localhost\r\nContent-Length: {length}\r\n'
                        if declared is not None:
                            headers += f'X-Upload-Size: {declared}\r\n'
                        client.sendall(headers.encode() + b'\r\n' + data)
                        client.shutdown(socket.SHUT_WR)
                        response = http.client.HTTPResponse(client)
                        response.begin()
                        self.assertEqual(response.status, 400)
                        self.assertIn(b'incomplete_upload', response.read())
                    upstream.assert_not_called()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_backend_rejects_short_body_even_without_proxy(self):
        # Execute the actual reader handler method without booting its global services.
        tree = ast.parse((Path(__file__).parent / 'reader_server.py').read_text())
        method = next(node for cls in tree.body if isinstance(cls, ast.ClassDef)
                      for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'read_import_upload')
        class UploadError(Exception):
            pass
        namespace = {'SaaSError': UploadError}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<reader upload>', 'exec'), namespace)
        for data, length, declared in ((b'part', 10, None), (b'part', 4, '10'), (b'part', 4, 'invalid')):
            handler = type('Handler', (), {'headers': {} if declared is None else {'X-Upload-Size': declared},
                                          'rfile': io.BytesIO(data), 'close_connection': False})()
            with self.subTest(declared=declared), self.assertRaises(UploadError):
                namespace['read_import_upload'](handler, length)
            self.assertTrue(handler.close_connection)
        handler.headers = {'X-Upload-Size': '4'}
        handler.rfile = io.BytesIO(b'full')
        self.assertEqual(namespace['read_import_upload'](handler, 4), b'full')


if __name__ == '__main__':
    unittest.main()
