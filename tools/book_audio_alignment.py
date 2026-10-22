#!/usr/bin/env python3
"""Bounded-window acoustic alignment of canonical book text; no database access."""
import argparse
import json
import math
import os
import sys
import wave
from difflib import SequenceMatcher
from pathlib import Path


def match_anchors(expected, heard):
    """Require consecutive words to disambiguate repeated short phrases."""
    result = {}
    for block in SequenceMatcher(None, expected, heard, autojunk=False).get_matching_blocks():
        if block.size >= min(3,len(expected)) and block.size:
            result.update((block.a+i, block.b+i) for i in range(block.size))
    return result


def apply_timings(book, positions, timings):
    for sentence in book['sentences']:
        sentence.pop('start', None)
        sentence.pop('end', None)
        sentence['timingPolicy'] = 'acoustic-only'
        for word in sentence['words']:
            for key in ('start', 'end', 'confidence', 'startTime', 'endTime', 'timingSource'):
                word.pop(key, None)
            word.update(aligned=False, estimated=False)
    for index, timing in timings.items():
        sentence, word = positions[index]
        book['sentences'][sentence]['words'][word].update(timing, aligned=True,
            estimated=False, timingSource='book-audio-ctc')
    for sentence in book['sentences']:
        timed = [w for w in sentence['words'] if w['aligned']]
        if timed:
            sentence.update(start=timed[0]['start'], end=timed[-1]['end'])
    book['alignment'] = 'book-audio-ctc-v1'
    book['audioAlignment'] = {'method': book['alignment'], 'words': len(positions),
        'alignedWords': len(timings), 'coverage': round(len(timings)/max(1,len(positions)),4),
        'timedSentences': sum('start' in s for s in book['sentences']),
        'unmatchedWordsHaveNoTimestamps': True}
    return book


