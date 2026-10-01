#!/usr/bin/env python3
"""Optional local SaT boundary inference shared by video/audio import pipelines."""
import json,os,subprocess,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SAT_PYTHON=ROOT/".local/sentence-segmenter/venv/bin/python"
SAT_SCRIPT=ROOT/"tools/sat_boundaries.py"
HF_HOME=ROOT/".local/sentence-segmenter/huggingface"

def original_words(book):return [word for sentence in book.get("sentences",[]) for word in sentence.get("words",[])]
def punctuation_ratio(words):return sum(bool(word.get("punctuationAfter") or word.get("speechBreakAfter")) for word in words)/max(1,len(words))

def should_use_sat(profile,words,force=False):
    if force:return True,"forced"
    if profile in {"youtube-auto","speech-asr"}:return True,"asr-profile"
    if profile in {"youtube-manual","local-subtitle"} and punctuation_ratio(words)<.025:return True,"sparse-punctuation"
    return False,"trusted-punctuation"

def annotate_sat_boundaries(book,profile,force=False):
    words=original_words(book);enabled,reason=should_use_sat(profile,words,force)
    report={"enabled":False,"profile":profile,"reason":reason,"words":len(words)}
    if not enabled:return report
    if not SAT_PYTHON.exists():return {**report,"reason":"environment-missing"}
    with tempfile.TemporaryDirectory(prefix="shiyue-sat-") as temp:
        source=Path(temp)/"words.json";target=Path(temp)/"boundaries.json";source.write_text(json.dumps(words,ensure_ascii=False));env={**os.environ,"HF_HOME":str(HF_HOME),"TOKENIZERS_PARALLELISM":"false"}
        try:subprocess.run([SAT_PYTHON,SAT_SCRIPT,"--input",source,"--output",target],check=True,cwd=ROOT,env=env,stdout=subprocess.DEVNULL)
        except subprocess.CalledProcessError as exc:return {**report,"reason":f"inference-failed:{exc.returncode}"}
        result=json.loads(target.read_text());probabilities=result.get("boundaryProbabilities",[])
    if len(probabilities)!=len(words):return {**report,"reason":"boundary-count-mismatch"}
    for word,probability in zip(words,probabilities):word["satBoundaryProbability"]=probability
    return {"enabled":True,"profile":profile,"reason":reason,"model":result.get("model","sat-3l-sm"),"words":len(words),"meanProbability":round(sum(probabilities)/max(1,len(probabilities)),6)}
