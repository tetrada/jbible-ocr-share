#!/usr/bin/env python3
"""JBible FR88 v2 reference audit: read-only, no OCR, no API, no SQL.

Audits the existing interpreted_rows.json and the local Bible catalog.
PARSED means syntax was understood; VALID means structurally possible.
Neither proves accurate OCR or a source-to-target verse connection.
"""
# Compatible with older Python 3 interpreters used on the JBible VPS.

import argparse
import csv
import hashlib
import html
import importlib.util
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/opt/jbible/data/raw")
DEFAULT_DATA = ROOT / "jbible_fr1988_v2/interpreted_rows.json"
DEFAULT_CATALOG = ROOT / "jbible_catalog.csv"
DEFAULT_IMAGES = ROOT / "fr_bible_1988"
DEFAULT_OUTPUT = ROOT / "jbible_reference_audit"
DEFAULT_PARSER = Path("/opt/jbible/importer/fr88_v2_normalize.py")

SEGMENT_COLUMNS = [
    "segment_id", "row_id", "image_page", "side", "y_fraction", "raw_line",
    "literal", "book_printed", "book_code", "reference_type", "chapter",
    "verse", "end_chapter", "end_verse", "verses", "suffix", "target",
    "parse_status", "catalog_status", "target_extent", "anchor_status",
    "source_chapter", "source_verse", "source_anchor_confident",
    "layout_uncertain", "review_reasons", "row_fingerprint",
    "stored_vs_current_parser_diff", "verified",
]
ROW_COLUMNS = [
    "row_id", "image_page", "side", "y_fraction", "kind", "raw_line",
    "segments", "parse_review_segments", "anchor_status",
    "layout_uncertain", "stored_vs_current_parser_diff",
    "row_fingerprint", "issues", "verified",
]
DECISION_COLUMNS = [
    "row_id", "segment_id", "row_fingerprint", "image_page", "side",
    "raw_line", "candidate_target", "decision", "corrected_target_book",
    "corrected_target_chapter", "corrected_target_verse",
    "corrected_target_end_chapter", "corrected_target_end_verse",
    "corrected_target_suffix", "confirmed_source_book",
    "confirmed_source_chapter", "confirmed_source_verse",
    "confirmed_source_end_verse", "image_evidence_notes", "reviewer_notes",
]


def save_json(path, data):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def save_csv(path, rows, columns):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for item in rows:
            w.writerow({
                k: json.dumps(item[k], ensure_ascii=False)
                if isinstance(item.get(k), (dict, list)) else item.get(k, "")
                for k in columns
            })


def load_catalog(path):
    limits, aliases = {}, defaultdict(set)
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            kind = (r.get("record_type") or "").strip()
            book = (r.get("book_code") or "").strip()
            if kind == "A":
                alias = " ".join((r.get("bali_alias") or "").casefold().split())
                if alias and book:
                    aliases[alias].add(book)
            elif kind == "C":
                chapter, last = int(r["chap_number"]), int(r["max_verse"])
                if chapter < 1 or last < 1 or not book or (book, chapter) in limits:
                    raise ValueError("Invalid catalog entry: " + repr(r))
                limits[book, chapter] = last
    if not limits:
        raise ValueError("Catalog has no verse limits")
    chapters = defaultdict(set)
    for book, chapter in limits:
        chapters[book].add(chapter)
    return limits, aliases, chapters


def posint(x):
    return x if type(x) is int and x > 0 else None


def source_anchor(row):
    if posint(row.get("source_chapter")) and posint(row.get("source_verse")):
        if row.get("source_anchor_confident") is True:
            return "OCR_CLAIMED_CONFIDENT_NOT_VERIFIED"
        return "TENTATIVE_OCR_NOT_VERIFIED"
    return "MISSING"


