"""Deployment keeps the static blog separate across future upgrades."""
import json
import shlex
import tempfile
import tarfile
from contextlib import ExitStack
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from deployment import manager


class Job:
    def update(self, *args, **kwargs):
        pass

    def write(self, message):
        pass


class BlogDeploymentTests(unittest.TestCase):
    def test_frontend_mounts_both_sites_without_changing_backend_access(self):
        target={'remote_root':'/srv/shiyue','public_domain':'learn.rynenglish.com',
                'blog_domain':'rynenglish.com','use_https':True}
        args=shlex.split(manager.saas_frontend_run_command(target,'/srv/shiyue/current').replace('\\\n',''))
        for value in ['APP_DOMAIN=learn.rynenglish.com','BLOG_DOMAIN=rynenglish.com',
                      'BLOG_ROOT=/app/blog','SAAS_BACKEND_URL=http://127.0.0.1:8790',
                      '/srv/shiyue/current/reader/blog:/app/blog:ro,z']:
            self.assertIn(value,args)
        self.assertEqual(args[-3:],[manager.SAAS_IMAGE,'python3','/app/tools/saas_frontend_server.py'])

    def test_upgrades_recover_sites_even_with_stale_local_primary_domain(self):
        settings={'public_domain':'learn.rynenglish.com','blog_domain':'rynenglish.com'}
        remote=SimpleNamespace(ssh=lambda _: 'SHIYUE_SITES_CONFIG\n'+json.dumps(settings))
        target=manager.saas_https_target(remote,{'remote_root':'/srv/shiyue','public_domain':'rynenglish.com'})
        self.assertEqual(target['public_domain'],'learn.rynenglish.com')
        self.assertEqual(target['blog_domain'],'rynenglish.com')

    def test_invalid_saved_sites_refuse_to_expose_single_application(self):
        for settings in [{}, {'public_domain':'same.example','blog_domain':'same.example'},
                         {'public_domain':'https://app.example','blog_domain':'blog.example'}]:
            remote=SimpleNamespace(ssh=lambda _: 'SHIYUE_SITES_CONFIG\n'+json.dumps(settings))
            with self.assertRaises(ValueError):
                manager.saas_https_target(remote,{'remote_root':'/srv/shiyue'})

    def test_blog_build_audits_all_outputs_including_feeds(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'blog').mkdir()
            (root/'blog/package.json').write_text('{}')
            for name in ['index.html','about/index.html','rss.xml','sitemap-index.xml','404.html']:
                path=root/'reader/blog'/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('纸间微光')
            result=SimpleNamespace(returncode=0,stdout='',stderr='')
            with patch.object(manager,'ROOT',root),patch.object(manager.subprocess,'run',return_value=result) as run:
                manager.build_blog_assets(Job())
                self.assertEqual(run.call_args.args[0],['npm','run','build'])
                (root/'reader/blog/rss.xml').write_text('<link>https://learn.rynenglish.com</link>')
                with self.assertRaisesRegex(ValueError,'博客产物混入'):
                    manager.build_blog_assets(Job())

    def test_same_domain_rejected_before_starting_upgrade(self):
        with self.assertRaises(ValueError):
            manager.start_saas_upgrade(1,{'public_domain':'same.example','blog_domain':'same.example'})

    def test_post_activation_failure_restores_previous_site_configuration(self):
        target={'id':1,'remote_root':'/srv/shiyue','service_port':5173,
                'public_domain':'old.example','use_https':True,'install_recording':False}
        scripts=[]
        remote=SimpleNamespace(ssh=lambda script: scripts.append(script) or '',scp=lambda *_:None)
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            metadata=Path(temp)/'.shiyue-release.json'
            metadata.write_text('{}')
            package=Path(temp)/'release.tar.gz'
            with tarfile.open(package,'w:gz') as archive:
                archive.add(metadata,arcname=metadata.name)
            replacements={
                'saas_https_target':lambda _remote,value:dict(value),
                'check_remote_saas_upgrade_target':None,
                'build_code_package':(package,'a'*64),
                'prepare_remote_saas_release':None,
                'backup_remote_saas_database':'backup.dump',
                'sync_remote_private_config':{'configured':False},
                'ensure_remote_tls':'certificate',
                'backup_remote_site_settings':'/srv/shiyue/backups/saas/settings-test',
                'ensure_remote_saas_config':None,'sync_remote_smtp_config':None,
                'ensure_remote_saas_image':None,
                'ensure_remote_captcha':None,'ensure_remote_aligner':None,
                'activate_saas_release':{'candidate':'ok'},
            }
            for name,value in replacements.items():
                options={'side_effect':value} if callable(value) else {'return_value':value}
                stack.enter_context(patch.object(manager,name,**options))
            save=stack.enter_context(patch.object(manager,'save_remote_site_config',side_effect=RuntimeError('settings write failed')))
            stack.enter_context(patch.object(manager,'run_task',side_effect=lambda _,worker,_id:worker(Job(),remote,target)))
            with self.assertRaisesRegex(RuntimeError,'settings write failed'):
                manager.start_saas_upgrade(1,{'public_domain':'app.example','blog_domain':'blog.example'},defer_https=True)
            save.assert_called_once()
        self.assertEqual(len(scripts),1)
        self.assertIn('current-release',scripts[0])
        self.assertIn('sites.absent',scripts[0])
        self.assertNotIn('APP_DOMAIN=app.example',scripts[0])
        self.assertIn('shiyue-saas-frontend-candidate',scripts[0])


if __name__ == '__main__':
    unittest.main()
