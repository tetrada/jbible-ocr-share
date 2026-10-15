#!/usr/bin/env python3
"""JBible FR 1988 v2 — OCR exactly one physically printed margin row at a time.

No SQL, no auto-verification, no English reference import.
DeepSeek Flash only, with thinking explicitly disabled.
Run --self-test / --preflight before the main batch.
"""
import argparse
import base64
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from fr88_v2_normalize import interpret_ocr_row, self_test as normalizer_test

RAW = Path("/raw")
SOURCE = RAW / "fr_bible_1988"
OUTPUT = RAW / "jbible_fr1988_v2"
CATALOG = RAW / "jbible_catalog.csv"
MODEL = "deepseek-flash"
API_URL = "https://api.deepseek.com/chat/completions"

SYSTEM_PROMPT = """
You are a VISUAL TRANSCRIBER of marginal biblical cross-references in the
FRENCH 1988 Jerusalem Bible scanned JPEG image.

TOP PRIORITY: ONE output item for EACH separate PHYSICALLY PRINTED ROW of
marginal references. Never merge different printed rows into one item,
even when no book name is printed on subsequent rows.
Never combine a continuation with a previous row unless both are physically
on the same baseline. If a reference visibly wraps across two baselines,
transcribe TWO physical rows and flag layout_uncertain=true.

Transcribe the exact reference text for each row into raw_line. Preserve book
abbreviations, chapter digits, commas, semicolons, periods, dashes, suffixes
(s, ss, p, +), equals signs, arrows, and spacing sufficiently to distinguish
tokens. There is NO NEED to assign a book to any numbers lacking a printed
book prefix. Do not expand abbreviations, insert missing book names, infer
biblical citations from memory, or complete cut-off text.

Examples of separate physical printed rows:
  "Sg 11 14-20"
  "16-18"
They are TWO independent items; DO NOT combine into "Sg 11 14-20; 16-18".
The second line does NOT automatically inherit "Sg".

Examples of ONE physical row:
  "Ps 78 47s; 105 32; Ap 16 21; 8 7"
Leave it as ONE raw_line: a deterministic parser will split it later.
  "Ne 9 18 Ps 106 19s 1 R 12 28"
Keep the printed sequence EXACTLY; do NOT represent all as Nehemiah.

A standalone "16-18" may mean whole chapters of the current SOURCE biblical
book, but do NOT guess the book. Preserve exactly "16-18".
"s" is a genuine printed suffix meaning following; not a failed verse range.

INPUT IMAGES:
- image 1: ONLY the requested side/half of a Bible page for context;
- image 2: requested-side MARGIN strip, full height;
- image 3: same margin, upper portion enlarged;
- image 4: same margin, lower portion enlarged (overlaps image 3).
Read ONLY from this margin. Exclude main Scripture text, ordinary verse
numbers, headers, editorial prose, section titles, and footer page numbers.
Overlapping images must NOT result in duplicate items.
Rows must be top-to-bottom ordered.

Output STRICT JSON object:
{
  "page_book_header": null,
  "items": [
    {
      "kind": "REFERENCE",
      "raw_line": "Nb 3 17s",
      "y_fraction": 0.35,
      "source_chapter": null,
      "source_verse": null,
      "source_anchor_confident": false,
      "layout_uncertain": false,
      "notes": ""
    }
  ],
  "warnings": []
}

kind may be "REFERENCE" or "SECTION_LABEL"; normally exclude labels entirely.
Use kind SECTION_LABEL ONLY when a note in the margin could be confused with
a biblical reference, preserving original text for auditing.
y_fraction is approximate vertical position (0..1) on full page.
source_chapter and source_verse refer to the source text aligned with the row.
Set them ONLY if the alignment is actually visible and certain; otherwise
use null and false. Do not assume Genesis for every page: scans span books.
page_book_header may be a book title if actually printed and visible; else null.
If there are no marginal reference rows, return an empty items list.
No hallucinations; no synthesized references; no verse/chapter normalization.
""".strip()

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        json.dump(obj, fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    os.replace(tmp, path)

def photo_bytes(img, width, height):
    img = img.convert("RGB")
    img.thumbnail((width, height), Image.Resampling.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.07)
    img = img.filter(ImageFilter.UnsharpMask(radius=0.7, percent=75, threshold=3))
    stream = io.BytesIO()
    img.save(stream, "JPEG", quality=91, optimize=True)
    return stream.getvalue()

def prepare_images(source_path, side):
    with Image.open(source_path) as src:
        page = ImageOps.exif_transpose(src).convert("RGB")
    w, h = page.size
    if side == "L":
        half = page.crop((0, 0, int(w * .50), h))
        strip = page.crop((0, 0, int(w * .41), h))
    else:
        half = page.crop((int(w * .50), 0, w, h))
        strip = page.crop((int(w * .59), 0, w, h))
    sw, sh = strip.size
    return {
        "half": photo_bytes(half, 1200, 2600),
        "full": photo_bytes(strip, 1650, 3900),
        "upper": photo_bytes(strip.crop((0, 0, sw, int(sh * .56))), 1650, 2850),
        "lower": photo_bytes(strip.crop((0, int(sh * .44), sw, sh)), 1650, 2850),
    }

def make_signature(page, side, image_parts):
    sha = hashlib.sha256()
    for value in (MODEL, SYSTEM_PROMPT, str(page), side):
        sha.update(value.encode("utf-8"))
    for name in ("half", "full", "upper", "lower"):
        sha.update(image_parts[name])
    return sha.hexdigest()

def call_deepseek(api_key, parts, page, side):
    content = [{"type": "text", "text":
                "French Bible scan image_%04d.jpg. Read margin %s ONLY. "
                "One printed row per JSON item; do not combine rows." % (page, side)}]
    for name in ("half", "full", "upper", "lower"):
        content.append({"type": "image_url",
                        "image_url": {"url": "data:image/jpeg;base64," +
                                           base64.b64encode(parts[name]).decode("ascii")}})
    body = json.dumps({
        "model": MODEL, "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "max_tokens": 8000,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content}
        ]
    }, ensure_ascii=False).encode("utf-8")
    for attempt in range(4):
        req = urllib.request.Request(
            API_URL, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + api_key})
        try:
            with urllib.request.urlopen(req, timeout=360) as resp:
                return json.loads(resp.read().decode("utf-8")), attempt + 1
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError("DeepSeek API HTTP %d" % e.code) from None
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise RuntimeError("DeepSeek API network timeout") from None
        time.sleep(5 * (attempt + 1))
    raise RuntimeError("Unexpected DeepSeek retry exhaustion")

