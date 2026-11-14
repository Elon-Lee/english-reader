"""Optional, offline Kokoro narration for new EPUB/PDF imports."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time

from saas_auth import ROOT, SaaSError

VOICES = {
    'af_heart': ('美式英语 · 女声', 'a'),
    'am_michael': ('美式英语 · 男声', 'a'),
    'bf_emma': ('英式英语 · 女声', 'b'),
    'bm_george': ('英式英语 · 男声', 'b'),
}
MAX_CHARACTERS = 500_000
GENERATION_LOCK = threading.BoundedSemaphore(1)


def runtime():
    home = Path(os.environ.get('SHIYUE_KOKORO_HOME', str(ROOT / '.local/kokoro'))).expanduser()
    python = Path(os.environ.get('SHIYUE_KOKORO_PYTHON', str(home / 'venv/bin/python'))).expanduser()
    return home, python


def options():
    home, python = runtime()
    try:
        manifest = json.loads((home / 'ready.json').read_text())
        ready = (manifest.get('version') == 1 and manifest.get('offlinePreflight') is True and python.is_file()
                 and all((home / name).is_file() for name in
                         ['model/config.json', 'model/kokoro-v1_0.pth', 'model/LICENSE']
                         + [f'model/voices/{voice}.pt' for voice in VOICES]))
    except (OSError, ValueError, TypeError, AttributeError):
        ready = False
    return {'available': ready, 'engine': 'kokoro', 'model': 'Kokoro-82M',
            'voices': [{'value': voice, 'label': label} for voice, (label, _) in VOICES.items()],
            'maxCharacters': MAX_CHARACTERS,
            'notice': '仅支持英文 EPUB/PDF；生成后保存音频，供播放与逐句复读。' if ready else 'AI 朗读尚未安装，请联系管理员。'}


def validate_request(value, kind, filename, metadata):
    if value is None:
        return None
    if not isinstance(value, dict) or value.get('engine') != 'kokoro':
        raise SaaSError('invalid_speech_options', '朗读生成选项无效。', 400)
    if kind != 'document' or Path(filename).suffix.lower() not in {'.epub', '.pdf'}:
        raise SaaSError('speech_document_required', 'AI 朗读仅支持 EPUB 或 PDF。', 400)
    if metadata.get('awaitingAudioUpload') or metadata.get('matchedAudioAssetId'):
        raise SaaSError('speech_audio_conflict', '已有配套音频时不能同时生成 AI 朗读。', 400)
    voice = value.get('voice', 'af_heart')
    speed = value.get('speed', 1)
    if not isinstance(voice, str) or voice not in VOICES or isinstance(speed, bool):
        raise SaaSError('invalid_speech_options', '请选择有效的英文音色和语速。', 400)
    try:
        speed = float(speed)
    except (ValueError, TypeError):
        speed = float('nan')
    if not math.isfinite(speed) or not .75 <= speed <= 1.25:
        raise SaaSError('invalid_speech_options', '生成语速须在 0.75 至 1.25 之间。', 400)
    return {'engine': 'kokoro', 'voice': voice, 'speed': speed}


def attach_timing(data, result, request):
    """Accept measured sentence boundaries and explicitly predicted word times."""
    sentences = data['sentences']
    timeline = result.get('sentences', [])
    duration = float(result.get('duration', 0))
    if not math.isfinite(duration) or not 0 < duration <= 12 * 3600 or len(timeline) != len(sentences):
        raise ValueError('invalid narration duration or sentence count')
    previous = 0
    timed_words = 0
    for sentence, timing in zip(sentences, timeline):
        start, end = float(timing['start']), float(timing['end'])
        if timing['id'] != sentence['id'] or not previous <= start < end <= duration:
            raise ValueError('invalid narration sentence timeline')
        sentence.update(start=start, end=end, timingPolicy='kokoro-sentence-audio')
        previous = end
        words = timing.get('words') or []
        if words:
            if len(words) != len(sentence['words']):
                raise ValueError('invalid narration word count')
            word_end = start
            previous_interval = None
            for word, measured in zip(sentence['words'], words):
                a, b = float(measured['start']), float(measured['end'])
                group = measured.get('timingGroup')
                shared = isinstance(group,str) and bool(group) and previous_interval == (a,b,group)
                if measured['text'] != word['text'] or not math.isfinite(a) or not math.isfinite(b) or not start <= a < b <= end or (a < word_end and not shared):
                    raise ValueError('invalid narration word timeline')
                word.update(start=a, end=b, timingSource='kokoro-predicted-duration', estimated=True)
                if group:word['timingGroup']=group
                word_end = b
                previous_interval = (a,b,group)
                timed_words += 1
    data.update(duration=duration, alignment='kokoro-sentence-audio', speechSynthesis={
        'engine': 'kokoro', 'model': 'hexgrad/Kokoro-82M', 'version': '1.0',
        'voice': request['voice'], 'language': 'en-US' if request['voice'][0] == 'a' else 'en-GB',
        'speed': request['speed'], 'synthetic': True,
        'sentenceTiming': 'generated-audio-samples', 'wordTiming': 'model-predicted-duration',
        'timedWords': timed_words,
    })
    return data


def reader_speech(data):
    value = data.get('speechSynthesis')
    if not isinstance(value, dict) or value.get('engine') != 'kokoro' or value.get('synthetic') is not True:
        return None
    return {key: value[key] for key in ('engine', 'model', 'voice', 'language', 'speed', 'synthetic') if key in value}


def generate(service, data, source, task_id, user_id, request):
    """Generate privately; the caller atomically registers the result with the book."""
    if not options()['available']:
        raise SaaSError('speech_unavailable', 'AI 朗读尚未安装，请联系管理员。', 503)
    text = ' '.join(sentence['text'] for sentence in data['sentences'])
    if len(text) > MAX_CHARACTERS:
        raise SaaSError('speech_text_too_long', f'本次试用最多生成 {MAX_CHARACTERS:,} 个字符，请分册导入。', 400)
    letters = [char for char in text if char.isalpha()]
    if not letters or sum(bool(re.fullmatch('[A-Za-z]', char)) for char in letters) / len(letters) < .9:
        raise SaaSError('speech_english_required', '本次 AI 朗读仅支持英文正文，请检查 PDF 识别结果或选择英文读物。', 400)

    def check(value, step):
        service.assert_access(user_id)
        with service.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                task = service._task(cursor, user_id, task_id)
                if task['status'] != 'running':
                    raise SaaSError('import_task_terminal', '导入已取消。', 409)
        service._update_progress(task_id, value, step)

    while not GENERATION_LOCK.acquire(timeout=2):
        check(40, '等待 AI 朗读生成')
    try:
        check(40, '正在加载 AI 朗读音色')
        home, python = runtime()
        budget = (service.media.ensure_private_capacity(user_id, 0)['available']
                  if not service.official else 2 * 1024**3)
        if budget < 1024:
            raise SaaSError('quota_exceeded', '私人学习空间不足，无法保存朗读音频。', 409)
        with tempfile.TemporaryDirectory(prefix='.kokoro-', dir=source.parent) as folder:
            root = Path(folder)
            input_file, output, wav, mp3 = [root / name for name in ('input.json', 'timing.json', 'audio.wav', 'audio.mp3')]
            input_file.write_text(json.dumps({**request, 'sentences': data['sentences']}, ensure_ascii=False))
            environment = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                           'HF_HOME': str(home / 'cache'), 'TOKENIZERS_PARALLELISM': 'false'}
            command = [str(python), str(ROOT / 'tools/kokoro_worker.py'), '--home', str(home),
                       '--input', str(input_file), '--output', str(output), '--audio', str(wav),
                       '--max-bytes', str(min(2 * 1024**3, budget * 5))]
            try:
                process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE,
                                           stderr=subprocess.DEVNULL, text=True)
                messages = queue.Queue()

                def read_progress():
                    for line in process.stdout:
                        try: messages.put(json.loads(line))
                        except ValueError: pass

                threading.Thread(target=read_progress, daemon=True).start()
                deadline = time.monotonic() + 4 * 3600
                value, step = 40, '正在生成 AI 朗读音频'
                while process.poll() is None:
                    if time.monotonic() > deadline:
                        raise SaaSError('speech_timeout', 'AI 朗读生成超时，请分册导入后重试。', 504)
                    try:
                        message = messages.get(timeout=2)
                        value = max(value, 40 + round(max(0, min(100, int(message['progress']))) * .45))
                        step = f"正在生成 AI 朗读 · {int(message['done'])}/{int(message['total'])} 句"
                    except queue.Empty:
                        pass
                    check(value, step)
                if process.returncode:
                    raise SaaSError('speech_generation_failed', 'AI 朗读生成失败，请检查英文正文和模型环境后重试。', 422)
            except OSError as exc:
                raise SaaSError('speech_unavailable', '无法启动 AI 朗读处理器，请联系管理员。', 503) from exc
            finally:
                if 'process' in locals():
                    if process.poll() is None:
                        process.kill()
                    process.wait()
                    process.stdout.close()
            check(88, '正在保存 AI 朗读音频')
            try:
                result = json.loads(output.read_text())
                attach_timing(data, result, request)
                ffmpeg = str(service.ffmpeg)
                if ffmpeg == 'ffmpeg' and not shutil.which(ffmpeg):
                    ffmpeg = str(ROOT / '.local/local-dev/tools/ffmpeg/bin/ffmpeg')
                ffprobe = str(Path(ffmpeg).with_name('ffprobe')) if Path(ffmpeg).is_file() else 'ffprobe'
                subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-i', str(wav),
                                '-codec:a', 'libmp3lame', '-b:a', '64k', str(mp3)],
                               check=True, timeout=600, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                duration = float(subprocess.check_output([ffprobe, '-v', 'error', '-show_entries',
                                 'format=duration', '-of', 'default=nk=1:nw=1', str(mp3)], timeout=30, text=True))
                if not math.isfinite(duration) or abs(duration - data['duration']) > .2:
                    raise ValueError('narration duration mismatch')
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
                raise SaaSError('speech_output_invalid', 'AI 朗读音频或时间轴校验失败，请重试。', 422) from exc
            if mp3.stat().st_size > budget:
                raise SaaSError('quota_exceeded', '私人学习空间不足，无法保存朗读音频。', 409)
            check(92, '校验 AI 朗读与导入权限')
            from saas_auth import new_id
            target = source.parent / (new_id() + '.mp3')
            try:
                shutil.copyfile(mp3, target)
            except Exception:
                target.unlink(missing_ok=True)
                raise
            return {'name': 'audio', 'storagePath': target.relative_to(service.media.media_root).as_posix(),
                    'contentType': 'audio/mpeg'}
    finally:
        GENERATION_LOCK.release()
