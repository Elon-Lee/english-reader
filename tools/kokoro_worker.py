#!/usr/bin/env python3
"""Isolated Kokoro worker. Models and English NLP resources must be installed."""
from __future__ import annotations

import argparse
import gc
import json
import math
import os
from pathlib import Path
import re
import sys
import wave

from text_segmentation import WORD_RE

SAMPLE_RATE = 24000


def speech_chunks(text, limit=0):
    """Bound inference activations without cutting a word or losing text."""
    if limit <= 0 or len(text) <= limit:
        return text
    chunks = []
    current = ''
    for token in re.findall(r'\S+\s*', text):
        if current and len(current) + len(token) > limit:
            chunks.append(current.strip())
            current = ''
        current += token
    if current.strip():
        chunks.append(current.strip())
    return chunks


def word_timing(sentence, tokens):
    """Match lexical boundaries, retaining a model token's compound-word group.

    A hyphenated model token may cover several display words; its measured
    interval belongs to the entire group. Never divide it into guessed times.
    """
    def lexical(text):
        return ''.join(WORD_RE.findall(text)).replace('’', "'").casefold()
    expected = [lexical(word['text']) for word in sentence['words']]
    measured = []
    previous = float(sentence['start'])
    for text, start, end in tokens:
        value = lexical(text)
        if not value:
            continue
        if start is None or end is None:
            return []
        start, end = float(start), float(end)
        if not math.isfinite(start) or not math.isfinite(end) or not previous <= start < end <= sentence['end']:
            return []
        measured.append({'text': value, 'start': start, 'end': end})
        previous = end
    if not all(expected) or ''.join(expected) != ''.join(word['text'] for word in measured):
        return []
    # Only boundaries shared by the model and the learning words split a group.
    expected_ends, measured_ends = [], []
    for word in expected:expected_ends.append((expected_ends[-1] if expected_ends else 0)+len(word))
    for word in measured:measured_ends.append((measured_ends[-1] if measured_ends else 0)+len(word['text']))
    boundaries = sorted(set(expected_ends) & set(measured_ends))
    result=[]; first_word=first_token=0
    for boundary in boundaries:
        last_word=first_word
        while expected_ends[last_word]<boundary:last_word+=1
        last_token=first_token
        while measured_ends[last_token]<boundary:last_token+=1
        for index in range(first_word,last_word+1):
            word={'text':sentence['words'][index]['text'], 'start':measured[first_token]['start'], 'end':measured[last_token]['end']}
            if last_word>first_word:word['timingGroup']=f'kokoro-{first_word}-{last_word}'
            result.append(word)
        first_word,first_token=last_word+1,last_token+1
    return result


def synthesize(sentences, pipeline, voice, speed, audio_path, max_bytes):
    import numpy as np
    output = []
    frames = 0
    chunk_limit = int(os.environ.get('SHIYUE_KOKORO_CHUNK_CHARACTERS','0'))
    with wave.open(str(audio_path), 'wb') as audio:
        audio.setparams((1, 2, SAMPLE_RATE, 0, 'NONE', 'not compressed'))
        for index, source in enumerate(sentences):
            start = frames / SAMPLE_RATE
            tokens = []
            text = speech_chunks(source['text'], chunk_limit)
            for chunk in pipeline(text, voice=voice, speed=speed, split_pattern=None):
                if chunk.audio is None:
                    raise ValueError('Kokoro produced no audio')
                samples = chunk.audio.detach().cpu().numpy().reshape(-1)
                if not len(samples) or not np.isfinite(samples).all():
                    raise ValueError('Kokoro produced invalid audio')
                offset = frames / SAMPLE_RATE
                for token in chunk.tokens or []:
                    a, b = getattr(token, 'start_ts', None), getattr(token, 'end_ts', None)
                    tokens.append((token.text, offset + a if a is not None else None,
                                   offset + b if b is not None else None))
                frames += len(samples)
                if frames > SAMPLE_RATE * 12 * 3600 or frames * 2 + 44 > max_bytes:
                    raise ValueError('朗读音频超过可用空间或 12 小时时长限制')
                audio.writeframes((np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes())
                if chunk_limit and sys.platform == 'linux':
                    # CPU inference frees temporary activations, but glibc can
                    # retain those arenas. Return them before the next chunk.
                    gc.collect()
                    import ctypes
                    try:ctypes.CDLL(None).malloc_trim(0)
                    except (AttributeError,OSError):pass
            end = frames / SAMPLE_RATE
            if end <= start:
                raise ValueError('此句未生成有效音频，请检查正文是否为英文')
            sentence = {'id': source['id'], 'start': start, 'end': end, 'words': source['words']}
            sentence['words'] = word_timing(sentence, tokens)
            output.append(sentence)
            print(json.dumps({'progress': round((index + 1) / len(sentences) * 100),
                              'done': index + 1, 'total': len(sentences)}), flush=True)
    return {'duration': frames / SAMPLE_RATE, 'sentences': output}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--max-bytes', type=int, required=True)
    args = parser.parse_args()
    # Never contact model hosts while processing a user's import.
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                      HF_HOME=str(args.home / 'cache'), TOKENIZERS_PARALLELISM='false')
    import torch
    import spacy
    from kokoro import KModel, KPipeline
    if not spacy.util.is_package('en_core_web_sm'):
        raise RuntimeError('English NLP model is not installed')
    request = json.loads(args.input.read_text())
    voice = request['voice']
    if voice not in {'af_heart', 'am_michael', 'bf_emma', 'bm_george'}:
        raise ValueError('unsupported voice')
    torch.set_num_threads(max(1,min(8,int(os.environ.get('SHIYUE_KOKORO_THREADS','2')))))
    if int(os.environ.get('SHIYUE_KOKORO_CHUNK_CHARACTERS','0')) > 0:
        # oneDNN's shape-specific convolution caches are costly on 2GiB hosts.
        # The bounded mode trades that acceleration for a lower memory peak.
        torch.backends.mkldnn.enabled = False
    model = KModel(repo_id='hexgrad/Kokoro-82M', config=str(args.home / 'model/config.json'),
                   model=str(args.home / 'model/kokoro-v1_0.pth')).to('cpu').eval()
    pipeline = KPipeline(lang_code=voice[0], repo_id='hexgrad/Kokoro-82M', model=model)
    pipeline.voices[voice] = torch.load(args.home / f'model/voices/{voice}.pt', map_location='cpu', weights_only=True)
    result = synthesize(request['sentences'], pipeline, voice, request['speed'], args.audio, args.max_bytes)
    args.output.write_text(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Do not put book text, input payloads or model-host credentials in task errors.
        print(f'Kokoro worker failed: {type(error).__name__}', file=sys.stderr)
        raise SystemExit(1)
