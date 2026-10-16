#!/usr/bin/env python3
"""Conservative, OFFLINE page-neighbor source-book suggestions for JBible FR88.

When DeepSeek sees a main-text verse marker but no book name printed on that
particular half-page, propose a book only from a visibly printed book header on
this page or one adjacent scanned page. NEVER mark as human-verified.

No API calls, no fabricated verse/chapter numbers, no SQL writes.
"""
from collections import defaultdict

ALLOWED_EVIDENCE=("HEADER_VISIBLE","CHAPTER_TITLE_VISIBLE")
SUGGESTION_SCHEMA="jbible.fr88.source-book-context.suggestions.v1"


def visible_headers(assignments):
    """Find explicit book-header evidence from completed margin assignments."""
    headers=defaultdict(set)
    chapters=defaultdict(set)
    for group in assignments:
        page=group.get("page")
        if type(page) is not int:
            continue
        for a in group.get("assignments",[]):
            if not isinstance(a,dict):
                continue
            code=a.get("source_book_code")
            if (a.get("source_book_evidence") not in ALLOWED_EVIDENCE
                    or not isinstance(code,str) or not code):
                continue
            headers[page].add(code)
            ch=a.get("source_chapter")
            if type(ch) is int and ch>0:
                chapters[page,code].add(ch)
    return headers,chapters


def suggest_unknown_book(groups, source_catalog):
    """Suggest context, not new source facts. Each suggestion still NEEDS_REVIEW."""
    headers,chapters=visible_headers(groups)
    output=[]
    for group in groups:
        page=group.get("page")
        side=group.get("side")
        if type(page) is not int:
            continue
        for anchor in group.get("assignments",[]):
            if not isinstance(anchor,dict):
                continue
            if anchor.get("source_book_code"):
                continue
            ch=anchor.get("source_chapter")
            v=anchor.get("source_verse")
            if not (type(ch) is int and ch>=1 and type(v) is int and v>=1 and
                    anchor.get("verse_marker_visible") is True):
                continue
            if anchor.get("source_book_evidence")!="NOT_VISIBLE":
                continue
            evidence=[]
            for distant_page in (page,page-1,page+1):
                codes=headers.get(distant_page,set())
                if len(codes)!=1:
                    continue
                code=next(iter(codes))
                if not (0 < v <= source_catalog.get((code,ch),0)):
                    continue
                # Never propagate across an obvious chapter jump.
                seen_chapters=chapters.get((distant_page,code),set())
                if not seen_chapters or min(abs(ch-c) for c in seen_chapters)>1:
                    continue
                evidence.append({"near_page":distant_page,
                                 "book_code":code,
                                 "printed_header_evidence":True,
                                 "distance_pages":abs(distant_page-page),
                                 "neighbor_visible_chapters":sorted(seen_chapters)})
            names={x["book_code"] for x in evidence}
            if len(names)!=1:
                continue
            code=next(iter(names))
            # A page immediately adjacent may actually start a different book.
            # This is ONLY a suggestion in a separate review field, never a
            # rewrite of anchor.source_book_code or a verified link.
            output.append({
                "margin_row_id":anchor["margin_row_id"],
                "image_page":page,"side":side,
                "observed_chapter":ch,"observed_verse":v,
                "suggested_source_book_code":code,
                "evidence_pages":evidence,
                "suggestion_status":"ADJACENT_PRINTED_HEADER_CONTEXT_UNVERIFIED",
                "review_required":True,
                "source_verse_verified":False,
                "link_authorized":False,
                "warning":"A nearby page's visible header may describe a different book; manually verify the transition."
            })
    return {"schema":SUGGESTION_SCHEMA,
            "suggestions":output,
            "automatically_verified_links":0,
            "sql_writes":False,
            "api_calls":0}
