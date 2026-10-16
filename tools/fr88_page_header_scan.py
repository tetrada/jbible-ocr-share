#!/usr/bin/env python3
"""Read top-of-page running head: page book title + first chapter:verse.

One DeepSeek Flash vision job per SCANNED PAGE, not per marginal reference.
This is read-only input and UNVERIFIED text-only output; no SQL or link import.
The later alignment step must still detect in-body verse markers and chapter
changes within each column, not assign a source by page start alone.
"""
import argparse
import base64
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps, ImageEnhance

RAW=Path("/raw")
SCANS=RAW/"fr_bible_1988"
OUT=RAW/"jbible_fr88_page_headers_pilot"
PROMPT=OUT/"frozen_header_prompt.txt"
MODEL="deepseek-flash"
URL="https://api.deepseek.com/chat/completions"
PIPELINE="FR88-page-running-head-v1"
FIRST,LAST=31,40


def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+".tmp")
    with temp.open("w",encoding="utf-8") as fh:
        json.dump(obj,fh,indent=2,ensure_ascii=False)
        fh.write("\n")
    os.replace(str(temp),str(path))


def jpeg(im,wide,tall):
    im=ImageEnhance.Contrast(im.convert("RGB")).enhance(1.12)
    im.thumbnail((wide,tall),Image.Resampling.LANCZOS)
    buff=io.BytesIO()
    im.save(buff,"JPEG",quality=93,optimize=True)
    return buff.getvalue()


def parts_for(page):
    path=SCANS/("image_%04d.jpg"%page)
    with Image.open(str(path)) as src:
        im=ImageOps.exif_transpose(src).convert("RGB")
    w,h=im.size
    return {
        "header_full":jpeg(im.crop((0,0,w,int(h*.23))),2400,900),
        "header_left":jpeg(im.crop((0,0,int(w*.55),int(h*.23))),1800,1000),
        "page_context":jpeg(im,1100,1850)
    }


def signature(page,parts,prompt):
    dig=hashlib.sha256()
    for chunk in (PIPELINE,MODEL,str(page),prompt):
        dig.update(chunk.encode("utf-8"))
    for name in ("header_full","header_left","page_context"):
        dig.update(parts[name])
    return dig.hexdigest()


def request_body(page,parts,prompt):
    content=[{"type":"text","text":"Original French Jerusalem Bible 1988 scanned JPEG image_%04d.jpg. Read the TOP LEFT chapter/verse running head and printed book header only. Images: upper strip, magnified upper left, full-page context. Ignore marginal cross-references."%page}]
    for name in ("header_full","header_left","page_context"):
        content.append({"type":"image_url","image_url":{"url":
            "data:image/jpeg;base64,"+base64.b64encode(parts[name]).decode("ascii")}})
    return json.dumps({"model":MODEL,"thinking":{"type":"disabled"},
        "response_format":{"type":"json_object"},"max_tokens":1200,
        "messages":[{"role":"system","content":prompt},
                    {"role":"user","content":content}]},
        ensure_ascii=False).encode("utf-8")


def call_deepseek(token,body):
    for attempt in range(1,5):
        req=urllib.request.Request(URL,data=body,method="POST",headers={
            "Content-Type":"application/json","Authorization":"Bearer "+token})
        try:
            with urllib.request.urlopen(req,timeout=300) as reply:
                return json.loads(reply.read().decode("utf-8")),attempt
        except urllib.error.HTTPError as exc:
            if exc.code not in (429,500,502,503,504) or attempt==4:
                raise RuntimeError("DeepSeek HTTP %d after %d tries"%(exc.code,attempt))
        except (urllib.error.URLError,TimeoutError,ConnectionError):
            if attempt==4:
                raise RuntimeError("DeepSeek unreachable after four tries")
        time.sleep(5*attempt)
    raise RuntimeError("DeepSeek retries exhausted")


def to_int(value):
    return value if type(value) is int and 1<=value<=2000 else None


