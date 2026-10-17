#!/usr/bin/env python3
"""Send the completed FR88 QA *sampling* milestone to TETRADA Status.

Read-only: no SQL, no reference edits, no image edits, no Git operations.
Uses the installed SDK bridge and the local, private .env.status.
"""
import os
import sys
from pathlib import Path

ROOT = Path("/opt/jbible/importer")
ENV = ROOT / ".env.status"

def main():
    if not ENV.is_file():
        print("STATUS NOT SENT: existing .env.status missing", file=sys.stderr)
        return 3
    for line in ENV.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("export "):
            s = s[7:].strip()
        key, sep, value = s.partition("=")
        if sep and key.strip() in ("TETRADA_STATUS_TOKEN", "TETRADA_STATUS_URL"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    if not os.environ.get("TETRADA_STATUS_TOKEN"):
        print("STATUS NOT SENT: token not configured", file=sys.stderr)
        return 3
    sys.path.insert(0, str(ROOT))
    try:
        from jbible_status_bridge import AsyncStatus
    except ImportError:
        print("STATUS NOT SENT: installed SDK bridge missing", file=sys.stderr)
        return 3
    status = AsyncStatus(
        title="FR88 independent accuracy review sample",
        language="fr",
        book="Genesis to 2 Chronicles",
        total=360,
        run_id="fr88_quality_sampling_20261017"
    )
    status.event("Started independent FR88 quality review sampling; no Bible accuracy asserted")
    status.update(
        message="Sampling complete: 300 random edges, 60 targeted edges, 59 page audits; awaiting scan review",
        phase="sampling_complete",
        processed=360,
        total=360,
        remaining=0,
        percent=100,
        valid_records=0,
        candidates=5452,
        exceptions=0,
        errors=0
    )
    status.event(
        "GitHub QA pack published for 469 images and 5452 draft links; 300 probability and 60 risk references; 59 pages for omissions check",
        level="success"
    )
    status.event("Actual exact verse accuracy still unknown; 0 references independently verified", level="warning")
    status.finish(
        "completed",
        "FR88 QA sampling pack published; human visual verification pending, no SQL writes"
    )
    print("STATUS SDK: QA sample milestone submitted (inspect status.tetrada.eu to confirm delivery)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
