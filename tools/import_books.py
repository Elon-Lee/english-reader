#!/usr/bin/env python3
"""Scan the Oxford Bookworms folders and prepare books for the local reader.

Run --scan first. For a scanned PDF, compile/run pdf_ocr.swift, then call this
tool with --book-dir and --ocr. Whisper/Vosk word timestamps can later replace
the estimated alignment without changing the reader UI.
"""
import argparse, json, re, shutil, subprocess
from pathlib import Path

def scan(root):
    books=[]
    for folder in sorted(p for p in root.glob("牛津书虫全系列7级（*）/*") if p.is_dir()):
        pdfs=list(folder.glob("*.pdf")); audio=list(folder.glob("*.mp3"))
        books.append({"folder":str(folder),"pdf":[str(x) for x in pdfs],"audio":[str(x) for x in audio],
                      "ready":bool(pdfs and audio)})
    return books

def main():
    ap=argparse.ArgumentParser(description="Import local graded readers")
    ap.add_argument("--root",type=Path,default=Path.cwd())
    ap.add_argument("--scan",action="store_true")
    ap.add_argument("--book-dir",type=Path)
    ap.add_argument("--ocr",type=Path)
    ap.add_argument("--slug")
    ap.add_argument("--title")
    ap.add_argument("--page-start",type=int,default=1)
    ap.add_argument("--page-end",type=int)
    ap.add_argument("--audio-start",type=float,default=0.0)
    ap.add_argument("--section-fixes",type=Path)
    ap.add_argument("--whisper-json",type=Path,help="existing whisper.cpp full JSON to align after import")
    args=ap.parse_args()
    if args.scan:
        items=scan(args.root)
        Path("reader/data/library-scan.json").write_text(json.dumps(items,ensure_ascii=False,indent=2))
        print(f"Found {len(items)} books; {sum(x['ready'] for x in items)} have PDF + MP3")
        return
    if not all([args.book_dir,args.ocr,args.slug,args.title]): ap.error("import requires --book-dir --ocr --slug --title")
    pdf=next(args.book_dir.glob("*.pdf")); audio=next(args.book_dir.glob("*.mp3"))
    out=Path("reader/assets")/args.slug; data=Path("reader/data")/args.slug
    out.mkdir(parents=True,exist_ok=True); data.mkdir(parents=True,exist_ok=True)
    shutil.copy2(pdf,out/"book.pdf"); shutil.copy2(audio,out/"audio.mp3")
    cmd=["python3","tools/build_book.py","--ocr",str(args.ocr),"--audio",str(audio),"--output",str(data/"book.json"),
         "--title",args.title,"--page-start",str(args.page_start),"--audio-url",f"assets/{args.slug}/audio.mp3",
         "--pdf-url",f"assets/{args.slug}/book.pdf","--audio-start",str(args.audio_start)]
    if args.page_end: cmd += ["--page-end",str(args.page_end)]
    if args.section_fixes: cmd += ["--section-fixes",str(args.section_fixes)]
    subprocess.run(cmd,check=True)
    if args.whisper_json:
        subprocess.run(["python3","tools/align_whisper.py","--book",str(data/"book.json"),
                        "--whisper",str(args.whisper_json),"--report",str(data/"whisper-alignment.json")],check=True)
    dictionary_books=list(Path("reader/data").glob("*/book.json"))
    if Path("tools/vendor/ECDICT/ecdict.csv").exists() and dictionary_books:
        dictionary_cmd=["python3","tools/build_local_dictionary.py"]
        for book_json in dictionary_books: dictionary_cmd += ["--book",str(book_json)]
        dictionary_cmd += ["--output","reader/data/dictionary.json"]
        subprocess.run(dictionary_cmd,check=True)
    report=data/"quality-report.json"
    if report.exists():
        info=json.loads(report.read_text())
        print("Quality:",json.dumps(info["summary"],ensure_ascii=False))
    print("Imported. Add the book JSON path to reader/data/library.json if this is a new title.")
if __name__ == "__main__": main()
