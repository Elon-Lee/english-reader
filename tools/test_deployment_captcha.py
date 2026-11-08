import os
import shutil
import subprocess
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from deployment.captcha import build_assets, install_script
from deployment import manager


class CaptchaDeploymentTests(unittest.TestCase):
    def run_jdk_check(self, root, version=None, managed=False):
        script = root / 'services/captcha/build.sh'
        script.parent.mkdir(parents=True)
        shutil.copyfile(manager.ROOT / 'services/captcha/build.sh', script)
        java_home = root / ('.local/captcha-tools/jdk' if managed else 'test jdk')
        if version is not None:
            (java_home / 'bin').mkdir(parents=True)
            for command in ('java', 'javac'):
                executable = java_home / 'bin' / command
                executable.write_text(f'#!/bin/sh\nprintf "%s\\n" "{command} {version}.0.1"\n')
                executable.chmod(0o700)
        environment = {**os.environ, 'JAVA_HOME': str(java_home), 'MAVEN_BIN': str(root / 'maven-must-not-run')}
        if managed:
            environment.pop('JAVA_HOME')
        return subprocess.run(['sh', str(script), '--check'], env=environment, capture_output=True, text=True)

    def test_missing_jdk_fails_before_maven_download_or_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_jdk_check(Path(folder))
            self.assertEqual(result.returncode, 2)
            self.assertIn('CAPTCHA_JDK_ERROR:', result.stderr)
            self.assertIn('java 和 javac', result.stderr)
            self.assertNotIn('Maven:', result.stdout)

    def test_old_jdk_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_jdk_check(Path(folder), 8)
            self.assertEqual(result.returncode, 2)
            self.assertIn('版本过低', result.stderr)

    def test_explicit_and_managed_jdk_pass_without_running_maven(self):
        for version, managed in ((17, False), (21, True)):
            with self.subTest(version=version, managed=managed), tempfile.TemporaryDirectory() as folder:
                result = self.run_jdk_check(Path(folder), version, managed)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'JDK: javac {version}', result.stdout)

    def test_job_failure_shows_missing_jdk_reason(self):
        result = subprocess.CompletedProcess([], 2, '', 'CAPTCHA_JDK_ERROR: 请安装 JDK 17 或以上版本\n')
        with patch('deployment.captcha.subprocess.run', return_value=result):
            with self.assertRaisesRegex(ValueError, '请安装 JDK 17'):
                build_assets(Mock(), manager.ROOT)

    def test_saas_environment_is_data_not_shell(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "shared/config"
            config.mkdir(parents=True)
            password = "literal-$undefined-$(echo forbidden)"
            (config / "saas.env").write_text("POSTGRES_DB=test_db\nPOSTGRES_USER=test_user\nPOSTGRES_PASSWORD=" + password + "\nREDIS_PASSWORD=redis-test\nSMTP_FROM_NAME=Ryn English\nSMTP_PASSWORD=$(exit 70)\n")
            docker = root / "docker"
            docker.write_text("#!/usr/bin/env python3\nimport os,sys,subprocess\na=sys.argv[1:]\nif a[:2]==['image','inspect']:sys.exit(0)\np=a[a.index('--env-file')+1]\ne=dict(line.split('=',1) for line in open(p).read().splitlines() if '=' in line)\nsys.exit(subprocess.run([sys.executable,'-c',a[-1]],env={**os.environ,**e}).returncode)\n")
            docker.chmod(0o700)
            script = manager.saas_shell_environment(str(root)) + '\nprintf "%s" "$POSTGRES_PASSWORD"\n'
            import os
            result = subprocess.run(["bash", "-euo", "pipefail", "-c", script], env={**os.environ, "PATH": str(root) + ":" + os.environ["PATH"]}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, password)

    def test_script_preserves_secrets_and_isolates_java(self):
        script = install_script({"remote_root": "/srv/shiyue"}, "code-test-release", "shiyue-saas-runtime:20261012-1")
        subprocess.run(["bash", "-n"], input=script, text=True, check=True)
        self.assertIn("secrets.token_urlsafe", script)
        self.assertIn("--env-file", script)
        self.assertIn("shared/config/captcha.env", script)
        self.assertIn("--memory 512m", script)
        self.assertIn("--cap-drop ALL", script)
        self.assertIn("SERVER_PORT=18081", script)
        self.assertIn("/health", script)
        self.assertNotIn("SMTP_PASSWORD=", script)

    def test_generated_secret_files_preserve_existing_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = root / "saas.env"
            env.write_text("SESSION_SECRET=preserve-test-value\nSMTP_HOST=smtp.example.test\n")
            script = install_script({"remote_root": "/srv/shiyue"}, "code-test", "runtime")
            first = script.split("\nif ! docker image", 1)[0].split("\n", 1)[1]
            code = shlex.split(first)[-1].replace("/config/", str(root) + "/")
            subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)
            values = dict(line.split("=", 1) for line in env.read_text().splitlines())
            self.assertEqual(values["SESSION_SECRET"], "preserve-test-value")
            self.assertGreaterEqual(len(values["SHIYUE_CAPTCHA_SECRET"]), 32)
            self.assertEqual((root / "captcha.env").read_text(), "SHIYUE_CAPTCHA_SECRET=" + values["SHIYUE_CAPTCHA_SECRET"] + "\n")
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)
            subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)
            self.assertEqual(values["SHIYUE_CAPTCHA_SECRET"], dict(line.split("=", 1) for line in env.read_text().splitlines())["SHIYUE_CAPTCHA_SECRET"])


if __name__ == "__main__":
    unittest.main()
