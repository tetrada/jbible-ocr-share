#!/usr/bin/env python3
"""Offline test of private data exclusion and V2/V3/V4 text Git export."""
import json
import sys
import tempfile
from pathlib import Path

import fr88_v4_git_export as export


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False),encoding="utf-8")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        export.V2=root/"v2.json"
        export.V3=root/"v3"
        export.V4=root/"v4"
        export.V3.mkdir()
        export.V4.mkdir()
        before=[]
        for page in range(31,35):
            for side in ("L","R"):
                raw="2 P 25" if (page,side)==(33,"R") else "Ps 8 3"
                old={"id":"fr88v2:p%04d:%s:01"%(page,side),
                     "image_page":page,"side":side,"raw_line":raw,
                     "kind":"REFERENCE","y_fraction":0.4,
                     "references":[{"type":"VERSE","book_code":"Ps",
                                    "chapter":8,"verse":3,"status":"PARSED"}]}
                before.append(old)
                for version,folder in (("v3",export.V3),("v4",export.V4)):
                    line="↗ 2 P 2 5" if (page,side)==(33,"R") and version=="v4" else raw
                    row=dict(old,id="fr88"+version+":p%04d:%s:01"%(page,side),
                             raw_line=line)
                    write(folder/("image_%04d_%s.result.json"%(page,side)),
                          {"rows":[row], "provider_response_NOT_EXPORTED":{"secret":"do_not_publish"}})
        write(export.V2,before)
        baseline=export.V2.read_bytes()
        write(export.V4/"comparison.json",{
            "pages":[31,34], "margins_complete":8,"margins_expected":8,
            "missing_v3_margins":[]})
        write(export.V4/"run_summary.json",{
            "errors":[],"complete":True,"fresh_requested_margin_jobs":8})
        write(export.V4/"heldout_comparison.json",{
            "holdouts_total":5,
            "results_by_model":{"v2":{"EXACT_TEXT_NEAR_ANCHOR":5},
                                "v3":{"EXACT_TEXT_NEAR_ANCHOR":5},
                                "v4":{"EXACT_TEXT_NEAR_ANCHOR":3,"NOT_PROCESSED":2}},
            "scope":"text-only test"})
        oldargs=sys.argv
        sys.argv=[oldargs[0],str(root/"github_publish")]
        try:
            export.main()
        finally:
            sys.argv=oldargs
        output=root/"github_publish"
        summary=json.loads((output/"pilot_summary.json").read_text(encoding="utf-8"))
        cases=json.loads((output/"readings_and_differences.json").read_text(encoding="utf-8"))
        assert summary["margins_processed"]==8
        assert summary["v4"]["physical_rows"]==8
        assert len(cases["readings"])==8
        assert summary["v2_to_v4_difference_groups"]==1
        assert len(cases["differences"]["v3_to_v4"])==1
        published="".join(p.read_text(encoding="utf-8") for p in output.glob("*.json"))
        assert "do_not_publish" not in published
        assert export.V2.read_bytes()==baseline
        print("PASS: text-only 8-margin Git export, diffs, no private provider data, v2 unchanged")


if __name__=="__main__":
    main()
