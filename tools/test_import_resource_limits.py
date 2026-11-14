"""Import memory controls must protect the API and include subprocesses."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from import_resource_limits import ImportLimits, MemoryCgroup, run_limited
from saas_auth import SaaSError
from deployment import manager


class ImportResourceLimitTests(unittest.TestCase):
    def test_local_is_unlimited_and_bad_values_fail_closed(self):
        self.assertFalse(ImportLimits.from_environment({}).enabled)
        self.assertFalse(ImportLimits.from_environment({'SHIYUE_IMPORT_MEMORY_MB': '0'}).enabled)
        self.assertEqual(ImportLimits.from_environment({'SHIYUE_IMPORT_MEMORY_MB': '1024'}).memory_mb, 1024)
        for values in ({'SHIYUE_IMPORT_MEMORY_MB': '-1'}, {'SHIYUE_IMPORT_MEMORY_MB': 'garbage'},
                       {'SHIYUE_IMPORT_MEMORY_MB': '12'}, {'SHIYUE_IMPORT_SWAP_MB': '-1'},
                       {'SHIYUE_IMPORT_THREADS': '0'}):
            with self.subTest(values=values), self.assertRaises(SaaSError):
                ImportLimits.from_environment(values)

    def group(self, path, v2=False):
        files = {'cgroup.procs': '', 'memory.max': 'max', 'memory.swap.max': 'max',
                 'memory.high': 'max', 'memory.oom.group': '0', 'memory.events': 'oom 2\noom_kill 1\nmax 5\n'} if v2 else {
            'cgroup.procs': '', 'memory.limit_in_bytes': str(1 << 60),
            'memory.memsw.limit_in_bytes': str(1 << 60), 'memory.oom_control': '0',
            'memory.failcnt': '0', 'memory.memsw.failcnt': '0'}
        for name, value in files.items():
            (path / name).write_text(value)
        return MemoryCgroup(path)

    def test_v1_limits_ram_and_total_memory_and_rejects_live_group(self):
        with tempfile.TemporaryDirectory() as folder, patch('import_resource_limits.sys.platform', 'linux'):
            group = self.group(Path(folder))
            group.configure(ImportLimits(512, 128))
            self.assertEqual((Path(folder) / 'memory.memsw.limit_in_bytes').read_text(), str(640 * 1024**2))
            # Both increase and decrease maintain the kernel's RAM <= memsw rule.
            group.configure(ImportLimits(1024, 256))
            group.configure(ImportLimits(256, 0))
            self.assertEqual(group.counters(), (0, 0))
            (Path(folder) / 'cgroup.procs').write_text('999999')
            with self.assertRaises(OSError):
                group.configure(ImportLimits(512, 128))

    def test_v2_uses_pressure_high_limit_and_separate_swap_budget(self):
        with tempfile.TemporaryDirectory() as folder, patch('import_resource_limits.sys.platform', 'linux'):
            group = self.group(Path(folder), True)
            group.configure(ImportLimits(512, 128))
            self.assertEqual((Path(folder) / 'memory.swap.max').read_text(), str(128 * 1024**2))
            self.assertEqual((Path(folder) / 'memory.oom.group').read_text(), '1')
            self.assertEqual(group.counters(), (5, 2, 1))

    def test_missing_swap_controller_never_falls_back_to_unlimited(self):
        with tempfile.TemporaryDirectory() as folder, patch('import_resource_limits.sys.platform', 'linux'):
            group = self.group(Path(folder))
            (Path(folder) / 'memory.memsw.limit_in_bytes').unlink()
            with self.assertRaises(OSError):
                group.configure(ImportLimits(512, 128))
            self.assertFalse((Path(folder) / 'memory.memsw.limit_in_bytes').exists())

    def test_kill_cleans_descendants_but_refuses_to_kill_api(self):
        group = MemoryCgroup('/unused')
        with patch.object(group, 'pids', side_effect=[[12345, 12346], []]), patch('import_resource_limits.os.kill') as kill:
            group.kill_all()
            self.assertEqual(kill.call_count, 2)
        with patch.object(group, 'pids', return_value=[os.getpid()]), self.assertRaises(RuntimeError):
            group.kill_all()

    def test_setup_failure_is_persisted_without_starting_a_processor(self):
        service = Mock()
        with patch('import_resource_limits._run_limited', side_effect=SaaSError('import_limit_unavailable', '隔离不可用', 503)), \
                patch('import_resource_limits._cleanup_narration_staging'), \
                self.assertRaises(SaaSError):
            run_limited(service, 'user', 'task', ImportLimits(512, 128))
        service.fail.assert_called_once_with('user', 'task', '隔离不可用')

    def test_remote_mount_delegates_only_import_group_and_shell_is_valid(self):
        command = manager.saas_app_run_command({'remote_root': '/srv/shiyue', 'install_recording': False}, '/srv/shiyue/current')
        subprocess.run(['bash', '-n'], input=command, text=True, check=True)
        self.assertIn(':/run/shiyue-import-cgroup:rw', command)
        self.assertNotIn('--privileged', command)
        self.assertNotIn('docker.sock', command)
        self.assertIn('SHIYUE_IMPORT_DISPATCHER=1',command)
        candidate=manager.saas_app_run_command({'remote_root':'/srv/shiyue','install_recording':False},'/srv/shiyue/candidate',name='shiyue-saas-candidate')
        self.assertIn('SHIYUE_IMPORT_DISPATCHER=0',candidate)

    def test_upgrade_adds_defaults_and_preserves_explicit_limit_and_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'saas.env'
            path.write_text('SESSION_SECRET=keep\nSHIYUE_IMPORT_MEMORY_MB=768\nSHIYUE_IMPORT_SWAP_MB=0\n')
            scripts = []
            remote = Mock()
            def ssh(script):
                scripts.append(script)
                if len(scripts) == 1:
                    return 'SHIYUE_SAAS_ENV_READY'
                code = shlex.split(script)[-1].replace("Path('/config/saas.env')", 'Path(' + repr(str(path)) + ')')
                exec(compile(code, '<remote-config>', 'exec'), {})
                return ''
            remote.ssh.side_effect = ssh
            manager.ensure_remote_saas_config(Mock(), remote, {'remote_root': '/srv/shiyue', 'host': '192.0.2.1', 'use_https': True})
            text = path.read_text()
            self.assertIn('SESSION_SECRET=keep\n', text)
            self.assertIn('SHIYUE_IMPORT_MEMORY_MB=768\n', text)
            self.assertIn('SHIYUE_IMPORT_SWAP_MB=0\n', text)
            self.assertIn('SHIYUE_IMPORT_THREADS=1\n', text)
            self.assertNotIn('SHIYUE_IMPORT_MEMORY_MB=1024', text)


if __name__ == '__main__':
    unittest.main()
