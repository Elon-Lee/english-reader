#!/usr/bin/env python3
"""Independent local SaaS stack; all debug services and media run on this machine."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.local/local-dev'
PORTS = {'postgres': 55432, 'redis': 56379, 'captcha': 18080, 'backend': 8790, 'frontend': 4173}
DATABASE = 'shiyue_saas_local'


def private_write(path, value):
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(value)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_config():
    path = STATE / 'config.json'
    if not path.exists():
        if (STATE / 'postgres/PG_VERSION').exists():
            raise RuntimeError('本地数据库已存在但配置缺失，请恢复 config.json，不自动重建数据库。')
        private_write(path, json.dumps({
            'databasePassword': secrets.token_urlsafe(32), 'redisPassword': secrets.token_urlsafe(32),
            'sessionSecret': secrets.token_urlsafe(48), 'captchaSecret': secrets.token_urlsafe(48),
            'adminEmail': 'admin@local.test', 'adminPassword': secrets.token_urlsafe(18),
        }, indent=2) + '\n')
    path.chmod(0o600)
    config = json.loads(path.read_text())
    if not all(isinstance(config.get(key), str) and len(config[key]) >= 16 for key in
               ('databasePassword', 'redisPassword', 'sessionSecret', 'captchaSecret', 'adminPassword')):
        raise RuntimeError('本地配置缺失或无效，请恢复 config.json。')
    return config


def environment(config, source=None):
    # Whitelist OS/toolchain settings. Inherited remote DB, media, SMTP, audit,
    # payment and bootstrap settings must never leak into independent debugging.
    source = os.environ if source is None else source
    env = {key: value for key, value in source.items() if key in {
        'PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TMPDIR', 'SSH_AUTH_SOCK', 'JAVA_HOME',
    }}
    from urllib.parse import quote
    env.update({
        'DATABASE_URL': f"postgresql://shiyue_local:{quote(config['databasePassword'], safe='')}@127.0.0.1:55432/{DATABASE}",
        'REDIS_URL': f"redis://:{quote(config['redisPassword'], safe='')}@127.0.0.1:56379/0",
        'SESSION_SECRET': config['sessionSecret'], 'SHIYUE_CAPTCHA_SECRET': config['captchaSecret'],
        'SHIYUE_DEPLOYMENT_MODE': 'local', 'SHIYUE_RUNTIME_MODE': 'saas', 'SHIYUE_SAAS_ENABLED': '1',
        'SHIYUE_SAAS_AUTO_MIGRATE': '1', 'BOOTSTRAP_ADMIN_EMAIL': '', 'BOOTSTRAP_ADMIN_PASSWORD': '',
        'READER_HOST': '127.0.0.1', 'READER_PORT': '8790', 'APP_BASE_URL': 'http://127.0.0.1:4173',
        'MEDIA_ROOT': str(STATE / 'media'),
        'SMTP_HOST': '127.0.0.1', 'SMTP_PORT': '1025', 'SMTP_FROM': 'debug@rynenglish.local',
        'SMTP_USER': '', 'SMTP_PASSWORD': '', 'SHIYUE_DEBUG_SMTP_PORT': '1025',
        'PYTHONDONTWRITEBYTECODE': '1', 'NO_PROXY': 'localhost,127.0.0.1,::1', 'no_proxy': 'localhost,127.0.0.1,::1',
    })
    tool_paths = [STATE / 'tools/postgresql/bin', STATE / 'tools/redis/bin', STATE / 'tools/node/bin',
                  Path('/opt/homebrew/opt/postgresql@16/bin'), Path('/usr/local/opt/postgresql@16/bin')]
    env['PATH'] = os.pathsep.join(str(path) for path in tool_paths) + os.pathsep + env.get('PATH', os.defpath)
    if (ROOT / '.local/captcha-tools/jdk/bin/javac').exists():
        env['JAVA_HOME'] = str(ROOT / '.local/captcha-tools/jdk')
    validate_environment(env)
    return env


def validate_environment(env):
    for name, scheme, port, path in (
        ('DATABASE_URL', 'postgresql', 55432, '/' + DATABASE), ('REDIS_URL', 'redis', 56379, '/0'),
    ):
        value = urlsplit(env[name])
        if value.scheme != scheme or value.hostname != '127.0.0.1' or value.port != port or value.path != path or value.query:
            raise RuntimeError(f'{name} 必须使用项目独立本地服务。')


def binary(name, family):
    candidates = [STATE / 'tools' / family / 'bin' / name]
    candidates.extend(Path(prefix) / 'opt' / ('postgresql@16' if family == 'postgresql' else family) / 'bin' / name
                      for prefix in ('/usr/local', '/opt/homebrew'))
    candidates.extend(Path(prefix) / 'bin' / name for prefix in ('/usr/local', '/opt/homebrew'))
    found = shutil.which(name)
    if found:
        candidates.append(Path(found))
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise RuntimeError(f'缺少 {name}；请运行 tools/install_local_services.sh 或安装 PostgreSQL 16 / Redis 7。')


def reachable(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.3):
            return True
    except OSError:
        return False


def command_line(pid):
    return subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True).stdout.strip()


def owned(record):
    command = command_line(record['pid'])
    return bool(command and record['marker'] in command and not command.startswith('['))


def read_pids():
    path = STATE / 'pids.json'
    return json.loads(path.read_text()) if path.exists() else {}


def save_pids(pids):
    private_write(STATE / 'pids.json', json.dumps(pids, indent=2) + '\n')


def wait_for(check, description, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except Exception:
            pass
        time.sleep(.2)
    raise RuntimeError(f'{description} 启动检查失败，请查看 {STATE} 内对应日志。')


def start_process(name, command, env, marker, pids, probe):
    record = pids.get(name)
    if record and owned(record):
        wait_for(probe, name)
        return
    port = PORTS[name]
    if reachable(port):
        raise RuntimeError(f'{port} 已由其他进程占用，请先停止旧调试环境。')
    with (STATE / f'{name}.log').open('ab') as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, start_new_session=True)
    pids[name] = {'pid': process.pid, 'marker': marker}
    save_pids(pids)
    wait_for(lambda: process.poll() is None and probe(), name)


def http_ready(url):
    with urlopen(url, timeout=2) as response:
        return response.status == 200


def ensure_captcha_build(env, jar):
    source = ROOT / 'services/captcha'
    files = [source / 'pom.xml', source / 'build.sh', *sorted((source / 'src').rglob('*'))]
    digest = hashlib.sha256()
    for path in files:
        if path.is_file():
            digest.update(path.relative_to(source).as_posix().encode() + b'\0' + path.read_bytes())
    signature = digest.hexdigest()
    stamp = STATE / 'captcha-build.json'
    previous = json.loads(stamp.read_text()) if stamp.exists() else {}
    # Maven intentionally fixes JAR timestamps for reproducible archives. Use
    # content hashes rather than mtimes, or every restart would rebuild the JAR.
    if jar.exists() and previous == {'source': signature, 'jar': hashlib.sha256(jar.read_bytes()).hexdigest()}:
        return
    record = read_pids().get('captcha')
    if record and owned(record):
        raise RuntimeError('验证码构建内容已变化，请先 --stop-saas-local，再启动以加载新程序。')
    subprocess.run(['sh', str(source / 'build.sh')], cwd=ROOT, env=env, check=True)
    private_write(stamp, json.dumps({'source': signature, 'jar': hashlib.sha256(jar.read_bytes()).hexdigest()}))


def prepare_database(config, env):
    cluster = STATE / 'postgres'
    pg_ctl = binary('pg_ctl', 'postgresql')
    if not (cluster / 'PG_VERSION').exists():
        if cluster.exists() and any(cluster.iterdir()):
            raise RuntimeError('PostgreSQL 数据目录非空但未初始化；保留现有文件，请检查。')
        with tempfile.NamedTemporaryFile(mode='w', dir=STATE) as password:
            password.write(config['databasePassword'] + '\n')
            password.flush()
            subprocess.run([binary('initdb', 'postgresql'), '-D', str(cluster), '-U', 'shiyue_local',
                            '--encoding=UTF8', '--locale=C', '--auth=scram-sha-256', '--pwfile=' + password.name],
                           check=True, env=env, stdout=subprocess.DEVNULL)
        with (cluster / 'postgresql.conf').open('a') as stream:
            stream.write("\nlisten_addresses = '127.0.0.1'\nport = 55432\nunix_socket_directories = ''\n")
    if (cluster / 'PG_VERSION').read_text().strip() != '16':
        raise RuntimeError('独立调试要求 PostgreSQL 16，不自动升级已有数据目录。')
    status = subprocess.run([pg_ctl, '-D', str(cluster), 'status'], capture_output=True, env=env)
    if status.returncode:
        if reachable(55432):
            raise RuntimeError('55432 已被其他 PostgreSQL 占用。')
        subprocess.run([pg_ctl, '-D', str(cluster), '-l', str(STATE / 'postgres.log'), '-w', 'start'],
                       check=True, env=env, stdout=subprocess.DEVNULL)
    from run_saas_debug import ensure_database
    from saas_auth import SaaSService
    ensure_database(env['DATABASE_URL'])
    service = SaaSService(environment=env)
    service.migrate()
    admin = service.bootstrap_admin(config['adminEmail'], config['adminPassword'])
    credentials = STATE / 'admin-credentials.txt'
    if not credentials.exists():
        private_write(credentials, f"地址：http://127.0.0.1:4173\n邮箱：{config['adminEmail']}\n初始密码：{config['adminPassword']}\n仅首次初始化使用；已有账号密码不会在重启时重设。\n")
    return service, admin


def start():
    config = load_config()
    env = environment(config)
    # Check build/runtime dependencies before initializing data or launching services.
    node = shutil.which('node', path=env['PATH'])
    if not node:
        raise RuntimeError('需要 Node.js 20.19+，请先把 node 加入 PATH。')
    java = ROOT / '.local/captcha-tools/jdk/bin/java'
    if not java.exists():
        java = Path(env.get('JAVA_HOME', '')) / 'bin/java'
    if not java.exists():
        java = Path(shutil.which('java', path=env['PATH']) or '/missing-java')
    if not java.exists():
        raise RuntimeError('需要 JDK 17+，请运行 sh tools/install_local_services.sh。')
    jar = ROOT / 'services/captcha/target/shiyue-captcha-1.0.0.jar'
    ensure_captcha_build(env, jar)
    binary('redis-server', 'redis')
    (STATE / 'media').mkdir(exist_ok=True)
    service, admin = prepare_database(config, env)
    pids = read_pids()
    redis_dir = STATE / 'redis'
    redis_dir.mkdir(exist_ok=True)
    redis_config = STATE / 'redis.conf'
    private_write(redis_config, '\n'.join([
        'bind 127.0.0.1', 'port 56379', 'protected-mode yes', 'daemonize no',
        'requirepass ' + config['redisPassword'], 'dir ' + json.dumps(str(redis_dir)),
        'appendonly yes', 'appendfsync everysec', 'save 60 1', '',
    ]))
    import redis
    cache = redis.Redis.from_url(env['REDIS_URL'], decode_responses=True, socket_timeout=2)
    try:
        redis_binary = binary('redis-server', 'redis')
        start_process('redis', [redis_binary, str(redis_config)], env,
                      redis_binary + ' 127.0.0.1:56379', pids, cache.ping)
        start_process('captcha', [str(java), '-Xms32m', '-Xmx192m', '-Djava.awt.headless=true', '-jar', str(jar)],
                      env, str(jar), pids, lambda: http_ready('http://127.0.0.1:18080/health'))
        from saas_captcha import CaptchaService
        captcha = CaptchaService(service, cache, env)
        # Test shared-secret authentication and actual image generation on every start.
        result = captcha._provider('/gen?type=ROTATE')
        data = result.get('data') or {}
        if result.get('code') != 200 or data.get('type') != 'ROTATE' or not data.get('backgroundImage'):
            raise RuntimeError('本地验证码未能生成 ROTATE 图片。')
        with service.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM platform_settings WHERE key='auth.captcha'")
                missing = cursor.fetchone() is None
        if missing:
            captcha.update_config(str(admin['id']), {'captchaEnabled': True})
    finally:
        cache.close()
    backend = str(ROOT / 'tools/run_local_saas.py')
    start_process('backend', [sys.executable, backend], env, backend, pids,
                  lambda: http_ready('http://127.0.0.1:8790/api/health'))
    vite = str(ROOT / 'node_modules/vite/bin/vite.js')
    start_process('frontend', [node, vite, '--config', 'frontend/vite.config.js'], env, vite, pids,
                  lambda: http_ready('http://127.0.0.1:4173'))
    print('独立本地 SaaS 已启动：http://127.0.0.1:4173')
    print('PostgreSQL 55432 / Redis 56379 / 验证码 18080 / API 8790；全部仅本机监听。')
    print(f'本地管理员初始凭据：{STATE / "admin-credentials.txt"}')
    print('调试邮件保存在 .local/smtp-outbox；本地书籍与账号独立于线上。')


def stop():
    pids = read_pids()
    for name in ('frontend', 'backend', 'captcha', 'redis'):
        record = pids.get(name)
        if not record:
            continue
        if owned(record):
            os.kill(record['pid'], signal.SIGTERM)
            wait_for(lambda: not owned(record), f'停止 {name}', timeout=20)
        pids.pop(name)
        save_pids(pids)
    cluster = STATE / 'postgres'
    if (cluster / 'postmaster.pid').exists():
        subprocess.run([binary('pg_ctl', 'postgresql'), '-D', str(cluster), '-m', 'fast', '-w', 'stop'], check=True)
    print('本地调试服务已停止，数据库、缓存和媒体文件均保留。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'stop', 'restart', 'status', 'exec'), nargs='?', default='start')
    parser.add_argument('command', nargs=argparse.REMAINDER, help='exec -- <command> 使用独立本地配置运行检查')
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True)
    STATE.chmod(0o700)
    if args.action == 'exec':
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        if not command:
            parser.error('exec 需要命令')
        return subprocess.call(command, cwd=ROOT, env=environment(load_config()))
    with (STATE / 'control.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'start':
            start()
        elif args.action == 'restart':
            stop()
            start()
        elif args.action == 'stop':
            stop()
        else:
            records = read_pids()
            print(json.dumps({name: bool(records.get(name) and owned(records[name]))
                              for name in ('redis', 'captcha', 'backend', 'frontend')}, ensure_ascii=False))
            print(json.dumps({'listeners': {name: reachable(port) for name, port in PORTS.items()}}))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, BlockingIOError) as error:
        # Commands contain only tool paths, never credentials. Avoid DB exceptions
        # echoing connection URLs; detailed service logs remain in private STATE.
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
