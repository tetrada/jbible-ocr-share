#!/usr/bin/env python3
"""Evaluate the held-out cut scan on page32 without exposing it to V5's prompt.
This measures *abstention on unreadable text*, not Bible-citation validity.
Python 3.6, read-only inputs, one local V5 JSON output.
"""
import json
import re
import sys
from pathlib import Path

RAW=Path("/raw")
V5=RAW/"jbible_fr1988_v5_visibility"
GOLD=Path("/app/fr88_ocr_gold.json")


def normalized(value):
    value=re.sub(r"^[↗→]\s*", "", value or "")
    return re.sub(r"\s+", " ", value.strip())


def load(model,page,side):
    if model=="v2":
        v2=json.loads((RAW/"jbible_fr1988_v2"/"interpreted_rows.json").read_text(encoding="utf-8"))
        return [r for r in v2 if r.get("image_page")==page and r.get("side")==side]
    folder={
        "v3":"jbible_fr1988_v3_pilot_31_50",
        "v4":"jbible_fr1988_v4_learning",
        "v5":"jbible_fr1988_v5_visibility"
    }[model]
    cp=RAW/folder/("image_%04d_%s.result.json"%(page,side))
    return json.loads(cp.read_text(encoding="utf-8"))["rows"] if cp.exists() else None


def assess(expected,rows):
    if rows is None:
        return {"result":"NOT_PROCESSED"}
    prefix=normalized(expected)
    candidates=[r for r in rows if normalized(r.get("raw_line","")).startswith(prefix)]
    if not candidates:
        return {"result":"VISIBLE_PREFIX_MISSING"}
    if len(candidates)>1:
        return {"result":"AMBIGUOUS_DUPLICATE_PREFIX","count":len(candidates)}
    line=candidates[0]
    actual=normalized(line.get("raw_line",""))
    status=line.get("visibility_status","UNSPECIFIED")
    if actual!=prefix:
        result="UNVERIFIED_COMPLETION_BEYOND_VISIBLE_TEXT"
    elif status in ("CUT_OFF","UNREADABLE"):
        result="VISIBLE_PREFIX_PRESERVED_AND_FLAGGED"
    else:
        result="VISIBLE_PREFIX_PRESERVED_BUT_NOT_FLAGGED"
    return {"result":result,"observed_raw_line":line["raw_line"],
            "ocr_visibility_status":status,"row_id":line.get("id"),
            "full_reference_verified":False}


def main():
    gold=json.loads(GOLD.read_text(encoding="utf-8"))
    holdouts=[h for h in gold.get("held_out_examples",[])
              if h.get("visually_truncated") is True]
    prompts={x.get("case_id") for x in gold.get("examples",[])
             if x.get("inclusion")=="prompt_example"}
    if len(holdouts)!=1 or holdouts[0]["case_id"] in prompts:
        raise ValueError("Expected one isolated truncated holdout without prompt leakage")
    h=holdouts[0]
    if h.get("expected_full_reference") is not None:
        raise ValueError("Full reference incorrectly invented in gold corpus")
    by_model={m:assess(h["expected_visible_prefix"],
                       load(m,h["image_page"],h["side"]))
              for m in ("v2","v3","v4","v5")}
    report={
        "schema":"jbible.fr88.v5.cutoff-holdout.v1",
        "human_verified_visible_prefix":h["expected_visible_prefix"],
        "page":h["image_page"],"side":h["side"],
        "not_visible":"Any trailing verse digits or punctuation after this prefix",
        "cases":by_model,
        "v5_pass":by_model["v5"]["result"]=="VISIBLE_PREFIX_PRESERVED_AND_FLAGGED",
        "not_full_reference_accuracy":True,
        "sql_writes":False,"api_calls_for_evaluation":0
    }
    out=V5/"cutoff_holdout_evaluation.json"
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("CUT-OFF HOLDOUT EVALUATION:")
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR %s: %s"%(type(exc).__name__,exc),file=sys.stderr)
        sys.exit(1)
