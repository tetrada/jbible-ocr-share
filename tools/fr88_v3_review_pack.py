#!/usr/bin/env python3
"""Create offline v2/v3 OCR disagreement review package with original scan crops.
Read-only v2/v3 checkpoints; output only into dedicated v3 pilot folder.
Python 3.6 compatible. Uses Pillow already present in jbible-ocr:1 Docker image.
"""
import csv
import hashlib
import html
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from PIL import Image, ImageOps

ROOT = Path("/raw")
V2 = ROOT / "jbible_fr1988_v2" / "interpreted_rows.json"
V3 = ROOT / "jbible_fr1988_v3_pilot_31_50"
IMAGES = ROOT / "fr_bible_1988"
OUTFILE = V3 / "fr88_v3_review_pack.zip"
COLUMNS = ["case_id", "page", "side", "issue", "v2_text", "v3_text",
           "review_decision", "correct_raw_line", "review_notes",
           "confirmed_against_scan"]
MAX_CASES = 200


def gather():
    v2_data = json.loads(V2.read_text(encoding="utf-8"))
    old_by_id = {r["id"]: r for r in v2_data if 31 <= r["image_page"] <= 50}
    new_by_id = {}
    for page in range(31, 51):
        for side in ("L", "R"):
            cp = V3 / ("image_%04d_%s.result.json" % (page, side))
            if not cp.is_file():
                raise RuntimeError("Incomplete v3 pilot: " + cp.name)
            rows = json.loads(cp.read_text(encoding="utf-8"))["rows"]
            for row in rows:
                if row["id"] in new_by_id:
                    raise ValueError("Duplicate v3 ID " + row["id"])
                new_by_id[row["id"]] = row
    differences = []
    with (V3 / "transcription_disagreements.csv").open(
            newline="", encoding="utf-8") as fh:
        differences = list(csv.DictReader(fh))
    cases = []
    used_v3 = set()
    for number, d in enumerate(differences, 1):
        ids2 = [x for x in d["v2_ids"].split(";") if x]
        ids3 = [x for x in d["v3_ids"].split(";") if x]
        missing2 = [x for x in ids2 if x not in old_by_id]
        missing3 = [x for x in ids3 if x not in new_by_id]
        if missing2 or missing3:
            raise RuntimeError("Missing reference IDs: %s %s" % (missing2, missing3))
        rows2 = [old_by_id[x] for x in ids2]
        rows3 = [new_by_id[x] for x in ids3]
        for x in rows3:
            used_v3.add(x["id"])
        case = build_case("D%03d" % number, int(d["page"]), d["side"],
                          "TRANSCRIPTION_" + d["change"].upper(), rows2, rows3)
        cases.append(case)
    for r in new_by_id.values():
        if r.get("kind") == "SECTION_LABEL":
            if r["id"] not in used_v3:
                cases.append(build_case("S%03d" % (len(cases) + 1),
                                        r["image_page"], r["side"],
                                        "V3_SECTION_LABEL", [], [r]))
            else:
                for case in cases:
                    if any(x["id"] == r["id"] for x in case["v3_rows"]):
                        case["issue"] += ";V3_SECTION_LABEL"
                        break
    if len(cases) > MAX_CASES:
        raise ValueError("Too many cases; stop to inspect")
    return cases


def build_case(case_id, page, side, issue, rows2, rows3):
    positions = [r["y_fraction"] for r in rows2 + rows3
                 if type(r.get("y_fraction")) in (float, int)
                 and 0 <= r["y_fraction"] <= 1]
    y = median(positions) if positions else 0.5
    if side not in ("L", "R"):
        raise ValueError("Invalid side")
    return {
        "case_id": case_id, "page": page, "side": side, "issue": issue,
        "v2_text": " || ".join(r["raw_line"] for r in rows2),
        "v3_text": " || ".join(r["raw_line"] for r in rows3),
        "v2_rows": rows2, "v3_rows": rows3, "y_fraction_estimate": round(y, 4),
        "human_verified": False,
        "human_gold_raw_line": None,
    }


def cropped_page(page, side, fraction):
    path = IMAGES / ("image_%04d.jpg" % page)
    if not path.is_file():
        raise RuntimeError("Missing original JPEG: " + str(path))
    with Image.open(str(path)) as photo:
        photo = ImageOps.exif_transpose(photo)
        w, h = photo.size
        # Include margin AND neighboring main-text column for context.
        x0, x1 = ((0, int(w * 0.5)) if side == "L" else (int(w * 0.5), w))
        center = int(h * fraction)
        vertical = max(180, int(h * .09))
        y0 = max(0, center - vertical)
        y1 = min(h, center + vertical)
        crop = photo.crop((x0, y0, x1, y1)).convert("RGB")
        stream = io.BytesIO()
        crop.save(stream, format="JPEG", quality=91, optimize=True)
        return stream.getvalue()