def parse_provider(provider, page, side):
    choices = provider.get("choices") or []
    if not choices:
        raise ValueError("DeepSeek returned no choices")
    text = (choices[0].get("message") or {}).get("content")
    data = json.loads(text)
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("Expected JSON object with items array")
    if len(items) > 130:
        raise ValueError("Unusually many OCR rows per margin; inspect provider checkpoint")
    rows, warnings = [], []
    header = data.get("page_book_header")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid OCR item type")
        kind = item.get("kind", "REFERENCE")
        if kind not in ("REFERENCE", "SECTION_LABEL"):
            raise ValueError("Invalid OCR item kind")
        line = item.get("raw_line")
        if not isinstance(line, str) or not line.strip():
            raise ValueError("Missing raw_line in OCR item")
        physically_separated = [x.strip() for x in line.splitlines() if x.strip()]
        if len(physically_separated) > 1:
            warnings.append("Model embedded several rows in one item on page %d %s" %
                            (page, side))
        for part in physically_separated:
            ch, v = item.get("source_chapter"), item.get("source_verse")
            if type(ch) is not int or ch < 1:
                ch = None
            if type(v) is not int or v < 1:
                v = None
            y = item.get("y_fraction")
            if not isinstance(y, (int, float)) or isinstance(y, bool) or not 0 <= y <= 1:
                y = None
            rows.append({
                "id": "fr88v2:p%04d:%s:%02d" % (page, side, len(rows) + 1),
                "edition": "fr88v2",
                "image_page": page, "side": side,
                "source_image": "image_%04d.jpg" % page,
                "kind": kind,
                "raw_line": part,
                "page_book_header": header if isinstance(header, str) else None,
                "source_chapter": ch,
                "source_verse": v,
                "source_anchor_confident": (
                    item.get("source_anchor_confident") is True and
                    ch is not None and v is not None),
                "y_fraction": y,
                "layout_uncertain": bool(item.get("layout_uncertain")) or len(physically_separated) > 1,
                "notes": str(item.get("notes") or ""),
                "verified": False
            })
    warnings += [str(v) for v in data.get("warnings", []) if isinstance(v, str)] if isinstance(data.get("warnings", []), list) else []
    return rows, warnings

