#!/usr/bin/env python3
"""JBible FR1988: DeepSeek source-verse anchors for saved marginal references.

Pilot: scanned pages 31..40. Source images and V2 OCR are READ ONLY.
The outputs are suggestions, NEVER verified Bible links and NEVER SQL writes.
Python 3.6 compatible; Docker image jbible-ocr:1 already contains Pillow.
"""
import argparse
import base64
import csv
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

from PIL import Image, ImageOps, ImageEnhance, ImageFilter

ROOT = Path("/raw")
SCANS = ROOT/"fr_bible_1988"
V2 = ROOT/"jbible_fr1988_v2"/"interpreted_rows.json"
CATALOG = ROOT/"jbible_catalog.csv"
OUT = ROOT/"jbible_fr88_source_links"
PROMPT = OUT/"frozen_source_prompt.txt"
OVERRIDES = Path("/app/fr88_source_visibility_overrides.json")
MODEL = "deepseek-flash"
URL = "https://api.deepseek.com/chat/completions"
FIRST, LAST = 31, 40
SIDES = ("L","R")
PIPELINE = "FR88-SOURCE-LINKS-PILOT-1"
SCOPES = ("VERSE","PASSAGE","CHAPTER","UNKNOWN")
EVIDENCE = ("HEADER_VISIBLE","CHAPTER_TITLE_VISIBLE",
            "OTHER_PRINTED_EVIDENCE","NOT_VISIBLE")
ALIGNMENT = ("VERSE_MARKER_AND_TEXT","VISIBLE_PASSAGE_BOUNDARY",
             "CHAPTER_HEADING","APPROXIMATE_POSITION_ONLY","UNKNOWN")


def utc():
    return datetime.now(timezone.utc).isoformat()


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    t = path.with_name(path.name+".tmp")
    with t.open("w",encoding="utf-8") as f:
        json.dump(obj,f,indent=2,ensure_ascii=False)
        f.write("\n")
    os.replace(str(t),str(path))


def rows_by_margin(start,end):
    records=json.loads(V2.read_text(encoding="utf-8"))
    groups={(page,side):[] for page in range(start,end+1) for side in SIDES}
    ids=set()
    for row in records:
        page,side=row.get("image_page"),row.get("side")
        if (page,side) not in groups:
            continue
        if row.get("kind")!="REFERENCE":
            continue
        if not isinstance(row.get("id"),str) or row["id"] in ids:
            raise ValueError("Invalid/duplicate source OCR row ID")
        ids.add(row["id"])
        groups[page,side].append(row)
    for rows in groups.values():
        rows.sort(key=lambda r:(r.get("y_fraction") if
                  type(r.get("y_fraction")) in (int,float) else 2,r["id"]))
    return groups


def limits_and_codes():
    codes=set()
    limits={}
    with CATALOG.open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            code=row.get("book_code")
            if not code:
                continue
            if row.get("record_type")=="A":
                codes.add(code)
            if row.get("record_type")=="C":
                limits[code,int(row["chap_number"])]=int(row["max_verse"])
                codes.add(code)
    if not limits:
        raise ValueError("Missing canonical Bible book/chapter catalog")
    return codes,limits


def photo(img,max_w,max_h):
    img=img.copy().convert("RGB")
    img.thumbnail((max_w,max_h),Image.Resampling.LANCZOS)
    img=ImageEnhance.Contrast(img).enhance(1.07)
    img=img.filter(ImageFilter.UnsharpMask(radius=.7,percent=70,threshold=3))
    buff=io.BytesIO()
    img.save(buff,"JPEG",quality=91,optimize=True)
    return buff.getvalue()


