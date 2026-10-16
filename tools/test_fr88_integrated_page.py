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
          "A,1Chr,1 Ch,,",
          "C,Gen,,2,25","C,Gen,,5,32","C,1Chr,,1,54",
          "C,Rom,,6,23","C,Ps,,78,72",
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
            assert all(x["source"]["verse"]==17 for x in edges)
            assert all(x["scan_human_verified"] is False for x in edges)
            cut=m.parse_task(response({"items":[{
                "raw_line":"1 Co 15 4","y_fraction":.8,
                "visibility_status":"CUT_OFF"}]}),"margin_L",33)
            assert cut["rows"][0]["typography_uncertain"] is True
            # Recover a wrong 'L' JSON response label for an R-only IMAGE.
            mislabeled=m.parse_task(response({"column":"L","markers":[
                {"column":"L","chapter":2,"verse":22,
                 "y_fraction":.19,"confidence":"HIGH"}
            ]}),"verses_R",38)
            assert mislabeled["column"]=="R"
            assert mislabeled["markers"][0]["column"]=="R"
            assert "OCR_JSON_COLUMN_LABEL_OVERRIDDEN_FROM_IMAGE_TASK" in mislabeled["warnings"]

            # Test a COMPLETE NO-API page rebundle with an actual pattern from
            # page36: V2 saw 'Ch 1 1-4', while the integrated pass omitted it.
            previous=(m.RAW,m.OUT,m.HUMAN_REVIEWS)
            try:
                m.RAW=Path(tmp)/"private"
                m.OUT=m.RAW/"jbible_fr88_integrated_v1"
                m.HUMAN_REVIEWS=m.OUT/"not_present_yet.json"
                m.OUT.mkdir(parents=True,exist_ok=True)
                oldrows=[
                  {"id":"fr88v2:p0036:L:01","image_page":36,
                   "side":"L","kind":"REFERENCE","raw_line":"Ch 1 1-4","y_fraction":.14},
                  {"id":"fr88v2:p0036:L:02","image_page":36,
                   "side":"L","kind":"REFERENCE","raw_line":"1 26+","y_fraction":.19},
                  {"id":"fr88v2:p0036:L:03","image_page":36,
                   "side":"L","kind":"REFERENCE","raw_line":"4 17+","y_fraction":.55}
                ]
                oldfile=m.RAW/"jbible_fr1988_v2"/"interpreted_rows.json"
                oldfile.parent.mkdir(parents=True,exist_ok=True)
                oldfile.write_text(json.dumps(oldrows),encoding="utf8")
                stages={
                    "header":{"header_position":"TOP_LEFT",
                              "boundary_role":"FIRST_ON_PAGE",
                              "chapter":5,"verse":1,"scan_confidence":"HIGH",
                              "visible":True,"book_code":"Gen"},
                    "verses_L":{"markers":[
                         {"column":"L","chapter":5,"verse":1,
                          "y_fraction":.10,"confidence":"HIGH"},
                         {"column":"L","chapter":5,"verse":2,
                          "y_fraction":.18,"confidence":"HIGH"},
                         {"column":"L","chapter":5,"verse":3,
                          "y_fraction":.26,"confidence":"HIGH"}]},
                    "verses_R":{"markers":[{"column":"R","chapter":5,
                         "verse":20,"y_fraction":.12,"confidence":"HIGH"}]},
                    "margin_L":{"rows":[
                       {"id":"fr88i:p0036:L:001","image_page":36,"side":"L",
                        "kind":"REFERENCE","raw_line":"1 26+",
                        "y_fraction":.135,"visibility_status":"COMPLETE"},
                       {"id":"fr88i:p0036:L:002","image_page":36,"side":"L",
                        "kind":"REFERENCE","raw_line":"4 17+",
                        "y_fraction":.548,"visibility_status":"COMPLETE"}
                    ]},
                    "margin_R":{"rows":[]}
                }
                for task,obj in stages.items():
                    (m.OUT/("image_0036."+task+".result.json")).write_text(
                        json.dumps({"data":obj}),encoding="utf8")
                new=m.collect_page(36,{36:{"source_book_code":"Gen"}},
                                   m.catalog_limits(path))
                assert new and new["legacy_recovered_row_ids"]==[
                    "fr88i:p0036:L:003"],new
                recovered=[e for e in new["atomic_source_to_destination_links"]
                           if e["row_id"]=="fr88i:p0036:L:003"]
                assert len(recovered)==1
                assert recovered[0]["printed_margin_line"]=="Ch 1 1-4"
                assert recovered[0]["destination"]["book_code"]=="1Chr",recovered
                assert recovered[0]["destination"]["chapter"]==1
                assert recovered[0]["destination"]["verse"]==1
                assert recovered[0]["destination"]["end_verse"]==4
                assert recovered[0]["status"]=="ACCEPTED_ESTIMATED"
                assert recovered[0]["accepted_automatically"] is True
                assert new["summary"]["atomic_links"]==3
                assert new["summary"]["exceptions"]==0,new["summary"]
            finally:
                m.RAW,m.OUT,m.HUMAN_REVIEWS=previous

            print("PASS: page geometry, wrong-column JSON label recovered, "
                  "legacy missed row restored and atomized, no DeepSeek or SQL")
        finally:
            m.CATALOG=old


if __name__=="__main__":
    test()
