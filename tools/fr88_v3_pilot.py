#!/usr/bin/env python3
"""JBible FR88 OCR v3 20-page typography pilot. Separate from immutable v2.
Python 3.6 compatible. No SQL, no source-verse verification, no OCR overwrite.
"""
import argparse
import base64
import csv
import difflib
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fr88_v2_ocr import prepare_images
from fr88_v2_normalize import interpret_ocr_row, self_test as parser_self_test

ROOT = Path("/raw")
IMAGES = ROOT / "fr_bible_1988"
CATALOG = ROOT / "jbible_catalog.csv"
V2 = ROOT / "jbible_fr1988_v2" / "interpreted_rows.json"
OUT = ROOT / "jbible_fr1988_v3_pilot_31_50"
PROMPT = Path("/app/fr88_v3_typography_prompt.txt")
MODEL = "deepseek-flash"
URL = "https://api.deepseek.com/chat/completions"
FIRST = 31
LAST = 50
SIDES = ("L", "R")
IMAGE_PARTS = ("half", "full", "upper", "lower")


def utc():
    return datetime.now(timezone.utc).isoformat()


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(str(temp), str(path))


def save_csv(path, rows, cols):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(str(temp), str(path))


def key_for(page, side):
    return "image_%04d_%s" % (page, side)


def signature(page, side, parts, prompt):
    dig = hashlib.sha256()
    for v in (MODEL, prompt, str(page), side):
        dig.update(v.encode("utf-8"))
    for name in IMAGE_PARTS:
        dig.update(parts[name])
    return dig.hexdigest()


def preflight(start, end):
    if start < FIRST or end > LAST or start > end:
        raise ValueError("Pilot is restricted to pages 31..50 (max 20 pages)")
    for path in (PROMPT, CATALOG, V2):
        if not path.is_file():
            raise RuntimeError("Missing required input: " + str(path))
    if not PROMPT.read_text(encoding="utf-8").strip():
        raise RuntimeError("Empty v3 prompt")
    missing = [p for p in range(start, end + 1)
               if not (IMAGES / ("image_%04d.jpg" % p)).is_file()]
    if missing:
        raise RuntimeError("Missing JPEG pages: %s" % missing)
    print(parser_self_test(str(CATALOG)))
    print("PREFLIGHT OK: pages %d-%d, %d margins. No API calls." %
          (start, end, 2 * (end - start + 1)), flush=True)


def api_call(key, parts, page, side, prompt):
    content = [{"type": "text", "text":
                "JPEG image_%04d.jpg, margin %s only. Follow typography and physical-row rules. "
                "Distinguish printed bold chapter from ordinary verse digits. "
                "Do not infer source verse." % (page, side)}]
    for name in IMAGE_PARTS:
        content.append({"type": "image_url", "image_url": {"url":
            "data:image/jpeg;base64," + base64.b64encode(parts[name]).decode("ascii")}})
    payload = json.dumps({
        "model": MODEL, "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "max_tokens": 8000,
        "messages": [{"role": "system", "content": prompt},
                     {"role": "user", "content": content}]
    }, ensure_ascii=False).encode("utf-8")
    attempts = 0
    for retry in range(4):
        attempts += 1
        request = urllib.request.Request(
            URL, data=payload, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + key})
        try:
            with urllib.request.urlopen(request, timeout=360) as response:
                return json.loads(response.read().decode("utf-8")), attempts
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or retry == 3:
                raise RuntimeError("DeepSeek HTTP %d after %d attempts" % (exc.code, attempts))
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if retry == 3:
                raise RuntimeError("DeepSeek unavailable after %d attempts" % attempts)
        time.sleep(5 * (retry + 1))
    raise RuntimeError("Exhausted retries")


