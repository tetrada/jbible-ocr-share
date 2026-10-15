#!/usr/bin/env python3
"""Finalize FR 1988 v2 from saved OCR checkpoints.

- Requires exactly the expected page range to avoid accidental paid reruns.
- Repairs ONLY missing margin checkpoints, capped at three API calls/jobs.
- Re-interprets every original saved raw_line with the current local parser.
- Rebuilds summaries, JSON shards, review queue with original OCR untouched.
- No SQL writes or verification.
"""
import argparse
import http.client
import json
import os
import time
import urllib.error
from datetime import datetime, timezone

import fr88_v2_ocr as ocr

def missing_checkpoints(start, end):
    existing = ocr.collect_existing()
    missing = [
        (page, side)
        for page in range(start, end + 1)
        for side in ("L", "R")
        if "image_%04d_%s.result.json" % (page, side) not in existing
    ]
    return existing, missing

def repair_margin(page, side, api_key):
    stem = "image_%04d_%s" % (page, side)
    jpg = ocr.SOURCE / ("image_%04d.jpg" % page)
    photos = ocr.prepare_images(jpg, side)
    fingerprint = ocr.make_signature(page, side, photos)
    prov = ocr.OUTPUT / (stem + ".provider.json")
    cp = ocr.OUTPUT / (stem + ".result.json")
    attempts_used = 0
    if prov.exists():
        payload = json.loads(prov.read_text(encoding="utf-8"))
        if payload["signature"] != fingerprint:
            raise RuntimeError("Mismatch in saved provider: " + stem)
        response = payload["response"]
        print("REUSE SAVED PROVIDER " + stem, flush=True)
    else:
        # The initial run suffered from IncompleteRead; retry only those
        # missing margins and preserve every successful provider response.
        for retry in range(3):
            try:
                print("DEEPSEEK RETRY %s (#%d)" % (stem, retry + 1), flush=True)
                response, n = ocr.call_deepseek(api_key, photos, page, side)
                attempts_used += n
                ocr.save(prov, {"signature": fingerprint, "response": response,
                                "created_utc": datetime.now(timezone.utc).isoformat(),
                                "recovery": True})
                break
            except (http.client.IncompleteRead, ConnectionResetError,
                    urllib.error.URLError, TimeoutError) as err:
                attempts_used += 1
                print("TEMPORARY NETWORK ERROR %s: %s" % (stem, err), flush=True)
                if retry == 2:
                    raise
                time.sleep(5 * (retry + 1))
    rows, warnings = ocr.parse_provider(response, page, side)
    ocr.save(cp, {"signature": fingerprint, "page": page, "side": side,
                  "rows": rows, "warnings": warnings,
                  "api_usage": response.get("usage", {}),
                  "recovery": True, "verified": 0, "sql_writes": False})
    print("RECOVERED %s: %d OCR rows" % (stem, len(rows)), flush=True)
    return attempts_used

def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--start", type=int, default=32)
    cli.add_argument("--end", type=int, default=500)
    cli.add_argument("--repair-missing", action="store_true",
                     help="Use DeepSeek Flash only for missing margin checkpoints")
    cli.add_argument("--max-missing", type=int, default=3)
    args = cli.parse_args()
    if args.start < 1 or args.end < args.start:
        cli.error("Invalid page range")
    if not ocr.CATALOG.is_file():
        cli.error("Missing catalog " + str(ocr.CATALOG))
    print(ocr.normalizer_test(str(ocr.CATALOG)), flush=True)

    old_summary_file = ocr.OUTPUT / "summary.json"
    previous = (json.loads(old_summary_file.read_text(encoding="utf-8"))
                if old_summary_file.is_file() else {})
    existing, missing = missing_checkpoints(args.start, args.end)
    print("EXISTING: %d margins; MISSING: %s" % (len(existing), missing), flush=True)

    if missing and not args.repair_missing:
        cli.error("Missing checkpoints; rerun with --repair-missing")
    if len(missing) > args.max_missing:
        cli.error("Missing %d margins; cap is %d. Stop to inspect before spending."
                  % (len(missing), args.max_missing))
    new_calls = 0
    if missing:
        key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not key:
            cli.error("DEEPSEEK_API_KEY needed for missing margin repair")
        for page, side in missing:
            new_calls += repair_margin(page, side, key)

    existing, still_missing = missing_checkpoints(args.start, args.end)
    if still_missing:
        raise RuntimeError("Unrecovered margins: %s" % still_missing)
    expected = 2 * (args.end - args.start + 1)
    if len(existing) != expected:
        raise RuntimeError("Unexpected checkpoint count: %d, expected %d" %
                           (len(existing), expected))

    run = {
        "requested_pages": [args.start, args.end],
        "margins_in_run": expected,
        "margins_total": expected,
        "api_calls": int(previous.get("api_calls", 0)) + new_calls,
        "recovery_api_calls": new_calls,
        "cached_jobs": expected - len(missing),
        "errors": 0,
        "failures": [],
        "recovered_failures": previous.get("failures", []),
        "ocr_margins_success": expected,
        "ocr_margin_success_percent": 100.0,
        "last_update_utc": datetime.now(timezone.utc).isoformat(),
        "verified": 0,
        "sql_writes": False,
    }
    summary = ocr.write_aggregates(existing, run)
    print("\nFINAL VERIFIED-PROCESSING SUMMARY (NOT BIBLE VERIFICATION)\n"
          + json.dumps({
              "pages": [args.start, args.end],
              "complete_margins": summary["checkpoint_margins"],
              "ocr_rows": summary["ocr_rows"],
              "reference_rows": summary["reference_rows"],
              "segments_total": summary["segments_total"],
              "parsed_segments": summary["parsed_segments"],
              "parse_success_percent": summary["parse_success_percent"],
              "interpretation_review": summary["interpretation_review"],
              "source_anchor_missing": summary["source_anchor_missing"],
              "recovery_api_calls": new_calls,
              "missing_after_repair": still_missing,
              "verified": 0, "sql_writes": False,
            }, ensure_ascii=False, indent=2), flush=True)
    print("\nSaved: " + str(ocr.OUTPUT / "summary.json"), flush=True)
    print("All original OCR checkpoints remain unchanged except newly recovered margins.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
