"""HTTPS deployment configuration and a real TLS/proxy cookie round trip."""
import http.cookiejar
import io
import json
import os
import shlex
import socket
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
import saas_frontend_server as frontend
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import URLError
from urllib.request import HTTPCookieProcessor, HTTPSHandler, ProxyHandler, Request, build_opener

from deployment import manager


class DeploymentHttpsTests(unittest.TestCase):
    def test_existing_env_preserves_secrets_and_https_domain(self):
        for base, expected in (
            ('http://192.0.2.1:8765', 'https://192.0.2.1:5173'),
            ('https://192.0.2.1:8765', 'https://192.0.2.1:5173'),
            ('"https://reading.example.test"', '"https://reading.example.test"'),
            (None, 'https://192.0.2.1:5173'),
        ):
            with self.subTest(base=base), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                env = root / 'shared/config/saas.env'
                env.parent.mkdir(parents=True)
                original = 'SESSION_SECRET=test-session-secret\nDATABASE_URL=test-database\n'
                env.write_text(original + (f'APP_BASE_URL={base}\n' if base else ''))
                env.chmod(0o600)
                remote = Mock()
                def ssh(script):
                    if script.startswith('test -s '):
                        return 'SHIYUE_SAAS_ENV_READY'
                    args = shlex.split(script)
                    self.assertEqual(args[:5], ['docker', 'run', '--rm', '--network', 'none'])
                    code = args[-1].replace("Path('/config/saas.env')", f'Path({str(env)!r})')
                    result = subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, text=True)
                    self.assertEqual(result.stdout, '')
                    return result.stdout
                remote.ssh.side_effect = ssh
                manager.ensure_remote_saas_config(Mock(), remote, {
                    'remote_root': str(root), 'host': '192.0.2.1', 'use_https': 1,
                })
                self.assertEqual(env.read_text(), original + f'APP_BASE_URL={expected}\n')
                self.assertEqual(env.stat().st_mode & 0o777, 0o600)
                remote.scp.assert_not_called()

    def test_upgrade_and_deploy_enable_https_for_old_http_node(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / 'release.tar.gz'
            with tarfile.open(package, 'w:gz') as archive:
                metadata = json.dumps({'gitCommit': 'test'}).encode()
                info = tarfile.TarInfo('.shiyue-release.json')
                info.size = len(metadata)
                archive.addfile(info, io.BytesIO(metadata))
            for action in (manager.start_saas_upgrade, manager.start_saas_deploy):
                with self.subTest(action=action.__name__), ExitStack() as stack:
                    target = {'id': 1, 'host': '192.0.2.1', 'service_port': 8765,
                              'remote_root': '/srv/shiyue', 'use_https': 0, 'install_recording': 0}
                    job, remote = Mock(), Mock()
                    remote.ssh.return_value = 'SHIYUE_SAAS_RELEASE_ACTIVE'
                    calls = []
                    results = {
                        'build_code_package': (package, 'a' * 64),
                        'build_saas_database_dump': (Path(temp) / 'db.dump', 'b' * 64),
                        'remote_arch': ('x86_64', 'amd64'),
                        'sync_remote_private_config': {'configured': True},
                        'ensure_remote_tls': Path(temp) / 'rootCA.pem',
                        'activate_saas_release': {'candidate': 'healthy'},
                        'sync_saas_public_content': {'contentRevision': 'public-test', 'media': {}},
                        'restore_remote_saas_database': False,
                    }
                    names = (*results, 'check_remote_saas_upgrade_target', 'prepare_remote_saas_release',
                             'backup_remote_saas_database', 'ensure_remote_saas_config',
                             'ensure_remote_docker', 'ensure_remote_runtime', 'ensure_remote_saas_services')
                    mocks = {}
                    for name in names:
                        def invoke(*args, _name=name, **kwargs):
                            calls.append(_name)
                            return results.get(_name)
                        mocks[name] = stack.enter_context(patch.object(manager, name, side_effect=invoke))
                    connection = stack.enter_context(patch.object(manager, 'connect')).return_value
                    stack.enter_context(patch.object(manager, 'run_task',
                        side_effect=lambda kind, worker, target_id: worker(job, remote, target)))
                    action(1)
                    effective = mocks['activate_saas_release'].call_args.args[2]
                    self.assertEqual((effective['use_https'], effective['service_port']), (1, 5173))
                    self.assertEqual((target['use_https'], target['service_port']), (0, 8765))
                    for name in ('ensure_remote_tls', 'ensure_remote_saas_config'):
                        self.assertLess(calls.index(name), calls.index('activate_saas_release'))
                    result = job.complete.call_args.args[0]
                    self.assertEqual(result['frontendUrl'], 'https://192.0.2.1:5173')
                    self.assertTrue(result['rootCertificate'].endswith('rootCA.pem'))
                    self.assertTrue(any('use_https=1' in call.args[0]
                                        for call in connection.execute.call_args_list))

    def test_frontend_docker_tls_options_precede_image(self):
        target = {'remote_root': '/srv/shiyue', 'use_https': 1}
        args = shlex.split(manager.saas_frontend_run_command(target, '/srv/shiyue/current'))
        self.assertLess(args.index('FRONTEND_TLS_CERT=/certs/server-cert.pem'), args.index(manager.SAAS_IMAGE))
        self.assertIn('FRONTEND_PORT=5173', args)
        self.assertIn('SAAS_BACKEND_URL=http://127.0.0.1:8790', args)
        self.assertIn('/srv/shiyue/shared/https:/certs:ro,z', args)

    def test_candidate_and_production_activation_use_https(self):
        from test_deployment_release_pipeline import SyntaxRemote
        target = {'remote_root': '/srv/shiyue', 'service_port': 5173,
                  'install_recording': False, 'use_https': 1}
        remote = SyntaxRemote()
        manager.activate_saas_release(Mock(), remote, target, 'code-test')
        for script, port in zip(remote.scripts, (15173, 5173)):
            self.assertIn(f'https://127.0.0.1:{port}/', script)
            self.assertIn('FRONTEND_TLS_CERT=/certs/server-cert.pem', script)
            self.assertIn('FRONTEND_TLS_KEY=/certs/server-key.pem', script)

    def test_tls_listener_rejects_public_plain_http_and_closes_failed_tls(self):
        for first_byte, client, error in ((b'G', '192.0.2.1', OSError),
                                          (b'\x16', '192.0.2.1', ssl.SSLError)):
            with self.subTest(client=client, first_byte=first_byte):
                server = frontend.TLSFrontendServer.__new__(frontend.TLSFrontendServer)
                server.context = Mock()
                server.context.wrap_socket.side_effect = ssl.SSLError('failed handshake')
                connection = Mock()
                connection.recv.return_value = first_byte
                with patch.object(frontend.ThreadingHTTPServer, 'get_request',
                                  return_value=(connection, (client, 12345))):
                    with self.assertRaises(error): server.get_request()
                connection.close.assert_called_once()

    def test_invalid_cached_certificates_are_preserved_and_replaced(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(manager, 'TLS', Path(temp)):
            directory = Path(temp) / '127.0.0.1'
            directory.mkdir()
            for name in ('rootCA-key.pem', 'rootCA.pem', 'server-key.pem', 'server-cert.pem'):
                (directory / name).write_text('invalid legacy certificate')
            generated = manager.build_tls_bundle({'host': '127.0.0.1'})
            backups = list(Path(temp).glob('127.0.0.1-previous-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / 'server-cert.pem').read_text(), 'invalid legacy certificate')
            self.assertIn('BEGIN CERTIFICATE', (generated / 'server-cert.pem').read_text())
            self.assertEqual(manager.build_tls_bundle({'host': '127.0.0.1'}), generated)
            self.assertEqual(len(list(Path(temp).glob('127.0.0.1-previous-*'))), 1)

    def test_real_tls_frontend_proxies_secure_login_cookies(self):
        class Backend(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(200)
                self.send_header('Set-Cookie', 'shiyue_session=test-session; Path=/; HttpOnly; Secure; SameSite=Lax')
                self.send_header('Set-Cookie', 'shiyue_csrf=test-csrf; Path=/; Secure; SameSite=Lax')
                self.end_headers()
                self.wfile.write(b'{"user":{"id":"test-user"}}')
            def do_GET(self):
                authorized = self.path == '/api/health' or 'shiyue_session=test-session' in self.headers.get('Cookie', '')
                self.send_response(200 if authorized else 401)
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            def log_message(self, *_args): pass

        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            root = Path(temp)
            stack.enter_context(patch.object(manager, 'TLS', root / 'certificates'))
            certs = manager.build_tls_bundle({'host': '127.0.0.1'})
            (root / 'index.html').write_text('<div id="root"></div>')
            backend = ThreadingHTTPServer(('127.0.0.1', 0), Backend)
            thread = threading.Thread(target=backend.serve_forever, daemon=True)
            thread.start()
            stack.callback(backend.server_close)
            stack.callback(backend.shutdown)
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1', 0))
                port = reservation.getsockname()[1]
            env = {**os.environ, 'FRONTEND_ROOT': str(root), 'FRONTEND_HOST': '127.0.0.1',
                   'FRONTEND_PORT': str(port), 'SAAS_BACKEND_URL': f'http://127.0.0.1:{backend.server_port}',
                   'FRONTEND_TLS_CERT': str(certs / 'server-cert.pem'),
                   'FRONTEND_TLS_KEY': str(certs / 'server-key.pem')}
            output = stack.enter_context((root / 'frontend.log').open('w'))
            process = subprocess.Popen([sys.executable, str(manager.ROOT / 'tools/saas_frontend_server.py')],
                                       env=env, stdout=output, stderr=subprocess.STDOUT)
            def stop():
                process.terminate()
                process.wait(timeout=10)
            stack.callback(stop)
            jar = http.cookiejar.CookieJar()
            context = ssl.create_default_context(cafile=str(certs / 'rootCA.pem'))
            opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), HTTPCookieProcessor(jar))
            base = f'https://127.0.0.1:{port}'
            for attempt in range(100):
                try:
                    with opener.open(base, timeout=1) as response:
                        self.assertIn(b'id="root"', response.read())
                    break
                except URLError as exc:
                    last_error = str(exc.reason)
                    if process.poll() is not None: self.fail('HTTPS frontend exited during startup')
                    time.sleep(0.05)
            else: self.fail('HTTPS frontend did not start: ' + last_error)
            code = shlex.split(manager.saas_frontend_health_check_command(port, https=True))[-1]
            subprocess.run([sys.executable, '-c', code], check=True, capture_output=True)
            with opener.open(Request(base + '/api/auth/login', data=b''), timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(len(response.headers.get_all('Set-Cookie')), 2)
            self.assertEqual({cookie.name for cookie in jar}, {'shiyue_session', 'shiyue_csrf'})
            self.assertTrue(all(cookie.secure for cookie in jar))
            request = Request(f'http://127.0.0.1:{port}/api/auth/me')
            jar.add_cookie_header(request)
            self.assertIsNone(request.get_header('Cookie'))
            # Existing Cloudflare tunnels can keep their HTTP localhost origin.
            with opener.open(f'http://127.0.0.1:{port}/api/health', timeout=5) as response:
                self.assertEqual(response.status, 200)
            with opener.open(base + '/api/auth/me', timeout=5) as response:
                self.assertEqual(response.status, 200)


if __name__ == '__main__':
    unittest.main()
