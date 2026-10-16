#!/usr/bin/env python3
"""Offline recognition safety: preserve only printed page starts; no inferred book."""
import json
import fr88_page_header_scan as scan


def answer(header):
    return {"choices":[{"message":{"content":json.dumps(header)}}]}


def test():
    one=scan.decode(answer({
        "page_book_header_printed":"LA GENÈSE",
        "top_left_running_head_raw":"24 45",
        "page_start_chapter":24,
        "page_start_verse":45,
        "header_verse_marker_visible":True,
        "header_chapter_marker_visible":True,
        "confidence":"HIGH","warnings":[]}),45)
    assert one["book_title_printed"]=="LA GENÈSE"
    assert one["start_chapter"]==24 and one["start_verse"]==45
    assert one["human_verified"] is False and one["sql_writes"] is False
    no_head=scan.decode(answer({
        "page_book_header_printed":None,"top_left_running_head_raw":None,
        "page_start_chapter":1,"page_start_verse":1,
        "header_chapter_marker_visible":False,
        "header_verse_marker_visible":False,
        "confidence":"LOW","issue":"NO_PRINTED_RUNNING_HEAD"}),31)
    assert no_head["start_chapter"] is None
    assert no_head["start_verse"] is None
    partial=scan.decode(answer({
        "page_book_header_printed":"EXODE","top_left_running_head_raw":"16 ?",
        "page_start_chapter":16,"page_start_verse":31,
        "header_chapter_marker_visible":True,"header_verse_marker_visible":False,
        "confidence":"LOW","issue":"UNREADABLE_HEADER"}),102)
    assert partial["start_chapter"]==16
    assert partial["start_verse"] is None
    print("PASS: visible Gen 24:45, absent heading and unreadable verse never guessed")


if __name__=="__main__":
    test()
