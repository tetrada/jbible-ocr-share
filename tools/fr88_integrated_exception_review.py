#!/usr/bin/env python3
"""Read-only integrated OCR exception queue + scan-grounded human decisions.

Each exception is ONE destination edge; the original full printed margin row
remains visible. Original images and DeepSeek provider responses stay on VPS.
Human decisions do not write SQL or alter the automatic accepted link dataset.
"""
import re
from datetime import datetime, timezone

EDGE=re.compile(r"^(?:fr88i:p\d{4}:[LR]:\d{3}/target\d{2}|fr88:p\d{4}:ref\d{3})$")
BOOK=re.compile(r"^[A-Za-z0-9]{1,12}$")
CHOICES=("as_printed","corrected","cut_off","unresolved")
CAUSES=("CATALOG_REJECTED_VALID_REFERENCE",
        "SOURCE_VERSE_BEFORE_FIRST_MARKER",
        "MARGINAL_OCR_ERROR",
        "MARGIN_ACTUALLY_CUT_OFF",
        "SOURCE_VERSE_POSITION_ERROR",
        "BOOK_ABBREVIATION_ERROR",
        "UNUSUAL_PRINTED_NOTATION",
        "OTHER_OR_UNKNOWN")
TYPES=("VERSE","VERSE_RANGE","CHAPTER_ONLY","CHAPTER_RANGE","UNKNOWN")


def cases_from_report(report):
    if not isinstance(report,dict) or report.get("schema")!="jbible.fr88.integrated-page-git-report.v1":
        raise ValueError("Wrong integrated page OCR report format")
    cases=[]
    seen=set()
    for page in report.get("pages",[]):
        p=page.get("image_page")
        if type(p) is not int or p<1 or p>3000:
            raise ValueError("Bad exception image page")
        for e in page.get("source_to_destination_edges",[]):
            if e.get("status")!="EXCEPTION":
                continue
            eid=e.get("edge_id")
            if not isinstance(eid,str) or not EDGE.fullmatch(eid) or eid in seen:
                raise ValueError("Duplicate or malformed exception edge ID")
            seen.add(eid)
            cases.append({
                "edge_id":eid,"page":p,
                "column":e.get("column"),
                "margin_y_fraction":e.get("margin_y_fraction"),
                "margin_text":str(e.get("printed_margin_line") or "")[:400],
                "target_index":e.get("target_segment_index"),
                "source_book":e.get("source_book_code"),
                "source_chapter":e.get("source_chapter"),
                "source_verse":e.get("source_verse"),
                "source_y_interval":e.get("source_y_interval"),
                "destination_book":e.get("target_book_code"),
                "destination_chapter":e.get("target_chapter"),
                "destination_verse":e.get("target_verse"),
                "destination_end_chapter":e.get("target_end_chapter"),
                "destination_end_verse":e.get("target_end_verse"),
                "destination_type":e.get("target_type"),
                "destination_suffix":e.get("target_suffix"),
                "destination_literal":e.get("target_literal"),
                "reason_codes":e.get("hard_exceptions") or [],
                "other_notes":e.get("qa_reasons") or [],
                "source_book_context":page.get("page_book"),
                "running_head":page.get("running_head"),
                "human_verified":False,
                "sql_writes":False
            })
    return sorted(cases,key=lambda c:(c["page"],c["column"] or "",c["margin_y_fraction"] if
        type(c["margin_y_fraction"]) in (int,float) else 2,c["target_index"] or 0))


def integer_or_none(val,name):
    if val is None or val=="":
        return None
    if type(val) is not int or val<1 or val>2000:
        raise ValueError("Invalid "+name)
    return val


def source_target(body,name):
    coord=body.get(name)
    if not isinstance(coord,dict):
        raise ValueError("Missing "+name+" coordinates")
    code=coord.get("book_code")
    if code is None: code=""
    if not isinstance(code,str) or code and not BOOK.fullmatch(code):
        raise ValueError("Invalid "+name+" book code")
    out={"book_code":code or None}
    for field in ("chapter","verse","end_chapter","end_verse"):
        out[field]=integer_or_none(coord.get(field),name+" "+field)
    if name=="destination":
        typ=coord.get("type") or "UNKNOWN"
        if typ not in TYPES:
            raise ValueError("Invalid destination reference type")
        out["type"]=typ
        suffix=coord.get("suffix") or ""
        if not isinstance(suffix,str) or len(suffix)>30:
            raise ValueError("Invalid destination suffix")
        out["suffix"]=suffix
    return out