def provider_rows(provider, page, side):
    choices = provider.get("choices") or []
    if not choices:
        raise ValueError("Missing DeepSeek choices")
    answer = (choices[0].get("message") or {}).get("content")
    if not isinstance(answer, str):
        raise ValueError("No JSON model content")
    parsed = json.loads(answer)
    items = parsed.get("items")
    if not isinstance(items, list) or len(items) > 130:
        raise ValueError("Expected items list of at most 130 rows")
    result = []
    warnings = list(parsed.get("warnings") or [])
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid row object")
        line = item.get("raw_line")
        kind = item.get("kind", "REFERENCE")
        if not isinstance(line, str) or not line.strip() or kind not in ("REFERENCE", "SECTION_LABEL"):
            raise ValueError("Invalid reference row kind/text")
        separated = [x.strip() for x in line.splitlines() if x.strip()]
        if len(separated) > 1:
            warnings.append("Multiple baselines in one row: %d %s" % (page, side))
        y = item.get("y_fraction")
        if not isinstance(y, (float, int)) or isinstance(y, bool) or not 0 <= y <= 1:
            y = None
        for raw in separated:
            row = {
                "id": "fr88v3:p%04d:%s:%02d" % (page, side, len(result) + 1),
                "edition": "fr88v3-pilot",
                "image_page": page, "side": side,
                "source_image": "image_%04d.jpg" % page,
                "kind": kind, "raw_line": raw, "y_fraction": y,
                "page_book_header": parsed.get("page_book_header"),
                "source_chapter": None, "source_verse": None,
                "source_anchor_confident": False,
                "layout_uncertain": bool(item.get("layout_uncertain")) or len(separated) > 1,
                "typography_uncertain": bool(item.get("typography_uncertain")),
                "typography_evidence": str(item.get("typography_evidence") or "")[:300],
                "notes": str(item.get("notes") or "")[:500],
                "verified": False
            }
            result.append(interpret_ocr_row(row, CATALOG))
    return result, warnings


def catalog_limits():
    with CATALOG.open(encoding="utf-8-sig", newline="") as fh:
        return {(r["book_code"], int(r["chap_number"])): int(r["max_verse"])
                for r in csv.DictReader(fh) if r["record_type"] == "C"}


def catalog_status(ref, limits):
    book, chapter = ref.get("book_code"), ref.get("chapter")
    typ = ref.get("type")
    if not book:
        return "MISSING_BOOK"
    if typ == "UNRESOLVED_NUMERIC":
        return "NOT_CHECKABLE"
    max_v = limits.get((book, chapter))
    if not max_v:
        return "INVALID"
    if typ == "CHAPTER_RANGE":
        last = ref.get("end_chapter")
        if not isinstance(last, int) or last < chapter or any(
            (book, x) not in limits for x in range(chapter, last + 1)):
            return "INVALID"
    if typ in ("VERSE", "VERSE_RANGE"):
        verse = ref.get("verse")
        if type(verse) is not int or not 1 <= verse <= max_v:
            return "INVALID"
        if typ == "VERSE_RANGE" and (
            type(ref.get("end_verse")) is not int or
            not verse <= ref["end_verse"] <= max_v):
            return "INVALID"
    if typ == "VERSE_LIST":
        verses = ref.get("verses")
        if not isinstance(verses, list) or not verses or any(
            type(v) is not int or v < 1 or v > max_v for v in verses):
            return "INVALID"
    return "VALID"


def stats(rows, limits):
    counts = Counter()
    for r in rows:
        counts["rows"] += 1
        if r.get("kind") != "REFERENCE":
            counts["section_labels"] += 1
            continue
        counts["reference_rows"] += 1
        for ref in r.get("references") or []:
            counts["segments"] += 1
            counts["parsed" if ref.get("status") == "PARSED" else "parse_review"] += 1
            counts["catalog_" + catalog_status(ref, limits)] += 1
    return dict(counts)


def normalize(s):
    return re.sub(r"\s+", " ", str(s or "").strip()).casefold()


