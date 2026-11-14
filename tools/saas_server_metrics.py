"""Bounded, on-demand server telemetry. No shell, credentials, or remote control."""
import os
import platform
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from saas_auth import SaaSError

LOCK = threading.Lock()
HISTORY = deque(maxlen=120)
CACHE = None
LAST_SAMPLE = 0.0
LAST_NETWORK = None
LAST_ROOT = None


def _read(path):
    try: return Path(path).read_text().strip()
    except OSError: return None


def container_limits():
    """Best-effort common cgroup namespaces; absent values remain unknown."""
    memory_max = _read('/sys/fs/cgroup/memory.max') or _read('/sys/fs/cgroup/memory/memory.limit_in_bytes')
    memory_used = _read('/sys/fs/cgroup/memory.current') or _read('/sys/fs/cgroup/memory/memory.usage_in_bytes')
    cpu = _read('/sys/fs/cgroup/cpu.max')
    quota = _read('/sys/fs/cgroup/cpu/cpu.cfs_quota_us')
    period = _read('/sys/fs/cgroup/cpu/cpu.cfs_period_us')
    result = {}
    try:
        limit, used = int(memory_max), int(memory_used)
        if 0 < limit < 2**60:
            result['memory'] = {'total': limit, 'used': used, 'percent': round(used / limit * 100, 1)}
    except (TypeError, ValueError): pass
    try:
        quota, period = cpu.split() if cpu else (quota, period)
        if int(quota) > 0 and int(period) > 0: result['cpuLimit'] = round(int(quota) / int(period), 2)
    except (TypeError, ValueError): pass
    return result


def server_metrics(media_root):
    global CACHE, LAST_SAMPLE, LAST_NETWORK, LAST_ROOT
    try: import psutil
    except ImportError as exc:
        raise SaaSError('metrics_unavailable', '服务器监测依赖尚未安装，请安装 requirements-saas.txt 后重启服务。', 503) from exc
    root = str(Path(media_root).resolve())
    with LOCK:
        now = time.monotonic()
        if LAST_ROOT != root:
            CACHE = None; LAST_NETWORK = None; HISTORY.clear(); LAST_ROOT = root
        if CACHE is not None and now - LAST_SAMPLE < 5: return CACHE
        errors = []

        def collect(name, callback):
            try: return callback()
            except (OSError, ValueError, psutil.Error):
                errors.append(name)
                return None

        cpu = collect('CPU', lambda: {'percent': psutil.cpu_percent(interval=.2), 'logicalCount': psutil.cpu_count(),
                                    'loadAverage': list(os.getloadavg()) if hasattr(os, 'getloadavg') else None})
        def memory():
            value = psutil.virtual_memory()
            return {'total': value.total, 'available': value.available, 'used': value.total - value.available,
                    'percent': round((value.total - value.available) / value.total * 100, 1)}
        mem = collect('内存', memory)
        swap = collect('交换空间', lambda: dict(zip(('total', 'used', 'free', 'percent'), psutil.swap_memory()[:4])))
        disks = []
        for label, directory in (('系统磁盘', '/'), ('媒体所在磁盘', root)):
            # Do not create paths merely to monitor them.
            path = Path(directory)
            while not path.exists() and path.parent != path: path = path.parent
            value = collect(label, lambda: psutil.disk_usage(str(path))._asdict())
            disks.append({'label': label, 'path': directory, **(value or {}), 'available': value is not None})
        proc = collect('后端进程', lambda: {'rss': psutil.Process().memory_info().rss,
                                        'uptimeSeconds': max(0, int(time.time() - psutil.Process().create_time()))})
        uptime = collect('系统运行时间', lambda: max(0, int(time.time() - psutil.boot_time())))
        counters = collect('网络', psutil.net_io_counters)
        network = None
        sampled = time.monotonic()
        if counters is not None:
            network = {'receivedBytes': counters.bytes_recv, 'sentBytes': counters.bytes_sent,
                       'receivePerSecond': None, 'sendPerSecond': None}
            if LAST_NETWORK is not None:
                previous, received, sent = LAST_NETWORK
                seconds = sampled - previous
                if seconds > 0 and counters.bytes_recv >= received and counters.bytes_sent >= sent:
                    network.update(receivePerSecond=round((counters.bytes_recv-received)/seconds),
                                   sendPerSecond=round((counters.bytes_sent-sent)/seconds))
            LAST_NETWORK = sampled, counters.bytes_recv, counters.bytes_sent
        timestamp = datetime.now(timezone.utc).isoformat()
        HISTORY.append({'at': timestamp, 'cpu': cpu['percent'] if cpu else None,
                        'memory': mem['percent'] if mem else None,
                        'disk': disks[-1].get('percent')})
        CACHE = {'sampledAt': timestamp, 'platform': platform.system(),
                 'scope': 'container' if Path('/.dockerenv').exists() or Path('/run/.containerenv').exists() else 'host',
                 'cpu': cpu, 'memory': mem, 'swap': swap, 'disks': disks, 'process': proc,
                 'uptimeSeconds': uptime, 'network': network, 'container': container_limits(),
                 'history': list(HISTORY), 'errors': errors}
        LAST_SAMPLE = sampled
        return CACHE
