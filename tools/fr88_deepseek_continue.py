#!/usr/bin/env python3
"""Continue French 1988 Bible marginal OCR using DeepSeek Flash only.
Next isolated batch: scanned pages 501..750, 500 independent margin jobs.

- Resumable, immutable provider+OCR checkpoints
- Model prompt assembled from scan-verified gold examples and visibility rules
- Missing/cut-off/unreadable rows never promoted to verified Bible links
- Zero SQL operations; V2/V3/V4/V5 data is never changed
- Python 3.6 compatible; runs in the existing jbible-ocr:1 container
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import fr88_v3_pilot as engine
import fr88_visibility_gate as gate

RAW = Path("/raw")
FIRST = 501
LAST = 750
SIDES = ("L", "R")
SOURCE = RAW / "fr_bible_1988"
OUT = RAW / "jbible_fr1988_deepseek_p0501_0750"
PROMPT = OUT / "batch_prompt.txt"
PIPELINE = "fr88-deepseek-continuation-1"
MAX_NEW = 500


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(str(temp), str(path))


def key(page, side):
    return "image_%04d_%s" % (page, side)


def fingerprint(page, side, parts, prompt):
    basis = engine.signature(page, side, parts, prompt)
    return hashlib.sha256((PIPELINE + ":" + basis).encode("ascii")).hexdigest()


def decode_rows(provider, page, side):
    """Parse physical reference rows and keep the model's visibility evidence."""
    rows, warnings = engine.provider_rows(provider, page, side)
    choices = provider.get("choices") or []
    if not choices:
        raise ValueError("Provider JSON has no choices")
    answer = (choices[0].get("message") or {}).get("content")
    if not isinstance(answer, str):
        raise ValueError("Provider OCR content missing")
    raw = json.loads(answer)
    items = raw.get("items", [])
    if not isinstance(items, list):
        raise ValueError("Provider did not return items list")

    cursor = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Malformed provider row")
        text = item.get("raw_line")
        if not isinstance(text, str):
            raise ValueError("Provider row missing text")
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        status = str(item.get("visibility_status") or "UNSPECIFIED").upper()
        if status not in gate.VISIBILITIES:
            status = "UNSPECIFIED"
        note = str(item.get("visibility_note") or "")[:350]
        for line in lines:
            if cursor >= len(rows) or rows[cursor]["raw_line"] != line:
                raise ValueError("Provider physical row mapping mismatch")
            row = rows[cursor]
            cursor += 1
            row["id"] = "fr88ds:p%04d:%s:%02d" % (page, side, cursor)
            row["edition"] = "fr88-deepseek-continue"
            row["visibility_status"] = status
            row["visually_truncated"] = status == "CUT_OFF"
            row["visibility_note"] = note
            row["ocr_visibility_review_needed"] = status != "COMPLETE"
            if status != "COMPLETE":
                row["typography_uncertain"] = True
                for segment in row.get("references", []):
                    segment["original_parse_status"] = segment.get("status")
                    segment["status"] = "NEEDS_SCAN_VISIBILITY_REVIEW"
                    segment["verified"] = False
            row["verified"] = False
            row["source_anchor_confident"] = False
    if cursor != len(rows):
        raise ValueError("OCR rows count differs from provider input")
    return rows, warnings


def checkpoints(start, end):
    valid = {}
    for page in range(start, end+1):
        for side in SIDES:
            cp = OUT / (key(page, side) + ".result.json")
            if cp.is_file():
                doc = json.loads(cp.read_text(encoding="utf-8"))
                if doc.get("page") != page or doc.get("side") != side:
                    raise ValueError("Checkpoint page mismatch in "+str(cp))
                if not isinstance(doc.get("rows"), list):
                    raise ValueError("Malformed checkpoint "+str(cp))
                valid[page, side] = doc
    return valid


def report(start, end, attempts_so_far, failures=None):
    existing = checkpoints(start, end)
    all_rows = [r for page in range(start, end+1) for side in SIDES
                for r in existing.get((page, side), {}).get("rows", [])]
    classified = gate.gate_rows(all_rows)
    expected = 2 * (end-start+1)
    counts = Counter()
    for row in all_rows:
        counts["physical_rows"] += 1
        counts["reference_rows" if row.get("kind")=="REFERENCE" else "section_labels"] += 1
        counts["segments"] += len(row.get("references", []))
        for ref in row.get("references", []):
            counts["parsed" if ref.get("status") == "PARSED" else "requires_interpretation"] += 1
    results = {
        "edition": "FR1988-DeepSeek-continuation",
        "model": engine.MODEL,
        "pages": [start, end],
        "margins_expected": expected,
        "margins_complete": len(existing),
        "margins_missing": [key(p, side) for p in range(start, end+1)
                            for side in SIDES if (p, side) not in existing],
        "progress_percent": round(100.0*len(existing)/expected, 1),
        "counts": dict(counts),
        "visibility_gate": classified["summary"],
        "verified_bible_links": 0,
        "sql_writes": False,
        "source_to_target_links_not_inferred": True,
        "checkpoint_failures": failures or [],
        "api_margin_jobs_this_run": attempts_so_far,
        "updated_utc": now()
    }
    save(OUT/"progress.json", results)
    if len(existing)==expected:
        for name in ("candidates","quarantine","excluded"):
            save(OUT/("staging_"+name+".json"), classified[name])
        # Parsed target coordinates remain only *staging candidates*, never linked
        # to a source verse or accepted automatically as canonical text.
        allowed = ("type", "book_code", "book_printed", "chapter", "verse",
                   "end_chapter", "end_verse", "verses", "suffix",
                   "literal", "status", "original_parse_status")
        stage_segments=[]
        for row in all_rows:
            status, reason=gate.classification(row)
            if status!="CANDIDATE":
                continue
            for segment_number,ref in enumerate(row.get("references") or [],1):
                stage_segments.append({
                    "source_ocr_row_id":row["id"],
                    "segment_index":segment_number,
                    "image_page":row["image_page"],
                    "side":row["side"],
                    "printed_target":{k:ref.get(k) for k in allowed},
                    "scan_verified":False,
                    "source_verse_verified":False,
                    "auto_link_allowed":False
                })
        save(OUT/"staging_candidate_segments.json",stage_segments)
        results["staged_unverified_segments"]=len(stage_segments)
        save(OUT/"completion_summary.json", results)
        print("BATCH COMPLETE (NOT BIBLE VERIFICATION):",json.dumps(results,indent=2),flush=True)
    return results