def validate_target(ref, limits, chapters):
    book, typ = ref.get("book_code"), ref.get("type")
    if not book:
        return "MISSING_BOOK", ["MISSING_PRINTED_OR_RESOLVED_BOOK"]
    ch = posint(ref.get("chapter"))
    if typ == "UNRESOLVED_NUMERIC":
        return "NOT_CHECKABLE", ["NOTATION_NOT_INTERPRETED"]
    if not ch or (book, ch) not in limits:
        return "INVALID", ["CHAPTER_OUTSIDE_CATALOG"]
    max_v = limits[book, ch]
    if typ == "CHAPTER_ONLY":
        return "VALID", ["CHAPTER_SCOPE_NOT_VERSE"]
    if typ == "CHAPTER_RANGE":
        last = posint(ref.get("end_chapter"))
        if not last or last < ch or any(i not in chapters[book] for i in range(ch, last + 1)):
            return "INVALID", ["CHAPTER_RANGE_OUTSIDE_CATALOG"]
        return "VALID", ["CHAPTER_SCOPE_NOT_VERSE"]
    if typ in ("VERSE", "VERSE_RANGE"):
        verse = posint(ref.get("verse"))
        if not verse or verse > max_v:
            return "INVALID", ["VERSE_OUTSIDE_CATALOG"]
        if typ == "VERSE_RANGE":
            end = posint(ref.get("end_verse"))
            if not end or end < verse or end > max_v:
                return "INVALID", ["VERSE_RANGE_OUTSIDE_CATALOG"]
        return "VALID", []
    if typ == "VERSE_LIST":
        vs = ref.get("verses")
        if not isinstance(vs, list) or not vs or any(
            not posint(v) or v > max_v for v in vs
        ):
            return "INVALID", ["VERSE_LIST_OUTSIDE_CATALOG"]
        return "VALID", []
    return "NOT_CHECKABLE", ["NOTATION_NOT_INTERPRETED"]


def describe_target(r):
    book, typ, ch = r.get("book_code") or "?", r.get("type"), r.get("chapter")
    if typ == "VERSE_LIST":
        coord = str(ch) + ":" + ",".join(map(str, r.get("verses") or []))
    elif typ in ("VERSE", "VERSE_RANGE"):
        coord = str(ch) + ":" + str(r.get("verse"))
        if r.get("end_verse") is not None:
            coord += "-" + str(r["end_verse"])
    elif typ == "CHAPTER_RANGE":
        coord = str(ch) + "-" + str(r.get("end_chapter"))
    elif typ == "CHAPTER_ONLY":
        coord = str(ch)
    else:
        coord = str(r.get("literal") or "?")
    return book + " " + coord + str(r.get("suffix") or "")


