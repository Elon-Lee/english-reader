#!/usr/bin/env python3
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MobileReaderPresentationTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "reader/index.html").read_text()
        self.script = (ROOT / "reader/app.js").read_text()
        self.styles = (ROOT / "reader/responsive.css").read_text()

    def test_mobile_assets_and_safe_area_are_enabled(self):
        self.assertIn("viewport-fit=cover", self.html)
        self.assertIn("responsive.css?v=20261005-2", self.html)
        self.assertIn("100dvh", self.styles)
        self.assertIn("safe-area-inset-bottom", self.styles)
        self.assertIn("prefers-reduced-motion", self.styles)

    def test_non_reader_pages_hide_reader_content_and_keep_menu_trigger(self):
        self.assertIn('screen-shelf', self.html)
        self.assertIn('body:not(.screen-reader) #reader', self.styles)
        self.assertIn('body:not(.screen-reader) #player', self.styles)
        self.assertIn('.topbar.non-reader .topbar-inner .sidebar-reveal', self.styles)
        self.assertIn('document.body.classList.toggle("screen-reader",reading)', self.script)

    def test_mobile_player_uses_centered_three_button_controls(self):
        self.assertIn('grid-template-areas:"time seek duration" "prev play next"', self.styles)
        self.assertIn('#speedBtn{position:absolute', self.styles)

    def test_mobile_sentence_actions_are_compact_and_aligned(self):
        self.assertIn('vertical-align:baseline', self.styles)
        self.assertIn('min-height:24px', self.styles)
        self.assertIn('touch-action:pan-y', self.styles)

    def test_drawers_have_backdrops_and_touch_detection(self):
        self.assertIn('id="sidebarBackdrop"', self.html)
        self.assertIn('id="mobilePanelBackdrop"', self.html)
        self.assertIn('(hover: none) and (pointer: coarse)', self.script)
        self.assertIn("mobile-nav-open", self.styles)
        self.assertIn("mobile-word-open", self.styles)
        self.assertIn("mobile-review-open", self.styles)

    def test_touch_seek_commits_after_drag(self):
        self.assertIn("seekPreviewDragging", self.script)
        self.assertIn("pendingSeekTime", self.script)
        self.assertIn("commitSeekTime", self.script)
        self.assertIn('addEventListener("pointerup"', self.script)

    def test_html_ids_are_unique(self):
        ids = re.findall(r'\bid="([^"]+)"', self.html)
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        self.assertEqual([], duplicates)


if __name__ == "__main__":
    unittest.main()
