#!/usr/bin/env python3
"""Offline tests for per-destination integrated OCR exception reviewer.

No DeepSeek API, scan image, real user credentials, network, Git or SQL.
"""
from fr88_integrated_exception_review import cases_from_report, validate_decision


def test():
    edge={
        "edge_id":"fr88i:p0032:R:003/target01",
        "status":"EXCEPTION","column":"R","margin_y_fraction":0.32,
        "printed_margin_line":"Qo 3 11; 7 2",
        "target_segment_index":1,
        "source_book_code":"Gen","source_chapter":1,"source_verse":29,
        "source_y_interval":[0.31,0.36],
        "target_book_code":"Eccl","target_chapter":3,"target_verse":11,
        "target_type":"VERSE","target_suffix":"",
        "hard_exceptions":["MARGINAL_TEXT_NOT_FULLY_VISIBLE"]
    }
    second=dict(edge,edge_id="fr88i:p0032:R:003/target02",
                target_segment_index=2,target_chapter=7,target_verse=2)
    valid=dict(edge,edge_id="fr88i:p0032:R:004/target01",status="ACCEPTED")
    data={
        "schema":"jbible.fr88.integrated-page-git-report.v1",
        "pages":[{"image_page":32,"page_book":{"book_code":"Gen"},
                  "running_head":{"chapter":1,"verse":29},
                  "source_to_destination_edges":[edge,second,valid]}]
    }
    cases=cases_from_report(data)
    assert len(cases)==2
    assert cases[0]["edge_id"]!=cases[1]["edge_id"]
    assert cases[0]["margin_text"]==cases[1]["margin_text"]
    assert cases[0]["target_index"]==1 and cases[1]["target_index"]==2
    assert cases[0]["destination_book"]=="Eccl"
    index={c["edge_id"]:c for c in cases}
    body={
        "edge_id":cases[0]["edge_id"],
        "choice":"as_printed","cause":"CATALOG_REJECTED_VALID_REFERENCE",
        "source":{"book_code":"Gen","chapter":1,"verse":29},
        "destination":{"book_code":"Eccl","chapter":3,"verse":11,
                       "type":"VERSE","suffix":""},
        "checked_original_scan":True,
        "notes":"The reference is printed in full; catalog error"
    }
    review=validate_decision(body,index)
    assert review["human_review_status"]=="SCAN_CONFIRMED_LINK"
    assert review["source"]["verse"]==29
    assert review["destination"]["verse"]==11
    assert review["sql_ready"] is False and review["sql_writes"] is False
    assert review["original_margin_text"]=="Qo 3 11; 7 2"
    # One target can be corrected without changing its sibling.
    other=dict(body,edge_id=cases[1]["edge_id"],choice="corrected",
               destination=dict(body["destination"],chapter=7,verse=2))
    d2=validate_decision(other,index)
    assert d2["edge_id"]!=review["edge_id"]
    assert d2["destination"]["chapter"]==7
    assert d2["destination"]["verse"]==2
    for bad in (
        dict(body,checked_original_scan=False),
        dict(body,edge_id="fr88i:p0999:R:001/target01"),
        dict(body,source=dict(body["source"],verse=None)),
        dict(body,destination=dict(body["destination"],chapter=-1)),
        dict(body,destination=dict(body["destination"],book_code="")),
        dict(body,cause="INVALID_CAUSE")
    ):
        try: validate_decision(bad,index)
        except ValueError: pass
        else: raise AssertionError("Invalid reviewer input was accepted: "+str(bad))
    cut=dict(body,choice="cut_off",cause="MARGIN_ACTUALLY_CUT_OFF",
             source={"book_code":"","chapter":None,"verse":None},
             destination={"book_code":"","chapter":None,"verse":None,"type":"UNKNOWN"},
             checked_original_scan=True)
    assert validate_decision(cut,index)["human_review_status"]=="SCAN_CONFIRMED_CUT_OFF"
    pending=dict(cut,choice="unresolved",checked_original_scan=False)
    assert validate_decision(pending,index)["human_review_status"]=="UNRESOLVED"
    print("PASS: independent destination exceptions, scan-checked corrections, cutoffs, safe private state, zero SQL")


if __name__=="__main__":
    test()
