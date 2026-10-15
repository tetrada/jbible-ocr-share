#!/usr/bin/env python3
"""V5 OCR visibility experiment, isolated from v2/v3/v4 checkpoints and labels.
Wrap the validated v3 OCR engine with an explicit cut-off visibility field.
"""
import json
import sys
from pathlib import Path

import fr88_v3_pilot as pilot

pilot.OUT = Path("/raw/jbible_fr1988_v5_visibility")
pilot.PROMPT = pilot.OUT / "visibility_prompt.txt"
previous_provider_rows = pilot.provider_rows
previous_compare = pilot.compare


def provider_rows_v5(provider, page, side):
    parsed_rows, warnings = previous_provider_rows(provider, page, side)
    content = (provider.get("choices") or [{}])[0].get("message", {}).get("content")
    answer = json.loads(content)
    source_items = answer.get("items", [])
    index = 0
    for item in source_items:
        if not isinstance(item, dict):
            continue
        text = item.get("raw_line", "")
        physical_rows = [line.strip() for line in text.splitlines() if line.strip()]
        visibility = item.get("visibility_status", "UNSPECIFIED")
        if visibility not in ("COMPLETE", "CUT_OFF", "UNREADABLE"):
            visibility = "UNSPECIFIED"
        note = str(item.get("visibility_note") or "")[:350]
        for raw in physical_rows:
            if index >= len(parsed_rows):
                raise ValueError("Provider physical-row count disagrees with parsed rows")
            row = parsed_rows[index]
            if row.get("raw_line") != raw:
                raise ValueError("Provider row order mismatch")
            row["visibility_status"] = visibility
            row["visually_truncated"] = visibility == "CUT_OFF"
            row["visibility_note"] = note
            row["ocr_visibility_review_needed"] = visibility != "COMPLETE"
            if visibility != "COMPLETE":
                row["typography_uncertain"] = True
                for ref in row.get("references", []):
                    ref["scan_readability"] = visibility
            index += 1
    if index != len(parsed_rows):
        raise ValueError("Provider OCR metadata not mapped to every parsed row")
    return parsed_rows, warnings


def compare_v5(start, end, gold=None):
    report = previous_compare(start, end, gold)
    report["v5"] = report.pop("v3")
    report["edition"] = "FR1988-v5-visibility"
    report["warning"] = (
        "Cut-off visible prefixes are NOT complete references. "
        "Catalog/parse success is NOT scan OCR accuracy.")
    rows = []
    for page in range(start, end+1):
        for side in ("L", "R"):
            cp = pilot.OUT / ("image_%04d_%s.result.json" % (page, side))
            if cp.exists():
                rows.extend(json.loads(cp.read_text(encoding="utf-8")).get("rows", []))
    report["visibility_status_counts"] = {
        status: sum(x.get("visibility_status") == status for x in rows)
        for status in ("COMPLETE", "CUT_OFF", "UNREADABLE", "UNSPECIFIED")
    }
    report["scan_ambiguous_reference_rows"] = sum(
        x.get("kind") == "REFERENCE" and x.get("visibility_status") != "COMPLETE"
        for x in rows)
    pilot.save_json(pilot.OUT/"comparison.json", report)
    print("V5 VISIBILITY COMPARISON SAVED:",pilot.OUT/"comparison.json",flush=True)
    return report


pilot.provider_rows = provider_rows_v5
pilot.compare = compare_v5

if __name__ == "__main__":
    code = pilot.main()
    summary_file = pilot.OUT / "run_summary.json"
    if summary_file.is_file():
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        summary["edition"] = "FR1988-v5-visibility"
        pilot.save_json(summary_file, summary)
    sys.exit(code)
