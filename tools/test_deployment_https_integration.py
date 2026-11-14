"""HTTPS entry integration must not publish code or overwrite application secrets."""
import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import library_db
from deployment import manager
import deploy_remote


class HttpsEntryIntegrationTests(unittest.TestCase):
    def test_remote_certificate_failure_reports_recovery_without_database_reinstall(self):
        remote = object.__new__(manager.Remote)
        remote.password = ''
        remote.job = Mock()
        process = Mock(stdout=io.StringIO(
            'Invalid response from http://example.test/.well-known/acme-challenge/test: 403\n'
            'SHIYUE_HTTPS_CERTIFICATE_FAILED: validation failed\n'))
        process.wait.return_value = 10
        with patch.object(manager.subprocess, 'Popen', return_value=process):
            with self.assertRaisesRegex(RuntimeError, 'HTTP 403.*单独补装 HTTPS.*无需重新部署数据库'):
                remote.execute(['ssh', 'test'])

    def test_remote_echoed_script_does_not_misclassify_unrelated_failure(self):
        remote = object.__new__(manager.Remote)
        remote.password = ''
        remote.job = Mock()
        process = Mock(stdout=io.StringIO(
            'echo "SHIYUE_HTTPS_CERTIFICATE_FAILED: validation failed" >&2\n'
            'HTTPS container ownership conflict\n'))
        process.wait.return_value = 1
        with patch.object(manager.subprocess, 'Popen', return_value=process):
            with self.assertRaisesRegex(RuntimeError, '远程命令失败，返回码 1'):
                remote.execute(['ssh', 'test'])

    def test_target_domain_is_validated_saved_and_preserved_for_old_clients(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(library_db, 'LOCAL_ROOT', Path(temp)), \
                patch.object(library_db, 'DB_PATH', Path(temp) / 'library.sqlite3'), \
                patch.object(manager, 'public_target', side_effect=dict):
            values = {'name': 'test', 'host': '192.0.2.1', 'publicDomain': 'RynEnglish.com'}
            target = manager.save_target(values)
            self.assertEqual(target.get('public_domain'), 'rynenglish.com')
            updated = manager.save_target({'id': target['id'], 'host': '192.0.2.1'})
            self.assertEqual(updated['public_domain'], 'rynenglish.com')
            with self.assertRaises(ValueError):
                manager.save_target({**values, 'publicDomain': 'example.com;touch /tmp/bad'})
            cleared = manager.save_target({'id': target['id'], 'host': '192.0.2.1', 'publicDomain': ''})
            self.assertEqual(cleared['public_domain'], '')

    def test_explicit_domain_replaces_old_https_base_without_changing_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = root / 'shared/config/saas.env'
            env.parent.mkdir(parents=True)
            original = 'DATABASE_URL=test-database\nSESSION_SECRET=test-secret\n'
            env.write_text(original + 'APP_BASE_URL=https://10ye.cc\n')
            env.chmod(0o600)
            def ssh(script):
                if script.startswith('test -s '):
                    return 'SHIYUE_SAAS_ENV_READY'
                code = shlex.split(script)[-1].replace("Path('/config/saas.env')", f'Path({str(env)!r})')
                return subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, text=True).stdout
            manager.ensure_remote_saas_config(Mock(), Mock(ssh=Mock(side_effect=ssh)), {
                'remote_root': str(root), 'host': '192.0.2.1', 'use_https': 1,
                'public_domain': 'rynenglish.com',
            })
            self.assertEqual(env.read_text(), original + 'APP_BASE_URL=https://rynenglish.com\nSHIYUE_IMPORT_MEMORY_MB=1024\nSHIYUE_IMPORT_SWAP_MB=512\nSHIYUE_IMPORT_THREADS=1\nSMTP_FROM_NAME=纸间微光\n')
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)

    def test_upgrade_rediscovers_remote_entry_before_base_url_changes(self):
        remote = Mock()
        remote.ssh.return_value = 'SHIYUE_HTTPS_ENTRY_CONFIG\n' + json.dumps({'public_domain': 'rynenglish.com'})
        target = {'host': '192.0.2.1', 'remote_root': '/srv/shiyue', 'use_https': 0}
        effective = manager.saas_https_target(remote, target)
        self.assertEqual(effective['public_domain'], 'rynenglish.com')
        self.assertEqual((effective['use_https'], effective['service_port']), (1, 5173))
        self.assertNotIn('public_domain', target)

    def test_upgrade_rejects_corrupt_remote_entry_manifest(self):
        remote = Mock()
        remote.ssh.return_value = 'SHIYUE_HTTPS_ENTRY_CONFIG\n{bad json'
        with self.assertRaises(ValueError):
            manager.saas_https_target(remote, {'remote_root': '/srv/shiyue'})

    def test_identity_file_uses_verified_default_known_hosts(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(manager, 'STATE', Path(temp)), \
                patch.object(manager, 'KEYS', Path(temp) / 'keys'), \
                patch.object(manager, 'KNOWN_HOSTS', Path(temp) / 'known_hosts'), \
                patch.object(manager, 'load_password', side_effect=AssertionError('must not access password')):
            key = Path(temp) / 'private.pem'
            key.touch()
            remote = manager.Remote({'id': 0, 'username': 'root', 'host': '192.0.2.1',
                                     'port': 22, 'identity_file': str(key)}, Mock())
            options = remote.ssh_options()
            self.assertIn(str(key), options)
            self.assertIn('StrictHostKeyChecking=yes', options)
            self.assertFalse(any(item.startswith('UserKnownHostsFile=') for item in options))

    def test_entry_only_cli_does_not_build_or_deploy_application(self):
        args = ['deploy_remote.py', '--https-entry', '--host', '192.0.2.1',
                '--identity-file', '/tmp/test-key', '--domain', 'rynenglish.com']
        with patch.object(sys, 'argv', args), \
                patch.object(manager, 'configure_existing_https_entry', return_value={'frontendUrl': 'https://rynenglish.com'}) as configure, \
                patch.object(manager, 'Remote') as remote, \
                patch.object(manager, 'build_code_package') as build, \
                patch.object(manager, 'start_saas_deploy') as deploy, \
                contextlib.redirect_stdout(io.StringIO()):
            deploy_remote.main()
            configure.assert_called_once()
            target = configure.call_args.args[2]
            self.assertEqual(target['public_domain'], 'rynenglish.com')
            self.assertEqual(target['identity_file'], '/tmp/test-key')
            build.assert_not_called()
            deploy.assert_not_called()

    def test_entry_public_health_check_uses_strict_domain_tls(self):
        remote=Mock()
        remote.ssh.side_effect=['SHIYUE_HTTPS_ENTRY_READY {}','SHIYUE_HTTPS_PUBLIC_READY']
        manager.ensure_remote_https_entry(Mock(),remote,{
            'host':'192.0.2.1','remote_root':'/srv/shiyue','public_domain':'rynenglish.com'})
        verification=remote.ssh.call_args.args[0]
        self.assertIn('ssl.create_default_context()',verification)
        self.assertIn('https://rynenglish.com',verification)
        self.assertNotIn('_create_unverified_context',verification)
        remote.ssh.side_effect=['SHIYUE_HTTPS_ENTRY_READY {}','not ready']
        with self.assertRaises(ValueError):
            manager.ensure_remote_https_entry(Mock(),remote,{
                'host':'192.0.2.1','remote_root':'/srv/shiyue','public_domain':'rynenglish.com'})

    def test_same_domain_reuses_running_application_without_recreating_it(self):
        image='sha256:'+'a'*64
        remote=Mock()
        remote.ssh.side_effect=['',image+'\nSHIYUE_BASE_URL=https://rynenglish.com\n','backup complete','healthy']
        target={'host':'192.0.2.1','remote_root':'/srv/shiyue','public_domain':'rynenglish.com'}
        with patch.object(manager,'ensure_remote_https_entry',return_value={'frontendUrl':'https://rynenglish.com'}), \
                patch.object(manager,'ensure_remote_saas_config') as config:
            result=manager.configure_existing_https_entry(Mock(),remote,target)
            self.assertTrue(result['applicationCodePreserved'])
            self.assertEqual(config.call_args.args[2]['runtime_image'],image)
        self.assertFalse(any('docker stop' in call.args[0] for call in remote.ssh.call_args_list))

    def test_failed_application_restart_restores_env_and_original_container(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            env=root/'shared/config/saas.env'
            env.parent.mkdir(parents=True)
            original='SESSION_SECRET=private-test\nAPP_BASE_URL=https://old.example.com\n'
            env.write_text(original)
            executable=root/'bin/docker'
            executable.parent.mkdir()
            executable.write_text("""#!/bin/bash
set -e
case "$1" in
  stop) touch "$FAKE_ROOT/stopped";;
  rename) if [ "$2" = shiyue-saas ]; then touch "$FAKE_ROOT/renamed"; else touch "$FAKE_ROOT/restored"; fi;;
  run) exit 7;;
  inspect) test -f "$FAKE_ROOT/renamed";;
  start) touch "$FAKE_ROOT/started";;
  rm) :;;
  *) exit 3;;
esac
""")
            executable.chmod(0o755)
            script_env={**os.environ,'PATH':str(executable.parent)+os.pathsep+os.environ['PATH'],'FAKE_ROOT':str(root)}
            calls=[]
            def ssh(script):
                calls.append(script)
                if 'SHIYUE_BASE_URL=' in script:return 'sha256:'+'a'*64+'\nSHIYUE_BASE_URL=https://old.example.com\n'
                if 'container.json' in script:
                    backup=root/'edge/backups/entry-test'
                    backup.mkdir(parents=True)
                    (backup/'saas.env').write_text(env.read_text())
                    return ''
                return subprocess.run(['bash','-c',script],env=script_env,check=True,capture_output=True,text=True).stdout
            def update(*args):
                env.write_text(original.replace('https://old.example.com','https://rynenglish.com'))
            with patch.object(manager,'ensure_remote_https_entry',return_value={}), \
                    patch.object(manager,'entry_paths',return_value={'state_root':str(root/'edge')}), \
                    patch.object(manager,'new_release_id',return_value='entry-test'), \
                    patch.object(manager,'ensure_remote_saas_config',side_effect=update):
                with self.assertRaises(subprocess.CalledProcessError):
                    manager.configure_existing_https_entry(Mock(),Mock(ssh=ssh),{
                        'host':'192.0.2.1','remote_root':str(root),'public_domain':'rynenglish.com'})
            self.assertEqual(env.read_text(),original)
            self.assertTrue((root/'restored').is_file())
            self.assertTrue((root/'started').is_file())


if __name__ == '__main__':
    unittest.main()
