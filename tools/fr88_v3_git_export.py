#!/usr/bin/env python3
"""Export text-only v2/v3 disagreement data for GitHub. No API, images or SQL."""
import csv
import json
import sys
from pathlib import Path

ROOT=Path("/opt/jbible/data/raw")
V2=ROOT/"jbible_fr1988_v2"/"interpreted_rows.json"
V3=ROOT/"jbible_fr1988_v3_pilot_31_50"
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else Path("/opt/jbible/ocr-share-git/fr88_v3_learning")

def simple(row):
    return {
        "id":row["id"], "image_page":row["image_page"],"side":row["side"],
        "kind":row.get("kind"),"raw_line":row.get("raw_line"),
        "y_fraction":row.get("y_fraction"),
        "typography_evidence":row.get("typography_evidence",""),
        "typography_uncertain":row.get("typography_uncertain",False),
        "references":[{"book_code":r.get("book_code"),"chapter":r.get("chapter"),
            "verse":r.get("verse"),"end_chapter":r.get("end_chapter"),
            "end_verse":r.get("end_verse"),"type":r.get("type"),
            "status":r.get("status"),"literal":r.get("literal")}
            for r in row.get("references",[])]
    }

def main():
    comparison=json.loads((V3/"comparison.json").read_text(encoding="utf-8"))
    if comparison.get("pages")!=[31,50] or comparison.get("margins_complete")!=40:
        raise RuntimeError("Require completed 40-margin pilot")
    v2=json.loads(V2.read_text(encoding="utf-8"))
    old={r["id"]:r for r in v2 if 31<=r["image_page"]<=50}
    new={}
    for page in range(31,51):
        for side in ("L","R"):
            cp=V3/("image_%04d_%s.result.json"%(page,side))
            for r in json.loads(cp.read_text(encoding="utf-8"))["rows"]:
                if r["id"] in new:
                    raise ValueError("Duplicate ID")
                new[r["id"]]=r
    with (V3/"transcription_disagreements.csv").open(encoding="utf-8",newline="") as fh:
        diffs=list(csv.DictReader(fh))
    cases=[]
    for i,d in enumerate(diffs,1):
        old_rows=[simple(old[x]) for x in d["v2_ids"].split(";") if x]
        new_rows=[simple(new[x]) for x in d["v3_ids"].split(";") if x]
        cases.append({
            "case_id":"D%03d"%i,"page":int(d["page"]),"side":d["side"],
            "change":d["change"],"v2":old_rows,"v3":new_rows,
            "review_state":"PENDING_IMAGE_REVIEW",
            "confirmed_raw_line":None,
            "human_notes":None
        })
    section_labels=[simple(r) for r in new.values() if r.get("kind")=="SECTION_LABEL"]
    out_summary={
        "pages":[31,50],"v2":comparison["v2"],"v3":comparison["v3"],
        "disagreement_groups":len(cases),"v3_section_labels":len(section_labels),
        "verified_disagreement_groups":0,"ocr_accuracy_improvement":"NOT_MEASURED",
        "sql_writes":False,
        "warning":"A syntactically valid reference is NOT human-verified OCR."
    }
    out_cases={
        "schema":"jbible.fr88.ocr.v3.review.v1",
        "status":"UNVERIFIED_NEEDS_ORIGINAL_SCAN",
        "cases":cases,"v3_section_labels_to_verify":section_labels,
        "no_scanned_images_published":True
    }
    OUT.mkdir(parents=True,exist_ok=True)
    for name,data in (("pilot_summary.json",out_summary),("disagreements.json",out_cases)):
        with (OUT/name).open("w",encoding="utf-8") as fh:
            json.dump(data,fh,ensure_ascii=False,indent=2)
            fh.write("\n")
    print("Prepared",len(cases),"disagreement groups and",len(section_labels),"section labels")
    print("Text-only output:",OUT)
    print("No OCR changes, images, provider payloads, API keys, API calls, or SQL writes.")

if __name__=="__main__":
    main()
