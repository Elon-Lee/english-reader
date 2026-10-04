#!/usr/bin/env python3
import inspect
import unittest

from deployment import manager

class DockerInstallScriptTests(unittest.TestCase):
    def test_one_click_deploy_contains_centos_docker_ce_flow(self):
        source=inspect.getsource(manager.ensure_remote_docker)
        for command in (
            "yum install -y yum-utils",
            "yum-config-manager --add-repo http://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo",
            "yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo",
            "yum makecache fast",
            "yum install -y docker-ce docker-ce-cli containerd.io",
            "systemctl start docker",
            "systemctl enable docker",
        ):
            self.assertIn(command,source)

    def test_deploy_flow_calls_docker_initialization_before_runtime(self):
        source=inspect.getsource(manager.start_deploy)
        self.assertLess(source.index("ensure_remote_docker"),source.index("ensure_remote_runtime"))

if __name__=="__main__":unittest.main()
