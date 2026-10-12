#!/usr/bin/env python3
"""Linux PDF text/OCR adapter matching the SaaS importer JSON contract."""
import json,re,subprocess,sys,tempfile
from pathlib import Path


def lines(text):
    return [{"text":value.strip(),"x":0,"y":0,"width":1,"height":0,"confidence":1.0} for value in text.splitlines() if value.strip()]


def main():
    if len(sys.argv)<4:raise SystemExit("Usage: pdf_ocr <input.pdf> <output.json> <image-directory> [scale]")
    source=Path(sys.argv[1]);output=Path(sys.argv[2]);images=Path(sys.argv[3]);images.mkdir(parents=True,exist_ok=True)
    text=subprocess.run(["pdftotext","-layout",str(source),"-"],text=True,capture_output=True,check=True).stdout
    pages=text.split("\f");use_ocr=sum(len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]",page)) for page in pages)<80
    if use_ocr:
        prefix=images/"page";subprocess.run(["pdftoppm","-jpeg","-r","144",str(source),str(prefix)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        pages=[]
        for image in sorted(images.glob("page-*.jpg")):
            result=subprocess.run(["tesseract",str(image),"stdout","-l","eng+chi_sim"],text=True,capture_output=True)
            if result.returncode and not result.stdout:result=subprocess.run(["tesseract",str(image),"stdout","-l","eng"],text=True,capture_output=True,check=True)
            pages.append(result.stdout)
    payload=[]
    for index,page in enumerate(pages):
        if not page.strip() and index==len(pages)-1:continue
        payload.append({"page":index+1,"width":0,"height":0,"image":"","lines":lines(page)})
    output.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")


if __name__=="__main__":main()