def preflight(start,end):
    if (start < FIRST or end > LAST or start > end):
        raise ValueError("This batch is restricted to pages %d..%d"%(FIRST,LAST))
    for file in (PROMPT,engine.CATALOG,engine.V2):
        if not file.is_file():
            raise RuntimeError("Missing input: "+str(file))
    prompt = PROMPT.read_text(encoding="utf-8")
    if "CUT_OFF" not in prompt or "SCAN-VERIFIED" not in prompt:
        raise RuntimeError("Missing cut-off policy or verified teaching examples in prompt")
    missing = [page for page in range(start,end+1)
               if not (SOURCE/("image_%04d.jpg"%page)).is_file()]
    if missing:
        raise RuntimeError("Scanned JPEGs missing (%d); first pages: %s"%
                           (len(missing),missing[:15]))
    engine.parser_self_test(str(engine.CATALOG))
    print("PREFLIGHT OK: %d pages, %d margins; DeepSeek=%s; no SQL; no paid calls"%
          (end-start+1,2*(end-start+1),engine.MODEL),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start",type=int,default=FIRST)
    p.add_argument("--end",type=int,default=LAST)
    p.add_argument("--preflight",action="store_true")
    p.add_argument("--report-only",action="store_true")
    p.add_argument("--max-new-margins",type=int,default=MAX_NEW)
    args=p.parse_args()
    if args.start != FIRST or args.end != LAST:
        p.error("Batch range must be 501..750. Smaller runs can resume by --max-new-margins.")
    if args.max_new_margins < 1 or args.max_new_margins > MAX_NEW:
        p.error("Allowed new margin jobs 1..500")
    if args.report_only:
        info=report(FIRST,LAST,0)
        print("PROGRESS:",json.dumps({
            "margins_complete":info["margins_complete"],
            "margins_expected":info["margins_expected"],
            "progress_percent":info["progress_percent"],
            "quarantine":info["visibility_gate"]["quarantined_rows"]},indent=2))
        return 0
    preflight(FIRST,LAST)
    if args.preflight:
        return 0
    key_value=os.environ.get("DEEPSEEK_API_KEY","").strip()
    if not key_value:
        p.error("Missing DEEPSEEK_API_KEY from existing .env.deepseek")
    OUT.mkdir(parents=True,exist_ok=True)
    prompt=PROMPT.read_text(encoding="utf-8")
    paid_jobs, failures = 0,[]
    for page in range(FIRST,LAST+1):
        for side in SIDES:
            name=key(page,side)
            cp=OUT/(name+".result.json")
            provider_file=OUT/(name+".provider.json")
            try:
                # Fingerprint *all* source crop bytes before trusting saved checkpoints.
                parts=engine.prepare_images(SOURCE/("image_%04d.jpg"%page),side)
                sig=fingerprint(page,side,parts,prompt)
                if cp.is_file():
                    saved=json.loads(cp.read_text(encoding="utf-8"))
                    if saved.get("signature")!=sig:
                        raise RuntimeError("Existing checkpoint fingerprint differs: "+name)
                    print("CACHE",name,"rows",len(saved["rows"]),flush=True)
                    continue
                if provider_file.is_file():
                    envelope=json.loads(provider_file.read_text(encoding="utf-8"))
                    if envelope.get("signature")!=sig:
                        raise RuntimeError("Provider fingerprint differs: "+name)
                    reply=envelope["response"]
                    print("REPARSE",name,flush=True)
                else:
                    if paid_jobs >= args.max_new_margins:
                        print("MAX NEW MARGINS reached:",paid_jobs,flush=True)
                        info=report(FIRST,LAST,paid_jobs)
                        return 0
                    paid_jobs+=1
                    print("DEEPSEEK OCR %s job %d/%d"%(
                        name,paid_jobs,args.max_new_margins),flush=True)
                    reply,retries=engine.api_call(key_value,parts,page,side,prompt)
                    save(provider_file,{"signature":sig,"response":reply,
                                        "created_utc":now(),"attempts":retries})
                rows,warnings=decode_rows(reply,page,side)
                save(cp,{"signature":sig,"page":page,"side":side,
                          "rows":rows,"warnings":warnings,
                          "api_usage":reply.get("usage",{}),
                          "verified":0,"sql_writes":False})
                if page%5==0 and side=="R":
                    state=report(FIRST,LAST,paid_jobs)
                    print("PROGRESS %.1f%% margins %d/%d"%(
                        state["progress_percent"],state["margins_complete"],
                        state["margins_expected"]),flush=True)
            except Exception as exc:
                error="%s: %s"%(type(exc).__name__,exc)
                failures.append({"page":page,"side":side,"error":error})
                print("STOPPED "+name+" "+error,flush=True)
                report(FIRST,LAST,paid_jobs,failures)
                return 1
    final=report(FIRST,LAST,paid_jobs,failures)
    return 0 if not final["margins_missing"] and not failures else 1


if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("FATAL %s: %s"%(type(exc).__name__,exc),file=sys.stderr)
        sys.exit(1)
