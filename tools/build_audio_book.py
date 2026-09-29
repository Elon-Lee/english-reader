#!/usr/bin/env python3
"""Build a readable local book directly from Whisper output."""
import argparse
import json
from pathlib import Path

from build_video_book import duration, whisper_book

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--whisper",required=True,type=Path)
    parser.add_argument("--audio",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--id",required=True)
    parser.add_argument("--title",required=True)
    parser.add_argument("--english-title",default="")
    parser.add_argument("--level",default="")
    parser.add_argument("--audio-url",required=True)
    args=parser.parse_args()
    whisper=json.loads(args.whisper.read_text());sentences=whisper_book(whisper)
    for sentence in sentences:sentence["page"]=1
    book={"id":args.id,"title":args.title,"englishTitle":args.english_title,"level":args.level,
          "sourceType":"audio","audio":args.audio_url,"pdf":"","pageBase":"","hasOriginalPages":False,
          "duration":duration(args.audio),"alignment":"whisper-dtw-normalized","sentences":sentences,
          "whisper":{"engine":"whisper.cpp","model":"base.en","timestampMethod":"dtw",
                     "transcribedWords":sum(len(sentence["words"]) for sentence in sentences)}}
    args.output.write_text(json.dumps(book,ensure_ascii=False,indent=2))
    print(f"Built audio book: {len(sentences)} sentences")

if __name__=="__main__":main()
