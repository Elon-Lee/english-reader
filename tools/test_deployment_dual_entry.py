"""Dual entry rollout contracts; all execution stays in temporary directories."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

from deployment import manager, https_entry


def target(**updates):
    return dict(remote_root='/srv/shiyue', host='192.0.2.1', id=1,
                public_domain='learn.rynenglish.com', blog_domain='rynenglish.com',
                intl_domain='10ye.cc', frontend_port=5174, intl_frontend_port=5173,
                service_port=5174, use_https=False, install_recording=False, **updates)


class DualEntryDeploymentTests(unittest.TestCase):
    def test_release_metadata_ignores_built_output_changes_but_reports_source_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            def git(*args):return subprocess.run(['git',*args],cwd=root,text=True,capture_output=True,check=True)
            git('init','-q')
            git('config','user.name','Deployment Test');git('config','user.email','deploy@example.test')
            for relative in ('reader/site/index.html','reader/site-intl/index.html','reader/blog/index.html','tools/code.py'):
                path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('initial')
            git('add','.');git('commit','-qm','fixture')
            for site in ('site','site-intl','blog'):(root/'reader'/site/'index.html').write_text('built')
            with patch.object(manager,'ROOT',root):
                self.assertFalse(manager.release_metadata('code-test')['sourceDirty'])
                (root/'tools/code.py').write_text('changed')
                self.assertTrue(manager.release_metadata('code-test')['sourceDirty'])

    def test_saving_sites_keeps_international_domain_and_ports(self):
        scripts=[]
        manager.save_remote_site_config(SimpleNamespace(ssh=lambda s:scripts.append(s)),target())
        args=shlex.split(scripts[0])
        values=json.loads(args[args.index("%s\\n")+1])
        self.assertEqual(values['intl_domain'],'10ye.cc')
        self.assertEqual((values['frontend_port'],values['intl_frontend_port']),(5174,5173))

    def test_saved_international_domain_and_ports_reject_unsafe_values(self):
        for changes in ({'intl_domain':'learn.rynenglish.com'}, {'frontend_port':5173},
                        {'intl_frontend_port':70000}, {'intl_domain':'https://10ye.cc'}):
            settings={**target(),**changes}
            remote=SimpleNamespace(ssh=lambda _: 'SHIYUE_SITES_CONFIG\n'+json.dumps(settings))
            with self.assertRaises(ValueError):manager.saas_https_target(remote,{'remote_root':'/srv/shiyue'})

    def test_saved_dual_entry_restores_domains_ports_and_http_origin(self):
        settings=target()
        remote=SimpleNamespace(ssh=lambda _: 'SHIYUE_SITES_CONFIG\n'+json.dumps(settings))
        actual=manager.saas_https_target(remote, {'remote_root':'/srv/shiyue'})
        for key in ('intl_domain','frontend_port','intl_frontend_port'):
            self.assertEqual(actual[key],settings[key])
        self.assertFalse(actual['use_https'])
        self.assertEqual(actual['service_port'],5174)

    def test_saved_old_sites_keep_single_frontend_5173(self):
        settings={'public_domain':'learn.rynenglish.com','blog_domain':'rynenglish.com'}
        remote=SimpleNamespace(ssh=lambda _: 'SHIYUE_SITES_CONFIG\n'+json.dumps(settings))
        actual=manager.saas_https_target(remote, {'remote_root':'/srv/shiyue'})
        self.assertFalse(actual.get('intl_domain'))
        self.assertEqual(actual.get('frontend_port'),5173)
        self.assertTrue(actual['use_https'])

    def test_cli_passes_explicit_international_domain_only_for_upgrade(self):
        import deploy_remote
        sites={'public_domain':'learn.rynenglish.com','blog_domain':'rynenglish.com','intl_domain':'10ye.cc'}
        argv=['deploy_remote.py','--target','1','--upgrade','--app-domain',sites['public_domain'],
              '--blog-domain',sites['blog_domain'],'--intl-domain',sites['intl_domain'],'--defer-https']
        with patch.object(sys,'argv',argv),patch.object(deploy_remote,'resolve_target',return_value={'id':1,'name':'test','host':'localhost','port':22}), \
                patch.object(manager,'start_saas_upgrade',return_value=123) as upgrade,patch.object(deploy_remote,'follow_job'):
            deploy_remote.main()
        upgrade.assert_called_once_with(1,site_domains=sites,defer_https=True)

    def test_final_rollback_restores_saved_configs_and_both_original_containers(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();config=root/'shared/config';config.mkdir(parents=True)
            backup=root/'backups/settings';backup.mkdir(parents=True)
            old=root/'releases/old';(old/'reader/site').mkdir(parents=True)
            (old/'reader/site/index.html').write_text('old')
            new=root/'releases/new';new.mkdir(parents=True);(root/'current').symlink_to(new)
            originals={'saas.env':'SESSION_SECRET=keep\n','sites.json':json.dumps(target()),
                       'frontend-cn.env':'FRONTEND_SITE_TOKEN=keep-cn\n',
                       'frontend-intl.env':'FRONTEND_SITE_TOKEN=keep-intl\n'}
            for name,content in originals.items():
                (backup/name).write_text(content);(config/name).write_text('replaced')
            (backup/'https-entry.json.absent').touch()
            (backup/'current-release').write_text(str(old)+'\n')
            bin_dir=root/'bin';bin_dir.mkdir();log=root/'calls'
            docker=bin_dir/'docker'
            docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$DOCKER_LOG"\n');docker.chmod(0o755)
            item=target();item.update(remote_root=str(root),_settings_backup=str(backup))
            script=manager.rollback_site_upgrade_command(item)
            subprocess.run(['bash','-s'],input=script,text=True,capture_output=True,check=True,
                           env={**os.environ,'PATH':str(bin_dir)+os.pathsep+os.environ['PATH'],'DOCKER_LOG':str(log)})
            for name,content in originals.items():self.assertEqual((config/name).read_text(),content)
            self.assertEqual((root/'current').resolve(),old)
            calls=log.read_text()
            self.assertIn('--name shiyue-saas-frontend-intl',calls)
            self.assertIn('FRONTEND_PORT=5174',calls)
            self.assertIn('FRONTEND_PORT=5173',calls)

    def test_two_frontends_use_private_loopback_and_separate_least_privilege_env(self):
        cn=shlex.split(manager.saas_frontend_run_command(target(),'/srv/shiyue/current'))
        intl=shlex.split(manager.saas_frontend_run_command(target(),'/srv/shiyue/current',site='intl'))
        for args,site,port in ((cn,'cn',5174),(intl,'intl',5173)):
            for value in ('FRONTEND_HOST=127.0.0.1',f'FRONTEND_PORT={port}',
                          f'FRONTEND_SITE={site}',f'/srv/shiyue/shared/config/frontend-{site}.env'):
                self.assertIn(value,args)
            self.assertNotIn('/srv/shiyue/shared/config/saas.env',args)
            self.assertNotIn('FRONTEND_TLS_CERT=/certs/server-cert.pem',args)
        self.assertIn('/srv/shiyue/current/reader/site-intl:/app/site:ro,z',intl)
        self.assertIn('APP_DOMAIN=10ye.cc',intl)
        self.assertNotIn('BLOG_DOMAIN=rynenglish.com',intl)

    def test_upgrade_preserves_payment_credentials_and_generates_private_gateway_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config=root/'shared/config';config.mkdir(parents=True)
            env=config/'saas.env'
            original='DATABASE_URL=private-db\nSESSION_SECRET=keep-session\nALIPAY_PRIVATE_KEY=keep-pay\nAPP_BASE_URL=https://old.example\n'
            env.write_text(original)
            scripts=[]
            def ssh(script):
                scripts.append(script)
                if script.startswith('test -s '):return 'SHIYUE_SAAS_ENV_READY'
                code=shlex.split(script)[-1].replace("Path('/config/saas.env')",f'Path({str(env)!r})')
                return subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,check=True).stdout
            job=Mock()
            item=target();item['remote_root']=str(root)
            manager.ensure_remote_saas_config(job,SimpleNamespace(ssh=ssh),item)
            values=dict(line.split('=',1) for line in env.read_text().splitlines())
            self.assertEqual(values['ALIPAY_PRIVATE_KEY'],'keep-pay')
            self.assertEqual(values['CN_APP_BASE_URL'],'https://learn.rynenglish.com')
            self.assertEqual(values['INTL_APP_BASE_URL'],'https://10ye.cc')
            self.assertNotEqual(values['CN_GATEWAY_TOKEN'],values['INTL_GATEWAY_TOKEN'])
            for site in ('cn','intl'):
                private=config/f'frontend-{site}.env'
                self.assertEqual(private.stat().st_mode & 0o777,0o600)
                self.assertEqual(private.read_text(),f'FRONTEND_SITE_TOKEN={values[site.upper()+"_GATEWAY_TOKEN"]}\n')
            serialized=json.dumps(scripts)+repr(job.mock_calls)
            for key in ('CN_GATEWAY_TOKEN','INTL_GATEWAY_TOKEN'):
                self.assertGreaterEqual(len(values[key]),40)
                self.assertNotIn(values[key],serialized)
            first=env.read_text()
            manager.ensure_remote_saas_config(job,SimpleNamespace(ssh=ssh),item)
            self.assertEqual(env.read_text(),first)

    def test_candidates_and_switch_include_both_frontends_and_failure_cleanup(self):
        scripts=[]
        remote=SimpleNamespace(ssh=lambda s:scripts.append(s) or 'healthy')
        item=target();item['_previous_target']={**item,'intl_domain':'','frontend_port':5173,'use_https':True}
        manager.activate_saas_release(Mock(),remote,item,'code-test')
        self.assertEqual(len(scripts),2)
        for script,ports in zip(scripts,((15174,15173),(5174,5173))):
            subprocess.run(['bash','-n'],input=script,text=True,check=True)
            for port in ports:self.assertIn(f'FRONTEND_PORT={port}',script)
            self.assertIn('shiyue-saas-frontend-intl',script)
            self.assertIn('10ye.cc',script)
            self.assertIn('/api/membership',script)
            self.assertIn('trap ',script)
        self.assertIn('FRONTEND_TLS_CERT=/certs/server-cert.pem',scripts[1])
        self.assertIn('FRONTEND_PORT=5173',scripts[1])

    def test_nginx_uses_configured_cn_port_and_deferred_script_never_issues_tls(self):
        script=https_entry.install_script(target())
        self.assertIn('proxy_pass http://127.0.0.1:5174;',script)
        self.assertNotIn('proxy_pass http://127.0.0.1:5173;',script)
        deferred=https_entry.deferred_script(target())
        subprocess.run(['bash','-n'],input=deferred,text=True,check=True)
        self.assertIn('proxy_pass http://127.0.0.1:5174;',deferred)
        self.assertIn('server_name _;',deferred)
        self.assertNotIn('certonly',deferred)
        self.assertNotIn('listen 443',deferred)

    def test_failed_candidate_or_production_start_restores_single_site_without_data_loss(self):
        for fail_name in ('shiyue-saas-frontend-intl-candidate','shiyue-saas-frontend-intl'):
            with self.subTest(fail_name=fail_name),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);bin_dir=root/'bin';bin_dir.mkdir()
                old=root/'releases/old';old.mkdir(parents=True)
                (old/'reader/site').mkdir(parents=True);(old/'reader/site/index.html').write_text('old')
                new=root/'releases/code-test';new.mkdir()
                (root/'current').symlink_to(old)
                (root/'shared/books').mkdir(parents=True)
                data=root/'shared/books/user-data';data.write_text('must survive')
                log=root/'docker.log'
                docker=bin_dir/'docker'
                docker.write_text('''#!/usr/bin/env python3
import json,os,sys
a=sys.argv[1:]
with open(os.environ['DOCKER_LOG'],'a') as f:f.write(json.dumps(a)+'\\n')
if a[0]=='run' and '--name' in a and a[a.index('--name')+1]==os.environ['FAIL_NAME']:sys.exit(7)
sys.exit(0)
''');docker.chmod(0o755)
                env={**os.environ,'PATH':str(bin_dir)+os.pathsep+os.environ['PATH'],
                     'DOCKER_LOG':str(log),'FAIL_NAME':fail_name}
                item=target();item['remote_root']=str(root)
                item['_previous_target']={**item,'intl_domain':'','frontend_port':5173,'use_https':True}
                def ssh(script):
                    return subprocess.run(['bash','-s'],input=script,env=env,text=True,capture_output=True,check=True).stdout
                with self.assertRaises(subprocess.CalledProcessError):
                    manager.activate_saas_release(Mock(),SimpleNamespace(ssh=ssh),item,'code-test')
                self.assertEqual((root/'current').resolve(),old.resolve())
                self.assertEqual(data.read_text(),'must survive')
                calls=[json.loads(line) for line in log.read_text().splitlines()]
                removals=[a for a in calls if a[0]=='rm']
                self.assertTrue(any('shiyue-saas-frontend-intl-candidate' in a for a in removals))
                if fail_name.endswith('-candidate'):
                    self.assertFalse(any('shiyue-saas' in a for a in removals))
                else:
                    runs=[a for a in calls if a[0]=='run']
                    restored=runs[-1]
                    self.assertIn('shiyue-saas-frontend',restored)
                    self.assertIn('FRONTEND_PORT=5173',restored)
                    self.assertIn('FRONTEND_TLS_CERT=/certs/server-cert.pem',restored)

    def test_international_asset_may_contain_commerce_but_cn_may_not(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'package.json').write_text('{}')
            for site in ('site','site-intl'):
                assets=root/'reader'/site/'assets';assets.mkdir(parents=True)
                (assets/'index.js').write_text('app')
                (assets/'index.css').write_text('app')
                (assets.parent/'index.html').write_text('<title>纸间微光</title><link href="/brand/paper-glow-mark.svg">')
            brand=root/'reader/site/brand';brand.mkdir();(brand/'paper-glow-mark.svg').write_text('icon')
            (root/'reader/site-intl/assets/index.js').write_text('fetch("/api/payments/alipay/orders")')
            with patch.object(manager,'ROOT',root),patch.object(manager.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='',stderr='')):
                manager.build_frontend_assets(Mock())
                (root/'reader/site/assets/index.js').write_text('fetch("/api/payments/alipay/orders")')
                with self.assertRaisesRegex(ValueError,'已移除接口'):manager.build_frontend_assets(Mock())


if __name__=='__main__':unittest.main()
