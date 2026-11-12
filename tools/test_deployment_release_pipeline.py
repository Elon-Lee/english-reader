#!/usr/bin/env python3
import inspect,json,os,shlex,subprocess,sys,tarfile,tempfile,unittest
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
    def test_jdk_failure_stops_before_frontend_build_and_packaging(self):
        with patch.object(manager, 'release_metadata', return_value={}), \
                patch.object(manager, 'build_captcha_assets', side_effect=ValueError('请安装 JDK 17')), \
                patch.object(manager, 'build_frontend_assets') as frontend:
            with self.assertRaisesRegex(ValueError, '请安装 JDK 17'):
                manager.build_code_package(Job(), 'code-test-jdk')
        frontend.assert_not_called()

    def brand_fixture(self,root):
        names=("paper-glow-mark.svg",)
        for name in names:
            path=root/"reader/site/brand"/name
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b"brand")
        (root/"reader/site/index.html").write_text('<title>纸间微光</title>'+''.join('<link href="/brand/'+name+'?v=test">' for name in names))

    def test_frontend_build_runs_production_script_and_checks_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"package.json").write_text("{}")
            required=tuple(f'reader/{site}/{name}' for site in ('site','site-intl') for name in ('index.html','assets/index.js','assets/index.css'))
            for relative in required:
                path=root/relative
                path.parent.mkdir(parents=True,exist_ok=True);path.write_text("ok")
            self.brand_fixture(root)
            completed=type("Completed",(),{"returncode":0,"stdout":"built\n","stderr":""})()
            with patch.object(manager,"ROOT",root),patch.object(manager.subprocess,"run",return_value=completed) as run:
                manager.build_frontend_assets(Job())
            self.assertEqual(run.call_args.args[0],["npm","run","build:sites"])
            self.assertEqual(run.call_args.kwargs["cwd"],root)

    def test_frontend_build_rejects_missing_stylesheet(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"package.json").write_text("{}")
            required=("reader/site/index.html","reader/site/assets/index.js")
            for relative in required:
                path=root/relative
                path.parent.mkdir(parents=True,exist_ok=True);path.write_text("ok")
            self.brand_fixture(root)
            completed=type("Completed",(),{"returncode":0,"stdout":"built\n","stderr":""})()
            with patch.object(manager,"ROOT",root),patch.object(manager.subprocess,"run",return_value=completed):
                with self.assertRaisesRegex(ValueError,"index.css"):
                    manager.build_frontend_assets(Job())

    def test_frontend_build_rejects_missing_brand_and_old_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"package.json").write_text("{}")
            for relative in ("reader/site/assets/index.js","reader/site/assets/index.css"):
                path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b"asset")
            self.brand_fixture(root)
            icon=root/"reader/site/brand/paper-glow-mark.svg";icon.unlink()
            completed=type("Completed",(),{"returncode":0,"stdout":"built\n","stderr":""})()
            with patch.object(manager,"ROOT",root),patch.object(manager.subprocess,"run",return_value=completed):
                with self.assertRaisesRegex(ValueError,"paper-glow-mark.svg"):
                    manager.build_frontend_assets(Job())
                icon.write_bytes(b"brand")
                (root/"reader/site/index.html").write_text('<title>拾页</title>')
                with self.assertRaisesRegex(ValueError,"纸间微光"):
                    manager.build_frontend_assets(Job())

    def test_runtime_package_does_not_include_development_tests(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"tools").mkdir()
            (root/"tools/test_old_payment.py").write_text("historic test")
            (root/"tools/reader_server.py").write_text("runtime")
            with patch.object(manager,"ROOT",root):
                files=manager.code_files()
            self.assertIn(root/"tools/reader_server.py",files)
            self.assertNotIn(root/"tools/test_old_payment.py",files)

    def test_frontend_build_rejects_retired_transaction_routes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"package.json").write_text("{}")
            assets=root/"reader/site/assets";assets.mkdir(parents=True)
            (assets/"index.css").write_text("style")
            (assets/"index.js").write_text('fetch("/api/payments/alipay/orders")')
            self.brand_fixture(root)
            completed=type("Completed",(),{"returncode":0,"stdout":"built\n","stderr":""})()
            with patch.object(manager,"ROOT",root),patch.object(manager.subprocess,"run",return_value=completed):
                with self.assertRaisesRegex(ValueError,"已移除接口"):
                    manager.build_frontend_assets(Job())

    def test_upgrade_config_removes_retired_provider_credentials(self):
        scripts=[]
        remote=type("Remote",(),{"ssh":lambda self,script: scripts.append(script) or ("SHIYUE_SAAS_ENV_READY" if len(scripts)==1 else "")})()
        target={"id":1,"host":"127.0.0.1","remote_root":"/srv/shiyue","service_port":8765,"use_https":False}
        manager.ensure_remote_saas_config(Job(),remote,target)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config=root/"saas.env"
            original="POSTGRES_PASSWORD=keep-secret\nSESSION_SECRET=keep-session\nSMTP_FROM_NAME=Old Brand\nALIPAY_APP_ID=old\nPADDLE_API_KEY=old\nMBDPAY_KEY=old\nCLOUDCAT_KEY=old\nAPP_BASE_URL=https://example.test\n"
            config.write_text(original)
            command=shlex.split(scripts[-1])
            code=command[-1].replace("Path('/config/saas.env')","Path("+repr(str(config))+")")
            exec(code,{"Path":Path})
            updated=config.read_text()
            self.assertIn("POSTGRES_PASSWORD=keep-secret",updated)
            self.assertIn("SESSION_SECRET=keep-session",updated)
            self.assertIn("SMTP_FROM_NAME=纸间微光",updated)
            for prefix in ("ALIPAY_","PADDLE_","MBDPAY_","CLOUDCAT_"):self.assertNotIn(prefix,updated)

    def test_release_package_contains_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"repo";state=Path(temp)/"state";source=root/"reader/site/index.html";source.parent.mkdir(parents=True);source.write_text("ok");legacy=root/"reader/modern-assets/assets/index.js";legacy.parent.mkdir(parents=True);legacy.write_text("legacy")
            (root/"reader/README.md").write_text("development documentation")
            (root/"reader/site/source.js.map").write_text("source map")
            self.brand_fixture(root)
            with patch.object(manager,"ROOT",root),patch.object(manager,"STATE",state),patch.object(manager,"build_frontend_assets"),patch.object(manager,"build_blog_assets"),patch.object(manager,"build_captcha_assets"),patch.object(manager,"code_files",return_value=[root/"reader"]),patch.object(manager,"release_metadata",return_value={"releaseId":"code-20261012-120000-abcdef12","packageFormat":2}):
                package,digest=manager.build_code_package(Job(),"code-20261012-120000-abcdef12")
            self.assertEqual(len(digest),64)
            with tarfile.open(package,"r:gz") as archive:
                self.assertFalse(any(name=="reader/modern-assets" or name.startswith("reader/modern-assets/") for name in archive.getnames()))
                self.assertNotIn("reader/README.md",archive.getnames())
                self.assertFalse(any(name.endswith(".map") for name in archive.getnames()))
                self.assertIn("reader/site/index.html",archive.getnames())
                for name in (root/"reader/site/brand").iterdir():self.assertIn(f"reader/site/brand/{name.name}",archive.getnames())
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
        self.assertIn("SHIYUE_DEPLOYMENT_MODE=remote",command)
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

    def test_initial_content_requires_review_and_sync_uses_current_apply_helper(self):
        remote=SyntaxRemote()
        manager.prune_initial_database_to_published_content(Job(),remote,{"remote_root":"/srv/shiyue"})
        applied_sql=shlex.split(remote.scripts[0])[-1]
        self.assertIn("SET publication_status='draft',reviewed_by=NULL,published_at=NULL",applied_sql)
        self.assertIn("publication_status IN ('draft','published')",applied_sql)
        source=inspect.getsource(manager.sync_saas_public_content)
        self.assertIn('remote.scp(ROOT/"tools/deployment/saas_public_sync.py"',source)
        self.assertIn('python3 /app/.local/',source)

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

    def test_redeploy_clears_empty_existing_or_partial_project_without_backup(self):
        for existing,database_exists,daemon_error in ((False,False,False),(True,True,False),(True,False,False),(False,False,True),(True,True,True)):
            with self.subTest(existing=existing,database_exists=database_exists,daemon_error=daemon_error),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);project=root/'project'
                if existing:project.mkdir();(project/'old-data.txt').write_text('old remote data')
                executable=root/'docker'
                executable.write_text('#!/bin/bash\ncase "$1" in\ninfo) exit '+('1' if daemon_error else '0')+';;\ncontainer) test "$REMOTE_DB_EXISTS" = yes;;\nrm) echo "$3" >> "$REMOVAL_LOG";;\nimages) echo shiyue-reader-runtime:20260930-1; echo shiyue-captcha:old;;\nimage) echo "$3" >> "$IMAGE_REMOVAL_LOG";;\n*) exit 9;;\nesac\n')
                executable.chmod(0o755)
                env={**os.environ,'PATH':str(root)+os.pathsep+os.environ['PATH'],'REMOTE_DB_EXISTS':'yes' if database_exists else 'no','REMOVAL_LOG':str(root/'removed.txt'),'IMAGE_REMOVAL_LOG':str(root/'removed-images.txt')}
                scripts=[]
                def ssh(script):
                    scripts.append(script)
                    return subprocess.run(['bash','-s'],input=script,env=env,text=True,capture_output=True,check=True).stdout
                remote=type('Remote',(),{})();remote.ssh=ssh
                if daemon_error:
                    with self.assertRaises(subprocess.CalledProcessError):manager.uninstall_saas_for_redeploy(Job(),remote,{'id':1,'remote_root':str(project)})
                else:
                    manager.uninstall_saas_for_redeploy(Job(),remote,{'id':1,'remote_root':str(project)})
                    self.assertFalse(project.exists())
                    self.assertEqual((root/'removed-images.txt').read_text().strip(),'shiyue-captcha:old')
                    if database_exists:
                        removed=(root/'removed.txt').read_text()
                        for name in ('shiyue-postgres','shiyue-redis','shiyue-saas','shiyue-captcha'):self.assertIn(name,removed)
                self.assertEqual(len(scripts),1)
                self.assertNotIn('pg_dump',scripts[0]);self.assertNotIn('/var/backups',scripts[0])
                if existing and daemon_error:self.assertEqual((project/'old-data.txt').read_text(),'old remote data')

    def test_redeploy_rejects_unsafe_root_before_remote_mutation(self):
        from unittest.mock import Mock
        remote=Mock()
        for root in ('/','/srv','/root','/srv/project/../','relative/project'):
            with self.subTest(root=root),self.assertRaises(ValueError):manager.uninstall_saas_for_redeploy(Job(),remote,{'id':1,'remote_root':root})
        remote.ssh.assert_not_called()

    def test_redeploy_uninstall_failure_stops_installation(self):
        from unittest.mock import Mock
        remote=Mock(ssh=Mock(return_value='uninstall incomplete'))
        with self.assertRaisesRegex(ValueError,'卸载未完成'):
            manager.uninstall_saas_for_redeploy(Job(),remote,{'id':1,'remote_root':'/srv/shiyue'})

    def test_post_activation_verification_resolves_symlinked_mount(self):
        source=inspect.getsource(manager.start_saas_upgrade)
        self.assertIn('readlink -f "$mount_source"',source)
        self.assertIn('"$current_release/reader"',source)

    def test_deployment_http_upgrade_uses_saas_specific_worker(self):
        server=(manager.ROOT/"tools/reader_server.py").read_text()
        self.assertIn('"/api/deployment/saas-upgrade"}:self.reply({"jobId":deployment_manager.start_saas_upgrade(target_id)}',server)

    def test_deployment_http_sync_uses_saas_content_upload(self):
        server=(manager.ROOT/"tools/reader_server.py").read_text()
        self.assertIn('if self.path == "/api/deployment/sync":self.reply({"jobId":deployment_manager.start_saas_public_sync(target_id)},202)',server)

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
