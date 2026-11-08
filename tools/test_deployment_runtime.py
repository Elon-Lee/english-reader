"""A first install must work without legacy containers, images or vendored models."""
import gzip
import hashlib
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

from deployment import manager, runtime


class RuntimeBootstrapTests(unittest.TestCase):
    def test_verified_download_rejects_corrupt_bytes_without_replacing_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'dependency.bin'
            path.write_bytes(b'old')
            with patch.object(runtime.urllib.request, 'urlopen', return_value=io.BytesIO(b'wrong')):
                with self.assertRaisesRegex(ValueError, 'SHA-256'):
                    runtime.download_verified('https://example.test/file', path, hashlib.sha256(b'correct').hexdigest())
            self.assertEqual(path.read_bytes(), b'old')
            self.assertEqual(list(Path(temp).iterdir()), [path])

    def test_verified_cache_does_not_download_again(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'model.bin'
            path.write_bytes(b'valid')
            with patch.object(runtime.urllib.request, 'urlopen') as download:
                self.assertEqual(runtime.download_verified('unused', path, runtime.digest(path)), path)
            download.assert_not_called()

    def test_verified_download_replaces_corrupt_cache_only_after_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'dependency.bin';path.write_bytes(b'old')
            with patch.object(runtime.urllib.request, 'urlopen', return_value=io.BytesIO(b'correct')):
                runtime.download_verified('https://example.test/file', path, hashlib.sha256(b'correct').hexdigest())
            self.assertEqual(path.read_bytes(), b'correct')
            self.assertEqual(list(Path(temp).iterdir()), [path])

    def test_model_cache_does_not_overwrite_existing_vendor_model(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);legacy=root/'tools/vendor/whisper.cpp/models/ggml-base.en.bin'
            legacy.parent.mkdir(parents=True);legacy.write_bytes(b'custom model')
            with patch.object(runtime,'download_verified',return_value=root/'cached') as download:
                runtime.prepare_model(Mock(),root)
            self.assertEqual(download.call_args.args[1],root/'.local/deployment/runtime/models/ggml-base.en.bin')
            self.assertEqual(legacy.read_bytes(),b'custom model')

    def test_build_context_contains_only_pinned_source_and_dockerfile(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dockerfile = root / 'deployment/docker/Dockerfile.runtime'
            dockerfile.parent.mkdir(parents=True);dockerfile.write_text('FROM test\n')
            (root / '.env').write_text('PRIVATE=must-not-upload')
            source = root / 'source.tar.gz'
            with tarfile.open(source, 'w:gz') as archive:
                for name in ('whisper.cpp-' + runtime.WHISPER_VERSION + '/CMakeLists.txt', 'other/private', 'whisper.cpp-' + runtime.WHISPER_VERSION + '/../escape'):
                    data = b'cmake';info = tarfile.TarInfo(name);info.size = len(data);archive.addfile(info, io.BytesIO(data))
            with patch.object(runtime, 'download_verified', return_value=source):
                context, checksum = runtime.prepare_context(Mock(), root, root)
            self.assertEqual(checksum, runtime.digest(context))
            with tarfile.open(context) as archive:
                self.assertEqual(set(archive.getnames()), {'Dockerfile', 'whisper.cpp/CMakeLists.txt'})

    def test_fresh_build_script_uses_digest_platform_and_executable_probe(self):
        with patch.object(runtime, 'prepare_context', return_value=(Path('/tmp/context.tar.gz'), 'a' * 64)):
            remote = Mock()
            runtime.build(Mock(), remote, Path('/project'), Path('/cache'), manager.RUNTIME_IMAGE, 'amd64')
        script = remote.ssh.call_args.args[0]
        subprocess.run(['bash', '-n'], input=script, text=True, check=True)
        self.assertIn('--platform linux/amd64', script)
        self.assertIn('sha256sum', script)
        self.assertIn('whisper-cli --help', script)
        self.assertNotIn('docker inspect -f', script)

    def test_empty_node_builds_without_exporting_image_back_to_local(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'runtime.tar.gz'
            remote = Mock();remote.ssh.return_value = ''
            with patch.object(manager, 'runtime_archive', return_value=archive), patch.object(manager, 'build_remote_runtime') as build:
                self.assertIsNone(manager.ensure_remote_runtime(Mock(), remote, 'amd64'))
            build.assert_called_once()
            self.assertFalse(archive.exists())
            remote.scp.assert_not_called();remote.scp_from.assert_not_called()

    def test_failed_build_stops_install_without_creating_runtime_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'runtime.tar.gz'
            remote = Mock();remote.ssh.return_value = ''
            with patch.object(manager, 'runtime_archive', return_value=archive), patch.object(manager, 'build_remote_runtime',side_effect=RuntimeError('build failed')):
                with self.assertRaisesRegex(RuntimeError,'build failed'):manager.ensure_remote_runtime(Mock(), remote, 'amd64')
            self.assertFalse(archive.exists())
            self.assertFalse(archive.with_suffix('.gz.partial').exists())

    def test_existing_runtime_is_exported_without_building(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'runtime.tar.gz';archive.write_bytes(b'cache')
            remote = Mock();remote.ssh.return_value = 'SHIYUE_RUNTIME_READY'
            with patch.object(manager, 'runtime_archive', return_value=archive), patch.object(manager, 'build_remote_runtime') as build:
                manager.ensure_remote_runtime(Mock(), remote, 'amd64')
            build.assert_not_called();remote.scp_from.assert_not_called()

    def test_ready_runtime_without_local_cache_does_not_delay_install(self):
        with tempfile.TemporaryDirectory() as temp:
            remote=Mock();remote.ssh.return_value='SHIYUE_RUNTIME_READY'
            with patch.object(manager,'runtime_archive',return_value=Path(temp)/'absent.tar.gz'),patch.object(manager,'build_remote_runtime') as build:
                self.assertIsNone(manager.ensure_remote_runtime(Mock(),remote,'amd64'))
            build.assert_not_called();remote.scp_from.assert_not_called()

    def test_new_node_loads_offline_cache_without_source_download(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'runtime.tar.gz'
            with gzip.open(archive, 'wb', compresslevel=0) as output:
                for _ in range(21):output.write(b'x' * 1024 * 1024)
            remote = Mock();remote.ssh.return_value = ''
            with patch.object(manager, 'runtime_archive', return_value=archive), patch.object(manager, 'build_remote_runtime') as build:
                manager.ensure_remote_runtime(Mock(), remote, 'amd64')
            build.assert_not_called()
            remote.scp.assert_called_once_with(archive, '/tmp/runtime.tar.gz')
            self.assertIn('docker load', remote.ssh.call_args.args[0])

    def test_model_preflight_failure_prevents_redeploy_uninstall(self):
        target = {'id': 1, 'install_recording': True}
        with patch.object(manager, 'run_task', side_effect=lambda _kind, worker, _id: worker(Mock(), Mock(), target)), \
                patch.object(manager, 'saas_https_target', return_value=target), \
                patch.object(manager, 'build_code_package', return_value=(Path('/tmp/code'), 'a' * 64)), \
                patch.object(manager, 'build_saas_database_dump', return_value=(Path('/tmp/dump'), 'b' * 64)), \
                patch.object(manager, 'prepare_whisper_model', side_effect=ValueError('模型校验失败')), \
                patch.object(manager, 'uninstall_saas_for_redeploy') as uninstall:
            with self.assertRaisesRegex(ValueError, '模型校验失败'):manager.start_saas_deploy(1, reinstall=True)
        uninstall.assert_not_called()


if __name__ == '__main__':unittest.main()
