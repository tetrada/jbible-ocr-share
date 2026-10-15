#!/usr/bin/env python3
"""Export text-only V2/V3/V4 OCR pilot comparisons for publication to JBible Git.
No API calls, scan images, API keys, provider payloads or SQL writes.
Python 3.6 compatible. Output is ONLY the directory passed as argv[1].
"""
import difflib
import json
import re
import sys
from collections import Counter
from pathlib import Path

RAW=Path("/opt/jbible/data/raw")
V2=RAW/"jbible_fr1988_v2"/"interpreted_rows.json"
V3=RAW/"jbible_fr1988_v3_pilot_31_50"
V4=RAW/"jbible_fr1988_v4_learning"
EXPECTED=[31,34]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_name(path.name+".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",
                   encoding="utf-8")
    tmp.replace(path)


def simple(r):
    return {
        "row_id":r.get("id"),
        "kind":r.get("kind"),
        "raw_line":r.get("raw_line"),
        "y_fraction":r.get("y_fraction"),
        "typography_uncertain":r.get("typography_uncertain"),
        "typography_evidence":r.get("typography_evidence"),
        "references":[{
            "type":p.get("type"),"book_code":p.get("book_code"),
            "chapter":p.get("chapter"),"verse":p.get("verse"),
            "suffix":p.get("suffix"),"status":p.get("status"),
        } for p in r.get("references",[])]
    }


def normalize(row):
    # Decoration arrows are not biblical reference content. Whitespace
    # between adjacent numbers IS evidence of a chapter/verse boundary.
    s=(row.get("raw_line") or "").strip()
    s=re.sub(r"^[↗→]\s*","",s)
    s=re.sub(r"\s+"," ",s)
    s=re.sub(r"\s*;\s*",";",s)
    s=re.sub(r"\s*-\s*","-",s)
    return s.casefold()


def pair_diffs(rows_a, rows_b, name_a, name_b, page, side):
    matcher=difflib.SequenceMatcher(None,
        [normalize(r) for r in rows_a],
        [normalize(r) for r in rows_b],autojunk=False)
    chunks=[]
    for tag,i,j,k,m in matcher.get_opcodes():
        if tag=="equal":
            continue
        chunks.append({
            "page":page,"side":side,"change":tag,
            "from_model":name_a,"to_model":name_b,
            "from_rows":[simple(r) for r in rows_a[i:j]],
            "to_rows":[simple(r) for r in rows_b[k:m]],
            "review_status":"NOT_INDEPENDENTLY_SCAN_VERIFIED",
        })
    return chunks


def stats(rows):
    return {
        "physical_rows":len(rows),
        "reference_rows":sum(r.get("kind")=="REFERENCE" for r in rows),
        "section_labels":sum(r.get("kind")=="SECTION_LABEL" for r in rows),
        "total_segments":sum(len(r.get("references",[])) for r in rows),
        "parser_parsed_segments":sum(
            p.get("status")=="PARSED"
            for r in rows for p in r.get("references",[])),
        "note":"Parser success is NOT independent OCR accuracy.",
    }


def main():
    if len(sys.argv)!=2:
        raise SystemExit("Usage: fr88_v4_git_export.py /path/to/git/checkout/fr88_v4_learning")
    dest=Path(sys.argv[1])
    report=read(V4/"comparison.json")
    run=read(V4/"run_summary.json")
    holdout=read(V4/"heldout_comparison.json")
    if (report.get("pages")!=EXPECTED or
        report.get("margins_complete")!=8 or
        report.get("margins_expected")!=8 or
        report.get("missing_v3_margins") or
        run.get("errors") or not run.get("complete")):
        raise RuntimeError("V4 trial is not a completed pages 31..34 run")
    v2_rows=[r for r in read(V2) if 31<=r.get("image_page",0)<=34]
    v2_by={(page,side):[r for r in v2_rows
                       if r.get("image_page")==page and r.get("side")==side]
           for page in range(31,35) for side in ("L","R")}
    v3_by,v4_by={},{}
    for page in range(31,35):
        for side in ("L","R"):
            name="image_%04d_%s.result.json"%(page,side)
            v3_by[page,side]=read(V3/name)["rows"]
            v4_by[page,side]=read(V4/name)["rows"]
    versions={"v2":v2_by,"v3":v3_by,"v4":v4_by}
    summary={
        "schema":"jbible.fr88.v4.learning.public-summary.v1",
        "pages":EXPECTED,
        "margins_processed":8,
        "model":"deepseek-flash",
        "new_margin_jobs":run.get("fresh_requested_margin_jobs"),
        "v2":stats([x for rows in v2_by.values() for x in rows]),
        "v3":stats([x for rows in v3_by.values() for x in rows]),
        "v4":stats([x for rows in v4_by.values() for x in rows]),
        "holdout_regression":{
            "holdouts_total":holdout.get("holdouts_total"),
            "results_by_model":holdout.get("results_by_model"),
            "scope":holdout.get("scope"),
            "warning":"The five holdouts were previous v2/v3 agreements; they test regression, not improvement."
        },
        "source_to_target_verified":0,
        "ocr_accuracy_improvement":"NOT_MEASURED",
        "sql_writes":False,
        "images_or_provider_responses_published":False
    }
    diffs={}
    for a,b in (("v2","v3"),("v2","v4"),("v3","v4")):
        changes=[]
        for page in range(31,35):
            for side in ("L","R"):
                changes+=pair_diffs(versions[a][page,side],
                                  versions[b][page,side],a,b,page,side)
        diffs[a+"_to_"+b]=changes
        summary[a+"_to_"+b+"_difference_groups"]=len(changes)
    cases={
        "schema":"jbible.fr88.v4.readings-for-review.v1",
        "pages":EXPECTED,
        "readings":[{"page":page,"side":side,
                     "v2":[simple(r) for r in v2_by[page,side]],
                     "v3":[simple(r) for r in v3_by[page,side]],
                     "v4":[simple(r) for r in v4_by[page,side]]}
                    for page in range(31,35) for side in ("L","R")],
        "differences":diffs,
        "review_state":"NOT_VISUALLY_VERIFIED_AS_A_SET",
        "no_copyrighted_scans_or_credentials":True
    }
    write(dest/"pilot_summary.json",summary)
    write(dest/"readings_and_differences.json",cases)
    print("GIT EXPORT COMPLETE: pages 31..34; 8 margins",flush=True)
    print("Comparisons v2/v3=%d, v2/v4=%d, v3/v4=%d"%
          (len(diffs["v2_to_v3"]),len(diffs["v2_to_v4"]),
           len(diffs["v3_to_v4"])),flush=True)
    print("Destination: "+str(dest),flush=True)
    print("No images, OCR provider responses, API keys or SQL writes.",flush=True)


if __name__=="__main__":
    main()
