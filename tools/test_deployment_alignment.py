"""Deployment must prove original-audio processing works before promotion."""
import inspect
import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import forced_aligner_setup as setup
from deployment import alignment, manager
from test_deployment_release_pipeline import SyntaxRemote


class DeploymentAlignmentTests(unittest.TestCase):
    def test_reuses_verified_persistent_environment_without_download(self):
        remote = Mock()
        remote.ssh.return_value = 'SHIYUE_ALIGNER_REUSED'
        with patch.object(alignment, 'prepare_bundle') as prepare:
            alignment.ensure_remote(Mock(), remote, {'remote_root': '/srv/test'}, 'code-test', 'runtime', Path('/tmp'))
        prepare.assert_not_called()
        remote.scp.assert_not_called()
        command = remote.ssh.call_args.args[0]
        self.assertIn('--network none', command)
        self.assertIn('/srv/test/shared/.local:/app/.local', command)

    def test_fresh_or_broken_node_installs_offline_with_digest_check(self):
        remote = Mock()
        remote.ssh.side_effect = ['', 'x86_64', setup.READY]
        target = {'remote_root': '/srv/test path'}
        with patch.object(alignment, 'prepare_bundle', return_value=(Path('/tmp/aligner.tar'), 'a' * 64)):
            alignment.ensure_remote(Mock(), remote, target, 'code-test', 'runtime', Path('/tmp'))
        script = remote.ssh.call_args.args[0]
        subprocess.run(['bash', '-n'], input=script, text=True, check=True)
        self.assertIn('sha256sum', script)
        self.assertIn('--offline-dir /artifacts', script)
        self.assertIn('--network none', script)
        self.assertNotIn('pip install', script)
        remote.scp.assert_called_once()

    def test_installer_failure_stops_deployment(self):
        remote = Mock()
        remote.ssh.side_effect = ['', 'aarch64', 'installer failed']
        with patch.object(alignment, 'prepare_bundle', return_value=(Path('/tmp/aligner.tar'), 'a' * 64)):
            with self.assertRaisesRegex(ValueError, '停止部署'):
                alignment.ensure_remote(Mock(), remote, {'remote_root': '/srv/test'}, 'code-test', 'runtime', Path('/tmp'))

    def test_bad_candidate_never_switches_current_or_stops_production(self):
        class FailedCandidate(SyntaxRemote):
            def ssh(self, script):
                if 'forced_aligner_setup.py --root /app --check' in script:
                    self.scripts.append(script)
                    raise RuntimeError('inference failed')
                return super().ssh(script)
        remote = FailedCandidate()
        with self.assertRaisesRegex(RuntimeError, 'inference failed'):
            manager.activate_saas_release(Mock(), remote, {'remote_root': '/srv/test', 'install_recording': False}, 'code-test')
        self.assertEqual(len(remote.scripts), 1)
        self.assertNotIn('ln -sfn', remote.scripts[0])
        self.assertNotIn('docker rm -f shiyue-saas shiyue-saas-frontend', remote.scripts[0])

    def test_new_install_reinstall_and_upgrade_all_provision_before_activation(self):
        for function in (manager.start_saas_deploy, manager.start_saas_upgrade):
            source = inspect.getsource(function)
            self.assertLess(source.index('ensure_remote_aligner('), source.index('activate_saas_release('))
        self.assertIn('install_forced_aligner.sh', [p.name for p in manager.code_files()])
        self.assertIn('forced_aligner_setup.py', [p.name for p in manager.code_files()])

    def test_offline_bundle_rejects_corrupt_model_and_wheel(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / setup.MODEL_FILE).write_bytes(b'model')
            wheel = directory / 'torch.whl'
            wheel.write_bytes(b'wheel')
            model_hash = setup.sha256(directory / setup.MODEL_FILE)
            manifest = {'modelSha256': model_hash, 'files': {setup.MODEL_FILE: model_hash, 'torch.whl': setup.sha256(wheel)}}
            (directory / 'manifest.json').write_text(json.dumps(manifest))
            with patch.object(setup, 'MODEL_SHA256', model_hash):
                setup.validate_bundle(directory)
                wheel.write_bytes(b'truncated')
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    setup.validate_bundle(directory)
                wheel.write_bytes(b'wheel')
                (directory / setup.MODEL_FILE).write_bytes(b'broken')
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    setup.validate_bundle(directory)

    def test_package_embeds_cached_symlink_target_instead_of_local_absolute_link(self):
        with tempfile.TemporaryDirectory() as temp:
            cache=Path(temp)
            directory=cache/'aligner-cp311-x86_64'
            directory.mkdir()
            original=cache/'model.pth';original.write_bytes(b'model')
            (directory/setup.MODEL_FILE).symlink_to(original)
            (directory/'torch.whl').write_bytes(b'wheel')
            (directory/'manifest.json').write_text(json.dumps({'files':{setup.MODEL_FILE:'hash','torch.whl':'hash'}}))
            with patch.object(alignment,'validate_bundle'):
                archive,_=alignment.prepare_bundle(Mock(),cache,'x86_64')
            with tarfile.open(archive) as bundle:
                self.assertTrue(bundle.getmember(setup.MODEL_FILE).isfile())
                self.assertEqual(bundle.extractfile(setup.MODEL_FILE).read(),b'model')
    def test_failed_replacement_preserves_previous_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / '.local/forced-aligner'
            previous = base / 'venv/keep'
            previous.parent.mkdir(parents=True)
            previous.write_text('previous environment')
            checkpoint = base / 'models/hub/checkpoints' / setup.MODEL_FILE
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_bytes(b'model')
            with patch.object(setup.sys, 'version_info', (3, 11)), \
                 patch.object(setup, 'MODEL_SHA256', setup.sha256(checkpoint)), \
                 patch.object(setup, 'check', side_effect=ValueError('broken')), \
                 patch.object(setup, 'validate_bundle'), \
                 patch.object(setup.subprocess, 'run', side_effect=RuntimeError('pip failed')):
                with self.assertRaisesRegex(RuntimeError, 'pip failed'):
                    setup.install(root, root)
            self.assertEqual(previous.read_text(), 'previous environment')
            self.assertEqual(list(base.glob('runtime-*')), [])


if __name__ == '__main__':
    unittest.main()
