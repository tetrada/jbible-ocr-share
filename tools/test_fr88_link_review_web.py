#!/usr/bin/env python3
"""Offline test: every destination is its OWN reviewable source-to-target edge.

Does not access scanned pages, passwords, DeepSeek, SQL, or the live server.
"""
from fr88_link_edges import build_cases, validate_decision, index_pages
from fr88_review_web_server import Handler


def test():
    rid="fr88v2:p0032:R:03"
    def entry(ix,vers):
        return {
            "row_id":rid,"image_page":32,"side":"R","margin_y_fraction":0.19,
            "margin_raw_line":"Ps 78 47s; 105 32; Ap 16 21",
            "target_segment_index":ix,
            "target":{"book_code":"Ps" if ix<3 else "Rev","book_printed":"Ps" if ix<3 else "Ap",
                      "chapter":78 if ix==1 else 105 if ix==2 else 16,
                      "verse":vers,"literal":"78 47s" if ix==1 else "105 32" if ix==2 else "16 21",
                      "status":"PARSED"},
            "source":{"scope":"VERSE","source_chapter":1,"source_verse":3,
                      "source_book_code":None,"source_book_evidence":"NOT_VISIBLE",
                      "source_marker_y_fraction":0.17,"verse_marker_visible":True},
            "state":"NEEDS_REVIEW","source_reason":"SOURCE_BOOK_NOT_PRINTED",
            "target_reason":"OCR_TARGET_NOT_SCAN_VERIFIED"
        }
    export={
        "progress":{"pages":[31,40],"margins_complete":20},
        "proposed_links":[],
        "review_queue":[entry(1,47),entry(2,32),entry(3,21)]
    }
    reg={
        "schema":"jbible.fr88.page-book-registry.v1",
        "page_ranges":[{"first_page":31,"last_page":40,"book_code":"Gen"}],
        "single_pages":[{"page":102,"book_code":"Exod",
                         "page_start_chapter":16,"page_start_verse":21}]
    }
    index=index_pages(reg)
    assert index[40]["source_book_code"]=="Gen"
    assert index[102]["source_book_code"]=="Exod"
    assert index[102]["page_start_chapter"]==16 and index[102]["page_start_verse"]==21
    edges=build_cases(export,reg)
    assert len(edges)==3, "One physical line with 3 references must create 3 edges"
    assert len({e["link_id"] for e in edges})==3
    assert len({e["row_id"] for e in edges})==1
    assert all(e["book_for_review"]=="Gen" for e in edges)
    assert [e["target_printed"] for e in edges]==["Ps 78 47s","Ps 105 32","Ap 16 21"]
    assert all(e["verified"] is False and e["sql_ready"] is False for e in edges)
    cases={e["link_id"]:e for e in edges}
    first=edges[0]
    payload={
        "link_id":first["link_id"],"row_id":rid,
        "target_segment_index":1,"choice":"confirm",
        "source":{"book_code":"Gen","source_book_basis":"PAGE_REGISTRY",
                  "scope":"VERSE","chapter":1,"verse":3,
                  "end_chapter":None,"end_verse":None},
        "target_printed":"Ps 78 47s",
        "checked":{"page_book":True,"source_marker":True,
                   "target_print":True,"alignment":True},
        "notes":"Checked printed source and printed destination"
    }
    decision=validate_decision(payload,cases)
    assert decision["scan_review_status"]=="VISUAL_EDGE_CONFIRMED"
    assert decision["canonical_target_verified"] is False
    assert decision["sql_ready"] is False
    assert decision["target_segment_index"]==1
    assert decision["target_printed"]=="Ps 78 47s"
    for altered in (
        {"checked":dict(payload["checked"],alignment=False)},
        {"checked":dict(payload["checked"],page_book=False)},
        {"source":dict(payload["source"],book_code="")},
        {"source":dict(payload["source"],verse=None)},
        {"target_segment_index":2},
        {"link_id":"fr88v2:p9999:R:01/target01"}
    ):
        try:
            validate_decision(dict(payload,**altered),cases)
        except ValueError:
            pass
        else:
            raise AssertionError("Allowed invalid link decision: "+str(altered))
    uncertain=dict(payload,choice="uncertain",checked={
        "page_book":False,"source_marker":False,
        "target_print":True,"alignment":False})
    assert validate_decision(uncertain,cases)["scan_review_status"]=="PENDING"
    clipped=dict(entry(1,47),target_reason="CUT_OFF_TARGET_FROM_HUMAN_REVIEW")
    export["review_queue"]=[clipped]
    clipped_cases={c["link_id"]:c for c in build_cases(export,reg)}
    try:
        validate_decision(payload,clipped_cases)
    except ValueError:
        pass
    else:
        raise AssertionError("Confirmed an incomplete cut-off target")
    assert hasattr(Handler,"do_GET") and hasattr(Handler,"do_POST")
    print("PASS: 1 printed line => 3 independent 1:1 edge reviews; Genesis page map, page 102 Exodus, no SQL")


if __name__=="__main__":
    test()
