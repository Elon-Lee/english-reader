#!/usr/bin/env python3
import inspect,json,sqlite3,tempfile,unittest
from pathlib import Path

from deployment import manager
import import_video_worker

ROOT=Path(__file__).resolve().parents[1]

class VideoQualityVariantTests(unittest.TestCase):
    def test_import_builds_high_and_low_video(self):
        source=inspect.getsource(import_video_worker.import_video)
        self.assertIn('video-muted.mp4',source);self.assertIn('video-low.mp4',source);self.assertIn('libx264',source);self.assertIn('scale=640:360',source);self.assertIn('videoVariants',source);self.assertIn('videoDefaultQuality',source)

    def test_player_defaults_high_and_can_auto_downgrade(self):
        script=(ROOT/'reader/app.js').read_text();html=(ROOT/'reader/index.html').read_text()
        self.assertIn('let videoQuality="high"',script);self.assertIn('switchVideoQuality("low",true,true)',script);self.assertIn('当前显示关键帧',script)
        self.assertIn('id="videoHighBtn"',html);self.assertIn('id="videoLowBtn"',html);self.assertIn('id="videoStatusOverlay"',html)
        self.assertNotIn('id="framesViewBtn"',html);self.assertNotIn('id="videoViewBtn"',html)
        self.assertGreater(html.index('id="closeStackLayoutBtn"'),html.index('id="videoQualitySwitch"'))

    def test_sync_exports_all_video_variants(self):
        source=inspect.getsource(manager.export_content)
        self.assertIn('videoVariants',source)

if __name__=='__main__':unittest.main()
