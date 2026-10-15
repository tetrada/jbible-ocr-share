#!/usr/bin/env python3
"""Read-only scan-confirmed OCR holdout regression evaluation for v2/v3/v4.
No API calls. Holdouts never enter v4 system prompt or its training examples.
Python 3.6 compatible. Only v4 evaluation directory is writable.
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/raw")
GOLD = Path("/app/fr88_ocr_gold.json")
V2 = ROOT / "jbible_fr1988_v2" / "interpreted_rows.json"
V3 = ROOT / "jbible_fr1988_v3_pilot_31_50"
V4 = ROOT / "jbible_fr1988_v4_learning"
OUTPUT = V4 / "heldout_comparison.json"
SOURCE_MARGIN_RADIUS = 0.20


def normalize(line):
    # Compare textual references, ignoring purely decorative leading arrows.
    # Preserve chapter/verse boundaries, words, commas, suffixes and row identity.
    return re.sub(r"\s+", " ", re.sub(r"^\s*[↗→]\s*", "", line or "")).strip()


def load_margin(model, page, side, old_rows):
    if model == "v2":
        return [x for x in old_rows if x.get("image_page") == page and x.get("side") == side]
    folder = V3 if model == "v3" else V4
    checkpoint = folder / ("image_%04d_%s.result.json" % (page, side))
    if not checkpoint.exists():
        return None
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    return payload.get("rows", [])


def inspect(holdout, rows):
    if rows is None:
        return {"result": "NOT_PROCESSED", "matches": 0}
    expected = normalize(holdout["expected_raw_line"])
    ypos = holdout.get("baseline_y_fraction")
    if not expected:
        raise ValueError("Blank expected line")
    possible = [r for r in rows if normalize(r.get("raw_line", "")) == expected]
    if len(possible) == 0:
        return {"result": "TEXT_NOT_FOUND", "matches": 0}
    if len(possible) > 1:
        return {"result": "DUPLICATE_TEXT_AMBIGUOUS", "matches": len(possible)}
    row = possible[0]
    y = row.get("y_fraction")
    if type(y) not in (int, float) or type(ypos) not in (int, float):
        result = "EXACT_TEXT_FOUND_NO_GEOMETRY"
        delta = None
    else:
        delta = round(abs(y - ypos), 4)
        result = ("EXACT_TEXT_NEAR_ANCHOR" if delta <= SOURCE_MARGIN_RADIUS
                  else "EXACT_TEXT_FAR_FROM_ANCHOR")
    return {"result": result, "matches": 1, "matched_row_id": row.get("id"),
            "y_delta_from_v2": delta, "kind": row.get("kind"),
            "note": "Printed-text match only; not independently aligned or Scripture-verified."}


def evaluate():
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    if gold.get("schema") != "jbible.fr88.ocr.gold.v1":
        raise ValueError("Unexpected gold-data schema")
    examples = gold.get("examples", [])
    holdouts = gold.get("held_out_examples", [])
    training_ids = {x.get("id") for x in examples if x.get("inclusion") == "prompt_example"}
    training_cases = {x.get("case_id") for x in examples if x.get("inclusion") == "prompt_example"}
    if len(holdouts) < 5:
        raise ValueError("At least five independent scan-confirmed holdouts required")
    if any(h["id"] in training_ids or h.get("case_id") in training_cases
           for h in holdouts):
        raise ValueError("TRAINING/HOLDOUT CONTAMINATION")
    if any(h.get("verification") != "human_confirmed_from_original_scan"
           for h in holdouts):
        raise ValueError("Nonverified holdout")
    v2 = json.loads(V2.read_text(encoding="utf-8"))
    detail = []
    totals = {m: Counter() for m in ("v2", "v3", "v4")}
    for h in holdouts:
        page, side = int(h["image_page"]), h["side"]
        entry = {"id": h["id"], "case_id": h["case_id"], "page": page,
                 "side": side, "expected_raw_line": h["expected_raw_line"],
                 "source": "Human scan-confirmed", "models": {}}
        for model in ("v2", "v3", "v4"):
            rows = load_margin(model, page, side, v2)
            result = inspect(h, rows)
            entry["models"][model] = result
            totals[model][result["result"]] += 1
        detail.append(entry)
    report = {
        "schema": "jbible.fr88.v4.holdout.regression.v1",
        "holdouts_total": len(holdouts), "training_examples": len(training_ids),
        "results_by_model": {m: dict(v) for m,v in totals.items()},
        "cases": detail,
        "scope": "Raw transcription presence by original page margin, with approximate v2 y-position cross-check.",
        "not_proof": ("All selected holdouts are previously agreed V2/V3 readings. "
                      "This test can detect some regressions, but cannot establish an OCR "
                      "accuracy improvement. A prospective benchmark needs independently "
                      "reviewed cases where previous OCR made mistakes."),
        "source_verse_verification": 0, "sql_writes": False, "api_calls": 0
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n",
                      encoding="utf-8")
    print("HOLDOUT REGRESSION EVALUATION:")
    print(json.dumps({"holdouts": len(holdouts), "results_by_model": report["results_by_model"],
                      "report": str(OUTPUT), "accuracy_improvement_measured": False},
                     ensure_ascii=False, indent=2), flush=True)
    return report


if __name__ == "__main__":
    try:
        evaluate()
    except Exception as exc:
        print("EVALUATION ERROR %s: %s"%(type(exc).__name__,exc),file=sys.stderr)
        sys.exit(1)
