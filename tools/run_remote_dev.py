#!/usr/bin/env python3
"""Run local SaaS/Vite against remote PostgreSQL/Redis over loopback SSH forwards."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.local/remote-dev'
FORWARDS = {15432: 5432, 16379: 6379, 18791: 8790, 18080: 18080}


def reachable(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            return True
    except OSError:
        return False


def local_url(value, port):
    parts = urlsplit(value)
    credentials = parts.netloc.rsplit('@', 1)[0] + '@' if '@' in parts.netloc else ''
    return urlunsplit(parts._replace(netloc=f'{credentials}127.0.0.1:{port}'))


def tunnel_command(ssh, host):
    forwards = [argument for local, remote in FORWARDS.items() for argument in ['-L', f'127.0.0.1:{local}:127.0.0.1:{remote}']]
    return ssh + ['-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3', '-N'] + forwards + [host]


def watch_tunnel(command):
    """Keep all forwards in one supervised connection; terminate both on shutdown."""
    stopped = threading.Event()
    child = None

    def stop(_signal, _frame):
        stopped.set()
        if child is not None and child.poll() is None:
            child.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    delay = 1
    state = STATE / 'tunnel.json'
    try:
        while not stopped.is_set():
            started = time.monotonic()
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL)
            state.write_text(json.dumps({'supervisor': os.getpid(), 'ssh': child.pid}))
            if stopped.is_set():
                child.terminate()
            result = child.wait()
            if stopped.is_set():
                break
            if time.monotonic() - started > 60:
                delay = 1
            print(f'SSH 连接已断开（退出码 {result}），{delay} 秒后重连。', flush=True)
            stopped.wait(delay)
            delay = min(30, delay * 2)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
        state.unlink(missing_ok=True)


def assert_dependencies(environment):
    """Probe real services, not merely the listening SSH forwarding sockets."""
    import psycopg
    import redis
    with psycopg.connect(environment['DATABASE_URL'], connect_timeout=5) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            assert cursor.fetchone() == (1,)
    cache = redis.Redis.from_url(environment['REDIS_URL'], socket_connect_timeout=5, socket_timeout=5)
    try:
        assert cache.ping()
    finally:
        cache.close()
    request = Request('http://127.0.0.1:18080/gen?type=ROTATE', headers={'X-Captcha-Secret': environment.get('SHIYUE_CAPTCHA_SECRET', '')})
    with urlopen(request, timeout=10) as response:
        challenge = json.load(response)
    data = challenge.get('data')
    if challenge.get('code') != 200 or not isinstance(data, dict) or data.get('type') != 'ROTATE' or not data.get('id') or not data.get('templateImage', '').startswith('data:image/'):
        raise RuntimeError('远端验证码未能生成 ROTATE 图片')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='root@117.72.209.44')
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--known-hosts', type=Path, required=True)
    parser.add_argument('--node-bin', type=Path, default=Path('/private/tmp/node-v22.16.0-darwin-x64/bin'))
    parser.add_argument('--watch-tunnel', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    ssh = ['ssh', '-i', str(args.key), '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
           '-o', f'UserKnownHostsFile={args.known_hosts}', '-o', 'ConnectTimeout=15']
    if args.watch_tunnel:
        watch_tunnel(tunnel_command(ssh, args.host))
        return
    if reachable(8790) or reachable(4173):
        raise SystemExit('本地 8790/4173 已占用，请先确认并停止已有开发服务。')
    # Capture credentials directly into process memory; never print or persist them.
    result = subprocess.run(ssh + [args.host, 'docker inspect shiyue-saas --format "{{json .Config.Env}}"'], capture_output=True, check=True, text=True)
    remote = dict(item.split('=', 1) for item in json.loads(result.stdout))
    env = os.environ.copy()
    for key in ('DATABASE_URL', 'REDIS_URL', 'SESSION_SECRET', 'SHIYUE_CAPTCHA_SECRET'):
        if remote.get(key):
            env[key] = remote[key]
    env.update(DATABASE_URL=local_url(env['DATABASE_URL'], 15432), REDIS_URL=local_url(env['REDIS_URL'], 16379),
               SHIYUE_SAAS_ENABLED='1', SHIYUE_SAAS_AUTO_MIGRATE='0', BOOTSTRAP_ADMIN_EMAIL='',
               SHIYUE_DEPLOYMENT_MODE='remote', SHIYUE_RUNTIME_MODE='saas', APP_BASE_URL='http://127.0.0.1:4173',
               READER_HOST='127.0.0.1', READER_PORT='8790', MEDIA_ROOT=str(STATE / 'media'),
               PYTHONUNBUFFERED='1', SHIYUE_MEDIA_PROXY_TARGET='http://127.0.0.1:18791',
               PATH=str(args.node_bin) + os.pathsep + env.get('PATH', ''))
    processes = {}

    def launch(name, command, environment=env):
        path = STATE / f'{name}.log'
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, 'ab') as log:
            child = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=log, start_new_session=True)
        processes[name] = child

    try:
        occupied = [port for port in FORWARDS if reachable(port)]
        if occupied:
            raise RuntimeError(f'隧道端口已占用：{occupied}')
        launch('ssh', [sys.executable, str(Path(__file__).resolve()), '--watch-tunnel', '--host', args.host,
                       '--key', str(args.key), '--known-hosts', str(args.known_hosts)])
        for _ in range(300):
            if all(reachable(port) for port in FORWARDS):
                break
            if processes['ssh'].poll() is not None:
                raise RuntimeError('SSH 隧道启动失败，见 .local/remote-dev/ssh.log')
            time.sleep(.1)
        else:
            raise RuntimeError('SSH 隧道启动超时')
        assert_dependencies(env)
        launch('backend', [sys.executable, str(ROOT / 'tools/reader_server.py')])
        for _ in range(150):
            if reachable(8790):
                break
            if processes['backend'].poll() is not None:
                raise RuntimeError('后台启动失败，见 .local/remote-dev/backend.log')
            time.sleep(.1)
        else:
            raise RuntimeError('后台启动超时')
        launch('frontend', [str(args.node_bin / 'node'), str(ROOT / 'node_modules/vite/bin/vite.js'), '--config', 'frontend/vite.config.js'])
        for _ in range(100):
            if reachable(4173):
                break
            if processes['frontend'].poll() is not None:
                raise RuntimeError('前台启动失败，见 .local/remote-dev/frontend.log')
            time.sleep(.1)
        else:
            raise RuntimeError('前台启动超时')
        (STATE / 'pids.json').write_text(json.dumps({name: child.pid for name, child in processes.items()}))
        print('前台 http://127.0.0.1:4173；后台 http://127.0.0.1:8790；PostgreSQL/Redis 已通过 SSH 连接远程。')
    except Exception:
        for child in processes.values():
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        raise


if __name__ == '__main__':
    main()
