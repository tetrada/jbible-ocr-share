#!/usr/bin/env python3
"""JBible FR88 integrated scanner: full page -> atomic source-to-target edges.

Only DeepSeek Flash. FIVE independently cached VISUAL tasks per scanned page:
 1 running head (TOP_LEFT FIRST or TOP_RIGHT LAST, physical printed page)
 2 main-text VERSE marker positions, column L and R
 2 marginal reference OCR, column L and R

Then deterministic verse-interval matching + independent target parsing.
Each parsed destination creates ONE edge. Nothing is written to SQL.
Existing historical OCR datasets, human decisions and source scans unchanged.

Run with /raw volume read-only EXCEPT new output overlay; never Git-publish
provider responses or copyrighted images. Python3.6-compatible, Pillow.
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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from fr88_page_layout_core import (
    catalog_limits, header_checked, make_intervals,
    atomic_edges, summary as edge_summary)
from fr88_v2_normalize import interpret_ocr_row
from fr88_link_edges import index_pages

RAW=Path("/raw")
IMAGES=RAW/"fr_bible_1988"
CATALOG=RAW/"jbible_catalog.csv"
OUT=RAW/"jbible_fr88_integrated_v1"
PAGE_REGISTRY=Path("/app/fr88_page_book_registry.json")
MODEL="deepseek-flash"
API="https://api.deepseek.com/chat/completions"
PIPELINE="JBIBLE-FR88-INTEGRATED-1"
TASKS=("header","verses_L","verses_R","margin_L","margin_R")
PROMPTS={task:OUT/(task.split("_")[0]+"_prompt.txt") for task in TASKS}


def utc():
    return datetime.now(timezone.utc).isoformat()


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+".tmp")
    with temp.open("w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)
        f.write("\n")
    os.replace(str(temp),str(path))


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def jpeg(im,w,h):
    pic=ImageEnhance.Contrast(im.convert("RGB")).enhance(1.09)
    pic.thumbnail((w,h),Image.Resampling.LANCZOS)
    pic=pic.filter(ImageFilter.UnsharpMask(radius=0.7,percent=70,threshold=3))
    b=io.BytesIO()
    pic.save(b,"JPEG",quality=92,optimize=True)
    return b.getvalue()


def images_for(scan,task):
    # Coordinates ALWAYS correspond to original scanned page height, not crop.
    with Image.open(str(scan)) as f:
        page=ImageOps.exif_transpose(f).convert("RGB")
    w,h=page.size
    if task=="header":
        return [
            jpeg(page.crop((0,0,w,max(1,int(h*.21)))),2200,900),
            jpeg(page.crop((0,0,int(w*.57),max(1,int(h*.19)))),1600,820),
            jpeg(page.crop((int(w*.43),0,w,max(1,int(h*.19)))),1600,820),
            jpeg(page,950,1600)
        ]
    side=task[-1]
    if side not in ("L","R"):
        raise ValueError("Unexpected page task "+task)
    if side=="L":
        half=page.crop((0,0,w//2,h))
        main=page.crop((int(w*.15),0,w//2,h))
        margin=page.crop((0,0,int(w*.41),h))
    else:
        half=page.crop((w//2,0,w,h))
        main=page.crop((w//2,0,int(w*.86),h))
        margin=page.crop((int(w*.59),0,w,h))
    if task.startswith("verses_"):
        hh=main.height
        return [
            jpeg(half,1270,3100),
            jpeg(main.crop((0,0,main.width,int(hh*.57))),1650,2450),
            jpeg(main.crop((0,int(hh*.43),main.width,hh)),1650,2450)
        ]
    hh=margin.height
    return [
        jpeg(half,1270,3100),
        jpeg(margin,1600,3400),
        jpeg(margin.crop((0,0,margin.width,int(hh*.57))),1600,2600),
        jpeg(margin.crop((0,int(hh*.43),margin.width,hh)),1600,2600)
    ]


def signature(page,task,prompt,source_bytes):
    digest=hashlib.sha256()
    for strval in (PIPELINE,MODEL,str(page),task,prompt):
        digest.update(strval.encode("utf-8"))
    digest.update(source_bytes)
    return digest.hexdigest()


def request_payload(page,task,prompt,images):
    description="Image image_%04d.jpg task %s. Return only printed visual observations, never biblical memory. All y positions relative to full scanned page height."%(page,task)
    msg=[{"type":"text","text":description}]
    for data in images:
        msg.append({"type":"image_url","image_url":{"url":
            "data:image/jpeg;base64,"+base64.b64encode(data).decode("ascii")}})
    return json.dumps({
        "model":MODEL,"thinking":{"type":"disabled"},
        "response_format":{"type":"json_object"},
        "max_tokens":8200 if task!="header" else 1400,
        "messages":[{"role":"system","content":prompt},
                    {"role":"user","content":msg}]
    },ensure_ascii=False).encode("utf-8")


def deepseek(key,payload):
    for attempt in range(1,5):
        request=urllib.request.Request(API,method="POST",data=payload,headers={
            "Authorization":"Bearer "+key,"Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(request,timeout=360) as response:
                return json.loads(response.read().decode("utf-8")),attempt
        except urllib.error.HTTPError as exc:
            if exc.code not in (429,500,502,503,504) or attempt==4:
                raise RuntimeError("DeepSeek HTTP %d (attempt %d)"%(exc.code,attempt))
        except (urllib.error.URLError,TimeoutError,ConnectionError):
            if attempt==4:
                raise RuntimeError("DeepSeek unreachable after four attempts")
        time.sleep(5*attempt)
    raise RuntimeError("DeepSeek retries exhausted")


def provider_content(response):
    choices=response.get("choices") or []
    content=(choices[0].get("message") or {}).get("content") if choices else None
    if not isinstance(content,str):
        raise ValueError("DeepSeek returned no text")
    data=json.loads(content)
    if not isinstance(data,dict):
        raise ValueError("DeepSeek returned non-object JSON")
    return data


def parse_task(response,task,page):
    data=provider_content(response)
    if task=="header":
        return header_checked(data)
    if task.startswith("verses_"):
        side=task[-1]
        if data.get("column")!=side:
            raise ValueError("Verse-marker model gave wrong text column")
        markers=data.get("markers")
        if not isinstance(markers,list) or len(markers)>150:
            raise ValueError("Expected up to 150 visible verse markers")
        for marker in markers:
            if not isinstance(marker,dict):
                raise ValueError("Malformed main-text verse marker")
            if marker.get("column") not in (None,side):
                raise ValueError("Main-text marker assigned to wrong half page")
            marker["column"]=side
        # Every marker MUST retain its physical text-column identity;
        # the model is only required to specify column at JSON root.
        return {"column":side,"markers":markers,
                "warnings":list(data.get("warnings") or [])[:15]}
    if not task.startswith("margin_"):
        raise ValueError("Invalid task")
    side=task[-1]
    items=data.get("items")
    if not isinstance(items,list) or len(items)>150:
        raise ValueError("Expected 0..150 physically printed marginal rows")
    result=[]
    for item in items:
        if not isinstance(item,dict) or not isinstance(item.get("raw_line"),str):
            raise ValueError("Invalid marginal OCR item")
        if item.get("kind","REFERENCE") not in ("REFERENCE","SECTION_LABEL"):
            raise ValueError("Invalid physical marginal item kind")
        lines=[x.strip() for x in item["raw_line"].splitlines() if x.strip()]
        if not lines:
            raise ValueError("Empty marginal OCR row")
        for line in lines:
            y=item.get("y_fraction")
            if type(y) not in (int,float) or not 0<=y<=1:
                y=None
            visibility=item.get("visibility_status","UNREADABLE")
            if visibility not in ("COMPLETE","CUT_OFF","UNREADABLE"):
                visibility="UNREADABLE"
            row={
                "id":"fr88i:p%04d:%s:%03d"%(page,side,len(result)+1),
                "image_page":page,"side":side,"kind":item.get("kind","REFERENCE"),
                "raw_line":line,"y_fraction":y,"visibility_status":visibility,
                "visibility_note":str(item.get("visibility_note") or "")[:220],
                "layout_uncertain":item.get("layout_uncertain") is True or len(lines)>1,
                "typography_uncertain":item.get("typography_uncertain") is True or
                                        visibility!="COMPLETE",
                "typography_evidence":str(item.get("typography_evidence") or "")[:220]
            }
            result.append(interpret_ocr_row(row,CATALOG))
    return {"column":side,"rows":result,
            "warnings":list(data.get("warnings") or [])[:15]}


def choose_book(page,head,registry,previous=None):
    registry_book=(registry.get(page) or {}).get("source_book_code")
    printed=head.get("book_code")
    issues=[]
    if registry_book and printed and registry_book!=printed:
        issues.append("PAGE_BOOK_CONFLICT")
    # Prefer a human-known page map over an inconsistent model title.
    if registry_book:
        return registry_book,issues,"PAGE_REGISTRY"
    if printed and head.get("book_title") and head.get("scan_confidence") in ("HIGH","MEDIUM"):
        return printed,issues,"PRINTED_PAGE_HEADER"
    if previous and previous.get("book_code"):
        # Provisional continuity, checked against future book transitions.
        # This is not enough by itself to declare a human-verified page book.
        issues.append("BOOK_INHERITED_FROM_PRIOR_PAGE")
        return previous["book_code"],issues,"PREVIOUS_PAGE_PROVISIONAL"
    issues.append("PAGE_BOOK_UNKNOWN")
    return None,issues,"UNKNOWN"


def collect_page(page,registry,limits):
    stages={}
    for task in TASKS:
        stage=OUT/("image_%04d.%s.result.json"%(page,task))
        if not stage.is_file():
            return None
        stages[task]=read(stage)["data"]
    header=stages["header"]
    prev=OUT/("image_%04d.bundle.json"%(page-1))
    previous=read(prev).get("page_book") if prev.exists() else None
    book,book_issues,book_evidence=choose_book(page,header,registry,previous)
    markers=stages["verses_L"]["markers"]+stages["verses_R"]["markers"]
    intervals,issues=make_intervals(markers,header,book,limits)
    issues+=book_issues
    issues=sorted(set(issues))
    rows=stages["margin_L"]["rows"]+stages["margin_R"]["rows"]
    links=atomic_edges(page,book,rows,intervals,limits,issues)
    counts=edge_summary(links)
    prior=RAW/"jbible_fr1988_v2"/"interpreted_rows.json"
    if prior.exists():
        old=read(prior)
        compare={}
        for side in ("L","R"):
            old_count=sum(r.get("image_page")==page and r.get("side")==side
                          and r.get("kind")=="REFERENCE" for r in old)
            new_count=sum(r.get("side")==side and r.get("kind")=="REFERENCE" for r in rows)
            compare[side]={"legacy_reference_rows":old_count,
                           "new_reference_rows":new_count,
                           "possible_missing_rows":max(0,old_count-new_count)}
            if new_count<old_count:
                issues.append("NEW_OCR_HAS_FEWER_ROWS_THAN_LEGACY_"+side)
        issues=sorted(set(issues))
    else:
        compare={}
    # Do not silently claim QA success if the OCR missed a known margin row.
    if any(x.get("possible_missing_rows",0) for x in compare.values()):
        for link in links:
            if link["status"]=="AUTO_PROPOSED":
                link["status"]="REVIEW_REQUIRED"
                link["qa_reasons"].append("POSSIBLE_MISSING_MARGIN_OCR")
    counts=edge_summary(links)
    result={
        "schema":"jbible.fr88.integrated-page.v1","image_page":page,
        "scanned_file":"image_%04d.jpg"%page,
        "page_book":{"book_code":book,"basis":book_evidence},
        "printed_running_head":header,
        "verse_markers_by_column":{
            "L":stages["verses_L"]["markers"],"R":stages["verses_R"]["markers"]},
        "verse_intervals_by_column":intervals,
        "marginal_ocr_rows":rows,
        "atomic_source_to_destination_links":links,
        "quality_flags":issues,
        "legacy_margin_comparison":compare,
        "summary":counts,
        "sql_writes":False,"human_verified_links":0,
        "created_utc":utc()
    }
    return result


def status(start,end,new_calls):
    total=0; links=[];issues=Counter()
    for page in range(start,end+1):
        file=OUT/("image_%04d.bundle.json"%page)
        if not file.is_file(): continue
        total+=1
        doc=read(file)
        links.extend(doc["atomic_source_to_destination_links"])
        issues.update(doc["quality_flags"])
    metrics=edge_summary(links)
    s={"pages":[start,end],"pages_bundled":total,
       "pages_requested":end-start+1,
       "percent":round(total*100/(end-start+1),1),
       "model":MODEL,"new_paid_tasks_this_run":new_calls,
       "source_link_metrics":metrics,
       "page_issue_counts":dict(issues),
       "verified":0,"sql_writes":False}
    save(OUT/"progress.json",s)
    print("PROGRESS pages=%d/%d (%.1f%%), %d atomic destinations, %d review-required"%
          (total,end-start+1,s["percent"],metrics["atomic_links"],
           metrics["needs_review"]),flush=True)
    return s


def run(args):
    if not 1<=args.start<=args.end<=500:
        raise ValueError("Only existing scanned image range 1..500 supported")
    if not 1<=args.max_new_calls<=100:
        raise ValueError("--max-new-calls must be 1..100")
    if args.report_only:
        status(args.start,args.end,0)
        return 0
    for path in [CATALOG,PAGE_REGISTRY]+list(set(PROMPTS.values())):
        if not path.is_file():
            raise RuntimeError("Missing input "+str(path))
    missing=[page for page in range(args.start,args.end+1)
             if not (IMAGES/("image_%04d.jpg"%page)).is_file()]
    if missing:
        raise RuntimeError("Missing scans; first "+str(missing[:12]))
    limits=catalog_limits(CATALOG)
    registry=index_pages(read(PAGE_REGISTRY))
    prompts={k:PROMPTS[k].read_text(encoding="utf-8") for k in TASKS}
    if not all(prompts.values()):
        raise RuntimeError("Empty OCR prompt")
    print("PREFLIGHT OK, %d scanned pages; five separate visual tasks per page; no SQL"%
          (args.end-args.start+1),flush=True)
    if args.preflight:
        return 0
    key=os.environ.get("DEEPSEEK_API_KEY","").strip()
    if not key:
        raise RuntimeError("Missing DEEPSEEK_API_KEY in existing Docker env")
    new_calls=0
    for page in range(args.start,args.end+1):
        file=IMAGES/("image_%04d.jpg"%page)
        raw=file.read_bytes()
        for task in TASKS:
            prompt=prompts[task]
            sig=signature(page,task,prompt,raw)
            base="image_%04d.%s"%(page,task)
            parsed_file=OUT/(base+".result.json")
            provider_file=OUT/(base+".provider.json")
            if parsed_file.exists():
                doc=read(parsed_file)
                if doc.get("signature")!=sig:
                    raise RuntimeError("Checkpoint fingerprint conflict: "+base)
                continue
            if provider_file.exists():
                saved=read(provider_file)
                if saved.get("signature")!=sig:
                    raise RuntimeError("Provider fingerprint conflict: "+base)
                response=saved["response"]
                print("REPARSE",base,flush=True)
            else:
                if new_calls>=args.max_new_calls:
                    status(args.start,args.end,new_calls)
                    print("API BUDGET STOP; safe to resume",flush=True)
                    return 0
                new_calls+=1
                print("DEEPSEEK",base,"call",new_calls,flush=True)
                images=images_for(file,task)
                response,attempts=deepseek(key,request_payload(page,task,prompt,images))
                save(provider_file,{"signature":sig,"response":response,
                                    "attempts":attempts,"utc":utc()})
            data=parse_task(response,task,page)
            save(parsed_file,{"page":page,"task":task,"signature":sig,
                              "data":data,"sql_writes":False})
        bundled=collect_page(page,registry,limits)
        if bundled is None:
            raise RuntimeError("Page stages incomplete unexpectedly")
        save(OUT/("image_%04d.bundle.json"%page),bundled)
        q=bundled["summary"]
        print("PAGE %d: %d separate targets, %d strong proposals, %d exceptions; %s"%
              (page,q["atomic_links"],q["auto_proposed"],
               q["needs_review"],",".join(bundled["quality_flags"])),flush=True)
        status(args.start,args.end,new_calls)
    report=status(args.start,args.end,new_calls)
    return 0 if report["pages_bundled"]==report["pages_requested"] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start",type=int,default=33)
    parser.add_argument("--end",type=int,default=33)
    parser.add_argument("--max-new-calls",type=int,default=5)
    parser.add_argument("--preflight",action="store_true")
    parser.add_argument("--report-only",action="store_true")
    args=parser.parse_args()
    try:
        return run(args)
    except Exception as exc:
        print("INTEGRATED OCR ERROR %s: %s"%(type(exc).__name__,exc),
              file=sys.stderr,flush=True)
        return 1


if __name__=="__main__":
    sys.exit(main())
