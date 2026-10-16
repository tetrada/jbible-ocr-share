#!/usr/bin/env python3
"""Offline tests for shared authenticated review server's source-link extension.

Does not access scans, passwords, running HTTP server, Git or SQL.
"""
import json
from fr88_review_web_server import link_cases_from_export, validate_link_review


def test():
    target=lambda ix,book,v: {
        "row_id":"fr88v2:p0032:R:%02d"%ix,
        "image_page":32,"side":"R","margin_y_fraction":0.25,
        "margin_raw_line":"Qo 3 11; 7 2" if ix==3 else "Ps 104 24",
        "target_segment_index":v,
        "target":{"book_code":book,"chapter":3,"verse":11,"status":"PARSED"},
        "source":{"source_book_code":"Gen","source_chapter":1,
                  "source_verse":31,"source_marker_y_fraction":0.22,
                  "scope":"VERSE","source_book_evidence":"HEADER_VISIBLE"},
        "state":"PROPOSED_REVIEW_REQUIRED","source_reason":"PROPOSED_NEEDS_HUMAN_REVIEW",
        "target_reason":"OCR_TARGET_NOT_SCAN_VERIFIED",
    }
    doc={
        "progress":{"margins_complete":20},
        "proposed_links":[target(3,"Eccl",1),target(3,"Eccl",2),target(2,"Ps",1)],
        "review_queue":[{
           **target(4,"1Cor",1),
           "state":"NEEDS_REVIEW","source_reason":"SOURCE_BOOK_NOT_PRINTED"
        }],
        "source_book_context_suggestions":[{
           "margin_row_id":"fr88v2:p0032:R:04",
           "suggested_source_book_code":"Gen",
           "evidence_pages":[{"near_page":32,"book_code":"Gen"}]
        }]
    }
    grouped=link_cases_from_export(doc)
    assert len(grouped)==3
    assert grouped[0]["row_id"]=="fr88v2:p0032:R:02"
    pair=next(c for c in grouped if c["row_id"]=="fr88v2:p0032:R:03")
    assert len(pair["targets"])==2
    cases={c["row_id"]:c for c in grouped}
    request={
        "row_id":pair["row_id"],
        "choice":"correct",
        "source":{"book_code":"Gen","source_book_basis":"PRINTED_THIS_PAGE",
                  "scope":"VERSE","chapter":1,"verse":31,
                  "end_chapter":None,"end_verse":None},
        "target_raw_line":"Qo 3 11; 7 2",
        "checked":{"source_verse":True,"target_print":True,"alignment":True},
        "notes":"Both main-text 31 and marginal reference visually checked"
    }
    accepted=validate_link_review(request,cases)
    assert accepted["scan_review_status"]=="VISUAL_LINK_REVIEW_CONFIRMED"
    assert accepted["sql_ready"] is False
    assert accepted["biblical_target_canonically_verified"] is False
    for change in (
        {"checked":{"source_verse":False,"target_print":True,"alignment":True}},
        {"source":dict(request["source"],book_code="")},
        {"source":dict(request["source"],source_book_basis="UNKNOWN")},
        {"source":dict(request["source"],chapter=None)},
        {"row_id":"fr88v2:p0099:L:01"},
        {"source":dict(request["source"],verse=None)},
    ):
        bad=dict(request,**change)
        try:
            validate_link_review(bad,cases)
        except ValueError:
            pass
        else:
            raise AssertionError("Accepted invalid link review: "+str(change))
    unknown=dict(request,choice="uncertain",checked={
        "source_verse":False,"target_print":True,"alignment":False})
    u=validate_link_review(unknown,cases)
    assert u["scan_review_status"]=="PENDING_REVIEW"
    assert u["checked"]["alignment"] is False
    reject=dict(request,choice="reject")
    r=validate_link_review(reject,cases)
    assert r["scan_review_status"]=="VISUAL_LINK_REJECTED"
    assert r["sql_writes"] is False
    print("PASS: one row per margin, multi-segment targets, separate decisions, scan checks, no SQL")


if __name__=="__main__":
    test()
