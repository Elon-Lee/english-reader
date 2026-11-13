"""Real HTTP checks for blog/application host and resource isolation."""
import http.client
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch

import saas_frontend_server as frontend


class Backend(BaseHTTPRequestHandler):
    calls = []

    def do_GET(self):
        self.calls.append(dict(self.headers))
        data = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class SiteDomainsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.app = root / 'app'
        self.blog = root / 'blog'
        self.app.mkdir()
        self.blog.mkdir()
        (self.app / 'index.html').write_text('private application')
        (self.app / 'private.js').write_text('private bundle')
        (self.blog / 'index.html').write_text('纸间微光 · 博客')
        (self.blog / '404.html').write_text('纸间微光 · 暂未找到这一页')
        (self.blog / 'posts' / 'light').mkdir(parents=True)
        (self.blog / 'posts' / 'light' / 'index.html').write_text('reading notes')
        (self.blog / 'rss.xml').write_text('<rss>notes</rss>')
        (self.blog / 'robots.txt').write_text('User-agent: *\nAllow: /\n')
        (self.blog / 'outside').symlink_to(self.app, target_is_directory=True)
        self.backend = self.start_server(Backend)
        Backend.calls = []
        values = {
            'ROOT': self.app, 'BLOG_ROOT': self.blog,
            'FRONTEND_SITE': 'cn',
            'APP_DOMAIN': 'learn.rynenglish.com', 'BLOG_DOMAIN': 'rynenglish.com',
            'BACKEND': urlsplit(f'http://127.0.0.1:{self.backend.server_port}'),
        }
        self.patcher = patch.multiple(frontend, **values)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.server = self.start_server(frontend.FrontendHandler)

    def start_server(self, handler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def request(self, path='/', host='rynenglish.com', method='GET', headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=4)
        connection.request(method, path, headers={'Host': host, **(headers or {})})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_blog_home_and_nested_article(self):
        for path, expected in [('/', '纸间微光'), ('/posts/light/', 'reading notes'), ('/rss.xml', '<rss>')]:
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertIn(expected.encode(), body)
                self.assertNotIn('Set-Cookie', headers)
                self.assertNotIn(b'learn.rynenglish.com', body)
        self.assertEqual(Backend.calls, [])

    def test_explicit_ip_preview_only_serves_blog_and_never_proxies(self):
        with patch.object(frontend, 'BLOG_PREVIEW_HOST', '192.0.2.1', create=True):
            status, _, body = self.request(host='192.0.2.1:5174')
            self.assertEqual(status, 200)
            self.assertIn('纸间微光'.encode(), body)
            for path in ['/api/health', '/api/auth/me', '/login', '/app', '/private.js']:
                self.assertEqual(self.request(path, host='192.0.2.1:5174')[0], 404)
            self.assertEqual(self.request('/api/auth/login', host='192.0.2.1:5174', method='POST')[0], 404)
            self.assertEqual(self.request(host='192.0.2.2:5174')[0], 421)
            with patch.object(frontend, 'FRONTEND_SITE', 'intl'):
                self.assertEqual(self.request(host='192.0.2.1:5174')[0], 421)
        self.assertEqual(Backend.calls, [])

    def test_blog_never_proxies_api_or_serves_app(self):
        for path in ['/api/health', '/api/auth/me', '/api', '/login', '/app', '/books/a', '/private.js']:
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 404)
                self.assertNotIn('Location', headers)
                self.assertNotIn(b'private application', body)
        self.assertEqual(Backend.calls, [])

    def test_blog_write_methods_are_not_proxied(self):
        for method in ['POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']:
            with self.subTest(method=method):
                self.assertEqual(self.request('/api/auth/login', method=method)[0], 404)
        self.assertEqual(Backend.calls, [])

    def test_missing_page_serves_blog_404_with_correct_status(self):
        status, _, body = self.request('/missing-page/')
        self.assertEqual(status, 404)
        self.assertIn('暂未找到这一页'.encode(), body)
        self.assertEqual(self.request('/missing-page/', method='HEAD')[2], b'')

    def test_application_and_proxy_preserve_original_host(self):
        self.assertIn(b'private application', self.request('/login', host='learn.rynenglish.com')[2])
        self.assertEqual(self.request('/api/health', host='learn.rynenglish.com')[0], 200)
        self.assertEqual(Backend.calls[-1]['X-Shiyue-Original-Host'], 'learn.rynenglish.com')

    def test_unknown_host_does_not_expose_app(self):
        for host in ['other.example.com', 'rynenglish.com.attacker.test', 'learn.rynenglish.com@evil.test',
                     'learn.\trynenglish.com', 'ryn\tenglish.com', 'learn.rynenglish.com ']:
            with self.subTest(host=host):
                self.assertEqual(self.request(host=host)[0], 421)

    def test_forwarded_host_cannot_switch_sites(self):
        status, _, body = self.request(headers={'X-Forwarded-Host': 'learn.rynenglish.com'})
        self.assertEqual(status, 200)
        self.assertIn('纸间微光'.encode(), body)

    def test_internal_probes_require_loopback_host_and_no_forwarding(self):
        self.assertEqual(self.request('/api/health', host='127.0.0.1')[0], 200)
        for headers in [{'X-Forwarded-For': '8.8.8.8'}, {'X-Forwarded-Proto':'https'},
                        {'X-Forwarded-Port':'443'}, {'X-Real-IP':'8.8.8.8'}, {'Forwarded':''}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request('/api/health', host='127.0.0.1', headers=headers)[0], 421)

    def test_paths_cannot_read_other_site_files(self):
        for path in ['/../app/private.js', '/%2e%2e/app/private.js', '/outside/private.js']:
            with self.subTest(path=path):
                status, _, body = self.request(path)
                self.assertIn(status, [403, 404])
                self.assertNotIn(b'private bundle', body)

    def test_head_and_feed_cache_policy(self):
        status, headers, body = self.request(method='HEAD')
        self.assertEqual(status, 200)
        self.assertEqual(body, b'')
        self.assertEqual(headers['Cache-Control'], 'no-cache')
        self.assertEqual(self.request('/rss.xml')[1]['Cache-Control'], 'no-cache')

    def test_response_does_not_depend_on_user_agent(self):
        normal = self.request(headers={'User-Agent': 'Mozilla/5.0'})
        crawler = self.request(headers={'User-Agent': 'SomeCrawler/1.0'})
        self.assertEqual((normal[0], normal[2]), (crawler[0], crawler[2]))

    def test_domestic_robots_disallows_all_with_get_and_head(self):
        for agent in ['Mozilla/5.0', 'SomeCrawler/1.0']:
            for method in ['GET', 'HEAD']:
                status, headers, body = self.request('/robots.txt?check=1', host='learn.rynenglish.com',
                                                     method=method, headers={'User-Agent': agent})
                self.assertEqual(status, 200)
                self.assertEqual(headers['Content-Type'], 'text/plain; charset=utf-8')
                self.assertEqual(headers['Cache-Control'], 'no-cache')
                self.assertEqual(body, b'' if method == 'HEAD' else b'User-agent: *\nDisallow: /\n')
        self.assertEqual(Backend.calls, [])

    def test_domestic_noindex_covers_pages_assets_api_and_errors(self):
        for path in ['/', '/login', '/app', '/private.js', '/api/health', '/pricing', '/missing']:
            for method in ['GET', 'HEAD']:
                with self.subTest(path=path, method=method):
                    _, headers, _ = self.request(path, host='learn.rynenglish.com', method=method)
                    self.assertEqual(headers.get('X-Robots-Tag'), 'noindex, nofollow')

    def test_blog_and_international_keep_existing_crawler_policy(self):
        status, headers, body = self.request('/robots.txt')
        self.assertEqual(status, 200)
        self.assertEqual(body, b'User-agent: *\nAllow: /\n')
        self.assertNotIn('X-Robots-Tag', headers)
        self.assertNotIn('X-Robots-Tag', self.request('/')[1])
        with patch.object(frontend, 'FRONTEND_SITE', 'intl'), patch.object(frontend, 'APP_DOMAIN', '10ye.cc'):
            self.assertNotIn('X-Robots-Tag', self.request('/', host='10ye.cc')[1])
            self.assertEqual(self.request('/robots.txt', host='10ye.cc')[0], 404)


if __name__ == '__main__':
    unittest.main()
