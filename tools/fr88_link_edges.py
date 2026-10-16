#!/usr/bin/env python3
"""Source -> TARGET edges for the French 1988 JBible.

One separately parsed target citation == one link record. Marginal OCR rows are
just physical provenance; a row containing three targets yields three edges.
Book identity is PAGE metadata, not a per-margin model visibility requirement.
No source/target relation is automatically verified or ready for SQL.
"""
import re
from datetime import datetime, timezone

RID_RE=re.compile(r"^fr88v2:p\d{4}:[LR]:\d{2,3}$")
SCOPES=("VERSE","PASSAGE","CHAPTER","UNKNOWN")
BOOK_BASES=("PRINTED_THIS_PAGE","PAGE_REGISTRY","NEIGHBORING_PAGE",
            "VISUALLY_CHECKED_CONTINUATION","UNKNOWN")
CHOICES=("confirm","correct","uncertain","reject")


def index_pages(registry):
    if not isinstance(registry,dict) or registry.get("schema")!="jbible.fr88.page-book-registry.v1":
        raise ValueError("Invalid page book registry")
    result={}
    for entry in registry.get("page_ranges",[]):
        lo,hi=entry.get("first_page"),entry.get("last_page")
        if type(lo) is not int or type(hi) is not int or not 1<=lo<=hi<=3000:
            raise ValueError("Invalid registered range")
        for page in range(lo,hi+1):
            if page in result:
                raise ValueError("Overlapping book ranges")
            result[page]={
                "source_book_code":entry["book_code"],
                "page_start_chapter":entry.get("page_start_chapter"),
                "page_start_verse":entry.get("page_start_verse"),
                "page_book_basis":entry.get("basis"),
                "human_checked_header":entry.get("human_checked_page_range") is True
            }
    for entry in registry.get("single_pages",[]):
        page=entry.get("page")
        if type(page) is not int or page<=0 or page>3000 or page in result:
            raise ValueError("Invalid or overlapping single page")
        result[page]={
            "source_book_code":entry["book_code"],
            "page_start_chapter":entry.get("page_start_chapter"),
            "page_start_verse":entry.get("page_start_verse"),
            "page_book_basis":entry.get("basis"),
            "human_checked_header":entry.get("human_checked_header") is True
        }
    return result


def target_label(target):
    """Human-readable target preserving source's within-line inherited book."""
    if not isinstance(target,dict):
        return "Unparsed citation"
    literal=str(target.get("literal") or "").strip()
    printed=str(target.get("book_printed") or "").strip()
    if printed and literal:
        return printed + " " + literal
    return literal or "Unparsed citation"


def build_cases(export,registry):
    if not isinstance(export,dict) or not isinstance(export.get("progress"),dict):
        raise ValueError("Missing source-link results")
    known_pages=index_pages(registry)
    edges={}
    for field in ("proposed_links","review_queue"):
        items=export.get(field,[])
        if not isinstance(items,list):
            raise ValueError("Invalid link result list")
        for item in items:
            if not isinstance(item,dict):
                continue
            row_id=item.get("row_id")
            page,side=item.get("image_page"),item.get("side")
            idx=item.get("target_segment_index")
            if (not isinstance(row_id,str) or not RID_RE.fullmatch(row_id) or
                type(page) is not int or not 1<=page<=3000 or side not in ("L","R")
                or type(idx) is not int or not 1<=idx<=99):
                continue
            link_id=row_id+"/target%02d"%idx
            if link_id in edges:
                raise ValueError("Duplicate source-target edge identifier "+link_id)
            target=item.get("target") or {}
            source=item.get("source") or {}
            page_context=known_pages.get(page)
            model_book=source.get("source_book_code")
            book_conflict=(page_context is not None and
                           model_book not in (None,page_context["source_book_code"]))
            edges[link_id]={
                "link_id":link_id,"row_id":row_id,
                "target_segment_index":idx,
                "page":page,"side":side,
                "y_fraction":item.get("margin_y_fraction"),
                "margin_raw_line":str(item.get("margin_raw_line") or "")[:400],
                "target_printed":target_label(target),
                "target":target,
                "source":source,
                "page_context":page_context,
                "page_model_book_conflict":book_conflict,
                "book_for_review":(
                    model_book if book_conflict else
                    page_context["source_book_code"] if page_context else model_book
                ),
                "source_reason":item.get("source_reason"),
                "target_reason":item.get("target_reason"),
                "state":item.get("state","NEEDS_REVIEW"),
                "verified":False,"sql_ready":False,
                "review_scope":"ONE_SOURCE_TO_ONE_TARGET"
            }
    return sorted(edges.values(),key=lambda x:(
        0 if x["state"]=="PROPOSED_REVIEW_REQUIRED" else 1,
        x["page"],x["side"],
        x["y_fraction"] if type(x["y_fraction"]) in (int,float) else 2,
        x["target_segment_index"]
    ))


