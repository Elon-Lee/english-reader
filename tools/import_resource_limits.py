"""Run the complete import process tree in a bounded Linux memory cgroup.

The HTTP process stays outside this group. A shared flock serializes limited
imports across API processes and candidate/production containers.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from saas_auth import ROOT, SaaSError

MIB = 1024 ** 2


@dataclass(frozen=True)
class ImportLimits:
    memory_mb: int = 0
    swap_mb: int = 512
    threads: int = 1

    @classmethod
    def from_environment(cls, environment):
        try:
            values = [int(environment.get(key, default)) for key, default in (
                ('SHIYUE_IMPORT_MEMORY_MB', 0), ('SHIYUE_IMPORT_SWAP_MB', 512),
                ('SHIYUE_IMPORT_THREADS', 1))]
            memory, swap, threads = values
            if memory != 0 and not 128 <= memory <= 1048576:
                raise ValueError()
            if not 0 <= swap <= 1048576 or not 1 <= threads <= 32:
                raise ValueError()
        except (TypeError, ValueError) as exc:
            raise SaaSError('import_limit_config_invalid', '导入资源限额配置无效，请联系管理员。', 503) from exc
        return cls(memory, swap, threads)

    @property
    def enabled(self):
        return self.memory_mb > 0

    def exhausted_message(self):
        return (f'导入处理达到内存上限（{self.memory_mb} MiB，额外 Swap {self.swap_mb} MiB）。'
                '主站服务已保留，请联系管理员调整限额后重试。')


class MemoryCgroup:
    def __init__(self, root):
        self.root = Path(root)
        self.v2 = (self.root / 'memory.max').is_file()

    def configure(self, limits):
        """Fail closed when real RAM AND swap limits cannot be enforced."""
        if sys.platform != 'linux' or not self.root.is_dir():
            raise OSError('A delegated Linux memory cgroup is required')
        if self.pids():
            raise OSError('Import cgroup still contains processes')
        ram, swap = limits.memory_mb * MIB, limits.swap_mb * MIB
        if self.v2:
            self._write('memory.max', ram)
            self._write('memory.swap.max', swap)
            self._write('memory.high', ram * 9 // 10)
            self._write('memory.oom.group', 1)
        else:
            # Set memsw first when increasing RAM, RAM first when decreasing.
            # The kernel requires RAM <= RAM+swap at every intermediate step.
            old = int((self.root / 'memory.limit_in_bytes').read_text())
            if ram > old:
                self._write('memory.memsw.limit_in_bytes', ram + swap)
                self._write('memory.limit_in_bytes', ram)
            else:
                self._write('memory.limit_in_bytes', ram)
                self._write('memory.memsw.limit_in_bytes', ram + swap)
            self._write('memory.oom_control', 0)
        self.verify(limits)

    def verify(self, limits):
        expected = {'memory.max': limits.memory_mb * MIB, 'memory.swap.max': limits.swap_mb * MIB} if self.v2 else {
            'memory.limit_in_bytes': limits.memory_mb * MIB,
            'memory.memsw.limit_in_bytes': (limits.memory_mb + limits.swap_mb) * MIB}
        for name, value in expected.items():
            if int((self.root / name).read_text()) != value:
                raise OSError('Import memory limit was not applied')

    def _write(self, name, value):
        # cgroup files must already exist; never create fake controller files.
        path = self.root / name
        if not path.is_file():
            raise OSError('Missing cgroup controller: ' + name)
        path.write_text(str(value))

    def pids(self):
        return [int(pid) for pid in (self.root / 'cgroup.procs').read_text().split()]

    def counters(self):
        if self.v2:
            values = dict(line.split() for line in (self.root / 'memory.events').read_text().splitlines())
            return tuple(int(values.get(key, 0)) for key in ('max', 'oom', 'oom_kill'))
        return tuple(int((self.root / key).read_text()) for key in
                     ('memory.failcnt', 'memory.memsw.failcnt'))

    def kill_all(self):
        # Descendants inherit this cgroup, even after the worker itself exits.
        # SIGKILL is retried while reparented children finish shutting down.
        for _ in range(50):
            pids = self.pids()
            if not pids:
                return
            for pid in pids:
                if pid == os.getpid():
                    raise RuntimeError('HTTP process must never join the import cgroup')
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            time.sleep(.1)
        raise OSError('Import children have not exited')


def preflight(environment=None):
    """Candidate releases must prove that a child can join the real budget."""
    import fcntl
    environment = os.environ if environment is None else environment
    limits = ImportLimits.from_environment(environment)
    result = {'enabled': limits.enabled, 'memoryMiB': limits.memory_mb,
              'swapMiB': limits.swap_mb, 'threads': limits.threads}
    if not limits.enabled:
        return result
    path = Path(environment.get('SHIYUE_IMPORT_LOCK', str(ROOT / '.local/import-memory.lock')))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        group = MemoryCgroup(environment.get('SHIYUE_IMPORT_CGROUP', '/run/shiyue-import-cgroup'))
        group.configure(limits)
        try:
            probe = "import os,sys; from pathlib import Path; (Path(sys.argv[1])/'cgroup.procs').write_text(str(os.getpid())); x=bytearray(1024*1024)"
            subprocess.run([sys.executable, '-c', probe, str(group.root)], check=True,
                           timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finally:
            group.kill_all()
        if os.getpid() in group.pids():
            raise RuntimeError('The API must remain outside the import budget')
    return result


def run_limited(service, user_id, task_id, limits):
    try:
        return _run_limited(service, user_id, task_id, limits)
    except Exception as exc:
        message = exc.message if isinstance(exc, SaaSError) else '导入处理器启动或运行失败，请联系管理员检查资源隔离配置。'
        service.fail(user_id, task_id, message)
        raise


def _run_limited(service, user_id, task_id, limits):
    import fcntl
    environment = {**os.environ, **service.accounts.environment}
    root = environment.get('SHIYUE_IMPORT_CGROUP', '/run/shiyue-import-cgroup')
    lock_path = Path(environment.get('SHIYUE_IMPORT_LOCK', str(ROOT / '.local/import-memory.lock')))
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    def current():
        service.assert_access(user_id)
        with service.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                return service._task(cursor, user_id, task_id)

    # No heavy processor is started until the global budget is acquired.
    with lock_path.open('a') as guard:
        while True:
            try:
                fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                task = current()
                if task['status'] != 'queued':
                    return {'task': service._public(task), 'idempotent': True}
                time.sleep(2)
        task = current()
        if task['status'] not in {'queued', 'running'}:
            return {'task': service._public(task), 'idempotent': True}
        if task['status'] == 'running':
            # Keep the established 80 minute stale recovery policy.
            with service.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT updated_at < NOW()-INTERVAL '80 minutes' FROM workspace_import_tasks WHERE id=%s", (task_id,))
                    if not cursor.fetchone()[0]:
                        return {'task': service._public(task), 'idempotent': True}
        source = None
        if task['kind'] in {'document', 'text'} and task.get('source_asset_id'):
            with service.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    source = service._source_path(cursor, user_id, task)
        group = MemoryCgroup(root)
        try:
            group.configure(limits)
            before = group.counters()
        except (OSError, ValueError) as exc:
            raise SaaSError('import_limit_unavailable', '导入内存隔离不可用，已停止处理以保护主站，请联系管理员。', 503) from exc
        environment.update(DATABASE_URL=service.accounts.database_url, MEDIA_ROOT=str(service.media.media_root),
                           SHIYUE_IMPORT_CGROUP=str(group.root), MALLOC_ARENA_MAX='2',
                           OMP_NUM_THREADS=str(limits.threads), MKL_NUM_THREADS=str(limits.threads),
                           OPENBLAS_NUM_THREADS=str(limits.threads),
                           SHIYUE_WHISPER_THREADS=str(limits.threads), SHIYUE_CTC_THREADS=str(limits.threads),
                           SHIYUE_KOKORO_THREADS=str(limits.threads),
                           SHIYUE_KOKORO_CHUNK_CHARACTERS=environment.get('SHIYUE_KOKORO_CHUNK_CHARACTERS','40'))
        # Preserve explicit processor paths; secrets are inherited, never CLI args.
        environment.update({name: str(getattr(service, attr)) for name, attr in (
            ('SHIYUE_PDF_OCR', 'pdf_ocr'), ('SHIYUE_WHISPER_CLI', 'whisper_cli'),
            ('SHIYUE_WHISPER_MODEL', 'whisper_model'), ('SHIYUE_FFMPEG', 'ffmpeg'),
            ('SHIYUE_YTDLP', 'yt_dlp'), ('SHIYUE_NODE', 'node'))})
        command = [sys.executable, str(ROOT / 'tools/import_resource_worker.py'),
                   '--user', user_id, '--task', task_id]
        if service.official:
            command.append('--official')
        try:
            process = subprocess.Popen(command, env=environment, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, start_new_session=True)
            try:
                code = process.wait(timeout=6 * 3600)
            except subprocess.TimeoutExpired as exc:
                raise SaaSError('import_processing_timeout', '导入处理超时，请联系管理员检查限额后重试。', 504) from exc
        finally:
            try:
                group.kill_all()
            finally:
                if 'process' in locals():
                    # Also reap a worker that failed before joining the cgroup.
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=15)
                # Clean only after all processing has stopped, while the shared
                # budget lock still excludes another import/retry. Keep the
                # authorized path even if cancellation deleted its asset.
                try:
                    _cleanup_narration_staging(service, user_id, task_id, source)
                except (OSError, SaaSError):
                    pass
        exhausted = group.counters() != before
        task = current()
        if code and task['status'] not in {'complete', 'cancelled'}:
            if exhausted:
                raise SaaSError('import_memory_limit', limits.exhausted_message(), 422)
            if task['status'] != 'failed':
                raise SaaSError('import_worker_failed', '导入处理器异常退出，请联系管理员检查资源隔离配置。', 422)
        return {'task': service._public(task), 'idempotent': False}


def _cleanup_narration_staging(service, user_id, task_id, source=None):
    import re
    import shutil
    with service.accounts.transaction() as connection:
        with connection.cursor() as cursor:
            task = service._task(cursor, user_id, task_id)
            if task['kind'] not in {'document', 'text'} or not task.get('source_asset_id'):
                return
            source = source or service._source_path(cursor, user_id, task)
            cursor.execute('SELECT storage_path FROM asset_variants WHERE asset_id=%s AND deleted_at IS NULL',
                           (task['source_asset_id'],))
            registered = {service.media._safe_path(row[0])[1] for row in cursor.fetchall()}
    for path in source.parent.iterdir():
        if path.name.startswith('.kokoro-') and path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif re.fullmatch(r'[0-9a-f]{32}\.mp3', path.name) and path != source and path not in registered:
            path.unlink(missing_ok=True)

