"""Local debugging must be isolated and safe to restart on a developer machine."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_local_dev as dev


class LocalDevTests(unittest.TestCase):
    def config(self):
        return {key: 'test-only-long-secret-material-1234' for key in (
            'databasePassword', 'redisPassword', 'sessionSecret', 'captchaSecret', 'adminPassword')}

    def test_remote_process_environment_cannot_leak_into_local_debugging(self):
        source = {'PATH': '/usr/bin', 'HOME': '/local/home',
                  'DATABASE_URL': 'postgresql://remote.example/production', 'REDIS_URL': 'redis://127.0.0.1:16379',
                  'SHIYUE_MEDIA_PROXY_TARGET': 'http://127.0.0.1:18791', 'SESSION_SECRET': 'remote-session-secret',
                  'SMTP_HOST': 'remote-smtp.example', 'BOOTSTRAP_ADMIN_EMAIL': 'production@example.test',
                  'SHIYUE_BROWSER_AUDIT_SECRET': 'inherited-audit-secret', 'SHIYUE_DEPLOYMENT_MODE': 'remote'}
        actual = dev.environment(self.config(), source)
        self.assertEqual(actual['DATABASE_URL'].rsplit('@', 1)[1], '127.0.0.1:55432/shiyue_saas_local')
        self.assertEqual(actual['REDIS_URL'].rsplit('@', 1)[1], '127.0.0.1:56379/0')
        self.assertNotIn('SHIYUE_MEDIA_PROXY_TARGET', actual)
        self.assertNotIn('SHIYUE_BROWSER_AUDIT_SECRET', actual)
        self.assertEqual(actual['SESSION_SECRET'], self.config()['sessionSecret'])
        self.assertEqual(actual['SHIYUE_DEPLOYMENT_MODE'], 'local')
        self.assertEqual(actual['BOOTSTRAP_ADMIN_EMAIL'], '')
        self.assertEqual(actual['SMTP_HOST'], '127.0.0.1')
        self.assertEqual(actual['MEDIA_ROOT'], str(dev.STATE / 'media'))
        self.assertEqual(source['SMTP_HOST'], 'remote-smtp.example')

    def test_remote_and_ssh_forward_database_urls_are_rejected(self):
        for value in ('postgresql://db.example/production', 'postgresql://127.0.0.1:15432/shiyue_saas_local',
                      'postgresql://127.0.0.1:55432/shiyue_saas_local?host=remote.example'):
            env = dev.environment(self.config(), {})
            env['DATABASE_URL'] = value
            with self.subTest(url=value), self.assertRaises(RuntimeError):
                dev.validate_environment(env)

    def test_secrets_persist_and_remain_private_across_restarts(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(dev, 'STATE', Path(folder)):
            first = dev.load_config()
            second = dev.load_config()
            self.assertEqual(first, second)
            self.assertGreaterEqual(len(first['sessionSecret']), 32)
            self.assertEqual((Path(folder) / 'config.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads((Path(folder) / 'config.json').read_text())['adminEmail'], 'admin@local.test')

    def test_existing_cluster_without_secrets_is_not_reinitialized(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(dev, 'STATE', Path(folder)):
            cluster = Path(folder) / 'postgres'
            cluster.mkdir()
            (cluster / 'PG_VERSION').write_text('16')
            with self.assertRaisesRegex(RuntimeError, '配置缺失'):
                dev.load_config()
            self.assertFalse((Path(folder) / 'config.json').exists())

    def test_occupied_service_port_does_not_replace_unrelated_process(self):
        with patch.object(dev, 'reachable', return_value=True), patch.object(dev.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError, '占用'):
                dev.start_process('backend', ['unused'], {}, 'unused', {}, lambda: True)
            spawn.assert_not_called()

    def test_stop_ignores_reused_pid(self):
        records = {'frontend': {'pid': 123, 'marker': '/project/vite/bin/vite.js'}}
        with tempfile.TemporaryDirectory() as folder, patch.object(dev, 'STATE', Path(folder)), \
                patch.object(dev, 'read_pids', return_value=records), \
                patch.object(dev, 'command_line', return_value='/some/unrelated/process'), \
                patch.object(dev.os, 'kill') as kill:
            dev.stop()
        kill.assert_not_called()

    def test_reproducible_jar_does_not_rebuild_on_every_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'services/captcha'
            source.mkdir(parents=True)
            (source / 'pom.xml').write_text('test pom')
            (source / 'build.sh').write_text('test build')
            (source / 'src').mkdir()
            jar = root / 'captcha.jar'
            jar.write_bytes(b'fixed timestamp jar')
            with patch.object(dev, 'ROOT', root), patch.object(dev, 'STATE', root), \
                    patch.object(dev.subprocess, 'run') as build:
                dev.ensure_captcha_build({}, jar)
                dev.ensure_captcha_build({}, jar)
                self.assertEqual(build.call_count, 1)
                (source / 'pom.xml').write_text('changed pom')
                dev.ensure_captcha_build({}, jar)
                self.assertEqual(build.call_count, 2)

    def test_public_launcher_ignores_dotenv_and_stale_python_override(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copyfile(dev.ROOT / 'start-reader.sh', root / 'start-reader.sh')
            (root / '.local/saas-venv/bin').mkdir(parents=True)
            (root / '.local/saas-venv/bin/python').symlink_to(sys.executable)
            (root / 'tools').mkdir()
            (root / 'tools/run_local_dev.py').write_text('import sys; print(sys.argv[1])')
            (root / '.env').write_text('echo DOTENV_MUST_NOT_RUN; exit 99\n')
            env = {**os.environ, 'READER_PYTHON': '/missing/old/session/python'}
            for args, expected in (([], 'start'), (['--saas-local'], 'start'),
                                   (['--status-saas-local'], 'status'), (['--restart-saas-local'], 'restart'),
                                   (['--stop-saas-local'], 'stop')):
                result = subprocess.run(['sh', str(root / 'start-reader.sh'), *args], env=env,
                                        cwd='/', capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)


if __name__ == '__main__':
    unittest.main()
