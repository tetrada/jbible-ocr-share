#!/usr/bin/env python3
"""Tests for book context: adjacent visible headers are suggestions, never facts."""
from fr88_source_book_context import suggest_unknown_book


def rec(rid, code=None, ch=1, verse=1, visible=False):
    return {"margin_row_id":rid, "source_book_code":code,
            "source_book_evidence":"HEADER_VISIBLE" if visible else "NOT_VISIBLE",
            "source_chapter":ch, "source_verse":verse,
            "verse_marker_visible":True}


def run():
    catalog={("Gen",1):31,("Gen",2):25,("Exod",1):22,
             ("Exod",2):25,("Ps",1):6}
    groups=[
      {"page":31,"side":"L","assignments":[
          rec("a",ch=1,verse=1), rec("b",ch=1,verse=6)]},
      {"page":32,"side":"R","assignments":[
          rec("c",code="Gen",ch=1,verse=29,visible=True),
          rec("d",code="Gen",ch=2,verse=2,visible=True)]}
    ]
    result=suggest_unknown_book(groups,catalog)
    assert {x["margin_row_id"] for x in result["suggestions"]}=={"a","b"}
    assert all(x["suggested_source_book_code"]=="Gen" for x in result["suggestions"])
    assert all(x["review_required"] and not x["link_authorized"]
               for x in result["suggestions"])
    assert groups[0]["assignments"][0]["source_book_code"] is None
    # Reject crossing a possible source-book transition with conflicting headers.
    groups.append({"page":30,"side":"L","assignments":[
        rec("e",code="Exod",ch=1,verse=3,visible=True)]})
    result=suggest_unknown_book(groups,catalog)
    assert not result["suggestions"],"Conflicting neighboring book headers cannot be inherited"
    # Reject unknown verse / invisible verse marker.
    groups=[{"page":31,"side":"L","assignments":[
        dict(rec("x",ch=1,verse=1),verse_marker_visible=False),
        rec("y",ch=6,verse=1)]},
       {"page":32,"side":"R","assignments":[
        rec("z",code="Gen",ch=2,verse=5,visible=True)]}]
    result=suggest_unknown_book(groups,catalog)
    assert not result["suggestions"]
    # Strictly no source book guesses from OCR target book.
    assert result["automatically_verified_links"]==0
    assert result["api_calls"]==0 and result["sql_writes"] is False
    print("PASS: neighboring printed headers only, continuity guard, conflict quarantine, no auto-link")


if __name__=="__main__":
    run()
