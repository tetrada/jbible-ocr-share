#!/usr/bin/env python3
"""Offline all-in-one page scanner tests, including atomic margin splitting."""
import json
import tempfile
from pathlib import Path

import fr88_integrated_page as m


def response(j):
    return {"choices":[{"message":{"content":json.dumps(j)}}]}


def test():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"catalog.csv"
        lines=[
          "record_type,book_code,bali_alias,chap_number,max_verse",
          "A,Gen,Gn,,","A,Rom,Rm,,","A,Ps,Ps,,","A,Rev,Ap,,",
          "C,Gen,,2,25","C,Rom,,6,23","C,Ps,,78,72",
          "C,Ps,,105,45","C,Rev,,16,21"
        ]
        path.write_text("\n".join(lines)+"\n",encoding="utf-8")
        old=m.CATALOG
        try:
            m.CATALOG=path
            h=m.parse_task(response({
                "printed_page_side":"RIGHT_BOOK_PAGE",
                "header_position":"TOP_RIGHT","boundary_role":"LAST_ON_PAGE",
                "chapter":2,"verse":25,"visible":True,
                "confidence":"HIGH","book_code":"Gen","book_title":"LA GENÈSE",
                "running_head_raw":"2 25"}),"header",33)
            assert h["boundary_role"]=="LAST_ON_PAGE"
            vs=m.parse_task(response({"column":"L","markers":[
                {"chapter":2,"verse":17,"y_fraction":.335,"confidence":"HIGH"},
                {"chapter":2,"verse":18,"y_fraction":.50,"confidence":"HIGH"}
            ]}),"verses_L",33)
            assert len(vs["markers"])==2
            rows=m.parse_task(response({"items":[{
                "kind":"REFERENCE","raw_line":"Rm 6 23","y_fraction":.452,
                "visibility_status":"COMPLETE","typography_uncertain":False,
                "layout_uncertain":False}]}),"margin_L",33)
            assert len(rows["rows"])==1
            row=rows["rows"][0]
            assert row["id"]=="fr88i:p0033:L:001"
            assert row["references"][0]["book_code"]=="Rom"
            assert row["references"][0]["chapter"]==6
            assert row["references"][0]["verse"]==23

            many=m.parse_task(response({"items":[{
                "kind":"REFERENCE",
                "raw_line":"Ps 78 47s; 105 32; Ap 16 21",
                "y_fraction":.452,"visibility_status":"COMPLETE"}]}),
                "margin_L",33)
            assert len(many["rows"])==1
            segments=many["rows"][0]["references"]
            assert len(segments)==3
            assert [(r["book_code"],r["chapter"],r["verse"]) for r in segments]==[
                ("Ps",78,47),("Ps",105,32),("Rev",16,21)]
            limits=m.catalog_limits(path)
            intervals,flags=m.make_intervals(vs["markers"],{"header_position":"NONE",
                "boundary_role":"UNKNOWN","chapter":None,"verse":None,"visible":False},
                "Gen",limits)
            edges=m.atomic_edges(33,"Gen",many["rows"],intervals,limits,flags)
            assert len(edges)==3
            print("DEBUG_INTERVALS", intervals, "DEBUG_ROWS",many["rows"],"DEBUG_EDGES",edges, flush=True)
            assert all(x["source"]["verse"]==17 for x in edges)
            assert all(x["scan_human_verified"] is False for x in edges)
            cut=m.parse_task(response({"items":[{
                "raw_line":"1 Co 15 4","y_fraction":.8,
                "visibility_status":"CUT_OFF"}]}),"margin_L",33)
            assert cut["rows"][0]["typography_uncertain"] is True
            print("PASS: five-stage JSON parsing, page-end header, 3 atomic destinations, Gen 2:17→Rom 6:23")
        finally:
            m.CATALOG=old


if __name__=="__main__":
    test()