def validate_decision(body,cases):
    if not isinstance(body,dict):
        raise ValueError("Invalid review input")
    lid=body.get("link_id")
    if not isinstance(lid,str) or lid not in cases:
        raise ValueError("Unknown source-target edge")
    case=cases[lid]
    if body.get("row_id")!=case["row_id"]:
        raise ValueError("Marginal row ID mismatch")
    if body.get("target_segment_index")!=case["target_segment_index"]:
        raise ValueError("Target segment index mismatch")
    choice=body.get("choice")
    if choice not in CHOICES:
        raise ValueError("Select Confirm, Corrected, Uncertain or Reject")
    source=body.get("source")
    if not isinstance(source,dict):
        raise ValueError("Invalid source fields")
    scope=source.get("scope","UNKNOWN")
    basis=source.get("source_book_basis","UNKNOWN")
    if scope not in SCOPES or basis not in BOOK_BASES:
        raise ValueError("Invalid source scope/book evidence")
    book=source.get("book_code")
    if book is None:
        book=""
    if not isinstance(book,str) or (book and not re.fullmatch("[A-Za-z0-9]{1,12}",book)):
        raise ValueError("Invalid source book code")
    nums={}
    for name in ("chapter","verse","end_chapter","end_verse"):
        v=source.get(name)
        if v is None or v=="":
            nums[name]=None
        elif type(v) is int and 1<=v<=2000:
            nums[name]=v
        else:
            raise ValueError("Invalid source "+name)
    printed=body.get("target_printed")
    if not isinstance(printed,str) or not printed.strip() or len(printed)>300:
        raise ValueError("Enter this one printed destination reference")
    notes=body.get("notes") or ""
    if not isinstance(notes,str) or len(notes)>1500:
        raise ValueError("Notes are too long")
    check=body.get("checked")
    if not isinstance(check,dict):
        raise ValueError("Missing scan checks")
    checked={name:check.get(name) is True for name in (
        "source_marker","target_print","alignment","page_book")}
    if choice in ("confirm","correct"):
        if not all(checked.values()):
            raise ValueError("Check the page book, source marker, target print and alignment")
        if not book or basis=="UNKNOWN" or not nums["chapter"] or scope=="UNKNOWN":
            raise ValueError("Confirmed connections need a known source book/chapter/scope")
        if scope in ("VERSE","PASSAGE") and nums["verse"] is None:
            raise ValueError("Confirmed verse/passage must have a source verse")
        if scope=="PASSAGE" and nums["end_verse"] is None:
            raise ValueError("Confirmed passage needs an end verse")
        if case["page_model_book_conflict"] and basis=="PAGE_REGISTRY":
            raise ValueError("Book conflict: inspect the scan, use checked continuity evidence")
        if case["target_reason"]=="CUT_OFF_TARGET_FROM_HUMAN_REVIEW":
            raise ValueError("Cut-off targets cannot be confirmed as complete references")
    return {
        "link_id":lid,"row_id":case["row_id"],
        "target_segment_index":case["target_segment_index"],
        "choice":choice,
        "source":{"book_code":book or None,"source_book_basis":basis,
                  "scope":scope,**nums},
        "target_printed":printed.strip(),
        "original_margin_raw_line":case["margin_raw_line"],
        "checked":checked,
        "scan_review_status":(
            "VISUAL_EDGE_CONFIRMED" if choice in ("confirm","correct")
            else "VISUAL_EDGE_REJECTED" if choice=="reject" else "PENDING"),
        "canonical_target_verified":False,
        "sql_ready":False,"sql_writes":False,
        "notes":notes.strip(),
        "saved_at_utc":datetime.now(timezone.utc).isoformat()
    }
