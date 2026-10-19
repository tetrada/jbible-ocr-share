#!/usr/bin/env python3
"""Regression tests for three-case FR88 human focus and preserved historic review.

Python 3.6 compatible. No external network, scan writes, SQL, or credentials.
"""
import json
from pathlib import Path
from fr88_integrated_exception_review import (
    curated_qa_cases, focused_cases, cases_from_report, validate_decision)

def test():
    manifest_path = Path("training/fr88_curated_qa_focus.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    focus = curated_qa_cases(manifest)
    assert len(focus) == 3
    assert {c["page"] for c in focus} == {102, 107, 378}
    assert all(c["curated_focus"] and c["review_hint"] for c in focus)
    assert all(c["human_verified"] is False and c["sql_writes"] is False for c in focus)

    # Historic exceptions remain intact and in the unchanged ID namespace.
    old = {
        "edge_id":"fr88i:p0032:R:003/target01",
        "status":"EXCEPTION", "column":"R", "margin_y_fraction":0.21,
        "printed_margin_line":"Qo 3 11",
        "target_segment_index":1,
        "source_book_code":"Gen", "source_chapter":1,"source_verse":29,
        "target_book_code":"Eccl", "target_chapter":3, "target_verse":11,
        "target_type":"VERSE", "hard_exceptions":["MARGINAL_DESTINATION_UNREADABLE"]
    }
    integrated = {"schema":"jbible.fr88.integrated-page-git-report.v1",
                  "pages":[{"image_page":32, "source_to_destination_edges":[old]}]}
    full = focused_cases(integrated, manifest)
    assert len(full) == 4
    assert len(cases_from_report(integrated)) == 1
    assert full[-1]["edge_id"] == old["edge_id"]
    assert len(set(c["edge_id"] for c in full)) == 4

    cases = {c["edge_id"]:c for c in full}
    candidate=cases["fr88:p0378:ref011"]
    row={"edge_id":candidate["edge_id"],
         "choice":"as_printed", "cause":"UNUSUAL_PRINTED_NOTATION",
         "source":{"book_code":"1Kgs","chapter":3,"verse":4},
         "destination":{"book_code":"Wis","chapter":8,"verse":19,
                        "end_chapter":9,"end_verse":None,
                        "type":"VERSE_CROSS_CHAPTER_RANGE","suffix":""},
         "checked_original_scan":True, "notes":"Printed 8:19–9, no end verse"}
    out=validate_decision(row,cases)
    assert out["destination"]["end_chapter"] == 9
    assert out["destination"]["end_verse"] is None
    assert out["sql_ready"] is False
    for eid in ("fr88:p0102:ref005","fr88:p0107:ref013"):
        obj=dict(row,edge_id=eid,choice="cut_off",
                 cause="MARGIN_ACTUALLY_CUT_OFF",
                 destination={"book_code":None,"chapter":None,"verse":None,
                              "type":"UNKNOWN"})
        assert validate_decision(obj,cases)["human_review_status"] == "SCAN_CONFIRMED_CUT_OFF"
    invalid=dict(row,checked_original_scan=False)
    try:
        validate_decision(invalid,cases)
    except ValueError:
        pass
    else:
        raise AssertionError("Accepted without original scan review")
    for wrong in (
        dict(manifest, expected_case_count=999),
        dict(manifest, sql_writes=True),
        dict(manifest, cases=[dict(manifest["cases"][0],edge_id="fr88:p9999:ref001")])
    ):
        try: curated_qa_cases(wrong)
        except ValueError: pass
        else: raise AssertionError("Malformed focus manifest accepted")
    print("PASS: 3 focused QA cases + historical queue, scan-required decisions, SQL disabled")

if __name__ == "__main__":
    test()
