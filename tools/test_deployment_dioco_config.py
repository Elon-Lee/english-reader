#!/usr/bin/env python3
import inspect
import json
import tempfile
import unittest
from pathlib import Path

from deployment import manager


class FakeJob:
    def __init__(self):self.lines=[]
    def write(self,value):self.lines.append(str(value))


class FakeRemote:
    def __init__(self,configured=False):
        self.configured=configured;self.commands=[];self.uploaded=None;self.remote_path=None
    def ssh(self,script):
        self.commands.append(script)
        if "SHIYUE_DIOCO_CONFIGURED" in script and self.configured:return "SHIYUE_DIOCO_CONFIGURED\n"
        return ""
    def scp(self,local,remote):
        self.uploaded=json.loads(Path(local).read_text());self.remote_path=remote


class DeploymentDiocoConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old_private=manager.PRIVATE_CONFIG
        manager.PRIVATE_CONFIG=Path(self.temp.name)/".dioco.local.json"

    def tearDown(self):
        manager.PRIVATE_CONFIG=self.old_private;self.temp.cleanup()

    def write_config(self):
        manager.PRIVATE_CONFIG.write_text(json.dumps({"userEmail":"reader@example.com","diocoToken":"secret-token"}))

    def test_empty_remote_receives_local_credentials_without_logging_values(self):
        self.write_config();job=FakeJob();remote=FakeRemote(False)
        result=manager.sync_remote_private_config(job,remote,{"id":3,"remote_root":"/srv/shiyue"})
        self.assertTrue(result["uploaded"]);self.assertEqual(remote.uploaded["diocoToken"],"secret-token")
        log="\n".join(job.lines+remote.commands)
        self.assertNotIn("secret-token",log);self.assertNotIn("reader@example.com",log)

    def test_existing_remote_credentials_are_preserved(self):
        self.write_config();job=FakeJob();remote=FakeRemote(True)
        result=manager.sync_remote_private_config(job,remote,{"id":3,"remote_root":"/srv/shiyue"})
        self.assertFalse(result["uploaded"]);self.assertEqual(result["source"],"remote");self.assertIsNone(remote.uploaded)

    def test_all_remote_update_flows_repair_missing_credentials(self):
        for function in (manager.start_deploy,manager.start_upgrade,manager.start_sync):
            self.assertIn("sync_remote_private_config",inspect.getsource(function))
        self.assertIn("remote_dioco_check",inspect.getsource(manager.start_deploy))
        self.assertIn("remote_dioco_check",inspect.getsource(manager.start_upgrade))
        self.assertIn("remote_dioco_check",inspect.getsource(manager.start_sync))


if __name__=="__main__":unittest.main()