def render_html(cases):
    styles = ("""
      body{background:#f2f4f6;font:14px system-ui,sans-serif;margin:22px auto;
      max-width:1350px;padding:0 20px;color:#222}
      article{background:white;border:1px solid #dde1e6;border-radius:10px;
      margin:14px 0;overflow:hidden}
      h2{font-size:16px;margin:0;padding:12px 16px;background:#e6ebf1}
      .case{display:grid;grid-template-columns:1fr 1fr 1.2fr;gap:15px;padding:14px}
      .txt{font-size:17px;white-space:pre-wrap;font-family:ui-monospace,monospace}
      .muted{color:#627080;font-size:12px}.scan img{width:100%;display:block}
      .scan{border:1px solid #ddd;overflow:auto}header{margin-bottom:25px}
      @media(max-width:900px){.case{grid-template-columns:1fr}}
      """)
    parts = ['<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" '
             'content="width=device-width,initial-scale=1"><style>' + styles +
             '</style><title>JBible FR88 v3 OCR pilot review</title></head><body>',
             '<header><h1>JBible FR88 v2/v3 OCR review</h1>'
             '<p>Original scan crops. Differences are NOT proof that either OCR is correct.</p>'
             '<p>Confirm bold chapter, normal verse, book prefixes, suffixes, '
             'and separate physical rows; no source verse alignment or SQL.</p></header>']
    for c in cases:
        img = "crops/" + c["case_id"] + ".jpg"
        parts.append('<article><h2>%s · page %04d · %s · %s</h2>'
                     '<div class="case"><div><p class="muted">V2</p><div class="txt">%s</div></div>'
                     '<div><p class="muted">V3</p><div class="txt">%s</div></div>'
                     '<div class="scan"><img src="%s" loading="lazy"></div></div></article>' %
                     (html.escape(c["case_id"]), c["page"], c["side"], html.escape(c["issue"]),
                      html.escape(c["v2_text"]), html.escape(c["v3_text"]), img))
    parts.append("</body></html>")
    return "\n".join(parts).encode("utf-8")


def as_csv(rows, cols):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def build():
    if not V2.is_file():
        raise RuntimeError("Missing v2 comparison baseline")
    if not (V3 / "comparison.json").is_file():
        raise RuntimeError("Missing v3 comparison; run v3 pilot first")
    summary = json.loads((V3 / "comparison.json").read_text(encoding="utf-8"))
    if summary["margins_complete"] != 40 or summary["margins_expected"] != 40:
        raise RuntimeError("Need all 40 margins before review")
    cases = gather()
    if not cases:
        raise RuntimeError("No OCR disagreements to review")
    template = [{
        "case_id": c["case_id"], "page": c["page"], "side": c["side"],
        "issue": c["issue"], "v2_text": c["v2_text"], "v3_text": c["v3_text"],
        "review_decision": "", "correct_raw_line": "", "review_notes": "",
        "confirmed_against_scan": ""
    } for c in cases]
    data = {
        "edition": "FR88-v3-pilot", "pages": [31, 50], "review_cases": len(cases),
        "transcription_differences": summary["transcription_difference_hunks"],
        "original_images_cropped": len(cases),
        "verified": 0, "sql_writes": False,
        "note": "Unverified optical transcription differences, use original scans before choosing."
    }
    tmp = OUTFILE.with_name(OUTFILE.name + ".tmp")
    with zipfile.ZipFile(str(tmp), "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("review_report.html", render_html(cases))
        z.writestr("review_cases.json", json.dumps(
            {"summary": data, "cases": cases}, ensure_ascii=False, indent=2).encode("utf-8"))
        z.writestr("review_decisions_template.csv", as_csv(template, COLUMNS))
        z.writestr("README.txt",
                   "Review HTML + original image crops from your own FR88 scans.\n"
                   "Do not infer verification from syntax or catalog validity.\n"
                   "Keep the completed review decisions separately. No SQL writes.\n")
        for i, c in enumerate(cases, 1):
            z.writestr("crops/" + c["case_id"] + ".jpg",
                       cropped_page(c["page"], c["side"], c["y_fraction_estimate"]))
            if i % 10 == 0:
                print("Prepared %d/%d image crops" % (i, len(cases)), flush=True)
    os.replace(str(tmp), str(OUTFILE))
    print("REVIEW CASES:", len(cases))
    print("REVIEW ZIP:", str(OUTFILE))
    print("FILE SIZE:", OUTFILE.stat().st_size)
    print("SHA256:", hashlib.sha256(OUTFILE.read_bytes()).hexdigest())
    print("v2 unchanged; v3 checkpoint files unchanged; verified=0; SQL writes=false")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(build())
    except Exception as exc:
        print("ERROR: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        sys.exit(1)
