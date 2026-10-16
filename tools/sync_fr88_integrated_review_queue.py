#!/usr/bin/env python3
"""Sync the protected JBible exception-review queue from the latest Git publication.

The original scan viewer and saved human decisions are NEVER modified. This
script replaces ONLY the local *data snapshot* read by the existing web app.
No OCR, model calls, SQL, remote scan exposure, or service restart.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

APP=Path("/opt/jbible/review-web")
SRC=Path("/opt/jbible/ocr-share-git/fr88_integrated_v1/pilot_report.json")
DST=APP/"integrated_report.json"
ENV=Path("/opt/jbible/importer/.env.status")
SCHEMA="jbible.fr88.integrated-page-git-report.v1"

def portal_log(message, page_bundles, exceptions):
    """Best-effort official SDK event, without logging tokens or private text."""
    if ENV.is_file():
        for raw in ENV.read_text(encoding="utf-8").splitlines():
            line=raw.strip()
            if line.startswith("export "):
                line=line[7:].strip()
            key,sep,val=line.partition("=")
            if sep and key.strip() in ("TETRADA_STATUS_TOKEN","TETRADA_STATUS_URL"):
                os.environ.setdefault(key.strip(),val.strip().strip("\"'"))
    if not os.environ.get("TETRADA_STATUS_TOKEN"):
        print("[STATUS] Portal token missing, data refresh still succeeded",flush=True)
        return
    try:
        sys.path.insert(0,"/opt/jbible/importer")
        from status_sdk.tetrada_status import StatusClient
        client=StatusClient(entity="jbible/importer/review_queue",
            name="Integrated OCR Exception Review Queue",
            kind="service",parent="jbible/importer",stale_after=2592000,
            heartbeat_interval=0,timeout=3,strict=False)
        payload={"pages_bundled":page_bundles,"exceptions":exceptions}
        response=client.publish(status="online",metrics=payload,message=message,
            widgets=[{"type":"metric","title":"Pages published","metric":"pages_bundled"},
                     {"type":"metric","title":"Unresolved exceptions","metric":"exceptions"},
                     {"type":"events","title":"Review queue updates"}])
        if response is not None:
            client.log(message,level="info")
        else:
            print("[STATUS] Delivery unavailable; local review snapshot is current",flush=True)
    except Exception as exc:
        print("[STATUS] Delivery exception category: "+type(exc).__name__,flush=True)

def main():
    if not SRC.is_file():
        print("REVIEW QUEUE: No published OCR report in local Git checkout",flush=True)
        return 1
    if not (APP/"server.py").is_file() or not (APP/"fr88_integrated_exception_review.py").is_file():
        print("REVIEW QUEUE: Existing integrated exception-review app not installed",flush=True)
        return 1
    if not (APP/"password").is_file():
        print("REVIEW QUEUE: Reviewer password file missing; refusing deployment",flush=True)
        return 1
    raw=SRC.read_bytes()
    doc=json.loads(raw)
    if doc.get("schema")!=SCHEMA or not isinstance(doc.get("pages"),list):
        print("REVIEW QUEUE: Unexpected OCR report schema",flush=True)
        return 1
    progress=doc.get("progress") or {}
    if progress.get("pages_bundled")!=len(doc["pages"]):
        print("REVIEW QUEUE: Published report and progress disagree; skipping sync",flush=True)
        return 1
    if doc.get("sql_writes") is not False:
        print("REVIEW QUEUE: SQL-write claim mismatch; skipping sync",flush=True)
        return 1
    # Reuse the exact existing validation/parser class that drives the site.
    source=APP/"fr88_integrated_exception_review.py"
    spec=importlib.util.spec_from_file_location("jbible_integrated_exception_review",str(source))
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cases=mod.cases_from_report(doc)
    actual=len(cases)
    expected=(progress.get("source_link_metrics") or {}).get("exceptions")
    if type(expected) is not int or actual!=expected:
        print("REVIEW QUEUE: Exception count mismatch: %d != %r"%(actual,expected),flush=True)
        return 1
    # Keep original reviewed cases, no matter how many new pages are added.
    if DST.is_file() and hashlib.sha256(DST.read_bytes()).digest()==hashlib.sha256(raw).digest():
        print("REVIEW QUEUE: Already current (%d pages, %d exceptions)"%
              (len(doc["pages"]),actual),flush=True)
        return 0
    fd,tmp=tempfile.mkstemp(prefix=".integrated_report.",suffix=".tmp",dir=str(APP))
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp,0o644)
        os.replace(tmp,str(DST))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    message="OCR exception review queue updated: %d pages, %d unresolved references"%(
        len(doc["pages"]),actual)
    print("REVIEW QUEUE: "+message,flush=True)
    portal_log(message,len(doc["pages"]),actual)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
