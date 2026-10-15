#!/usr/bin/env python3
"""JBible French 1988 JPEG OCR pilot. Read-only source; no SQL or auto-verification.

Usage:
  python /app/jbible_fr1988_pilot.py --start 32 --end 36

Input: /raw/fr_bible_1988/image_XXXX.jpg
Output: /raw/jbible_fr1988_pilot/
Dependencies already present in JBible Docker image and importer:
    fitz, Pillow, jbible_v79_typography, jbible_dual,
    jbible_v711_catalog, jbible_status_bridge, status_sdk
"""
import argparse
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

import jbible_v79_typography as ocr
import jbible_v711_catalog as bible
from jbible_dual import compare
import jbible_status_bridge as bridge
from jbible_status_bridge import AsyncStatus

RAW = Path("/raw")
SOURCE = RAW / "fr_bible_1988"
OUT = RAW / "jbible_fr1988_pilot"
EN_FILE = RAW / "jbible_dual_v1/en/all_records.json"
MODEL = "deepseek-flash"

bridge.WIDGETS = [
    {"type": "progress", "title": "French 1988 OCR", "metric": "processed", "total_metric": "total"},
    {"type": "metric", "title": "FR88 references", "metric": "candidates"},
    {"type": "metric", "title": "Structural pass (%)", "metric": "structural_percent"},
    {"type": "metric", "title": "Supported by EN", "metric": "supported_by_en"},
    {"type": "metric", "title": "Needs review", "metric": "review_records"},
    {"type": "metric", "title": "DeepSeek calls", "metric": "api_calls"},
    {"type": "events", "title": "OCR activity"},
]

PROMPT = ocr.PROMPT + """

ADDITIONAL INSTRUCTIONS FOR THIS 1988 FRENCH EDITION:
- The input is a scanned JPEG page, NOT a PDF crop.
- The first image shows the whole page for context. Other images show
  ONE SIDE of the same page, enlarged and with overlapping vertical crops.
- Return references printed on that requested SIDE only. Do not duplicate
  references from overlapping images.
- Be careful: independent references separated by whitespace, different
  printed book abbreviations, or separate typographic lines must not be
  merged into a single item. Semicolon continuations may remain together.
- Do not include ordinary verse numbers, scripture running text, chapter
  headings, footer prose, or editorial footnote prose as cross-references.
- The typography may differ from other French editions. Determine bold
  chapter digits only by what is visible here, not by assumptions.
- If no marginal cross-references appear on this side return {"items":[]}.
- Never invent a reference based on biblical knowledge.
- For EACH item, ALSO return:
  "source_chapter": Genesis chapter as integer or null,
  "source_verse": Genesis verse as integer or null,
  "source_anchor_confident": true or false.
- These are the GENESIS location of the marginal reference, NOT its target.
  If the aligned source verse is not visually clear use null and false.
"""

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)

def jpeg(img, max_w=1800, max_h=3700):
    img = img.copy().convert("RGB")
    img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = img.filter(ImageFilter.UnsharpMask(radius=0.8, percent=100, threshold=3))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=93, optimize=True)
    return buf.getvalue()

def images_for(path, side):
    with Image.open(path) as orig:
        page = ImageOps.exif_transpose(orig).convert("RGB")
    w, h = page.size
    if side == "L":
        strip = page.crop((0, 0, int(w * 0.39), h))
    else:
        strip = page.crop((int(w * 0.61), 0, w, h))
    sh = strip.height
    return {
        "overview": jpeg(page, 1200, 2000),
        "full": jpeg(strip, 1600, 3700),
        "upper": jpeg(strip.crop((0, 0, strip.width, int(sh * 0.57))), 1600, 2900),
        "lower": jpeg(strip.crop((0, int(sh * 0.43), strip.width, sh)), 1600, 2900),
    }

def request_ocr(token, images, page, side):
    content = [{
        "type": "text",
        "text": (
            "French Bible 1988, Genesis, image page %d, margin side %s. "
            "The first image is PAGE CONTEXT only. "
            "Read cross-references ONLY from the %s side crops and "
            "do not repeat overlapped entries." % (page, side, side)
        )
    }]
    for part in ("overview", "full", "upper", "lower"):
        content.append(ocr.image_part(images[part]))
    payload = {
        "model": MODEL,
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "max_tokens": 8000,
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": content}
        ]
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(3):
        req = urllib.request.Request(
            "https://api.deepseek.com/chat/completions", data=data, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + token}
        )
        try:
            with urllib.request.urlopen(req, timeout=360) as response:
                return json.loads(response.read().decode("utf-8")), attempt + 1
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError("DeepSeek HTTP %d" % exc.code) from None
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError("DeepSeek request failed") from None
        time.sleep((attempt + 1) * 5)

