#!/usr/bin/env python3
"""Offline regression over all 24 real scan-reviewed JBible exceptions."""
import json
from pathlib import Path
from fr88_page_layout_core import summary, reference_assessment, make_intervals, choose_source
from fr88_integrated_human_replay import apply_reviews


def review_file():
    a=Path("/app/fr88_human_exception_reviews.json")
    if not a.exists():
        a=Path(__file__).resolve().parent.parent/"fr88_integrated_v1"/"human_exception_reviews.json"
    return a


def test():
    document=json.loads(review_file().read_text(encoding="utf-8"))
    assert len(document["reviews"])==24
    lines=[]
    for eid,review in document["reviews"].items():
        dst=review.get("destination") or {}
        src=review.get("source") or {}
        # Test each real saved decision against a deliberately unverified
        # automated edge, not against a pre-corrected source.
        line={
            "edge_id":eid,"source":{"book_code":"Gen",
                "chapter":None,"verse":None,"source_verse_interval":None},
            "destination":{"book_code":dst.get("book_code"),
                "chapter":dst.get("chapter"),"verse":dst.get("verse"),
                "type":("UNRESOLVED_NUMERIC" if dst.get("type")=="UNKNOWN"
                        else dst.get("type")),"status":"PARSED",
                "suffix":dst.get("suffix",""),"end_verse":dst.get("end_verse")},
            "status":"EXCEPTION","accepted_automatically":False,
            "human_review_required":True,"hard_exceptions":["ORIGINAL_ERROR"],
            "qa_reasons":["ORIGINAL_ERROR"],
            "source_alignment_estimate_flags":[],
            "scan_human_verified":False
        }
        lines.append(line)
    apply_reviews(lines,document,{})
    by_id={e["edge_id"]:e for e in lines}
    stats=summary(lines)
    assert stats["atomic_links"]==24
    assert stats["accepted"]==23,stats
    assert stats["exceptions"]==1,stats
    assert stats["accepted_human_corrected"]==21,stats
    assert stats["accepted_estimated"]==2,stats
    assert stats["human_verified"]==21,stats
    first=by_id["fr88i:p0033:L:001/target01"]
    assert first["source"]["book_code"]=="Gen"
    assert first["source"]["chapter"]==2 and first["source"]["verse"]==9
    sibling=by_id["fr88i:p0033:L:002/target02"]
    assert sibling["source"]["verse"]==9
    assert sibling["destination"]["book_code"]=="Rev"
    assert sibling["destination"]["chapter"]==22
    assert sibling["destination"]["verse"]==14
    assert by_id["fr88i:p0034:R:001/target01"]["source"]["verse"]==16
    assert by_id["fr88i:p0037:L:001/target01"]["source"]["verse"]==4
    assert by_id["fr88i:p0037:R:001/target01"]["source"]["verse"]==4
    cut=by_id["fr88i:p0032:R:017/target01"]
    assert cut["status"]=="EXCEPTION"
    assert "SCAN_CONFIRMED_UNUSABLE_CUT_OFF" in cut["hard_exceptions"]
    assert cut["accepted_automatically"] is False
    cropped=by_id["fr88i:p0032:R:014/target01"]
    assert cropped["status"]=="ACCEPTED_ESTIMATED"
    assert cropped["destination"]["book_code"]=="Wis"
    assert cropped["destination"]["chapter"]==15
    assert cropped["destination"]["verse"]==8
    assert cropped["destination"]["type"]=="VERSE"
    # Exceptional reviewer corrections are one-off, NOT global parser rules.
    unique=by_id["fr88i:p0034:R:011/target01"]
    assert unique["destination"]["book_code"]=="Rev"
    assert unique["destination"]["chapter"]==1
    assert unique["original_automated_link"]["status"]=="EXCEPTION"
    matt=by_id["fr88i:p0037:L:005/target01"]
    assert matt["destination"]["suffix"]=="sp"
    assert matt["destination"]["chapter"]==24
    assert matt["destination"]["verse"]==27
    # Incomplete local catalog must not reject valid supported book chapters.
    for book,chapter,verse in (("Exod",20,8),("Heb",4,4),("Gen",31,12),
                              ("Ps",104,29),("Hos",4,3),("Isa",11,6)):
        valid,notes=reference_assessment({"status":"PARSED","type":"VERSE",
                       "book_code":book,"chapter":chapter,"verse":verse},{})
        assert valid and notes,(book,notes)
    invalid,_=reference_assessment({"status":"PARSED","type":"VERSE",
           "book_code":"Gen","chapter":999,"verse":1},{})
    assert not invalid
    # Previous page 2:9 -> current first visible 2:10, source is 2:9 at top.
    m=[{"column":"L","chapter":2,"verse":10,
        "y_fraction":.14,"confidence":"HIGH"},
       {"column":"L","chapter":2,"verse":11,
        "y_fraction":.18,"confidence":"HIGH"}]
    h={"boundary_role":"UNKNOWN","visible":False,"chapter":None,"verse":None,
       "scan_confidence":"LOW"}
    iv,issues=make_intervals(m,h,"Gen",{},previous_page_last={"chapter":2,"verse":9})
    source,flags=choose_source({"side":"L","y_fraction":.075},iv)
    assert (source["chapter"],source["verse"])==(2,9),(source,issues)
    # No previous page? Infer 6:4 from first printed 6:5 and the same book.
    m[0].update(chapter=6,verse=5)
    m[1].update(chapter=6,verse=6)
    iv,issues=make_intervals(m,h,"Gen",{})
    source,flags=choose_source({"side":"L","y_fraction":.062},iv)
    assert (source["chapter"],source["verse"])==(6,4),(source,issues)
    # Right-column first printed 3:17, left final is 3:16.
    markers=[{"column":"L","chapter":3,"verse":16,
              "y_fraction":.75,"confidence":"HIGH"},
             {"column":"R","chapter":3,"verse":17,
              "y_fraction":.15,"confidence":"HIGH"}]
    iv,_=make_intervals(markers,h,"Gen",{})
    source,flags=choose_source({"side":"R","y_fraction":.13},iv)
    assert (source["chapter"],source["verse"])==(3,16),(source,flags)
    print("PASS: all 24 real human decisions replayed; 23 usable incl. 2 "
          "partial targets; 1 real cutoff; page/column carry-over sources; "
          "no API or SQL.")


if __name__=="__main__":
    test()
