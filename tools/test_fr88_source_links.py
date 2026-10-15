#!/usr/bin/env python3
"""Offline tests of main-text source anchoring, target parsing and strict review gate."""
import json
import tempfile
from pathlib import Path
import fr88_source_links as m


def row(id_,literal,position,ref,uncertain=False):
    return {"id":id_,"image_page":31,"side":"L",
            "kind":"REFERENCE","raw_line":literal,
            "y_fraction":position,"layout_uncertain":uncertain,
            "references":[ref]}


def test():
    verse={"type":"VERSE","book_code":"John","chapter":1,"verse":5,
           "status":"PARSED","suffix":"","literal":"Jn 1 5"}
    valid=row("ref-A","Jn 1 5",0.4,verse)
    clipped=row("ref-B","1 Co 15 4",0.7,{"type":"VERSE","book_code":"1Cor",
                 "chapter":15,"verse":4,"status":"PARSED"},True)
    answer={"choices":[{"message":{"content":json.dumps({
       "assignments":[
        {"margin_row_id":"ref-A","scope":"VERSE",
         "source_book_printed":"Gn","source_book_code":"Gen",
         "source_book_evidence":"HEADER_VISIBLE","source_chapter":1,
         "source_verse":3,"source_marker_y_fraction":0.42,
         "verse_marker_visible":True,"chapter_marker_visible":True,
         "alignment_evidence":"VERSE_MARKER_AND_TEXT","confidence":"HIGH",
         "source_text_evidence":"Dieu dit","reason":"visible 3"},
        {"margin_row_id":"ref-B","scope":"UNKNOWN",
         "source_book_printed":"Gn","source_book_code":"Gen",
         "source_book_evidence":"NOT_VISIBLE","source_chapter":1,
         "source_verse":4,"source_marker_y_fraction":0.8,
         "verse_marker_visible":False,"alignment_evidence":"UNKNOWN",
         "confidence":"LOW"}
       ],"warnings":[]})}}]}
    assigned=m.validated(answer,[valid,clipped])
    assert len(assigned["assignments"])==2
    assert assigned["assignments"][1]["source_book_code"] is None
    limits={("Gen",1):31,("John",1):51,("1Cor",15):58}
    assignments=assigned["assignments"]
    output=m.safe_segments(valid,assignments[0],{},limits)
    assert len(output)==1 and output[0]["state"]=="PROPOSED_REVIEW_REQUIRED"
    assert output[0]["source"]["source_chapter"]==1
    assert output[0]["source"]["source_verse"]==3
    assert output[0]["target"]["verse"]==5
    assert output[0]["source_to_target_link_verified"] is False
    assert output[0]["sql_ready"] is False

    cuts={"ref-B":{"visibility_status":"CUT_OFF"}}
    quarantined=m.safe_segments(clipped,assignments[1],cuts,limits)
    assert quarantined[0]["state"]=="NEEDS_REVIEW"
    assert quarantined[0]["target_reason"]=="CUT_OFF_TARGET_FROM_HUMAN_REVIEW"
    assert quarantined[0]["source_reason"]=="SOURCE_SCOPE_UNKNOWN"
    wrong=dict(verse,verse=99)
    assert m.target_status(valid,wrong,{},limits)=="TARGET_VERSE_OUTSIDE_CATALOG"
    chapter=dict(verse,type="CHAPTER_ONLY")
    assert m.target_status(valid,chapter,{},limits)=="TARGET_CHAPTER_SCOPE_REVIEW"
    far=dict(assignments[0],source_marker_y_fraction=.9)
    assert m.anchor_status(far,valid,limits)=="POSITION_DISAGREEMENT_NEEDS_REVIEW"
    unknown_book=dict(assignments[0],source_book_evidence="NOT_VISIBLE",
                      source_book_code=None)
    assert m.anchor_status(unknown_book,valid,limits)=="SOURCE_BOOK_NOT_PRINTED"
    broken=json.loads(json.dumps(answer))
    broken["choices"][0]["message"]["content"]=json.dumps({
        "assignments":[{"margin_row_id":"ref-A"}]})
    try:
        m.validated(broken,[valid,clipped])
    except ValueError:
        pass
    else:
        raise AssertionError("Missing per-row source assignment allowed")
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/"checkpoint.json"
        m.save(path,assigned)
        assert json.loads(path.read_text(encoding="utf-8"))==assigned
    print("PASS: visual-source candidate, bad source rejected, cut-off quarantine, target catalog constraints, no SQL")


if __name__=="__main__":
    test()
