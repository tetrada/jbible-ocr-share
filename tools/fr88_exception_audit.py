#!/usr/bin/env python3
"""Read-only diagnostic of FR88 integrated exception edges.
Runs on the published text-only report; never touches scans, OCR caches, SQL or reviews.
"""
import collections
import json
import sys
from pathlib import Path

src = Path(sys.argv[1] if len(sys.argv) > 1 else "fr88_integrated_v1/pilot_report.json")
dst = Path(sys.argv[2] if len(sys.argv) > 2 else "fr88_integrated_v1/exception_audit.json")
report = json.loads(src.read_text(encoding="utf-8"))
if report.get("schema") != "jbible.fr88.integrated-page-git-report.v1":
    raise SystemExit("Unexpected report schema")
pages = report.get("pages", [])
if not isinstance(pages, list):
    raise SystemExit("Invalid page list")
counts = collections.Counter()
by_reason = collections.Counter()
detail = []
for page in pages:
    number = page.get("image_page")
    exceptions = []
    for edge in page.get("source_to_destination_edges", []):
        if edge.get("status") != "EXCEPTION":
            continue
        reasons = edge.get("hard_exceptions") or ["UNKNOWN"]
        counts[number] += 1
        by_reason.update(reasons)
        y = edge.get("margin_y_fraction")
        top = isinstance(y, (int, float)) and y < 0.25
        exceptions.append({
            "id": edge.get("edge_id"),
            "column": edge.get("column"),
            "y": y,
            "top_quarter": top,
            "printed": edge.get("printed_margin_line"),
            "source": edge.get("source"),
            "destination": edge.get("destination"),
            "reasons": reasons
        })
    if exceptions:
        markers = page.get("main_text_verse_markers") or {}
        detail.append({
            "page": number,
            "page_book": page.get("page_book"),
            "running_head": page.get("running_head"),
            "verse_marker_count": {side: len(markers.get(side) or [])
                                      for side in ("L", "R")},
            "quality_flags": page.get("page_flags", []),
            "exception_count": len(exceptions), "exceptions": exceptions
        })
numbers = sorted(p.get("image_page") for p in pages if type(p.get("image_page")) is int)
ranges = []
for n in numbers:
    if not ranges or n > ranges[-1][1] + 1:
        ranges.append([n, n])
    else:
        ranges[-1][1] = n
out = {
    "schema": "jbible.fr88.exception-audit.v1",
    "input": str(src),
    "processed_page_count": len(numbers),
    "processed_page_ranges": ranges,
    "highest_published_page": max(numbers) if numbers else None,
    "exception_total": sum(counts.values()),
    "exceptions_by_reason": dict(by_reason.most_common()),
    "exception_counts_by_page": {str(k): v for k, v in sorted(counts.items())},
    "pages_with_exceptions": detail,
    "method": "read-only inspection of GitHub-published OCR results; not human verification",
    "sql_writes": False
}
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("published pages:", ranges, "exceptions:", out["exception_total"],
      "highest page:", out["highest_published_page"])
