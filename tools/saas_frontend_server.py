"""Small production frontend server for the SaaS release.

The public listener serves the built React site and proxies business requests
to the private SaaS API listener. It keeps the Python business server off the
public interface while avoiding a second runtime dependency such as nginx.
"""
import http.client
import mimetypes
import os
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(os.environ.get("FRONTEND_ROOT", "/app/site")).resolve()
BACKEND = urlsplit(os.environ.get("SAAS_BACKEND_URL", "http://127.0.0.1:8790"))
PORT = int(os.environ.get("FRONTEND_PORT", "5173"))
PROXY_PREFIXES = ("/api/", "/books/")


class FrontendHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _proxy(self):
        body = None
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length:
            body = self.rfile.read(length)
        headers = {key: value for key, value in self.headers.items() if key.lower() not in {"host", "content-length", "connection"}}
        headers["Host"] = BACKEND.netloc
        connection = http.client.HTTPConnection(BACKEND.hostname, BACKEND.port or 80, timeout=60)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            data = response.read()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() not in {"connection", "transfer-encoding", "content-length", "server", "date"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        finally:
            connection.close()

    def _file(self):
        requested = urlsplit(self.path).path
        relative = requested.lstrip("/")
        path = (ROOT / relative).resolve()
        try:
            path.relative_to(ROOT)
        except ValueError:
            self.send_error(403)
            return
        if not path.is_file() and requested in {"/", "/app", "/pricing", "/login", "/register", "/support", "/verify-email", "/reset-password"}:
            path = ROOT / "index.html"
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache" if path.name == "index.html" else "public, max-age=31536000, immutable")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith(PROXY_PREFIXES):
            self._proxy()
        else:
            self._file()

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        self._proxy() if self.path.startswith(PROXY_PREFIXES) else self.send_error(404)

    def do_PUT(self):
        self._proxy() if self.path.startswith(PROXY_PREFIXES) else self.send_error(404)

    def do_PATCH(self):
        self._proxy() if self.path.startswith(PROXY_PREFIXES) else self.send_error(404)

    def do_DELETE(self):
        self._proxy() if self.path.startswith(PROXY_PREFIXES) else self.send_error(404)

    def log_message(self, format, *args):
        print(f"frontend {self.address_string()} - {format % args}", flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer((os.environ.get("FRONTEND_HOST", "0.0.0.0"), PORT), FrontendHandler)
    cert = os.environ.get("FRONTEND_TLS_CERT", "")
    key = os.environ.get("FRONTEND_TLS_KEY", "")
    if cert and key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    print(f"SaaS frontend listening on 0.0.0.0:{PORT}, backend={BACKEND.geturl()}", flush=True)
    server.serve_forever()
