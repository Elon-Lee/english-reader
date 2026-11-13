"""Small production frontend server for the SaaS release.

The public listener serves the built React site and proxies business requests
to the private SaaS API listener. It keeps the Python business server off the
public interface while avoiding a second runtime dependency such as nginx.
"""
import http.client
import ipaddress
import mimetypes
import os
import socket
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from saas_sites import is_commercial_path

ROOT = Path(os.environ.get("FRONTEND_ROOT", "/app/site")).resolve()
BACKEND = urlsplit(os.environ.get("SAAS_BACKEND_URL", "http://127.0.0.1:8790"))
PORT = int(os.environ.get("FRONTEND_PORT", "5173"))
PROXY_PREFIXES = ("/api/", "/books/")
APP_DOMAIN = os.environ.get("APP_DOMAIN", "").strip().lower()
BLOG_DOMAIN = os.environ.get("BLOG_DOMAIN", "").strip().lower()
BLOG_PREVIEW_HOST = os.environ.get('BLOG_PREVIEW_HOST', '').strip()
BLOG_ROOT = Path(os.environ["BLOG_ROOT"]).resolve() if os.environ.get("BLOG_ROOT") else None
FRONTEND_SITE = os.environ.get('FRONTEND_SITE', 'cn')
SITE_TOKEN = os.environ.get('FRONTEND_SITE_TOKEN', '') or os.environ.get(
    'INTL_GATEWAY_TOKEN' if FRONTEND_SITE == 'intl' else 'CN_GATEWAY_TOKEN', '')


class TLSFrontendServer(ThreadingHTTPServer):
    """Serve TLS publicly while retaining a local HTTP tunnel origin."""

    def __init__(self, address, handler, context):
        self.context = context
        super().__init__(address, handler)

    def get_request(self):
        connection, address = super().get_request()
        try:
            connection.settimeout(5)
            if connection.recv(1, socket.MSG_PEEK) == b'\x16':
                connection = self.context.wrap_socket(connection, server_side=True)
            elif not ipaddress.ip_address(address[0]).is_loopback:
                raise OSError('Plain HTTP is restricted to loopback tunnel origins')
            connection.settimeout(None)
            return connection, address
        except Exception:
            connection.close()
            raise


class FrontendHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def end_headers(self):
        # Apply to every domestic app response, including API and error pages.
        # The public blog and international entry retain their own policies.
        if FRONTEND_SITE == 'cn' and getattr(self, 'headers', None) is not None and self._site() == 'app':
            self.send_header('X-Robots-Tag', 'noindex, nofollow')
        super().end_headers()

    def _site(self):
        if not BLOG_ROOT and not APP_DOMAIN:
            return 'app'
        hosts = self.headers.get_all('Host', [])
        if len(hosts) != 1:
            return None
        if any(character.isspace() or ord(character) < 33 or ord(character) == 127 for character in hosts[0]):
            return None
        try:
            value = urlsplit('//' + hosts[0])
            value.port  # Reject malformed ports rather than trusting only the hostname.
            if value.username or value.password or value.path or value.query or value.fragment:
                return None
            host = value.hostname
        except ValueError:
            return None
        if BLOG_ROOT and host == BLOG_DOMAIN:
            return 'blog'
        if BLOG_ROOT and FRONTEND_SITE == 'cn' and BLOG_PREVIEW_HOST and host == BLOG_PREVIEW_HOST:
            return 'blog'
        if host == APP_DOMAIN:
            return 'app'
        # Existing container probes are local HTTP requests without an edge hop.
        if (host in {'127.0.0.1', 'localhost', '::1'}
                and ipaddress.ip_address(self.client_address[0]).is_loopback
                and not any(key.lower().startswith('x-forwarded-')
                            or key.lower() in {'x-real-ip', 'cf-connecting-ip', 'forwarded'}
                            for key in self.headers)):
            return 'app'
        return None

    def _blog_file(self):
        requested = unquote(urlsplit(self.path).path)
        path = (BLOG_ROOT / requested.lstrip('/')).resolve()
        if path.is_dir():
            path = (path / 'index.html').resolve()
        try:
            path.relative_to(BLOG_ROOT)
        except ValueError:
            self.send_error(403)
            return
        status = 200
        if not path.is_file():
            path = BLOG_ROOT / '404.html'
            status = 404
            if not path.is_file():
                self.send_error(404)
                return
        data = path.read_bytes()
        self.send_response(status)
        self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'public, max-age=31536000, immutable' if '/_astro/' in requested else 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def _dispatch(self):
        site = self._site()
        if site is None:
            self.send_error(421, 'Misdirected Request')
        elif site == 'blog':
            if self.command in {'GET', 'HEAD'}:
                self._blog_file()
            else:
                self.send_error(404)
        elif (FRONTEND_SITE == 'cn' and urlsplit(self.path).path == '/robots.txt'
              and self.command in {'GET', 'HEAD'}):
            data = b'User-agent: *\nDisallow: /\n'
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(data)
        elif FRONTEND_SITE == 'cn' and is_commercial_path(self.path):
            self.send_error(404)
        elif self.path.startswith(PROXY_PREFIXES):
            self._proxy()
        elif self.command in {'GET', 'HEAD'}:
            self._file()
        else:
            self.send_error(404)

    def _proxy(self):
        body = None
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length:
            body = self.rfile.read(length)
        declared = self.headers.get('X-Upload-Size')
        if (length and len(body) != length) or (declared is not None and (not declared.isdecimal() or int(declared) != length)):
            self.log_message('incomplete upload: expected=%d received=%d declared=%s',length,len(body or b''),declared if declared and declared.isdecimal() and len(declared)<=12 else 'invalid-or-missing')
            self.close_connection = True
            data = '{"code":"incomplete_upload","error":"上传文件不完整，请重新上传完整文件。"}'.encode('utf-8')
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Connection', 'close')
            self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass
            return
        headers = {key: value for key, value in self.headers.items() if key.lower() not in {"host", "content-length", "connection"}}
        headers["Host"] = BACKEND.netloc
        # Overwrite internal identity headers on every ingress, including direct TLS.
        headers = {key: value for key, value in headers.items() if not key.lower().startswith('x-shiyue-')}
        peer = self.client_address[0]
        client_ip = peer
        if ipaddress.ip_address(peer).is_loopback:
            # Nginx appends its socket peer to XFF. Cloudflared sets CF-Connecting-IP.
            forwarded = self.headers.get("X-Forwarded-For", "").split(",")[-1].strip()
            cloudflare = self.headers.get("CF-Connecting-IP", "")
            candidate = cloudflare if FRONTEND_SITE == 'intl' and cloudflare else forwarded or cloudflare
            try: client_ip = str(ipaddress.ip_address(candidate))
            except ValueError: pass
        headers["X-Shiyue-Client-IP"] = client_ip
        headers["X-Shiyue-Original-Host"] = self.headers.get("Host", "")
        if SITE_TOKEN:
            headers['X-Shiyue-Site'] = FRONTEND_SITE
            headers['X-Shiyue-Site-Token'] = SITE_TOKEN
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
        app_route = requested in {"/", "/app", "/login", "/register", "/support", "/verify-email", "/reset-password", "/terms", "/privacy", "/content-policy", "/copyright"}
        if FRONTEND_SITE == 'intl' and (requested in {'/pricing', '/refunds'} or requested.startswith('/purchase/')):
            app_route = True
        if not path.is_file() and app_route:
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
        self._dispatch()

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        self._dispatch()

    def do_PUT(self):
        self._dispatch()

    def do_PATCH(self):
        self._dispatch()

    def do_DELETE(self):
        self._dispatch()

    def do_OPTIONS(self):
        self._dispatch()

    def log_message(self, format, *args):
        print(f"frontend {self.address_string()} - {format % args}", flush=True)


if __name__ == "__main__":
    if BLOG_PREVIEW_HOST:
        BLOG_PREVIEW_HOST = str(ipaddress.ip_address(BLOG_PREVIEW_HOST))
    if FRONTEND_SITE not in {'cn', 'intl'}:
        raise ValueError('FRONTEND_SITE must be cn or intl')
    if FRONTEND_SITE == 'intl' and not SITE_TOKEN:
        raise ValueError('International ingress requires its configured gateway token')
    if APP_DOMAIN or BLOG_DOMAIN or BLOG_ROOT:
        from deployment.https_entry import normalize_domain
        APP_DOMAIN = normalize_domain(APP_DOMAIN)
    if BLOG_DOMAIN or BLOG_ROOT:
        if (not all((APP_DOMAIN, BLOG_DOMAIN, BLOG_ROOT))
                or normalize_domain(APP_DOMAIN) == normalize_domain(BLOG_DOMAIN)
                or not (BLOG_ROOT / 'index.html').is_file()):
            raise ValueError('Dual-site mode requires distinct APP_DOMAIN/BLOG_DOMAIN and a built BLOG_ROOT')
        BLOG_DOMAIN = normalize_domain(BLOG_DOMAIN)
    address = (os.environ.get("FRONTEND_HOST", "0.0.0.0"), PORT)
    cert = os.environ.get("FRONTEND_TLS_CERT", "")
    key = os.environ.get("FRONTEND_TLS_KEY", "")
    if cert and key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        server = TLSFrontendServer(address, FrontendHandler, context)
    else:
        server = ThreadingHTTPServer(address, FrontendHandler)
    print(f"SaaS frontend site={FRONTEND_SITE} listening on {address[0]}:{PORT}, backend={BACKEND.geturl()}", flush=True)
    server.serve_forever()