def main():
    parser = argparse.ArgumentParser()
    for name in ('audio', 'input', 'output', 'model-home'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--limit-seconds', type=float)
    parser.add_argument('--emissions-cache', type=Path)
    parser.add_argument('--cached-only', action='store_true', help='Inspect an incomplete acoustic cache without publishing')
    args = parser.parse_args()
    from manual_caption_alignment import MODEL_FILE
    if not (args.model_home/'hub/checkpoints'/MODEL_FILE).is_file():
        raise ValueError('Local acoustic model missing')
    os.environ['TORCH_HOME'] = str(args.model_home)
    import numpy as np
    import torch
    import torchaudio
    from ctc_forced_align import normalized_word
    torch.set_num_threads(max(1,min(3,int(os.environ.get('SHIYUE_CTC_THREADS','2')))))
    torch.set_num_interop_threads(1)
    bundle = torchaudio.pipelines.WAV2VEC2_ASR_BASE_960H
    model = bundle.get_model().eval()
    labels = bundle.get_labels(); dictionary = {c:i for i,c in enumerate(labels)}
    book = json.loads(args.input.read_text())
    positions=[]; expected=[]
    for si,sentence in enumerate(book['sentences']):
        for wi,word in enumerate(sentence['words']):
            positions.append((si,wi)); expected.append(normalized_word(word['text']) or '<unsupported>')
    # Keep emissions, rather than the full waveform/attention matrices, in memory.
    chunks=[]; frame_times=[]
    with wave.open(str(args.audio),'rb') as audio:
        if (audio.getframerate(),audio.getnchannels(),audio.getsampwidth()) != (16000,1,2):
            raise ValueError('Expected mono 16kHz PCM16 WAV')
        duration=audio.getnframes()/16000
        if args.limit_seconds: duration=min(duration,args.limit_seconds)
        cache=args.emissions_cache
        resume=0
        if cache and cache.is_file():
            saved=torch.load(cache,weights_only=True)
            if saved['audioSize']!=args.audio.stat().st_size or saved['duration']!=duration:
                raise ValueError('Acoustic cache belongs to a different audio file')
            chunks=saved['chunks'];frame_times=saved['times'];resume=saved['resume']
        if args.cached_only and not chunks:raise ValueError('No acoustic cache to inspect')
        for offset in range(resume, resume if args.cached_only else math.ceil(duration),10):
            left=max(0,offset-1); right=min(duration,offset+11)
            audio.setpos(int(left*16000))
            samples=np.frombuffer(audio.readframes(int((right-left)*16000)),dtype=np.int16).copy()
            waveform=torch.from_numpy(samples).float().unsqueeze(0)/32768
            with torch.inference_mode():
                emissions,_=model(waveform)
                probs=torch.log_softmax(emissions[0],-1).cpu()
            times=left+(np.arange(len(probs))+.5)*(len(samples)/16000/len(probs))
            keep=(times>=offset)&(times<min(duration,offset+10))
            chunks.append(probs[keep]); frame_times.extend(times[keep].tolist())
            if cache and ((offset//10)%20==0 or offset+10>=duration):
                temporary=cache.with_suffix('.tmp')
                torch.save({'audioSize':args.audio.stat().st_size,'duration':duration,
                    'chunks':chunks,'times':frame_times,'resume':offset+10},temporary)
                temporary.replace(cache)
            print(f'caption_progress={round(min(duration,offset+10)/duration*85)}',file=sys.stderr,flush=True)
    probs=torch.cat(chunks); times=frame_times
    ids=probs.argmax(-1).tolist(); decoded=[]; pending=[]; last=None
    for frame,value in enumerate(ids):
        if value!=last and value:
            char=labels[value]
            if char=='|':
                if pending:
                    decoded.append({'text':''.join(x[0] for x in pending), 'left':pending[0][1], 'right':pending[-1][2]})
                    pending=[]
            else: pending.append([char,frame,frame+1])
        elif value and value==last and pending and labels[value]!='|': pending[-1][2]=frame+1
        last=value
    if pending: decoded.append({'text':''.join(x[0] for x in pending),'left':pending[0][1],'right':pending[-1][2]})
    anchors=match_anchors(expected,[w['text'] for w in decoded])
    if len(anchors)<min(20,len(expected)*.3): raise ValueError('Book text does not match this audio')
    timings={}
    def record(index,left,right,confidence):
        start=max(0,times[left]-.01); end=times[min(right-1,len(times)-1)]+.01
        if end>start and end-start<=2.5 and confidence>=.35:
            timings[index]={'start':round(start,3),'end':round(end,3),'confidence':round(confidence,4)}
    for index,di in anchors.items():
        word=decoded[di]
        segment=probs[word['left']:word['right']]
        nonblank=segment.argmax(-1)!=0
        confidence=float(segment.max(-1).values[nonblank].exp().mean()) if nonblank.any() else 0
        record(index,word['left'],word['right'],confidence)
    # Refine recognition errors between verified monotonic anchors using CTC.
    boundaries=[(-1,None)]+sorted(anchors.items())+[(len(expected),None)]
    for (previous,pdi),(following,fdi) in zip(boundaries,boundaries[1:]):
        if following-previous<=1 or following-previous>60: continue
        left=decoded[pdi]['right'] if pdi is not None else 0
        right=decoded[fdi]['left'] if fdi is not None else len(times)
        if right<=left or times[right-1]-times[left]>25: continue
        text='|'.join(expected[previous+1:following])
        if any(c not in dictionary for c in text): continue
        target=torch.tensor([[dictionary[c] for c in text]],dtype=torch.int32)
        if right-left<len(text)+sum(a==b for a,b in zip(text,text[1:])): continue
        with torch.inference_mode():
            path,scores=torchaudio.functional.forced_align(probs[left:right].unsqueeze(0),target,blank=0)
            spans=torchaudio.functional.merge_tokens(path[0],scores[0],blank=0)
        if len(spans)!=len(text): continue
        cursor=0
        for index in range(previous+1,following):
            selected=spans[cursor:cursor+len(expected[index])]; cursor+=len(expected[index])+1
            confidence=sum(math.exp(float(s.score)) for s in selected)/len(selected)
            record(index,left+selected[0].start,left+selected[-1].end,confidence)
    result=apply_timings(book,positions,timings)
    if result['audioAlignment']['coverage']<.5 and not args.cached_only: raise ValueError('Insufficient acoustic alignment coverage')
    if args.cached_only:result['audioAlignment']['diagnosticOnly']=True
    args.output.write_text(json.dumps(result,ensure_ascii=False))
    print('caption_progress=100',file=sys.stderr,flush=True)


if __name__=='__main__':main()