def load_reparser(path):
    spec = importlib.util.spec_from_file_location("jbible_audit_normalizer", str(path))
    if not spec or not spec.loader:
        raise RuntimeError("Cannot load current normalizer: " + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_rows(rows, segments, maximum):
    by_row = defaultdict(list)
    for s in segments:
        by_row[s["row_id"]].append(s)
    buckets = defaultdict(list)
    for row in rows:
        ss = by_row[row["row_id"]]
        if row["kind"] != "REFERENCE":
            cat = "SECTION_LABEL"
        elif row["layout_uncertain"]:
            cat = "LAYOUT_UNCERTAIN"
        elif any(s["catalog_status"] == "INVALID" for s in ss):
            cat = "INVALID_TARGET"
        elif any(s["parse_status"] == "NEEDS_NOTATION_REVIEW" for s in ss):
            cat = "NOTATION_REVIEW"
        elif any(s["catalog_status"] == "MISSING_BOOK" for s in ss):
            cat = "MISSING_BOOK"
        elif any(s["parse_status"] != "PARSED" for s in ss):
            cat = "OTHER_PARSE_REVIEW"
        elif any(s["suffix"] for s in ss):
            cat = "SUFFIX_EXTENT"
        else:
            cat = "SOURCE_ALIGNMENT"
        buckets[cat].append(row)
    order = [
        "INVALID_TARGET", "NOTATION_REVIEW", "MISSING_BOOK",
        "LAYOUT_UNCERTAIN", "SUFFIX_EXTENT", "OTHER_PARSE_REVIEW",
        "SOURCE_ALIGNMENT", "SECTION_LABEL",
    ]
    sample = []
    for i in range(max(map(len, buckets.values()), default=0)):
        for cat in order:
            if i < len(buckets[cat]):
                sample.append((cat, buckets[cat][i]))
                if len(sample) >= maximum:
                    return sample
    return sample


def make_html(path, output_dir, selected, by_row, summary, image_dir, copy_images):
    assets = output_dir / "assets"
    if copy_images:
        assets.mkdir(exist_ok=True)
    cards = []
    for category, row in selected:
        page, side = row["image_page"], row["side"]
        name = "image_%04d.jpg" % page
        if copy_images and (image_dir / name).is_file():
            if not (assets / name).exists():
                shutil.copy2(image_dir / name, assets / name)
            y = row["y_fraction"]
            marker = '<div class="marker" style="top:%.2f%%"></div>' % (100 * y) if isinstance(y, (int, float)) else ""
            picture = '<div class="pic"><img loading="lazy" src="assets/%s">%s</div>' % (html.escape(name), marker)
        else:
            picture = "<p>Image not included; inspect the original page on VPS.</p>"
        trs = "".join(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % tuple(
                html.escape(str(seg[k])) for k in ("target", "parse_status", "catalog_status", "target_extent")
            )
            for seg in by_row.get(row["row_id"], [])
        )
        cards.append(
            '<article><header>%s — %s — page %s %s</header>'
            '<section><div><h2>%s</h2><p>Source anchor: %s</p>'
            '<p><strong>Approximate margin position, NOT verified verse alignment.</strong></p>'
            '<table><tr><th>Target candidate</th><th>Parse</th><th>Catalog</th><th>Extent</th></tr>%s</table>'
            '</div>%s</section></article>' % (
                html.escape(row["row_id"]), html.escape(category), page, side,
                html.escape(row["raw_line"]), html.escape(row["anchor_status"]), trs, picture,
            )
        )
    css = (
        "body{font:15px system-ui,sans-serif;max-width:1250px;margin:25px auto;padding:0 16px;background:#f6f7f9}"
        "article{background:#fff;border:1px solid #ddd;border-radius:9px;margin:20px 0;overflow:hidden}"
        "header{padding:12px;background:#ecf0f5;font-weight:bold}section{padding:12px;display:grid;"
        "grid-template-columns:1fr 300px;gap:16px}.pic{position:relative}.pic img{width:100%}"
        ".marker{position:absolute;left:0;right:0;border-top:3px solid red}"
        "table{border-collapse:collapse;width:100%;font-size:12px}td,th{border-bottom:1px solid #ddd;"
        "padding:6px;text-align:left}h2{overflow-wrap:anywhere}"
        "@media(max-width:800px){section{grid-template-columns:1fr}}"
    )
    doc = (
        '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>JBible reference audit</title><style>%s</style></head><body>' % css
    )
    doc += "<h1>JBible FR88 v2 — reference audit</h1>"
    doc += "<p><strong>Read-only:</strong> targets are catalog-checked but no reference or source verse is verified.</p>"
    doc += "<p>Reference rows: %s; segments: %s; sample rows: %s.</p>" % (
        summary["reference_rows"], summary["segments"], len(selected)
    )
    path.write_text(doc + "".join(cards) + "</body></html>", encoding="utf-8")


def run(args):
    if not args.data.is_file() or not args.catalog.is_file():
        raise FileNotFoundError("Missing input JSON or Bible catalog")
    if args.start_page is not None and args.end_page is not None and args.end_page < args.start_page:
        raise ValueError("Invalid page range")
    if args.sample < 1:
        raise ValueError("Sample size must be positive")
    with args.data.open(encoding="utf-8") as f:
        document = json.load(f)
    entries = document if isinstance(document, list) else document.get("rows")
    if not isinstance(entries, list):
        raise ValueError("Input must be a list of interpreted rows")
    limits, aliases, chapters = load_catalog(args.catalog)
    parser = load_reparser(args.parser) if args.reparse else None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = "p%04d_%04d" % (args.start_page or 0, args.end_page or 9999)
    out = args.out_dir / ("audit_%s_%s" % (label, timestamp))
    out.mkdir(parents=True, exist_ok=False)

    row_results, seg_results = [], []
    parse_counts, catalog_counts, anchor_counts, reasons = Counter(), Counter(), Counter(), Counter()
    page_counts = defaultdict(Counter)
    seen, order, bad_order, missing_images = set(), {}, [], set()
    drift = 0
    for row in entries:
        if not isinstance(row, dict):
            raise ValueError("Malformed OCR row")
        page = posint(row.get("image_page"))
        if not page:
            raise ValueError("Row missing page number")
        if args.start_page is not None and page < args.start_page:
            continue
        if args.end_page is not None and page > args.end_page:
            continue
        row_id = row.get("id")
        if not isinstance(row_id, str) or not row_id or row_id in seen:
            raise ValueError("Missing or duplicate row ID: " + repr(row_id))
        seen.add(row_id)
        side = row.get("side")
        if side not in ("L", "R"):
            raise ValueError("Unknown margin side: " + repr(side))
        y = row.get("y_fraction")
        if y is not None and (isinstance(y, bool) or not isinstance(y, (float, int)) or not 0 <= y <= 1):
            raise ValueError("Invalid margin position: " + row_id)
        if y is not None:
            key = (page, side)
            if key in order and y + 1e-5 < order[key]:
                bad_order.append(row_id)
            order[key] = y
        if not (args.images / ("image_%04d.jpg" % page)).is_file():
            missing_images.add(page)
        kind = row.get("kind") or "REFERENCE"
        raw = str(row.get("raw_line") or "")
        fp = hashlib.sha256(json.dumps(
            [row_id, raw, kind, y, row.get("source_chapter"), row.get("source_verse")],
            ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        previous = row.get("references") or []
        if not isinstance(previous, list):
            raise ValueError("Invalid reference array: " + row_id)
        refs = previous
        if parser and kind == "REFERENCE":
            refs = parser.interpret_line(raw, str(args.catalog), layout_uncertain=bool(row.get("layout_uncertain")))
        changed = refs != previous
        if changed:
            drift += 1
        anchor = source_anchor(row)
        anchor_counts[anchor] += 1
        page_counts[page]["rows"] += 1
        page_counts[page]["reference_rows" if kind == "REFERENCE" else "section_labels"] += 1
        problems = []
        if changed:
            problems.append("PARSER_OUTPUT_CHANGED")
        if kind == "REFERENCE" and not refs:
            problems.append("NO_REFERENCE_SEGMENTS")
        count_review = 0
        for i, ref in enumerate(refs, 1):
            if not isinstance(ref, dict):
                raise ValueError("Malformed reference in " + row_id)
            pstatus = ref.get("status") or "UNKNOWN"
            cstatus, why = validate_target(ref, limits, chapters)
            extent = (
                "OPEN_ENDED_SUFFIX_NOT_EXPANDED" if ref.get("suffix") else
                {"VERSE": "EXACT_VERSE", "VERSE_RANGE": "EXPLICIT_VERSE_RANGE",
                 "VERSE_LIST": "EXPLICIT_VERSE_LIST", "CHAPTER_ONLY": "CHAPTER",
                 "CHAPTER_RANGE": "CHAPTER_RANGE"}.get(ref.get("type"), "UNRESOLVED")
            )
            rwhy = ([] if pstatus == "PARSED" else ["PARSE_" + pstatus])
            if cstatus in ("INVALID", "MISSING_BOOK", "NOT_CHECKABLE"):
                rwhy += why
            if row.get("layout_uncertain"):
                rwhy.append("LAYOUT_UNCERTAIN")
            if ref.get("suffix"):
                rwhy.append("SUFFIX_EXTENT_AMBIGUOUS")
            rwhy.append("SOURCE_ANCHOR_UNVERIFIED")
            if changed:
                rwhy.append("PARSER_OUTPUT_CHANGED")
            rwhy = list(dict.fromkeys(rwhy))
            problems += rwhy
            reasons.update(rwhy)
            parse_counts[pstatus] += 1
            catalog_counts[cstatus] += 1
            count_review += int(pstatus != "PARSED")
            page_counts[page]["segments"] += 1
            seg_results.append({
                "segment_id": "%s/r%02d" % (row_id, i),
                "row_id": row_id, "image_page": page, "side": side,
                "y_fraction": y, "raw_line": raw, "literal": ref.get("literal"),
                "book_printed": ref.get("book_printed"),
                "book_code": ref.get("book_code"), "reference_type": ref.get("type"),
                "chapter": ref.get("chapter"), "verse": ref.get("verse"),
                "end_chapter": ref.get("end_chapter"), "end_verse": ref.get("end_verse"),
                "verses": ref.get("verses"), "suffix": ref.get("suffix") or "",
                "target": describe_target(ref), "parse_status": pstatus,
                "catalog_status": cstatus, "target_extent": extent,
                "anchor_status": anchor, "source_chapter": row.get("source_chapter"),
                "source_verse": row.get("source_verse"),
                "source_anchor_confident": bool(row.get("source_anchor_confident")),
                "layout_uncertain": bool(row.get("layout_uncertain")),
                "review_reasons": rwhy, "row_fingerprint": fp,
                "stored_vs_current_parser_diff": changed, "verified": False,
            })
        row_results.append({
            "row_id": row_id, "image_page": page, "side": side, "y_fraction": y,
            "kind": kind, "raw_line": raw, "segments": len(refs),
            "parse_review_segments": count_review, "anchor_status": anchor,
            "layout_uncertain": bool(row.get("layout_uncertain")),
            "stored_vs_current_parser_diff": changed, "row_fingerprint": fp,
            "issues": sorted(set(problems)), "verified": False,
        })
    if not row_results:
        raise ValueError("No rows in requested page range")

    selected = sample_rows(row_results, seg_results, args.sample)
    by_row = defaultdict(list)
    for seg in seg_results:
        by_row[seg["row_id"]].append(seg)
    review = [s for s in seg_results if s["review_reasons"]]
    # Target interpretation issues and source alignment are independent workflows.
    # A valid catalog coordinate is not yet OCR-confirmed or source-verse-aligned.
    target_review = [s for s in seg_results
                     if s["parse_status"] != "PARSED" or s["catalog_status"] != "VALID"]
    by_margin = defaultdict(list)
    for row in row_results:
        by_margin[row["image_page"], row["side"]].append(row)
    margin_neighbors = {}
    for margin_rows in by_margin.values():
        for index, current in enumerate(margin_rows):
            margin_neighbors[current["row_id"]] = {
                "previous_printed_rows": [
                    {"row_id": x["row_id"], "raw_line": x["raw_line"],
                     "y_fraction": x["y_fraction"]}
                    for x in margin_rows[max(0, index - 2):index]
                ],
                "next_printed_rows": [
                    {"row_id": x["row_id"], "raw_line": x["raw_line"],
                     "y_fraction": x["y_fraction"]}
                    for x in margin_rows[index + 1:index + 3]
                ],
            }
    target_context = []
    for seg in target_review:
        target_context.append({
            "segment": seg,
            "neighbors_for_visual_review_only": margin_neighbors[seg["row_id"]],
            "important": "Neighboring rows do NOT establish inherited book or source verse. Check the original scan.",
        })
    summary = {
        "purpose": "Read-only structural audit, not scanned-image or Bible verification",
        "edition": "FR1988-v2", "data_file": str(args.data),
        "input_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "pages": [args.start_page, args.end_page],
        "rows": len(row_results),
        "reference_rows": sum(r["kind"] == "REFERENCE" for r in row_results),
        "section_labels": sum(r["kind"] != "REFERENCE" for r in row_results),
        "segments": len(seg_results),
        "parsed_by_parser": parse_counts["PARSED"],
        "parser_review_segments": len(seg_results) - parse_counts["PARSED"],
        "target_interpretation_review_segments": len(target_review),
        "source_alignment_pending_reference_rows": sum(r["kind"] == "REFERENCE" for r in row_results),
        "invalid_target_segments": catalog_counts["INVALID"],
        "suffix_segments": sum(bool(s["suffix"]) for s in seg_results),
        "layout_uncertain_rows": sum(r["layout_uncertain"] for r in row_results),
        "parser_drift_rows": drift,
        "counts_by_parser_status": dict(sorted(parse_counts.items())),
        "counts_by_catalog_status": dict(sorted(catalog_counts.items())),
        "counts_by_source_anchor_status": dict(sorted(anchor_counts.items())),
        "counts_by_review_reason": dict(sorted(reasons.items())),
        "pages_detail": {str(k): dict(v) for k, v in sorted(page_counts.items())},
        "missing_local_image_pages": sorted(missing_images),
        "out_of_order_y_rows": bad_order,
        "sample_rows": len(selected),
        "catalog_chapters": len(limits),
        "catalog_aliases": sum(len(a) for a in aliases.values()),
        "verified": 0, "sql_writes": False, "api_calls": 0,
        "notes": [
            "PARSED only means the deterministic parser understood the printed notation.",
            "Catalog VALID does not prove accurate OCR or edition-specific versification.",
            "All source-verse suggestions are OCR only; nothing is scan-verified.",
            "Numeric-only rows do not inherit a book from neighboring printed rows.",
            "Suffixes s, ss, p and + are not automatically expanded.",
        ],
    }
    save_json(out / "audit_summary.json", summary)
    save_csv(out / "rows.csv", row_results, ROW_COLUMNS)
    save_csv(out / "segments.csv", seg_results, SEGMENT_COLUMNS)
    save_csv(out / "review_queue.csv", review, SEGMENT_COLUMNS)
    save_csv(out / "target_interpretation_queue.csv", target_review, SEGMENT_COLUMNS)
    save_json(out / "target_interpretation_context.json", target_context)
    with (out / "segments.jsonl").open("w", encoding="utf-8") as f:
        for s in seg_results:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    decisions = [{
        "row_id": r["row_id"], "segment_id": s["segment_id"],
        "row_fingerprint": r["row_fingerprint"],
        "image_page": r["image_page"], "side": r["side"],
        "raw_line": r["raw_line"], "candidate_target": s["target"],
        "decision": "UNREVIEWED",
    } for _, r in selected for s in by_row.get(r["row_id"], [])]
    save_csv(out / "review_decisions_template.csv", decisions, DECISION_COLUMNS)
    save_json(out / "sample_30_records.json", [
        {"category": category, "row": row, "segments": by_row[row["row_id"]]}
        for category, row in selected
    ])
    make_html(out / "audit_report.html", out, selected, by_row, summary, args.images, args.copy_images)
    print("REPORT:", out)
    print("ROWS:", summary["rows"], "REFERENCE ROWS:", summary["reference_rows"],
          "SEGMENTS:", summary["segments"])
    print("PARSER PARSED:", summary["parsed_by_parser"],
          "PARSER REVIEW:", summary["parser_review_segments"],
          "INVALID TARGETS:", summary["invalid_target_segments"])
    print("TARGET INTERPRETATION REVIEW:", len(target_review))
    print("CATALOG:", json.dumps(summary["counts_by_catalog_status"]))
    print("ANCHORS:", json.dumps(summary["counts_by_source_anchor_status"]))
    print("Verified: 0; SQL writes: 0; API calls: 0")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=DEFAULT_DATA)
    p.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    p.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--start-page", type=int)
    p.add_argument("--end-page", type=int)
    p.add_argument("--sample", type=int, default=30)
    p.add_argument("--copy-images", action="store_true")
    p.add_argument("--reparse", action="store_true")
    p.add_argument("--parser", type=Path, default=DEFAULT_PARSER)
    try:
        return run(p.parse_args())
    except Exception as e:
        print("ERROR: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