def compare(start, end, gold=None):
    if not V2.is_file():
        raise RuntimeError("Missing v2 baseline " + str(V2))
    v2 = json.loads(V2.read_text(encoding="utf-8"))
    v2 = [r for r in v2 if start <= r["image_page"] <= end]
    margins2 = defaultdict(list)
    margins3 = defaultdict(list)
    for row in v2:
        margins2[row["image_page"], row["side"]].append(row)
    missing = []
    for page in range(start, end + 1):
        for side in SIDES:
            cp = OUT / (key_for(page, side) + ".result.json")
            if cp.is_file():
                data = json.loads(cp.read_text(encoding="utf-8"))
                margins3[page, side] = data["rows"]
            else:
                missing.append(key_for(page, side))
    limits = catalog_limits()
    differences = []
    margin_summary = []
    for page in range(start, end + 1):
        for side in SIDES:
            old = margins2[page, side]
            new = margins3[page, side]
            a = [normalize(x["raw_line"]) for x in old]
            b = [normalize(x["raw_line"]) for x in new]
            matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
            n = 0
            for tag, i, j, k, m in matcher.get_opcodes():
                if tag == "equal":
                    continue
                n += 1
                differences.append({
                    "page": page, "side": side, "change": tag,
                    "v2_ids": ";".join(x["id"] for x in old[i:j]),
                    "v2_text": " || ".join(x["raw_line"] for x in old[i:j]),
                    "v3_ids": ";".join(x["id"] for x in new[k:m]),
                    "v3_text": " || ".join(x["raw_line"] for x in new[k:m]),
                    "note": "DIFFERENCE, NOT PROOF OF OCR IMPROVEMENT"
                })
            margin_summary.append({
                "page": page, "side": side, "v2_rows": len(old),
                "v3_rows": len(new), "diff_hunks": n,
                "v2_parse_review": stats(old, limits).get("parse_review", 0),
                "v3_parse_review": stats(new, limits).get("parse_review", 0),
                "v2_catalog_invalid": stats(old, limits).get("catalog_INVALID", 0),
                "v3_catalog_invalid": stats(new, limits).get("catalog_INVALID", 0),
            })
    all_v3 = [r for group in margins3.values() for r in group]
    raw_counts_v2 = stats(v2, limits)
    raw_counts_v3 = stats(all_v3, limits)
    payload = {
        "pages": [start, end],
        "margins_complete": (end - start + 1) * 2 - len(missing),
        "margins_expected": (end - start + 1) * 2,
        "missing_v3_margins": missing,
        "v2": raw_counts_v2, "v3": raw_counts_v3,
        "transcription_difference_hunks": len(differences),
        "warning": "Transcription disagreement or parser success is NOT OCR accuracy. Verify against scan.",
        "verified_source_to_target_links": 0, "sql_writes": False,
        "gold_evaluation": None
    }
    if gold:
        checked, v2_ok, v3_ok, skipped = 0, 0, 0, []
        with gold.open(encoding="utf-8-sig", newline="") as fh:
            reviews = list(csv.DictReader(fh))
        for item in reviews:
            if str(item.get("verified_from_scan") or "").strip().upper() not in ("YES", "TRUE", "1"):
                continue
            expected = normalize(item.get("expected_raw_line"))
            page, side = int(item["page"]), item["side"]
            identity = item["v2_row_id"]
            source = next((r for r in margins2[page, side] if r["id"] == identity), None)
            if source is None or not expected:
                skipped.append(identity + " missing baseline/expected value")
                continue
            pool = margins3[page, side]
            original_y = source.get("y_fraction")
            candidates = sorted(
                [r for r in pool if isinstance(r.get("y_fraction"), (float, int))
                 and isinstance(original_y, (float, int))],
                key=lambda r: abs(r["y_fraction"] - original_y))
            if len(candidates) != 1 and (
                len(candidates) < 1 or
                (abs(candidates[0]["y_fraction"] - original_y) >= 0.03) or
                (abs(candidates[1]["y_fraction"] - original_y) -
                 abs(candidates[0]["y_fraction"] - original_y) < 0.01)):
                skipped.append(identity + " ambiguous v3 geometry")
                continue
            if not candidates or abs(candidates[0]["y_fraction"] - original_y) >= 0.03:
                skipped.append(identity + " no nearby v3 row")
                continue
            checked += 1
            v2_ok += int(normalize(source["raw_line"]) == expected)
            v3_ok += int(normalize(candidates[0]["raw_line"]) == expected)
        payload["gold_evaluation"] = {
            "human_verified_rows_matched": checked,
            "v2_exact_raw_matches": v2_ok, "v3_exact_raw_matches": v3_ok,
            "skipped": skipped,
            "warning": "Only supplied scan-confirmed rows count; geometric matching must be manually checked."
        }

    save_json(OUT / "comparison.json", payload)
    save_csv(OUT / "comparison_by_margin.csv", margin_summary,
             ["page","side","v2_rows","v3_rows","diff_hunks",
              "v2_parse_review","v3_parse_review",
              "v2_catalog_invalid","v3_catalog_invalid"])
    save_csv(OUT / "transcription_disagreements.csv", differences,
             ["page","side","change","v2_ids","v2_text","v3_ids","v3_text","note"])
    template = OUT / "gold_review_template.csv"
    if not template.exists():
        records = [{
            "page": r["image_page"], "side": r["side"],
            "v2_row_id": r["id"], "v2_raw_line": r["raw_line"],
            "v2_y_fraction": r.get("y_fraction"),
            "expected_raw_line": "", "verified_from_scan": "",
            "reviewer_notes": ""
        } for r in v2 if r.get("kind") == "REFERENCE"]
        save_csv(template, records,
                 ["page","side","v2_row_id","v2_raw_line","v2_y_fraction",
                  "expected_raw_line","verified_from_scan","reviewer_notes"])
    print("COMPARISON:", json.dumps(payload, indent=2, ensure_ascii=False), flush=True)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=int, default=FIRST)
    parser.add_argument("--end", type=int, default=LAST)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--compare-only", action="store_true")
    parser.add_argument("--gold", type=Path)
    parser.add_argument("--max-new-margins", type=int, default=40)
    args = parser.parse_args()
    preflight(args.start, args.end)
    if args.preflight:
        return 0
    if args.compare_only:
        compare(args.start, args.end, args.gold)
        return 0
    if args.max_new_margins < 1 or args.max_new_margins > 40:
        parser.error("--max-new-margins must be 1..40")
    prompt = PROMPT.read_text(encoding="utf-8")
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        parser.error("DEEPSEEK_API_KEY missing; use the existing Docker .env.deepseek")
    OUT.mkdir(parents=True, exist_ok=True)
    new_calls, cached, completed = 0, 0, 0
    failures = []
    stop = False
    total = 2 * (args.end - args.start + 1)
    for page in range(args.start, args.end + 1):
        for side in SIDES:
            name = key_for(page, side)
            cp = OUT / (name + ".result.json")
            prov = OUT / (name + ".provider.json")
            try:
                parts = prepare_images(IMAGES / ("image_%04d.jpg" % page), side)
                sig = signature(page, side, parts, prompt)
                if cp.exists():
                    existing = json.loads(cp.read_text(encoding="utf-8"))
                    if existing.get("signature") != sig:
                        raise RuntimeError("v3 checkpoint fingerprint changed: " + name)
                    print("CACHE %s rows=%d" % (name, len(existing["rows"])), flush=True)
                    cached += 1
                else:
                    if prov.exists():
                        data = json.loads(prov.read_text(encoding="utf-8"))
                        if data.get("signature") != sig:
                            raise RuntimeError("v3 provider fingerprint changed: " + name)
                        response = data["response"]
                        print("REPARSE saved %s" % name, flush=True)
                    else:
                        if new_calls >= args.max_new_margins:
                            print("API call budget reached (%d margins)" % new_calls, flush=True)
                            stop = True
                            break
                        print("OCR V3 %s (%d/%d)" % (name, completed + 1, total), flush=True)
                        response, attempts = api_call(key, parts, page, side, prompt)
                        new_calls += 1
                        save_json(prov, {"signature": sig, "response": response,
                                         "created_utc": utc(), "attempts": attempts})
                    rows, warnings = provider_rows(response, page, side)
                    save_json(cp, {"signature": sig, "page": page, "side": side,
                                   "rows": rows, "warnings": warnings,
                                   "api_usage": response.get("usage", {}),
                                   "verified": 0, "sql_writes": False})
                    print("  %d physical rows, %d warnings" % (len(rows), len(warnings)), flush=True)
            except Exception as exc:
                failures.append({"page":page,"side":side,"error":"%s: %s" %
                                 (type(exc).__name__, exc)})
                print("ERROR %s: %s" % (name, failures[-1]["error"]), flush=True)
            completed += 1
        if stop:
            break
    # Comparison is safe even if some margin calls failed.
    result = compare(args.start, args.end, args.gold)
    report = {"edition": "FR1988-v3-pilot", "pages": [args.start, args.end],
              "finished_utc": utc(), "model": MODEL,
              "fresh_successful_margin_calls": new_calls,
              "cached_margins_used": cached, "errors": failures,
              "comparison": str(OUT / "comparison.json"),
              "complete": result["margins_complete"] == result["margins_expected"],
              "verified": 0, "sql_writes": False}
    save_json(OUT / "run_summary.json", report)
    print("RUN SUMMARY:", json.dumps(report, indent=2), flush=True)
    return 0 if not failures and report["complete"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("FATAL %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        sys.exit(1)