def validate_decision(body,cases):
    if not isinstance(body,dict):
        raise ValueError("Expected JSON review object")
    eid=body.get("edge_id")
    if eid not in cases:
        raise ValueError("Unknown integrated exception")
    choice=body.get("choice")
    if choice not in CHOICES:
        raise ValueError("Select as printed, corrected, cut off or unresolved")
    cause=body.get("cause")
    if cause not in CAUSES:
        raise ValueError("Choose the reason for the exception")
    src=source_target(body,"source")
    dst=source_target(body,"destination")
    checked=body.get("checked_original_scan") is True
    if choice in ("as_printed","corrected"):
        if not checked:
            raise ValueError("Check the original scan before accepting/correcting")
        if (not src["book_code"] or not src["chapter"] or not src["verse"] or
            not dst["book_code"] or not dst["chapter"]):
            raise ValueError("Accepted link requires a complete source and destination book/chapter")
        if dst["type"] in ("VERSE","VERSE_RANGE") and not dst["verse"]:
            raise ValueError("Verse-level destination needs a verse number")
        if dst["type"]=="VERSE_RANGE" and not dst["end_verse"]:
            raise ValueError("Verse range needs an end verse")
        if dst["type"]=="UNKNOWN":
            raise ValueError("Choose the correct destination type before accepting")
    if choice=="cut_off" and not checked:
        raise ValueError("Confirm cut-off against the scanned page")
    notes=body.get("notes") or ""
    if not isinstance(notes,str) or len(notes)>1200:
        raise ValueError("Review note too long")
    original=cases[eid]
    return {
        "edge_id":eid,"image_page":original["page"],
        "choice":choice,"cause":cause,
        "source":src,"destination":dst,
        "checked_original_scan":checked,
        "original_margin_text":original["margin_text"],
        "original_exception_reasons":original["reason_codes"],
        "human_review_status":(
            "SCAN_CONFIRMED_LINK" if choice in ("as_printed","corrected")
            else "SCAN_CONFIRMED_CUT_OFF" if choice=="cut_off"
            else "UNRESOLVED"),
        "notes":notes.strip(),
        "sql_ready":False,"sql_writes":False,
        "reviewed_utc":datetime.now(timezone.utc).isoformat()
    }


def curated_qa_cases(manifest):
    """Three explicitly curated FR88 draft-reference ambiguities for private scan review.

    Separate provenance/IDs from the integrated OCR edges. Read-only manifest.
    Never promote catalog failures, estimated verse shifts or cutoff claims to
    verified links merely because they appear here.
    """
    if (not isinstance(manifest, dict) or
            manifest.get("schema") != "jbible.fr88.curated-unresolved-qa.v1" or
            manifest.get("sql_writes") is not False):
        raise ValueError("Invalid curated QA manifest")
    raw = manifest.get("cases")
    if not isinstance(raw, list) or len(raw) != manifest.get("expected_case_count"):
        raise ValueError("Curated QA count mismatch")
    out = []
    seen = set()
    for c in raw:
        eid = c.get("edge_id")
        page = c.get("page")
        side = c.get("column")
        if (not isinstance(eid, str) or
                not re.fullmatch(r"fr88:p\d{4}:ref\d{3}", eid) or
                type(page) is not int or page < 31 or page > 500 or
                "p%04d:" % page not in eid or side not in ("L", "R") or
                eid in seen):
            raise ValueError("Bad curated QA edge identity")
        seen.add(eid)
        y = c.get("margin_y_fraction")
        if type(y) not in (float, int) or not 0 <= y <= 1:
            raise ValueError("Invalid curated margin marker")
        reasons = c.get("reason_codes")
        if not isinstance(reasons, list) or not reasons or not all(
                isinstance(x, str) and 0 < len(x) < 100 for x in reasons):
            raise ValueError("Missing specific QA reason")
        out.append({
            "edge_id": eid,
            "page": page,
            "column": side,
            "margin_y_fraction": y,
            "margin_text": str(c.get("margin_text") or "")[:400],
            "target_index": 1,
            "source_book": c.get("source_book"),
            "source_chapter": c.get("source_chapter"),
            "source_verse": c.get("source_verse"),
            "source_y_interval": None,
            "destination_book": c.get("destination_book"),
            "destination_chapter": c.get("destination_chapter"),
            "destination_verse": c.get("destination_verse"),
            "destination_end_chapter": c.get("destination_end_chapter"),
            "destination_end_verse": c.get("destination_end_verse"),
            "destination_type": c.get("destination_type") or "UNKNOWN",
            "destination_suffix": "",
            "destination_literal": c.get("destination_literal") or "",
            "reason_codes": reasons,
            "other_notes": [],
            "source_book_context": {"book_code": c.get("source_book")},
            "running_head": {},
            "review_hint": str(c.get("review_hint") or "")[:450],
            "source_ref": str(c.get("source_ref") or "")[:200],
            "curated_focus": True,
            "human_verified": False,
            "sql_writes": False
        })
    return out


def focused_cases(integrated_report, manifest):
    """Preserve unmodified integrated cases; add a distinct curated QA focus."""
    combined = curated_qa_cases(manifest) + cases_from_report(integrated_report)
    ids = [c["edge_id"] for c in combined]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate edge ID across integrated and focused QA")
    return combined
