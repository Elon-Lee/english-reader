#!/usr/bin/env python3
import inspect,sqlite3,tempfile,unittest
from pathlib import Path

import library_db
from deployment import manager
from unittest.mock import Mock, patch

class DeploymentNodeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old_db=library_db.DB_PATH;self.old_local=library_db.LOCAL_ROOT;self.old_state=manager.STATE;self.old_logs=manager.LOGS;self.old_keys=manager.KEYS
        root=Path(self.temp.name);library_db.LOCAL_ROOT=root;library_db.DB_PATH=root/"library.sqlite3";manager.STATE=root/"deployment";manager.LOGS=manager.STATE/"logs";manager.KEYS=manager.STATE/"keys";library_db.connect().close()

    def tearDown(self):
        library_db.DB_PATH=self.old_db;library_db.LOCAL_ROOT=self.old_local;manager.STATE=self.old_state;manager.LOGS=self.old_logs;manager.KEYS=self.old_keys;manager.MEMORY_PASSWORDS.clear();self.temp.cleanup()

    def test_multiple_targets_can_be_saved_and_updated(self):
        first=manager.save_target({"name":"北京节点","host":"10.0.0.1","port":22,"username":"root","remoteRoot":"/srv/shiyue-a","servicePort":8765,"installRecording":True})
        second=manager.save_target({"name":"上海节点","host":"10.0.0.2","port":2222,"username":"root","remoteRoot":"/srv/shiyue-b","servicePort":9765,"installRecording":False})
        self.assertNotEqual(first["id"],second["id"]);self.assertEqual(len(manager.list_targets()),2)
        updated=manager.save_target({"id":second["id"],"name":"上海主节点","host":"10.0.0.2","port":2222,"username":"root","remoteRoot":"/srv/shiyue-b","servicePort":9765,"installRecording":False})
        self.assertEqual(updated["name"],"上海主节点");self.assertEqual(len(manager.list_targets()),2)

    def test_jobs_are_owned_by_target(self):
        target=manager.save_target({"name":"节点","host":"10.0.0.3","remoteRoot":"/srv/shiyue-c"})
        job=manager.Job("connection_test",target["id"])
        self.assertEqual(manager.job_info(job.id)["target_id"],target["id"])
        self.assertEqual(manager.recent_jobs(target["id"],10)[0]["id"],job.id)

    def test_delete_invalid_jobs_preserves_active_completed_and_logs(self):
        jobs=[]
        for status in ['failed','cancelled','queued','running','complete']:
            job=manager.Job('connection_test',len(jobs)+1)
            job.update(50,status,status)
            jobs.append(job)
        hidden=manager.Job('release_list',1);hidden.fail('hidden query failure')
        for _ in range(21):manager.Job('connection_test',1).complete()
        self.assertEqual(manager.invalid_job_count(),2)
        self.assertTrue(all(row['status']=='complete' for row in manager.recent_jobs()))
        audit=[]
        result=manager.delete_invalid_jobs(audit=audit.append)
        self.assertEqual(result['deletedCount'],2)
        self.assertEqual(set(result['deletedIds']),{jobs[0].id,jobs[1].id})
        self.assertEqual(audit,[result])
        self.assertEqual(manager.invalid_job_count(),0)
        for job in jobs[:2]:
            self.assertIsNone(manager.job_info(job.id));self.assertTrue(job.log.exists())
        for job in jobs[2:]+[hidden]:self.assertIsNotNone(manager.job_info(job.id))
        self.assertEqual(manager.delete_invalid_jobs()['deletedCount'],0)

    def test_delete_invalid_jobs_rolls_back_when_audit_fails(self):
        job=manager.Job('connection_test',1);job.fail('test failure')
        def failing_audit(result):raise RuntimeError('audit unavailable')
        with self.assertRaises(RuntimeError):manager.delete_invalid_jobs(audit=failing_audit)
        self.assertEqual(manager.invalid_job_count(),1)
        self.assertEqual(manager.job_info(job.id)['status'],'failed')

    def test_delete_invalid_jobs_route_requires_admin_session_and_csrf(self):
        import reader_server as server
        failed=manager.Job('connection_test',1);failed.fail('test failure')
        handler=object.__new__(server.Handler)
        handler.path='/api/deployment/jobs/delete-invalid'
        handler.client_address=('127.0.0.1',12345)
        handler.headers={}
        handler.rate_limit=Mock(return_value=True)
        handler.cookie_value=Mock(return_value='test-session')
        handler.json_body=Mock(return_value={})
        handler.reply=Mock()
        with patch.object(server,'SAAS',spec=True) as accounts,patch.object(server,'ADMIN') as admin,patch.object(server,'RUNTIME_MODE','saas'),patch.object(server,'DEPLOYMENT_MODE','local'):
            accounts.enabled=True
            cases=[(None,False,401),({'id':'member','is_admin':False},False,403),({'id':'admin','is_admin':True},True,403)]
            for session,bad_csrf,status in cases:
                accounts.authenticate.return_value=session
                accounts.assert_csrf.side_effect=server.SaaSError('csrf_failed','CSRF invalid',403) if bad_csrf else None
                handler.do_POST()
                self.assertEqual(handler.reply.call_args.args[1],status)
                self.assertEqual(manager.invalid_job_count(),1)
                admin.record_action.assert_not_called()
            accounts.assert_csrf.side_effect=None
            handler.do_POST()
            self.assertEqual(handler.reply.call_args.args[0]['deletedCount'],1)
            self.assertEqual(manager.invalid_job_count(),0)
            admin.record_action.assert_called_once_with('admin','deployment_jobs_delete_invalid',payload={'deletedCount':1,'deletedIds':[failed.id]})

    def test_platform_access_requires_local_mode_and_logged_in_admin(self):
        import reader_server as server
        from urllib.parse import urlsplit
        handler=object.__new__(server.Handler)
        handler.reply=Mock()
        handler.client_address=('127.0.0.1',12345)
        handler._saas_session={'id':'admin','is_admin':True}
        with patch.object(server,'SAAS',spec=True) as accounts,patch.object(server,'ADMIN') as admin,patch.object(server,'RUNTIME_MODE','saas'):
            accounts.enabled=True
            with patch.object(server,'DEPLOYMENT_MODE','remote'):
                self.assertFalse(handler.can_manage_platform())
                self.assertFalse(handler.deployment_allowed())
                handler.admin_get(urlsplit('/api/admin/platform-config'))
                handler.admin_post('/api/admin/platform-config')
                admin.platform_config.assert_not_called();admin.update_platform_config.assert_not_called()
                self.assertEqual(handler.reply.call_args.args[1],403)
            with patch.object(server,'DEPLOYMENT_MODE','local'):
                self.assertTrue(handler.can_manage_platform());self.assertTrue(handler.deployment_allowed())
                handler._saas_session={'id':'member','is_admin':False}
                self.assertFalse(handler.can_manage_platform());self.assertFalse(handler.deployment_allowed())
                handler._saas_session={'id':'admin','is_admin':True};handler.client_address=('192.0.2.1',12345)
                self.assertFalse(handler.can_manage_platform());self.assertFalse(handler.deployment_allowed())
                handler.client_address=('127.0.0.1',12345);accounts.enabled=False
                self.assertFalse(handler.can_manage_platform());self.assertFalse(handler.deployment_allowed())

    def test_retired_content_routes_return_404_without_creating_jobs(self):
        import reader_server as server
        handler=server.Handler.__new__(server.Handler)
        handler.rate_limit=Mock(return_value=True)
        handler.require_saas_user=Mock(return_value=True)
        handler.require_csrf=Mock(return_value=True)
        handler.deployment_allowed=Mock(return_value=True)
        handler.json_body=Mock(return_value={'targetId':1,'releaseId':'content-20261012-120000-abcd'})
        handler.reply=Mock();handler.send_error=Mock()
        with patch.object(server,'SAAS',spec=True) as accounts,patch.object(manager,'run_task') as run_task:
            accounts.enabled=True
            handler.path='/api/deployment/content-releases?targetId=1'
            handler.do_GET()
            handler.send_error.assert_called_once_with(404)
            handler.send_error.reset_mock()
            handler.path='/api/deployment/content-rollback'
            handler.do_POST()
            handler.send_error.assert_called_once_with(404)
            handler.reply.assert_not_called();run_task.assert_not_called()
            handler.send_error.reset_mock()
            handler.json_body.return_value={'targetId':1,'releaseId':'code-20261012-120000-abcd'}
            handler.path='/api/deployment/rollback'
            with patch.object(manager,'start_rollback',return_value=123) as rollback:
                handler.do_POST()
                rollback.assert_called_once_with(1,'code-20261012-120000-abcd')
                handler.reply.assert_called_once_with({'jobId':123},202)
                handler.send_error.assert_not_called()

    def test_uninstall_requires_exact_node_name_and_preserves_docker(self):
        target=manager.save_target({"name":"测试节点","host":"10.0.0.4","remoteRoot":"/srv/shiyue-d"})
        with self.assertRaises(ValueError):manager.start_uninstall(target["id"],"错误名称")
        source=inspect.getsource(manager.start_uninstall)
        self.assertIn("docker rm -f shiyue-reader",source);self.assertIn("rm -rf --",source);self.assertIn("shiyue-reader-runtime:*",source);self.assertNotIn("docker-ce",source)

    def test_legacy_single_target_table_is_migrated(self):
        library_db.DB_PATH.unlink(missing_ok=True);db=sqlite3.connect(library_db.DB_PATH)
        db.execute("CREATE TABLE deployment_targets(id INTEGER PRIMARY KEY CHECK(id=1),name TEXT,host TEXT,port INTEGER,username TEXT,remote_root TEXT,service_port INTEGER,install_recording INTEGER,host_fingerprint TEXT,created_at TEXT,updated_at TEXT)")
        db.execute("INSERT INTO deployment_targets VALUES(1,'旧节点','1.2.3.4',22,'root','/srv/shiyue',8765,1,'','x','x')");db.commit();db.close()
        migrated=library_db.connect();sql=migrated.execute("SELECT sql FROM sqlite_master WHERE name='deployment_targets'").fetchone()[0];row=migrated.execute("SELECT name FROM deployment_targets WHERE id=1").fetchone();migrated.close()
        self.assertNotIn("CHECK(id=1)",sql.replace(" ",""));self.assertEqual(row[0],"旧节点")

    def test_retrying_half_saved_node_does_not_duplicate(self):
        first=manager.save_target({"name":"节点A","host":"10.0.0.8","port":22,"username":"root","remoteRoot":"/srv/shiyue-a"})
        second=manager.save_target({"name":"节点A重试","host":"10.0.0.8","port":22,"username":"root","remoteRoot":"/srv/shiyue-a"})
        self.assertEqual(first["id"],second["id"]);self.assertEqual(len(manager.list_targets()),1);self.assertEqual(second["name"],"节点A重试")

    def test_keychain_password_is_passed_non_interactively(self):
        target={"id":7,"username":"root","host":"10.0.0.9","port":22}
        completed=type("Completed",(),{"returncode":0,"stderr":""})()
        with patch("deployment.manager.shutil.which",return_value="/usr/bin/security"),patch("deployment.manager.subprocess.run",return_value=completed) as run:
            manager.save_password(target,"secret-value")
        command=run.call_args.args[0];self.assertEqual(command[-2:],['-w','secret-value']);self.assertNotIn("input",run.call_args.kwargs);self.assertEqual(run.call_args.kwargs["timeout"],15)

    def test_http_protocol_is_saved_independently_from_recording(self):
        target=manager.save_target({"name":"HTTP节点","host":"10.0.0.10","remoteRoot":"/srv/shiyue-http","useHttps":False,"installRecording":True})
        self.assertEqual(target["use_https"],0);self.assertEqual(target["install_recording"],1)
        command=manager.docker_run_command(manager.get_target(target["id"]));health=manager.health_check_command(manager.get_target(target["id"]))
        self.assertIn("ggml-base.en.bin",command);self.assertNotIn("READER_TLS_CERT",command);self.assertNotIn("/certs",command);self.assertIn("http://127.0.0.1:5173",health)

    def test_https_protocol_mounts_certificates(self):
        target=manager.save_target({"name":"HTTPS节点","host":"10.0.0.11","remoteRoot":"/srv/shiyue-https","useHttps":True,"installRecording":False})
        command=manager.docker_run_command(manager.get_target(target["id"]));health=manager.health_check_command(manager.get_target(target["id"]))
        self.assertIn("READER_TLS_CERT",command);self.assertNotIn("ggml-base.en.bin",command);self.assertIn("https://127.0.0.1:5173",health)

if __name__=="__main__":unittest.main()
