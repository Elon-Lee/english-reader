"""Opt-in real-kernel regression; only a dedicated disposable test group."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from import_resource_limits import ImportLimits, MemoryCgroup

TEST_GROUP = os.environ.get('SHIYUE_IMPORT_LIMIT_TEST_CGROUP', '')


@unittest.skipUnless(sys.platform == 'linux' and TEST_GROUP, 'requires explicit disposable Linux test cgroup')
class LinuxImportLimitTests(unittest.TestCase):
    def test_descendant_oom_is_confined_and_supervisor_survives(self):
        root = Path(TEST_GROUP)
        self.assertTrue(root.name.startswith('shiyue-import-limit-test-'))
        group = MemoryCgroup(root)
        group.configure(ImportLimits(32, 0))
        before = group.counters()
        # The worker itself uses little memory; its child exceeds the budget.
        code = """import json,os,subprocess,sys
from pathlib import Path
(Path(sys.argv[1])/'cgroup.procs').write_text(str(os.getpid()))
child=subprocess.run([sys.executable,'-c','x=bytearray(128*1024*1024)'])
print(json.dumps({'childExit':child.returncode}),flush=True)
"""
        try:
            process = subprocess.run([sys.executable, '-c', code, str(root)],
                                     text=True, capture_output=True, timeout=30)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(process.stdout)['childExit'], -9)
            self.assertNotEqual(group.counters(), before)
            self.assertNotIn(os.getpid(), group.pids())
            group.verify(ImportLimits(32, 0))
        finally:
            group.kill_all()


if __name__ == '__main__':
    unittest.main()
