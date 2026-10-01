#!/usr/bin/env python3
"""Run SaT in its isolated environment and return per-word boundary probabilities."""
import argparse,json,re
from pathlib import Path

from wtpsplit import SaT

WORD_RE=re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|\d+")

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--input",required=True,type=Path);parser.add_argument("--output",required=True,type=Path);parser.add_argument("--model",default="sat-3l-sm");args=parser.parse_args()
    words=json.loads(args.input.read_text());pieces=[];ends=[];cursor=0
    for index,word in enumerate(words):
        token=str(word.get("text","")).strip();punctuation=str(word.get("punctuationAfter","")).strip();piece=token+punctuation
        if index:pieces.append(" ");cursor+=1
        pieces.append(piece);cursor+=len(piece);ends.append(max(0,cursor-1))
    text="".join(pieces);model=SaT(args.model,ort_providers=["CPUExecutionProvider"]);probabilities=model.predict_proba(text)
    result={"model":args.model,"words":len(words),"textCharacters":len(text),"boundaryProbabilities":[round(float(probabilities[min(index,len(probabilities)-1)]),6) for index in ends]}
    args.output.write_text(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
