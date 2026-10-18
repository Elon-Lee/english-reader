#!/usr/bin/env python3
import inspect,json,subprocess,sys,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

from deployment import manager
import deploy_remote


class Job:
    def update(self,*_args,**_kwargs):pass
    def write(self,*_args,**_kwargs):pass


class SyntaxRemote:
    def __init__(self):self.scripts=[]
    def ssh(self,script):
        subprocess.run(["bash","-n"],input=script,text=True,check=True);self.scripts.append(script)
        if "SHIYUE_SAAS_BACKUP_READY" in script:return "SHIYUE_SAAS_BACKUP_READY deadbeef\n"
        if "SHIYUE_SAAS_UPGRADE_READY" in script:return "SHIYUE_SAAS_UPGRADE_READY\n"
        return "SHIYUE_DATABASE_RESTORED\nSHIYUE_SAAS_READY\n"
    def scp(self,*_args,**_kwargs):pass


class DeploymentReleasePipelineTests(unittest.TestCase):
    def test_frontend_build_runs_production_script_and_checks_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"package.json").write_text("{}")
            for path in (root/"reader/site/index.html",root/"reader/site/assets/index.js",root/"reader/site/assets/index.css"):
                path.parent.mkdir(parents=True,exist_ok=True);path.write_text("ok")
            completed=type("Completed",(),{"returncode":0,"stdout":"built\n","stderr":""})()
            with patch.object(manager,"ROOT",root),patch.object(manager.subprocess,"run",return_value=completed) as run:
                manager.build_frontend_assets(Job())
            self.assertEqual(run.call_args.args[0],["npm","run","build:modern"])
            self.assertEqual(run.call_args.kwargs["cwd"],root)

    def test_release_package_contains_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"repo";state=Path(temp)/"state";source=root/"reader/site/index.html";source.parent.mkdir(parents=True);source.write_text("ok");legacy=root/"reader/modern-assets/assets/index.js";legacy.parent.mkdir(parents=True);legacy.write_text("legacy")
            with patch.object(manager,"ROOT",root),patch.object(manager,"STATE",state),patch.object(manager,"build_frontend_assets"),patch.object(manager,"code_files",return_value=[root/"reader"]),patch.object(manager,"release_metadata",return_value={"releaseId":"code-20261012-120000-abcdef12","packageFormat":2}):
                package,digest=manager.build_code_package(Job(),"code-20261012-120000-abcdef12")
            self.assertEqual(len(digest),64)
            with tarfile.open(package,"r:gz") as archive:
                self.assertFalse(any(name=="reader/modern-assets" or name.startswith("reader/modern-assets/") for name in archive.getnames()))
                metadata=json.load(archive.extractfile(".shiyue-release.json"))
            self.assertEqual(metadata["packageFormat"],2)

    def test_bootstrap_verifies_digest_and_required_modern_assets(self):
        target={"remote_root":"/srv/shiyue","service_port":8765,"install_recording":False,"use_https":False}
        script=manager.bootstrap_script(target,"code-20261012-120000-abcdef12","code-20261012-120000-abcdef12.tar.gz","a"*64)
        self.assertIn('sha256sum "$archive"',script)
        self.assertIn("reader/site/assets/index.js",script)
        self.assertIn(".shiyue-release.json",script)

    def test_saas_runtime_uses_root_site_and_persistent_services(self):
        target={"remote_root":"/srv/shiyue","service_port":8765,"install_recording":True,"use_https":False}
        command=manager.saas_app_run_command(target,"/srv/shiyue/current")
        self.assertIn("SHIYUE_RUNTIME_MODE=saas",command)
        self.assertIn("/current/reader:/app/reader:ro",command)
        self.assertIn("saas.env",command)
        self.assertIn("shiyue-saas-runtime",command)
        self.assertEqual(manager.POSTGRES_IMAGE,"postgres:16-bookworm")
        self.assertEqual(manager.REDIS_IMAGE,"redis:7-bookworm")
        self.assertIn("m.daocloud.io/docker.io/library",__import__('inspect').getsource(manager.ensure_remote_saas_services))

    def test_generated_saas_remote_scripts_are_valid_bash(self):
        target={"id":1,"host":"127.0.0.1","remote_root":"/srv/shiyue","service_port":8765,"install_recording":False,"use_https":False}
        remote=SyntaxRemote();job=Job();release="code-20261012-120000-abcdef12";package=release+".tar.gz";digest="a"*64
        manager.prepare_remote_saas_release(remote,target,release,package,digest)
        manager.ensure_remote_saas_services(job,remote,target,release)
        with tempfile.NamedTemporaryFile(suffix=".dump") as dump:
            manager.restore_remote_saas_database(job,remote,target,Path(dump.name),digest)
        manager.prune_initial_database_to_published_content(job,remote,target)
        manager.activate_saas_release(job,remote,target,release)
        self.assertGreaterEqual(len(remote.scripts),6)
        self.assertIn("SHIYUE_MIGRATIONS_READY",remote.scripts[-2])
        self.assertIn("/app/reader",remote.scripts[-2])

    def test_saas_upgrade_has_remote_backup_and_database_validation(self):
        target={"id":1,"remote_root":"/srv/shiyue","service_port":8765,"install_recording":False,"use_https":False}
        remote=SyntaxRemote();job=Job();release="code-20261017-120000-abcdef12"
        backup=manager.backup_remote_saas_database(job,remote,target,release)
        manager.check_remote_saas_upgrade_target(remote,target)
        self.assertEqual(backup,"/srv/shiyue/backups/saas/pre-upgrade-code-20261017-120000-abcdef12.dump")
        self.assertIn("pg_dump",remote.scripts[0])
        self.assertIn("umask 077",remote.scripts[0])
        self.assertIn("SHIYUE_SAAS_UPGRADE_READY",remote.scripts[1])
        self.assertIn("saas.env",manager.saas_app_run_command(target,"/srv/shiyue/candidate"))
        self.assertIn("ensure_migrated",manager.saas_migration_check_command())

    def test_post_activation_verification_resolves_symlinked_mount(self):
        source=inspect.getsource(manager.start_saas_upgrade)
        self.assertIn('readlink -f "$mount_source"',source)
        self.assertIn('"$current_release/reader"',source)

    def test_deployment_http_upgrade_uses_saas_specific_worker(self):
        server=(manager.ROOT/"tools/reader_server.py").read_text()
        self.assertIn('"/api/deployment/saas-upgrade"}:self.reply({"jobId":deployment_manager.start_saas_upgrade(target_id)}',server)

    def test_cli_upgrade_uses_saas_specific_worker(self):
        target={"id":1,"name":"test","host":"localhost","port":22}
        for flags in ([], ["--upgrade"]):
            with self.subTest(flags=flags), patch.object(sys,"argv",["deploy_remote.py","--target","1",*flags]), \
                    patch.object(deploy_remote,"resolve_target",return_value=target), \
                    patch.object(manager,"start_saas_upgrade",return_value=123) as upgrade, \
                    patch.object(manager,"start_upgrade") as legacy, \
                    patch.object(deploy_remote,"follow_job") as follow:
                deploy_remote.main()
                upgrade.assert_called_once_with(1)
                legacy.assert_not_called()
                follow.assert_called_once_with(123,1800)

    def test_public_export_manifest_has_incremental_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);python=root/".local/saas-venv/bin/python";python.parent.mkdir(parents=True);python.write_text("")
            state=root/"state";media=root/"books";media.mkdir();asset=media/"book.mp3";asset.write_bytes(b"audio")
            completed=type("Completed",(),{"stdout":json.dumps({"catalogBooks":1,"files":1,"bytes":5})+"\n"})()
            def fake_run(*_args,**_kwargs):
                bundle=state/"public-test.public.json.gz";manifest=state/"public-test.public.manifest.json";bundle.parent.mkdir(parents=True,exist_ok=True);bundle.write_bytes(b"bundle");manifest.write_text(json.dumps({"files":[{"path":"book.mp3","size":5,"mtime":1}]}));return completed
            with patch.object(manager,"ROOT",root),patch.object(manager,"STATE",state),patch.object(manager,"local_env_values",return_value={"MEDIA_ROOT":str(media)}),patch.object(manager,"local_saas_database_url",return_value="postgresql://test"),patch.object(manager.subprocess,"run",side_effect=fake_run):
                _,_,manifest,_=manager.export_saas_public_content(Job(),"public-test")
            self.assertEqual(json.loads(manifest.read_text())["revision"],"public-test")


if __name__=="__main__":unittest.main()