def parse(response, page, side):
    rows = ocr.parse_response(response, page, side)
    raw = json.loads(response["choices"][0]["message"]["content"])["items"]
    if len(rows) != len(raw):
        raise ValueError("Parsed/raw item count mismatch")
    for row, original in zip(rows, raw):
        row["id"] = row["id"].replace("fr:", "fr88:", 1)
        row["edition"] = "fr88"
        row["image_page"] = page
        row["source_image"] = "image_%04d.jpg" % page
        for field in ("source_chapter", "source_verse"):
            x = original.get(field)
            row[field] = x if type(x) is int and x > 0 else None
        row["source_anchor_confident"] = (
            original.get("source_anchor_confident") is True
            and row["source_chapter"] is not None
            and row["source_verse"] is not None
        )
    return rows

def summarize(rows, en, catalog, completed, total, calls, cached, errors):
    comparison = compare(rows, en, catalog, (1, 50))
    refs = [r for r in comparison if r.get("kind") == "REFERENCE"]
    counts = Counter(r.get("review_status") for r in refs)
    accepted = counts["CANDIDATE_UNVERIFIED"] + counts["SUPPORTED_BY_EN"]
    return comparison, {
        "source": "French Bible 1988 JPEG",
        "pages_requested": [min(r["image_page"] for r in rows), max(r["image_page"] for r in rows)] if rows else [],
        "margins_done": completed,
        "margins_total": total,
        "references": len(refs),
        "structural_ok": accepted,
        "structural_percent": round(100 * accepted / len(refs), 1) if refs else 0,
        "supported_by_en": counts["SUPPORTED_BY_EN"],
        "review_records": counts["REVIEW"],
        "source_anchor_missing": sum(not r.get("source_anchor_confident") for r in refs),
        "section_labels": sum(r.get("kind") == "SECTION_LABEL" for r in comparison),
        "status_counts": dict(counts),
        "api_calls": calls,
        "cached_jobs": cached,
        "errors": errors,
        "verified": 0,
        "sql_writes": False,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=32)
    ap.add_argument("--end", type=int, default=36)
    ap.add_argument("--prepare-only", action="store_true")
    args = ap.parse_args()
    if args.start < 1 or args.end < args.start:
        ap.error("Invalid page range")
    pages = range(args.start, args.end + 1)
    for page in pages:
        img = SOURCE / ("image_%04d.jpg" % page)
        if not img.is_file() or img.stat().st_size == 0:
            ap.error("Missing image: %s" % img)

    token = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not token and not args.prepare_only:
        ap.error("Missing DEEPSEEK_API_KEY")
    if not EN_FILE.exists() and not args.prepare_only:
        ap.error("Missing existing EN comparison data: %s" % EN_FILE)

    OUT.mkdir(parents=True, exist_ok=True)
    if not args.prepare_only:
        bible.CATALOG = RAW / "jbible_catalog.csv"
        catalog = bible.catalog_load()
        en = json.loads(EN_FILE.read_text(encoding="utf-8"))
    else:
        catalog, en = None, []

    total = len(pages) * 2
    status = None if args.prepare_only else AsyncStatus("JBible FR1988 OCR", "FR88", "GEN", total)
    calls, cached, done, errors = 0, 0, 0, 0
    rows = []
    failures = []
    began = time.monotonic()
    if status:
        print("[STATUS] %s" % status.entity, flush=True)
        status.event("1988 French JPEG pilot started",
                     details={"start": args.start, "end": args.end, "margins": total})

    for page in pages:
        source = SOURCE / ("image_%04d.jpg" % page)
        for side in ("L", "R"):
            stem = "image_%04d_%s" % (page, side)
            result_path = OUT / (stem + ".result.json")
            provider_path = OUT / (stem + ".provider.json")
            try:
                images = images_for(source, side)
                for part, data in images.items():
                    dst = OUT / "images" / (stem + "_" + part + ".jpg")
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    if not dst.exists():
                        dst.write_bytes(data)
                if args.prepare_only:
                    print("PREPARED", stem, flush=True)
                    continue

                sha = hashlib.sha256()
                sha.update(PROMPT.encode("utf-8"))
                sha.update(MODEL.encode("ascii"))
                sha.update(stem.encode("ascii"))
                for part in ("overview", "full", "upper", "lower"):
                    sha.update(images[part])
                signature = sha.hexdigest()

                if result_path.exists():
                    result = json.loads(result_path.read_text(encoding="utf-8"))
                    if result.get("signature") != signature:
                        raise RuntimeError("Result checkpoint mismatch")
                    cached += 1
                    print("CACHE", stem, flush=True)
                else:
                    if provider_path.exists():
                        provider = json.loads(provider_path.read_text(encoding="utf-8"))
                        if provider.get("signature") != signature:
                            raise RuntimeError("Provider checkpoint mismatch")
                        response = provider["response"]
                        print("PROVIDER CACHE", stem, flush=True)
                    else:
                        print("DEEPSEEK", stem, flush=True)
                        response, attempts = request_ocr(token, images, page, side)
                        calls += attempts
                        save(provider_path, {"signature": signature, "response": response,
                                             "attempts": attempts})
                    items = parse(response, page, side)
                    result = {"signature": signature, "edition": "fr88",
                              "page": page, "side": side, "items": items,
                              "usage": response.get("usage", {}),
                              "verified": 0, "sql_writes": False}
                    save(result_path, result)

                rows.extend(result["items"])
                print("  %s: %d items" % (stem, len(result["items"])), flush=True)
            except Exception as exc:
                errors += 1
                failures.append({"page": page, "side": side, "error": str(exc)})
                print("  ERROR %s: %s" % (stem, exc), flush=True)
                if status:
                    status.event("OCR error %s (%s)" % (stem, type(exc).__name__), "warning")
            finally:
                if not args.prepare_only:
                    done += 1
                    comparison, metrics = summarize(
                        rows, en, catalog, done, total, calls, cached, errors)
                    elapsed = time.monotonic() - began
                    eta = round(elapsed * (total - done) / done) if done and done < total else 0
                    if status:
                        status.update(
                            message="FR 1988 page %d %s (%d/%d)" % (page, side, done, total),
                            phase="fr1988_ocr",
                            processed=done, total=total, remaining=total-done,
                            percent=round(100*done/total, 1), eta_seconds=eta,
                            candidates=metrics["references"],
                            structural_ok=metrics["structural_ok"],
                            structural_percent=metrics["structural_percent"],
                            supported_by_en=metrics["supported_by_en"],
                            review_records=metrics["review_records"],
                            api_calls=calls, cached_jobs=cached, errors=errors,
                            valid_records=0)
                        status.event(
                            "%s: %d refs; %.1f%% structure; EN %d; review %d" %
                            (stem, metrics["references"], metrics["structural_percent"],
                             metrics["supported_by_en"], metrics["review_records"])
                        )
    if args.prepare_only:
        print("PREPARE ONLY; API 0; SQL 0", flush=True)
        return 0

    comparison, metrics = summarize(rows, en, catalog, done, total, calls, cached, errors)
    metrics["pages_requested"] = [args.start, args.end]
    metrics["failures"] = failures
    save(OUT / "all_records.json", rows)
    save(OUT / "comparison.json", comparison)
    save(OUT / "review_queue.json",
         [r for r in comparison if r.get("review_status") == "REVIEW"])
    save(OUT / "summary.json", metrics)
    print("\nFINAL SUMMARY\n" + json.dumps(metrics, ensure_ascii=False, indent=2),
          flush=True)
    print("\nSAMPLE REFERENCES", flush=True)
    for r in comparison[:18]:
        print("%s  %-26s %s" %
              (r["id"], r.get("literal", ""), r.get("review_status", "")),
              flush=True)
    if status:
        status.finish(
            "warning" if errors else "completed",
            "FR1988 pages %d-%d: %d refs; structure %.1f%%; EN %d; review %d; errors %d" %
            (args.start, args.end, metrics["references"],
             metrics["structural_percent"], metrics["supported_by_en"],
             metrics["review_records"], errors)
        )
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main())