def collect_existing():
    data = {}
    for cp in sorted(OUTPUT.glob("image_????_?.result.json")):
        rec = json.loads(cp.read_text(encoding="utf-8"))
        if not isinstance(rec.get("rows"), list):
            raise ValueError("Invalid saved checkpoint: " + cp.name)
        data[cp.name] = rec
    return data

def compute_aggregate(checkpoints):
    rows = []
    for key in sorted(checkpoints):
        rows.extend(checkpoints[key]["rows"])
    ids = [v["id"] for v in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate OCR row IDs across checkpoints")
    interpreted = [interpret_ocr_row(r, CATALOG) for r in rows]
    segments = [part for r in interpreted for part in r["references"]]
    successful = sum(x["status"] == "PARSED" for x in segments)
    needs_review = len(segments) - successful
    parse_percent = round(100 * successful / len(segments), 1) if segments else 0.0
    metrics = {
        "edition": "FR1988-v2",
        "source": "JPEG marginal references",
        "checkpoint_margins": len(checkpoints),
        "pages_with_checkpoints": sorted(set(r.get("image_page") for r in rows)
                                         | set(int(k[6:10]) for k in checkpoints)),
        "ocr_rows": len(rows),
        "reference_rows": sum(r["kind"] == "REFERENCE" for r in rows),
        "section_labels": sum(r["kind"] == "SECTION_LABEL" for r in rows),
        "parsed_segments": successful,
        "interpretation_review": needs_review,
        "segments_total": len(segments),
        "parse_success_percent": parse_percent,
        "parse_review_percent": round(100 * needs_review / len(segments), 1) if segments else 0.0,
        "metrics_note": ("Parse success means the deterministic interpreter understood "
                         "the printed notation; it is not independently measured OCR accuracy."),
        "source_anchor_missing": sum(r["kind"] == "REFERENCE"
                                     and not r["source_anchor_confident"] for r in rows),
        "layout_uncertain_rows": sum(bool(r["layout_uncertain"]) for r in rows),
        "no_auto_book_inheritance_across_rows": True,
        "verified": 0, "sql_writes": False,
    }
    review = [{"id": r["id"], "raw_line": r["raw_line"],
               "image_page": r["image_page"], "side": r["side"],
               "references": [p for p in r["references"] if p["status"] != "PARSED"]}
              for r in interpreted
              if any(p["status"] != "PARSED" for p in r["references"])]
    return rows, interpreted, review, metrics

def write_aggregates(checkpoints, run):
    rows, interpreted, review, metrics = compute_aggregate(checkpoints)
    metrics.update(run)
    # Full outputs remain on the VPS. Small, stable 20-page shards are
    # published to GitHub for reliable inspection by ChatGPT.
    save(OUTPUT / "all_rows.json", rows)
    save(OUTPUT / "interpreted_rows.json", interpreted)
    save(OUTPUT / "parse_review.json", review)
    shards = OUTPUT / "shards"
    shards.mkdir(parents=True, exist_ok=True)
    raw_groups, parsed_groups = {}, {}
    for row, parsed in zip(rows, interpreted):
        page = row["image_page"]
        first = ((page - 1) // 20) * 20 + 1
        last = first + 19
        bucket = (first, last)
        raw_groups.setdefault(bucket, []).append(row)
        parsed_groups.setdefault(bucket, []).append(parsed)
    manifest = {"edition": "FR1988-v2", "shard_page_span": 20,
                "rows_total": len(rows), "chunks": [],
                "verified": 0, "sql_writes": False}
    produced = set()
    for first, last in sorted(raw_groups):
        suffix = "p%04d_%04d.json" % (first, last)
        rows_name = "rows_" + suffix
        interpreted_name = "interpreted_" + suffix
        save(shards / rows_name, raw_groups[(first, last)])
        save(shards / interpreted_name, parsed_groups[(first, last)])
        produced.update((rows_name, interpreted_name))
        manifest["chunks"].append({
            "page_range": [first, last],
            "rows_file": "fr88_v2_shards/" + rows_name,
            "interpreted_file": "fr88_v2_shards/" + interpreted_name,
            "row_count": len(raw_groups[(first, last)]),
        })
    for old in shards.glob("*.json"):
        if old.name not in produced:
            old.unlink()
    save(OUTPUT / "manifest.json", manifest)
    save(OUTPUT / "summary.json", metrics)
    return metrics

def preflight(start, end):
    if not CATALOG.is_file():
        raise RuntimeError("Missing catalog: " + str(CATALOG))
    print(normalizer_test(str(CATALOG)), flush=True)
    missing = []
    for page in range(start, end + 1):
        jpg = SOURCE / ("image_%04d.jpg" % page)
        if not jpg.is_file() or jpg.stat().st_size < 500:
            missing.append(str(jpg))
    if missing:
        raise RuntimeError("%d JPEG pages missing/empty, examples: %s" %
                           (len(missing), ", ".join(missing[:12])))
    for page in (start, end):
        with Image.open(SOURCE / ("image_%04d.jpg" % page)) as img:
            img.verify()
    print("PREFLIGHT OK: %d JPG pages (%d..%d), catalog, parser" %
          (end - start + 1, start, end), flush=True)

def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--start", type=int, default=32)
    cli.add_argument("--end", type=int, default=500)
    cli.add_argument("--preflight", action="store_true")
    cli.add_argument("--initialize", action="store_true",
                     help="Create empty v2 aggregate files without DeepSeek calls")
    args = cli.parse_args()
    if args.start < 1 or args.end < args.start:
        cli.error("Invalid page range")
    preflight(args.start, args.end)
    if args.preflight:
        return 0
    if args.initialize:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        metrics = write_aggregates(collect_existing(), {
            "requested_pages": [args.start, args.end],
            "margins_in_run": 0,
            "margins_total": (args.end - args.start + 1) * 2,
            "api_calls": 0, "cached_jobs": 0,
            "errors": 0, "failures": [],
            "ocr_margins_success": 0,
            "ocr_margin_success_percent": 0.0,
            "last_update_utc": datetime.now(timezone.utc).isoformat(),
        })
        print("INITIALIZED: %d existing OCR rows; no API calls" %
              metrics["ocr_rows"], flush=True)
        return 0
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        cli.error("DEEPSEEK_API_KEY is not set")
    from jbible_status_bridge import AsyncStatus
    import jbible_status_bridge as bridge
    bridge.WIDGETS = [
        {"type":"progress","title":"FR88 v2 margins","metric":"processed","total_metric":"total"},
        {"type":"metric","title":"OCR printed rows","metric":"ocr_rows"},
        {"type":"metric","title":"Reference interpretation (%)","metric":"parse_success_percent"},
        {"type":"metric","title":"OCR margin processing success (%)","metric":"ocr_margin_success_percent"},
        {"type":"metric","title":"Parsed reference segments","metric":"parsed_segments"},
        {"type":"metric","title":"Interpretation review","metric":"interpretation_review"},
        {"type":"metric","title":"Missing source anchors","metric":"source_anchor_missing"},
        {"type":"metric","title":"New API calls","metric":"api_calls"},
        {"type":"events","title":"FR88 v2 events"},
    ]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    saved = collect_existing()
    total = (args.end - args.start + 1) * 2
    done, api_calls, cache_hits, errors = 0, 0, 0, []
    begin = time.monotonic()
    status = AsyncStatus("French 1988 OCR v2", "FR88", "BIBLE", total)
    status.event("Starting page-by-page row-preserving OCR", details={
        "start_page": args.start, "end_page": args.end, "total_margins": total})
    print("START FR88 V2 pages %d..%d, total %d margins" %
          (args.start, args.end, total), flush=True)
    for page in range(args.start, args.end + 1):
        jpg = SOURCE / ("image_%04d.jpg" % page)
        for side in ("L", "R"):
            name = "image_%04d_%s" % (page, side)
            cp_path = OUTPUT / (name + ".result.json")
            provider_path = OUTPUT / (name + ".provider.json")
            try:
                parts = prepare_images(jpg, side)
                fingerprint = make_signature(page, side, parts)
                if cp_path.exists():
                    data = json.loads(cp_path.read_text(encoding="utf-8"))
                    if data.get("signature") != fingerprint:
                        raise ValueError("Checkpoint fingerprint differs: " + name)
                    cache_hits += 1
                    print("CACHE %s rows=%d" % (name, len(data["rows"])), flush=True)
                else:
                    if provider_path.exists():
                        provider = json.loads(provider_path.read_text(encoding="utf-8"))
                        if provider.get("signature") != fingerprint:
                            raise ValueError("Provider fingerprint differs: " + name)
                        response = provider["response"]
                        print("REPARSE %s" % name, flush=True)
                    else:
                        print("OCR %s" % name, flush=True)
                        response, attempts = call_deepseek(api_key, parts, page, side)
                        api_calls += attempts
                        provider = {"signature": fingerprint, "response": response,
                                    "created_utc": datetime.now(timezone.utc).isoformat()}
                        save(provider_path, provider)
                    rows, warnings = parse_provider(response, page, side)
                    data = {"signature": fingerprint, "page": page, "side": side,
                            "rows": rows, "warnings": warnings,
                            "api_usage": response.get("usage", {}),
                            "verified": 0, "sql_writes": False}
                    save(cp_path, data)
                    print("  %d printed rows, %d warnings" %
                          (len(rows), len(warnings)), flush=True)
                saved[cp_path.name] = data
            except Exception as exc:
                failure = {"page": page, "side": side,
                           "error": "%s: %s" % (type(exc).__name__, exc)}
                errors.append(failure)
                print("ERROR %s %s" % (name, failure["error"]), flush=True)
                status.event("OCR margin failed: " + name, level="warning",
                             details=failure)
            finally:
                done += 1
                rows_now, interpreted, review, metrics = compute_aggregate(saved)
                elapsed = time.monotonic() - begin
                eta = round(elapsed * (total - done) / done) if done else None
                ocr_margin_success_percent = round(
                    100 * (done - len(errors)) / done, 1) if done else 0.0
                status.update(message="FR88 v2 p%04d %s, %d/%d" %
                              (page, side, done, total),
                              status="running",
                              processed=done, total=total,
                              percent=round(100 * done / total, 1),
                              eta_seconds=eta,
                              ocr_rows=metrics["ocr_rows"],
                              parsed_segments=metrics["parsed_segments"],
                              interpretation_review=metrics["interpretation_review"],
                              parse_success_percent=metrics["parse_success_percent"],
                              ocr_margin_success_percent=ocr_margin_success_percent,
                              source_anchor_missing=metrics["source_anchor_missing"],
                              api_calls=api_calls, cache_hits=cache_hits,
                              errors=len(errors), verified=0)
                if done % 10 == 0 or done == total:
                    run = {"requested_pages": [args.start, args.end],
                           "margins_in_run": done, "margins_total": total,
                           "api_calls": api_calls, "cached_jobs": cache_hits,
                           "errors": len(errors), "failures": errors,
                           "ocr_margins_success": done - len(errors),
                           "ocr_margin_success_percent": ocr_margin_success_percent,
                           "last_update_utc": datetime.now(timezone.utc).isoformat()}
                    metrics = write_aggregates(saved, run)
                    print("CHECKPOINT: %d margins, %d rows, parsed %.1f%% (%d/%d), "
                          "OCR-processing success %.1f%%, review %d, errors %d" %
                          (done, metrics["ocr_rows"], metrics["parse_success_percent"],
                           metrics["parsed_segments"], metrics["segments_total"],
                           metrics["ocr_margin_success_percent"],
                           metrics["interpretation_review"], len(errors)), flush=True)
    if errors:
        status.finish("warning", "FR88 v2 finished with %d failed margins" % len(errors))
        return 1
    status.finish("completed",
                  "FR88 v2 complete: %d pages, %d rows, %d API calls" %
                  (args.end - args.start + 1, metrics["ocr_rows"], api_calls))
    print("FINAL SUMMARY:\n" + json.dumps(metrics, indent=2, ensure_ascii=False), flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