def scan_parts(path,side):
    # Coordinates on all three outputs refer to the SAME page half.
    with Image.open(str(path)) as f:
        page=ImageOps.exif_transpose(f).convert("RGB")
    w,h=page.size
    half=page.crop((0,0,w//2,h) if side=="L" else (w//2,0,w,h))
    hh=half.height
    return {
      "half":photo(half,1400,3200),
      "upper":photo(half.crop((0,0,half.width,int(hh*.57))),1650,2500),
      "lower":photo(half.crop((0,int(hh*.43),half.width,hh)),1650,2500)
    }


def signature(page,side,rows,parts,prompt):
    digest=hashlib.sha256()
    for piece in (PIPELINE,MODEL,str(page),side,prompt):
        digest.update(piece.encode("utf-8"))
    for row in rows:
        digest.update(json.dumps({
            "id":row["id"],"raw_line":row.get("raw_line"),
            "y_fraction":row.get("y_fraction")},ensure_ascii=False,
            sort_keys=True).encode("utf-8"))
    for key in ("half","upper","lower"):
        digest.update(parts[key])
    return digest.hexdigest()


def make_request_body(page,side,rows,parts,prompt):
    given=[{"margin_row_id":r["id"],"raw_line":r["raw_line"],
            "approximate_y_fraction":r.get("y_fraction")}
           for r in rows]
    content=[{"type":"text","text":
             "French Jerusalem Bible 1988, scanned page %d, %s half. "
             "Find MAIN-TEXT source verses for these existing MARGINAL reference rows; "
             "do not infer them from their targets. These are the input IDs: %s. "
             "The 3 images are the whole requested half, enlarged upper, enlarged lower. "
             "Return one assignment per input ID, including UNKNOWN if necessary."
             %(page,side,json.dumps(given,ensure_ascii=False))}]
    for name in ("half","upper","lower"):
        content.append({"type":"image_url","image_url":{"url":
          "data:image/jpeg;base64,"+base64.b64encode(parts[name]).decode("ascii")}})
    return json.dumps({
      "model":MODEL,"thinking":{"type":"disabled"},
      "response_format":{"type":"json_object"},"max_tokens":7800,
      "messages":[{"role":"system","content":prompt},
                  {"role":"user","content":content}]
    },ensure_ascii=False).encode("utf-8")


def call_deepseek(token,body):
    for n in range(1,5):
        request=urllib.request.Request(URL,data=body,method="POST",headers={
            "Content-Type":"application/json","Authorization":"Bearer "+token})
        try:
            with urllib.request.urlopen(request,timeout=360) as response:
                return json.loads(response.read().decode("utf-8")),n
        except urllib.error.HTTPError as e:
            if e.code not in (429,500,502,503,504) or n==4:
                raise RuntimeError("DeepSeek HTTP %d after %d attempts"%(e.code,n))
        except (urllib.error.URLError,TimeoutError,ConnectionError):
            if n==4:
                raise RuntimeError("DeepSeek network unavailable after four attempts")
        time.sleep(5*n)
    raise RuntimeError("DeepSeek retries exhausted")


def number(x):
    return x if type(x) is int and x>=1 else None


def fraction(x):
    return x if type(x) in (int,float) and 0<=x<=1 else None


def validated(provider,rows):
    choices=provider.get("choices") or []
    content=(choices[0].get("message") or {}).get("content") if choices else None
    if not isinstance(content,str):
        raise ValueError("DeepSeek JSON answer missing")
    result=json.loads(content)
    assignments=result.get("assignments")
    if not isinstance(assignments,list):
        raise ValueError("Missing assignments[] from DeepSeek")
    row_ids={r["id"] for r in rows}
    if len(assignments)!=len(row_ids):
        raise ValueError("Expected %d assignments; received %d"%
                         (len(row_ids),len(assignments)))
    decided={}
    for item in assignments:
        if not isinstance(item,dict):
            raise ValueError("Malformed source assignment")
        rid=item.get("margin_row_id")
        if rid not in row_ids or rid in decided:
            raise ValueError("Unknown/duplicate source assignment row ID")
        scope=item.get("scope","UNKNOWN")
        if scope not in SCOPES:
            scope="UNKNOWN"
        evidence=item.get("source_book_evidence","NOT_VISIBLE")
        if evidence not in EVIDENCE:
            evidence="NOT_VISIBLE"
        align=item.get("alignment_evidence","UNKNOWN")
        if align not in ALIGNMENT:
            align="UNKNOWN"
        confidence=item.get("confidence","LOW")
        if confidence not in ("HIGH","MEDIUM","LOW"):
            confidence="LOW"
        code=item.get("source_book_code")
        if not isinstance(code,str) or not code.strip():
            code=None
        printed=item.get("source_book_printed")
        if not isinstance(printed,str) or not printed.strip():
            printed=None
        if evidence=="NOT_VISIBLE":
            code=None
            printed=None
        decided[rid]={
            "margin_row_id":rid,
            "scope":scope,
            "source_book_printed":printed,
            "source_book_code":code,
            "source_book_evidence":evidence,
            "source_chapter":number(item.get("source_chapter")),
            "source_verse":number(item.get("source_verse")),
            "source_end_chapter":number(item.get("source_end_chapter")),
            "source_end_verse":number(item.get("source_end_verse")),
            "source_marker_y_fraction":fraction(item.get("source_marker_y_fraction")),
            "verse_marker_visible":item.get("verse_marker_visible") is True,
            "chapter_marker_visible":item.get("chapter_marker_visible") is True,
            "alignment_evidence":align,"confidence":confidence,
            "source_text_evidence":str(item.get("source_text_evidence") or "")[:70],
            "reason":str(item.get("reason") or "")[:240],
            "source_verified_from_scan":False
        }
    return {"assignments":[decided[r["id"]] for r in rows],
            "warnings":[str(x)[:300] for x in result.get("warnings",[])
                        if isinstance(x,str)][:20],
            "page_book_evidence":str(result.get("page_book_evidence") or "")[:120]}


def cutoff_overrides():
    data=json.loads(OVERRIDES.read_text(encoding="utf-8"))
    if data.get("schema")!="jbible.fr88.source-visibility-overrides.v1":
        raise ValueError("Unknown cut-off evidence schema")
    ids={}
    for x in data.get("overrides",[]):
        if x.get("visibility_status")!="CUT_OFF" or not x.get("row_id"):
            raise ValueError("Unexpected visibility override")
        ids[x["row_id"]]=x
    return ids


def anchor_status(anchor,margin_row,limits):
    if anchor.get("scope") not in ("VERSE","PASSAGE"):
        return "SOURCE_SCOPE_UNKNOWN"
    code,ch,verse=(anchor.get("source_book_code"),
                   anchor.get("source_chapter"),anchor.get("source_verse"))
    if not code or anchor.get("source_book_evidence")=="NOT_VISIBLE":
        return "SOURCE_BOOK_NOT_PRINTED"
    if (code,ch) not in limits or verse is None or verse>limits[code,ch]:
        return "SOURCE_COORDINATES_NOT_CATALOG_VALID"
    if not anchor.get("verse_marker_visible"):
        return "SOURCE_VERSE_MARKER_NOT_VISIBLE"
    if anchor.get("alignment_evidence") not in ("VERSE_MARKER_AND_TEXT",
                                                "VISIBLE_PASSAGE_BOUNDARY"):
        return "SOURCE_ALIGNMENT_UNCONFIRMED"
    if anchor.get("confidence")=="LOW":
        return "LOW_MODEL_CONFIDENCE"
    y=fraction(margin_row.get("y_fraction"))
    ay=anchor.get("source_marker_y_fraction")
    if y is None or ay is None:
        return "MISSING_COORDINATE_EVIDENCE"
    if abs(y-ay)>0.17:
        return "POSITION_DISAGREEMENT_NEEDS_REVIEW"
    if anchor["scope"]=="PASSAGE":
        endc=anchor.get("source_end_chapter")
        endv=anchor.get("source_end_verse")
        if (endc,endv)==(None,None):
            return "PASSAGE_END_UNRESOLVED"
        if endc!=ch or endv is None or endv<verse or endv>limits[code,ch]:
            return "PASSAGE_RANGE_UNVERIFIED"
    return "PROPOSED_NEEDS_HUMAN_REVIEW"


def target_status(r,segment,overrides):
    if r["id"] in overrides:
        return "CUT_OFF_TARGET_FROM_HUMAN_REVIEW"
    if r.get("layout_uncertain") is True or r.get("typography_uncertain") is True:
        return "MARGIN_LAYOUT_OR_TYPOGRAPHY_UNCERTAIN"
    if segment.get("status")!="PARSED":
        return "TARGET_INTERPRETATION_UNRESOLVED"
    if not segment.get("book_code"):
        return "TARGET_BOOK_UNRESOLVED"
    return "OCR_TARGET_NOT_SCAN_VERIFIED"


def safe_segments(row,anchor,overrides,limits):
    entries=[]
    geometry=anchor_status(anchor,row,limits)
    for n,segment in enumerate(row.get("references") or [],1):
        target=target_status(row,segment,overrides)
        if geometry=="PROPOSED_NEEDS_HUMAN_REVIEW" and target=="OCR_TARGET_NOT_SCAN_VERIFIED":
            state="PROPOSED_REVIEW_REQUIRED"
        else:
            state="NEEDS_REVIEW"
        entry={
            "row_id":row["id"],"image_page":row["image_page"],"side":row["side"],
            "margin_y_fraction":row.get("y_fraction"),"margin_raw_line":row.get("raw_line"),
            "target_segment_index":n,
            "target":{
                k:segment.get(k) for k in
                ("book_code","book_printed","chapter","verse","end_chapter",
                 "end_verse","verses","type","suffix","literal","status")},
            "source":{
                k:anchor.get(k) for k in
                ("source_book_code","source_book_printed","source_book_evidence",
                 "source_chapter","source_verse","source_end_chapter",
                 "source_end_verse","scope","source_marker_y_fraction",
                 "verse_marker_visible","chapter_marker_visible",
                 "alignment_evidence","source_text_evidence","confidence","reason")},
            "state":state,"source_reason":geometry,"target_reason":target,
            "source_verified":False,"target_verified":False,
            "source_to_target_link_verified":False,
            "sql_ready":False
        }
        entries.append(entry)
    return entries


def aggregate(start,end,groups,overrides,limits,paid_jobs=0):
    done=0
    proposals=[]
    queue=[]
    statuses=Counter()
    for page in range(start,end+1):
        for side in SIDES:
            file=OUT/("image_%04d_%s.result.json"%(page,side))
            if not file.exists():
                continue
            doc=json.loads(file.read_text(encoding="utf-8"))
            done+=1
            found={a["margin_row_id"]:a for a in doc["assignments"]}
            for row in groups[page,side]:
                anchor=found[row["id"]]
                items=safe_segments(row,anchor,overrides,limits)
                if not items:
                    queue.append({"row_id":row["id"],"reason":"NO_TARGET_SEGMENTS"})
                for item in items:
                    statuses[item["state"]]+=1
                    (proposals if item["state"]=="PROPOSED_REVIEW_REQUIRED" else queue).append(item)
    summary={
        "schema":"jbible.fr88.source-links-pilot.summary.v1",
        "pages":[start,end],"model":MODEL,
        "margins_complete":done,"margins_expected":2*(end-start+1),
        "progress_percent":round(done*100/(2*(end-start+1)),1),
        "margin_jobs_this_run":paid_jobs,
        "candidate_links_needing_review":len(proposals),
        "other_items_needing_review":len(queue),
        "statuses":dict(statuses),
        "verified_links":0,"sql_writes":False,
        "source_anchor_estimates_not_verified":True,
        "updated_utc":utc()
    }
    save(OUT/"progress.json",summary)
    # These are snapshots; provider bodies, scans, credentials are not included.
    save(OUT/"proposed_links.json",proposals)
    save(OUT/"source_link_review_queue.json",queue)
    return summary


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--start",type=int,default=FIRST)
    cli.add_argument("--end",type=int,default=LAST)
    cli.add_argument("--preflight",action="store_true")
    cli.add_argument("--report-only",action="store_true")
    cli.add_argument("--max-new-jobs",type=int,default=4)
    args=cli.parse_args()
    if not (FIRST<=args.start<=args.end<=LAST):
        cli.error("Pilot restricted to scanned pages 31..40")
    if not 1<=args.max_new_jobs<=20:
        cli.error("Allowed new margin jobs: 1..20")
    groups=rows_by_margin(args.start,args.end)
    codes,limits=limits_and_codes()
    overrides=cutoff_overrides()
    if args.report_only:
        print(json.dumps(aggregate(args.start,args.end,groups,overrides,limits),
                         ensure_ascii=False,indent=2))
        return 0
    if not PROMPT.exists() or "MAIN-TEXT" not in PROMPT.read_text(encoding="utf-8"):
        raise RuntimeError("Missing frozen source-text prompt")
    missing=[page for page in range(args.start,args.end+1)
             if not (SCANS/("image_%04d.jpg"%page)).is_file()]
    if missing:
        raise RuntimeError("Missing input scans: "+str(missing))
    model_rows=sum(len(x) for x in groups.values())
    print("PREFLIGHT: pages %d..%d, %d margin rows, %d sides, DeepSeek only, zero SQL"%(
        args.start,args.end,model_rows,2*(args.end-args.start+1)),flush=True)
    if args.preflight:
        return 0
    token=os.environ.get("DEEPSEEK_API_KEY","").strip()
    if not token:
        cli.error("Missing DeepSeek key (Docker .env.deepseek)")
    prompt=PROMPT.read_text(encoding="utf-8")
    paid=0
    for page in range(args.start,args.end+1):
        for side in SIDES:
            rows=groups[page,side]
            key="image_%04d_%s"%(page,side)
            cp=OUT/(key+".result.json")
            provider=OUT/(key+".provider.json")
            if not rows:
                # No marginal targets: no vision call needed for this half.
                if not cp.exists():
                    save(cp,{"page":page,"side":side,"signature":"EMPTY",
                             "assignments":[],"warnings":[],"empty_margin":True})
                continue
            parts=scan_parts(SCANS/("image_%04d.jpg"%page),side)
            sig=signature(page,side,rows,parts,prompt)
            if cp.exists():
                old=json.loads(cp.read_text(encoding="utf-8"))
                if old.get("signature")!=sig:
                    raise RuntimeError("Checkpoint fingerprint mismatch: "+key)
                print("CACHE "+key,flush=True)
                continue
            if provider.exists():
                old=json.loads(provider.read_text(encoding="utf-8"))
                if old.get("signature")!=sig:
                    raise RuntimeError("Provider fingerprint mismatch: "+key)
                response=old["response"]
                print("REPARSE "+key,flush=True)
            else:
                if paid>=args.max_new_jobs:
                    print("BUDGET STOP: %d paid margin jobs"%paid,flush=True)
                    print(json.dumps(aggregate(args.start,args.end,groups,overrides,limits,paid),
                                     indent=2),flush=True)
                    return 0
                paid+=1
                print("DEEPSEEK MAIN TEXT %s (%d/%d)"%(
                    key,paid,args.max_new_jobs),flush=True)
                response,tries=call_deepseek(token,make_request_body(
                    page,side,rows,parts,prompt))
                save(provider,{"signature":sig,"response":response,
                               "created_utc":utc(),"attempts":tries})
            decoded=validated(response,rows)
            decoded.update({"page":page,"side":side,"signature":sig,
                            "verified":0,"sql_writes":False})
            save(cp,decoded)
            status=aggregate(args.start,args.end,groups,overrides,limits,paid)
            print("PROGRESS: %s/%s sides (%s%%), %s proposed links, %s review"%(
                status["margins_complete"],status["margins_expected"],
                status["progress_percent"],status["candidate_links_needing_review"],
                status["other_items_needing_review"]),flush=True)
    result=aggregate(args.start,args.end,groups,overrides,limits,paid)
    print("FINAL SOURCE LINK CANDIDATES:",json.dumps(result,indent=2),flush=True)
    return 0 if result["margins_complete"]==result["margins_expected"] else 1


if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("SOURCE LINK ERROR %s: %s"%(type(exc).__name__,exc),
              file=sys.stderr,flush=True)
        sys.exit(1)
