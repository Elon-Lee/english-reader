#!/usr/bin/env python3
"""Annotate a timed book with SaT boundaries and run fused global segmentation."""
import argparse,json
from pathlib import Path

from sat_integration import annotate_sat_boundaries
from timed_segmentation import detect_silences,flatten_book_words,resegment_timed_book

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--book",required=True,type=Path);parser.add_argument("--audio",required=True,type=Path);parser.add_argument("--output",type=Path);parser.add_argument("--profile",choices=["youtube-auto","youtube-manual","local-subtitle","speech-asr"],required=True);parser.add_argument("--force",action="store_true");args=parser.parse_args()
    book=json.loads(args.book.read_text());report=annotate_sat_boundaries(book,args.profile,args.force)
    segmentation=resegment_timed_book(book,"yt",detect_silences(args.audio),profile=args.profile);segmentation["sat"]=report;book["segmentation"]=segmentation
    (args.output or args.book).write_text(json.dumps(book,ensure_ascii=False,indent=2));print(json.dumps(segmentation,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
