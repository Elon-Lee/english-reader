#!/usr/bin/env python3
"""HTTPS entry generation and execution tests; no Docker daemon is contacted."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

try:
    from deployment import https_entry
except ImportError:
    https_entry = None


FAKE_DOCKER = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
a=sys.argv[1:]; root=pathlib.Path(os.environ['FAKE_ROOT']); state_path=root/'docker-state.json'
s=json.loads(state_path.read_text()) if state_path.exists() else {}
with (root/'docker-calls.jsonl').open('a') as f: f.write(json.dumps(a)+'\n')
def save(): state_path.write_text(json.dumps(s))
def volume(dest):
    for i,v in enumerate(a):
        if v in ('-v','--volume'):
            host,container,*_=a[i+1].split(':')
            if container==dest: return pathlib.Path(host)
    raise RuntimeError('missing mount '+dest)
if a[:2]==['image','inspect']: sys.exit(0 if not s.get('missing_images') else 1)
if a[0]=='pull': sys.exit(1 if a[1] in s.get('pull_fail_images',[]) else 0)
if a[0]=='tag': sys.exit(0)
if a[0]=='inspect':
    if not s.get('exists'): sys.exit(1)
    fmt=a[a.index('--format')+1] if '--format' in a else ''
    if '.State.Running' in fmt: print('true' if s.get('running') else 'false')
    elif 'Labels' in fmt: print(s.get('owner',os.environ['FAKE_OWNER']))
    sys.exit(0)
if a[0]=='start': s['running']=True; save(); sys.exit(0)
if a[0]=='exec':
    if '-t' in a and s.get('exec_test_fail'): sys.exit(1)
    if 'reload' in a and s.get('reload_fail'): sys.exit(1)
    sys.exit(0)
if a[0]=='run':
    if any(v.startswith('certbot/certbot:') for v in a):
        work=volume('/var/lib/letsencrypt')
        if 'renew' in a:
            if s.get('renew_marker'): (work/'reload-required').touch()
            sys.exit(1 if s.get('renew_fail') else 0)
        if s.get('cert_fail'): sys.exit(1)
        domain=a[a.index('--cert-name')+1]
        live=volume('/etc/letsencrypt')/'live'/domain; live.mkdir(parents=True,exist_ok=True)
        for name in ('fullchain.pem','privkey.pem'): (live/name).write_text('fake certificate')
        sys.exit(0)
    if '-t' in a:
        config=volume('/etc/nginx/conf.d')/'default.conf'
        if s.get('config_test_fail') and 'listen 443 ssl' in config.read_text(): sys.exit(1)
        sys.exit(0)
    s.update(exists=True,running=True,owner=os.environ['FAKE_OWNER']); save(); sys.exit(0)
sys.exit('unexpected fake docker invocation '+repr(a))
'''


class HttpsEntryTests(unittest.TestCase):
    def test_dual_sites_have_separate_certificate_blocks_and_unknown_host_rejection(self):
        script=https_entry.install_script({'remote_root':'/srv/shiyue','public_domain':'learn.rynenglish.com','blog_domain':'rynenglish.com'})
        config=https_entry._https_config('learn.rynenglish.com','rynenglish.com')
        self.assertIn('server_name learn.rynenglish.com;',config)
        self.assertIn('server_name rynenglish.com;',config)
        self.assertIn('/live/learn.rynenglish.com/fullchain.pem',config)
        self.assertIn('/live/rynenglish.com/fullchain.pem',config)
        self.assertIn('ssl_reject_handshake on',config)
        self.assertIn('for cert_domain in learn.rynenglish.com rynenglish.com',script)
        self.assertEqual(subprocess.run(['bash','-n'],input=script,text=True,capture_output=True).returncode,0)
        self.assertIn('"blog_domain": "rynenglish.com"',script)
        with self.assertRaises(ValueError):
            https_entry.install_script({'remote_root':'/srv/shiyue','public_domain':'rynenglish.com','blog_domain':'rynenglish.com'})

    def setUp(self):
        self.assertIsNotNone(https_entry, 'HTTPS entry module must be implemented')

    def test_domain_normalization(self):
        self.assertEqual(https_entry.normalize_domain('RYNEnglish.COM'), 'rynenglish.com')
        self.assertEqual(https_entry.normalize_domain('例子.中国'), 'xn--fsqu00a.xn--fiqs8s')
        self.assertEqual(https_entry.normalize_domain(None), '')
        self.assertEqual(https_entry.normalize_domain(''), '')

    def test_domain_rejects_injection_non_dns_names_and_bad_labels(self):
        for value in ('127.0.0.1', '::1', '*.example.com', 'https://example.com',
                      'example.com/a', 'example.com:443', 'example.com\n',
                      'example.com;id', '$(id).com', '-a.example', 'a-.example',
                      'a..com', 'a_b.com', 'localhost', 'a'*64+'.com', 'a.123'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                https_entry.normalize_domain(value)

    def test_url_and_persistent_paths(self):
        target={'host':'117.72.209.44','remote_root':'/srv/shiyue','public_domain':'RYNEnglish.COM'}
        self.assertEqual(https_entry.frontend_url(target),'https://rynenglish.com')
        self.assertEqual(https_entry.frontend_url({'host':'117.72.209.44'}),'https://117.72.209.44:5173')
        self.assertEqual(https_entry.frontend_url({'host':'127.0.0.1','use_https':False}),'http://127.0.0.1:5173')
        paths=https_entry.entry_paths(target)
        expected='/var/lib/shiyue/https/'+hashlib.sha256(b'/srv/shiyue').hexdigest()[:12]
        self.assertEqual(paths['state_root'],expected)
        self.assertEqual(paths['manifest'],'/srv/shiyue/shared/config/https-entry.json')
        self.assertTrue(paths['letsencrypt'].startswith(expected+'/'))

    def test_unsafe_install_root_and_missing_domain_rejected(self):
        for value in ('/', 'relative', '/srv/../root', '/srv/a b', '/srv/$(id)', '/srv/a\n'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                https_entry.install_script({'remote_root':value,'public_domain':'example.com'})
        with self.assertRaises(ValueError):
            https_entry.install_script({'remote_root':'/srv/shiyue'})

    def test_install_script_has_valid_bash_and_persistent_mounts(self):
        script=https_entry.install_script({'remote_root':'/srv/shiyue','public_domain':'example.com',
                                          'acme_email':'test@example.com'})
        result=subprocess.run(['bash','-n'],input=script,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        for text in ('nginx:1.28-alpine','certbot/certbot:v5.4.0',
                     '--network host','--email test@example.com',
                     '$state/nginx:/etc/nginx/conf.d:ro,z',
                     '$state/letsencrypt:/etc/letsencrypt:ro,z',
                     '$state/letsencrypt:/etc/letsencrypt:z',
                     '--keep-until-expiring','--server https://acme-v02.api.letsencrypt.org/directory'):
            self.assertIn(text,script)
        self.assertNotIn('RandomizedDelaySec',script)  # CentOS 7 systemd 219.

    def test_email_rejects_whitespace_and_newlines(self):
        for email in ('test @example.com','test@example.com\n','test\t@example.com'):
            with self.subTest(email=email),self.assertRaises(ValueError):
                https_entry.install_script({'remote_root':'/srv/shiyue','public_domain':'example.com',
                                            'acme_email':email})


@unittest.skipUnless(shutil.which('bash'), 'bash required for script tests')
class InstallExecutionTests(unittest.TestCase):
    def test_dual_install_and_renew_include_both_separate_certificates(self):
        self.target.update(public_domain='learn.rynenglish.com',blog_domain='rynenglish.com')
        result=self.install()
        self.assertEqual(result.returncode,0,result.stderr)
        manifest=json.loads(Path(self.paths['manifest']).read_text())
        self.assertEqual(manifest['version'],2)
        self.assertEqual(manifest['blog_domain'],'rynenglish.com')
        issues=[c for c in self.calls() if 'certonly' in c]
        self.assertEqual([c[c.index('--domain')+1] for c in issues],['learn.rynenglish.com','rynenglish.com'])
        before=len(self.calls())
        self.assertEqual(self.renew().returncode,0)
        renews=[c for c in self.calls()[before:] if 'renew' in c]
        self.assertEqual([c[c.index('--cert-name')+1] for c in renews],['learn.rynenglish.com','rynenglish.com'])

    def setUp(self):
        self.assertIsNotNone(https_entry, 'HTTPS entry module must be implemented')
        self.tmp=tempfile.TemporaryDirectory(prefix='https-entry-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.bin=self.root/'bin'; self.bin.mkdir()
        self.target={'host':'117.72.209.44','remote_root':str(self.root/'app'),'public_domain':'rynenglish.com'}
        self.paths={k:v.replace('/var/lib/shiyue/https',str(self.root/'persistent'))
                    if isinstance(v,str) else v for k,v in https_entry.entry_paths(self.target).items()}
        self.fake('docker',FAKE_DOCKER)
        # macOS has no util-linux flock; execution tests model the lock acquisition.
        self.fake('flock','#!/bin/sh\nexit 0\n')
        self.fake('systemctl','#!/bin/sh\nprintf "%s\\n" "$*" >> "$FAKE_ROOT/systemctl-calls"\n')
        self.fake('ss','#!/bin/sh\n[ ! -f "$FAKE_ROOT/port-conflict" ] || echo "LISTEN 0 128 0.0.0.0:80 0.0.0.0:*"\nexit 0\n')
        self.env={**os.environ,'PATH':str(self.bin)+os.pathsep+os.environ['PATH'],
                  'FAKE_ROOT':str(self.root),'FAKE_OWNER':self.target['remote_root']}

    def fake(self,name,body):
        file=self.bin/name; file.write_text(body); file.chmod(0o755)

    def state(self,**updates):
        file=self.root/'docker-state.json'
        value=json.loads(file.read_text()) if file.exists() else {}
        value.update(updates); file.write_text(json.dumps(value))

    def calls(self):
        file=self.root/'docker-calls.jsonl'
        return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []

    def script(self):
        script=https_entry.install_script(self.target)
        return script.replace('/var/lib/shiyue/https',str(self.root/'persistent')).replace('/etc/systemd/system',str(self.root/'systemd'))

    def install(self):
        return subprocess.run(['bash','-s'],input=self.script(),text=True,capture_output=True,env=self.env)

    def renew(self,*args):
        return subprocess.run(['bash',self.paths['renew_script'],*args],text=True,capture_output=True,env=self.env)

    def test_first_install_then_reuse_with_real_generated_scripts(self):
        first=self.install(); self.assertEqual(first.returncode,0,first.stderr)
        self.assertIn('SHIYUE_HTTPS_ENTRY_READY',first.stdout)
        manifest=json.loads(Path(self.paths['manifest']).read_text())
        self.assertEqual(manifest['public_domain'],'rynenglish.com')
        self.assertEqual(manifest['state_root'],self.paths['state_root'])
        config=Path(self.paths['nginx_config']).read_text()
        for text in ('listen 443 ssl','ssl_protocols TLSv1.2 TLSv1.3',
                     'return 308 https://rynenglish.com$request_uri',
                     'try_files $uri =404','proxy_pass http://127.0.0.1:5173',
                     'proxy_set_header X-Forwarded-Proto https','client_max_body_size 20g',
                     'proxy_request_buffering off'):
            self.assertIn(text,config)
        second=self.install(); self.assertEqual(second.returncode,0,second.stderr)
        calls=self.calls()
        self.assertEqual(sum(1 for c in calls if c[0]=='run' and '-d' in c),1)
        self.assertFalse(any(c[0] in ('stop','rm','pull') for c in calls))
        self.assertIn('Persistent=true',Path(str(self.root/'systemd')+'/'+self.paths['timer_name']).read_text())
        self.assertIn('TimeoutStartSec=3600',Path(str(self.root/'systemd')+'/'+self.paths['service_name']).read_text())
        self.assertEqual(subprocess.run(['bash','-n',self.paths['renew_script']],capture_output=True).returncode,0)

    def test_existing_edge_survives_certificate_issue_failure(self):
        self.assertEqual(self.install().returncode,0)
        old=Path(self.paths['nginx_config']).read_bytes(); self.state(cert_fail=True)
        result=self.install(); self.assertNotEqual(result.returncode,0)
        self.assertEqual(Path(self.paths['nginx_config']).read_bytes(),old)
        self.assertFalse(any(c[0] in ('stop','rm') for c in self.calls()))

    def test_first_certificate_failure_leaves_only_http_bootstrap(self):
        self.state(cert_fail=True)
        result=self.install(); self.assertNotEqual(result.returncode,0)
        self.assertNotIn('SHIYUE_HTTPS_ENTRY_READY',result.stdout)
        self.assertNotIn('listen 443',Path(self.paths['nginx_config']).read_text())
        self.assertFalse(Path(self.paths['manifest']).exists())
        self.assertFalse(Path(self.paths['renew_script']).exists())
        self.assertFalse((self.root/'systemctl-calls').exists())
        self.assertEqual(result.returncode,10)
        self.assertIn('SHIYUE_HTTPS_CERTIFICATE_FAILED:',result.stderr)

    def test_failed_new_config_rolls_back_existing_file(self):
        self.assertEqual(self.install().returncode,0)
        file=Path(self.paths['nginx_config']); file.write_text(file.read_text()+'\n# previous working config\n')
        old=file.read_bytes(); self.state(config_test_fail=True)
        result=self.install(); self.assertNotEqual(result.returncode,0)
        self.assertEqual(file.read_bytes(),old)

    def test_running_nginx_validation_or_reload_failure_restores_old_config(self):
        self.assertEqual(self.install().returncode,0)
        file=Path(self.paths['nginx_config']); file.write_text(file.read_text()+'\n# keep this\n')
        old=file.read_bytes()
        for failure in ('exec_test_fail','reload_fail'):
            self.state(exec_test_fail=failure=='exec_test_fail',reload_fail=failure=='reload_fail')
            result=self.install(); self.assertNotEqual(result.returncode,0)
            self.assertEqual(file.read_bytes(),old)

    def test_missing_images_are_pulled_and_stopped_owned_container_is_reused(self):
        self.state(missing_images=True)
        first=self.install(); self.assertEqual(first.returncode,0,first.stderr)
        pulls=[c for c in self.calls() if c[0]=='pull']
        self.assertEqual(pulls,[['pull','m.daocloud.io/docker.io/library/nginx:1.28-alpine'],
                                ['pull','m.daocloud.io/docker.io/certbot/certbot:v5.4.0']])
        self.assertIn(['tag','m.daocloud.io/docker.io/library/nginx:1.28-alpine','nginx:1.28-alpine'],self.calls())
        self.assertIn(['tag','m.daocloud.io/docker.io/certbot/certbot:v5.4.0','certbot/certbot:v5.4.0'],self.calls())
        self.state(missing_images=False,running=False)
        second=self.install(); self.assertEqual(second.returncode,0,second.stderr)
        self.assertIn(['start','shiyue-https'],self.calls())
        self.assertEqual(sum(1 for c in self.calls() if c[0]=='run' and '-d' in c),1)

    def test_failed_mirror_pull_falls_back_to_official_without_changing_daemon(self):
        self.state(missing_images=True,pull_fail_images=[
            'm.daocloud.io/docker.io/library/nginx:1.28-alpine',
            'm.daocloud.io/docker.io/certbot/certbot:v5.4.0'])
        result=self.install(); self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual([c for c in self.calls() if c[0]=='pull'],[
            ['pull','m.daocloud.io/docker.io/library/nginx:1.28-alpine'],['pull','nginx:1.28-alpine'],
            ['pull','m.daocloud.io/docker.io/certbot/certbot:v5.4.0'],['pull','certbot/certbot:v5.4.0']])
        self.assertFalse(any(c[0]=='tag' for c in self.calls()))
        self.assertNotIn('daemon.json',self.script())

    def test_conflicting_owner_or_ports_does_not_start_container(self):
        self.state(exists=True,running=True,owner='/srv/someone-else')
        result=self.install(); self.assertNotEqual(result.returncode,0)
        self.assertFalse(any(c[0] in ('run','start') for c in self.calls()))
        self.state(exists=False,running=False)
        (self.root/'port-conflict').touch()
        result=self.install(); self.assertNotEqual(result.returncode,0)
        self.assertFalse(any(c[0] in ('run','start') for c in self.calls()))

    def test_renewal_reloads_only_after_successful_marker_and_validation(self):
        self.assertEqual(self.install().returncode,0)
        before=len(self.calls())
        self.assertEqual(self.renew().returncode,0)
        self.assertFalse(any(c[0]=='exec' for c in self.calls()[before:]))
        self.assertTrue(any(c[0]=='run' and 'renew' in c and '--no-random-sleep-on-renew' in c
                            for c in self.calls()[before:]))
        self.state(renew_marker=True)
        result=self.renew('--dry-run','--run-deploy-hooks'); self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(Path(self.paths['work'],'reload-required').exists())
        self.assertTrue(any(c[0]=='exec' and 'reload' in c for c in self.calls()[before:]))
        self.state(exec_test_fail=True)
        result=self.renew(); self.assertNotEqual(result.returncode,0)
        self.assertTrue(Path(self.paths['work'],'reload-required').exists())
        self.state(exec_test_fail=False,renew_fail=True)
        before=len(self.calls()); result=self.renew(); self.assertNotEqual(result.returncode,0)
        self.assertFalse(any(c[0]=='exec' for c in self.calls()[before:]))
        self.assertTrue(Path(self.paths['work'],'reload-required').exists())

    def test_renew_rejects_unapproved_arguments(self):
        self.assertEqual(self.install().returncode,0)
        before=len(self.calls())
        self.assertNotEqual(self.renew('--force-renewal').returncode,0)
        self.assertEqual(len(self.calls()),before)


if __name__=='__main__':
    unittest.main()