def decode(provider,page):
    choices=provider.get("choices") or []
    message=(choices[0].get("message") or {}) if choices else {}
    content=message.get("content")
    if not isinstance(content,str):
        raise ValueError("DeepSeek page header JSON missing")
    j=json.loads(content)
    if not isinstance(j,dict):
        raise ValueError("Expected JSON object for page header")
    chapter=to_int(j.get("page_start_chapter"))
    verse=to_int(j.get("page_start_verse"))
    chapter_visible=j.get("header_chapter_marker_visible") is True
    verse_visible=j.get("header_verse_marker_visible") is True
    if not chapter_visible:
        chapter=None
    if not verse_visible:
        verse=None
    confidence=j.get("confidence")
    if confidence not in ("HIGH","MEDIUM","LOW"):
        confidence="LOW"
    title=j.get("page_book_header_printed")
    raw=j.get("top_left_running_head_raw")
    issue=j.get("issue")
    return {
        "schema":"jbible.fr88.page-start-header.v1",
        "page":page,
        "book_title_printed":str(title)[:90] if isinstance(title,str) else None,
        "top_left_raw":str(raw)[:50] if isinstance(raw,str) else None,
        "start_chapter":chapter,
        "start_verse":verse,
        "chapter_marker_visible":chapter_visible,
        "verse_marker_visible":verse_visible,
        "confidence":confidence,
        "issue":str(issue or "")[:130],
        "warnings":[str(v)[:180] for v in j.get("warnings",[])
                    if isinstance(v,str)][:10] if isinstance(j.get("warnings"),list) else [],
        "human_verified":False,
        "sql_writes":False,
        "note":"Only scanned top-of-page start, not full verse-marker layout. In-page chapter changes must be tracked separately."
    }


def report(start,end,started=0):
    pages={}
    for p in range(start,end+1):
        file=OUT/("image_%04d.result.json"%p)
        if file.exists():
            record=json.loads(file.read_text(encoding="utf-8"))
            pages[str(p)]=record["header"]
    summary={
        "schema":"jbible.fr88.page-start-pilot.summary.v1",
        "pages":[start,end],
        "complete":len(pages),
        "expected":end-start+1,
        "new_deepseek_page_jobs_this_run":started,
        "headers":pages,
        "human_verified_headers":0,
        "sql_writes":False
    }
    save(OUT/"page_headers.json",summary)
    print("PAGE HEADERS: %d/%d scanned; API jobs this run=%d"%
          (len(pages),end-start+1,started),flush=True)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start",type=int,default=FIRST)
    parser.add_argument("--end",type=int,default=LAST)
    parser.add_argument("--preflight",action="store_true")
    parser.add_argument("--report-only",action="store_true")
    parser.add_argument("--max-new-pages",type=int,default=2)
    args=parser.parse_args()
    if not FIRST<=args.start<=args.end<=LAST:
        parser.error("Pilot restricted to pages 31..40")
    if not 1<=args.max_new_pages<=10:
        parser.error("Use --max-new-pages 1..10")
    if args.report_only:
        report(args.start,args.end)
        return 0
    if not PROMPT.is_file():
        raise RuntimeError("Missing frozen page-header instructions")
    prompt=PROMPT.read_text(encoding="utf-8")
    missing=[p for p in range(args.start,args.end+1)
             if not (SCANS/("image_%04d.jpg"%p)).is_file()]
    if missing:
        raise RuntimeError("Missing source scanned pages: "+str(missing))
    print("PREFLIGHT OK: running headers for %d pages; DeepSeek only; no SQL"%
          (args.end-args.start+1),flush=True)
    if args.preflight:
        return 0
    token=os.environ.get("DEEPSEEK_API_KEY","").strip()
    if not token:
        parser.error("Missing DeepSeek key from Docker env")
    paid=0
    for page in range(args.start,args.end+1):
        key="image_%04d"%page
        cp=OUT/(key+".result.json")
        provider=OUT/(key+".provider.json")
        images=parts_for(page)
        sig=signature(page,images,prompt)
        if cp.is_file():
            old=json.loads(cp.read_text(encoding="utf-8"))
            if old.get("signature")!=sig:
                raise RuntimeError("Header checkpoint fingerprint mismatch: "+key)
            print("CACHE",key,flush=True)
            continue
        if provider.is_file():
            old=json.loads(provider.read_text(encoding="utf-8"))
            if old.get("signature")!=sig:
                raise RuntimeError("Header provider fingerprint mismatch: "+key)
            result=old["response"]
            print("REPARSE SAVED HEADER",key,flush=True)
        else:
            if paid>=args.max_new_pages:
                report(args.start,args.end,paid)
                print("PAGE BUDGET reached; rerun to resume",flush=True)
                return 0
            paid+=1
            print("DEEPSEEK HEADER",key,"job",paid,flush=True)
            result,attempts=call_deepseek(token,request_body(page,images,prompt))
            save(provider,{"signature":sig,"response":result,"attempts":attempts})
        head=decode(result,page)
        save(cp,{"signature":sig,"header":head})
        report(args.start,args.end,paid)
    final=report(args.start,args.end,paid)
    return 0 if final["complete"]==final["expected"] else 1


if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("PAGE HEADER ERROR %s: %s"%(type(exc).__name__,exc),
              file=sys.stderr,flush=True)
        sys.exit(1)
