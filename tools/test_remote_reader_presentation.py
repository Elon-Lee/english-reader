#!/usr/bin/env python3
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class RemoteReaderPresentationTests(unittest.TestCase):
    def test_initial_html_uses_neutral_copy(self):
        html=(ROOT/"reader/index.html").read_text()
        self.assertIn('class="runtime-pending"',html)
        self.assertIn('id="brandModeLabel">ENGLISH READER',html)
        self.assertIn('id="settingsModeLabel">READER SETTINGS',html)
        self.assertNotIn('id="brandModeLabel">LOCAL READER',html)

    def test_runtime_copy_has_remote_and_local_variants(self):
        script=(ROOT/"reader/app.js").read_text()
        self.assertIn('remote?"WEB READER":"LOCAL READER"',script)
        self.assertIn('remote?"管理账户、快捷键与阅读体验。"',script)
        self.assertIn("runtimeMode==='reader'?'词级点读':'本地点读'",script)
        self.assertIn('replace("本地词典","内置词典")',script)

    def test_remote_mode_hides_local_only_navigation(self):
        script=(ROOT/"reader/app.js").read_text();styles=(ROOT/"reader/styles.css").read_text()
        self.assertIn("runtimeMode===\"reader\"",script)
        self.assertIn("[data-screen=\"import\"]",styles)
        self.assertIn("#settingsDeploymentTab",styles)

if __name__=="__main__":unittest.main()
