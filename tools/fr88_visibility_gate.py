#!/usr/bin/env python3
"""Non-destructive safety gate for JBible FR88 OCR transcripts.

Input: persisted .result.json checkpoint(s) containing OCR rows.
Output: candidates + quarantine + audit summary. NO SQL/API/Git operations.

A parseable or catalog-valid reference is NOT verified against a scan.
Any uncertain/cut-off row is quarantined rather than treated as a full link.
Python 3.6 compatible.
"""
import argparse
import json
import os
from collections import Counter
from pathlib import Path

VISIBILITIES = ("COMPLETE", "CUT_OFF", "UNREADABLE", "UNSPECIFIED")


def classification(row):
    kind = row.get("kind")
    visibility = row.get("visibility_status", "UNSPECIFIED")
    uncertain = row.get("typography_uncertain") is True
    if visibility not in VISIBILITIES:
        return "QUARANTINE", "INVALID_VISIBILITY_STATUS"
    if kind != "REFERENCE":
        return "EXCLUDED", "NOT_A_REFERENCE"
    if visibility != "COMPLETE":
        return "QUARANTINE", "VISIBILITY_" + visibility
    if uncertain:
        return "QUARANTINE", "TYPOGRAPHY_UNCERTAIN"
    if not isinstance(row.get("raw_line"), str) or not row["raw_line"].strip():
        return "QUARANTINE", "MISSING_OCR_TEXT"
    return "CANDIDATE", "UNVERIFIED_OCR_ONLY"


def clean(row, classification_name, reason):
    # Use an allowlist so provider bodies, secrets and embedded images cannot leak.
    record = {
        "id": row.get("id"),
        "image_page": row.get("image_page"),
        "side": row.get("side"),
        "kind": row.get("kind"),
        "raw_line": row.get("raw_line"),
        "y_fraction": row.get("y_fraction"),
        "visibility_status": row.get("visibility_status", "UNSPECIFIED"),
        "visibility_note": row.get("visibility_note", ""),
        "typography_uncertain": row.get("typography_uncertain"),
        "gate_status": classification_name,
        "gate_reason": reason,
        "scan_verified": False,
        "complete_bible_reference_verified": False,
        "automatic_linking_authorized": False,
    }
    if classification_name == "QUARANTINE":
        # A model's candidate raw text is evidence, NOT a safe source link.
        record["unverified_ocr_proposal"] = record.pop("raw_line")
        record["raw_line"] = None
    return record


def gate_rows(rows):
    if not isinstance(rows, list):
        raise ValueError("Expected a list of OCR row objects")
    seen = set()
    result = {"candidates": [], "quarantine": [], "excluded": []}
    counts = Counter()
    for r in rows:
        if not isinstance(r, dict) or not isinstance(r.get("id"), str):
            raise ValueError("Malformed or unidentified OCR row")
        if r["id"] in seen:
            raise ValueError("Duplicate OCR row id: " + r["id"])
        seen.add(r["id"])
        status, why = classification(r)
        counts[why] += 1
        item = clean(r, status, why)
        result[{"CANDIDATE": "candidates", "QUARANTINE": "quarantine",
                "EXCLUDED": "excluded"}[status]].append(item)
    result["summary"] = {
        "schema": "jbible.fr88.visibility-gate.v1",
        "ocr_rows": len(rows),
        "candidate_unverified_rows": len(result["candidates"]),
        "quarantined_rows": len(result["quarantine"]),
        "excluded_nonreferences": len(result["excluded"]),
        "reasons": dict(counts),
        "source_verse_verified": 0,
        "automatic_linking_authorized": 0,
        "sql_writes": False,
        "api_calls": 0,
        "note": "Candidates are incomplete QA work, not authorized links. No inferred digits may leave quarantine."
    }
    return result


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(str(temp), str(path))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--start", type=int, default=32)
    p.add_argument("--end", type=int, default=32)
    args = p.parse_args()
    if args.start > args.end:
        p.error("start must be <= end")
    if args.start < 1 or args.end > 3000 or args.end-args.start > 40:
        p.error("Refusing unexpected page range")
    if args.output_dir.resolve() == args.input_dir.resolve():
        p.error("Output directory must not overwrite raw OCR checkpoints")
    rows = []
    for page in range(args.start, args.end+1):
        for side in ("L", "R"):
            cp = args.input_dir / ("image_%04d_%s.result.json" % (page, side))
            if not cp.is_file():
                raise RuntimeError("Missing input checkpoint: " + str(cp))
            document = json.loads(cp.read_text(encoding="utf-8"))
            if not isinstance(document.get("rows"), list):
                raise ValueError("Missing OCR rows in " + str(cp))
            for r in document["rows"]:
                if r.get("image_page") != page or r.get("side") != side:
                    raise ValueError("Checkpoint row page/side mismatch: " + str(cp))
            rows.extend(document["rows"])
    outcome = gate_rows(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for key in ("candidates", "quarantine", "excluded", "summary"):
        save(args.output_dir / (key + ".json"), outcome[key])
    print("FR88 SAFETY GATE:")
    print(json.dumps(outcome["summary"], ensure_ascii=False, indent=2))
    print("Checkpoints untouched. No SQL, network, or API calls.")


if __name__ == "__main__":
    main()
