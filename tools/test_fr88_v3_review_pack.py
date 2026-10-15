#!/usr/bin/env python3
"""Offline test for v3 scan-crop review ZIP; no API or v2 writes."""
import csv
import json
import tempfile
import zipfile
from pathlib import Path
from PIL import Image
import fr88_v3_review_pack as mod

def test():
    with tempfile.TemporaryDirectory() as temp:
        d = Path(temp)
        mod.V2 = d / "v2.json"
        mod.V3 = d / "v3"
        mod.IMAGES = d / "images"
        mod.OUTFILE = mod.V3 / "fr88_v3_review_pack.zip"
        mod.V3.mkdir()
        mod.IMAGES.mkdir()
        Image.new("RGB",(1200,1600),(255,255,255)).save(str(mod.IMAGES/"image_0031.jpg"))
        v2rows=[{"id":"fr88v2:p0031:R:02","image_page":31,"side":"R",
                 "y_fraction":0.4,"raw_line":"2 P 25","kind":"REFERENCE"}]
        mod.V2.write_text(json.dumps(v2rows),encoding="utf-8")
        v2old=mod.V2.read_bytes()
        for pg in range(31,51):
            for side in ("L","R"):
                rows=[]
                if pg==31 and side=="R":
                    rows=[{"id":"fr88v3:p0031:R:02","image_page":31,"side":"R",
                           "y_fraction":0.4,"raw_line":"2 P 2 5","kind":"REFERENCE"}]
                mod.V3.joinpath("image_%04d_%s.result.json"%(pg,side)).write_text(
                    json.dumps({"rows":rows}),encoding="utf-8")
        mod.V3.joinpath("comparison.json").write_text(json.dumps({
            "margins_complete":40,"margins_expected":40,
            "transcription_difference_hunks":1}),encoding="utf-8")
        with mod.V3.joinpath("transcription_disagreements.csv").open(
                "w",newline="",encoding="utf-8") as fh:
            w=csv.DictWriter(fh,fieldnames=["page","side","change","v2_ids","v3_ids"])
            w.writeheader()
            w.writerow({"page":"31","side":"R","change":"replace",
                        "v2_ids":v2rows[0]["id"],
                        "v3_ids":"fr88v3:p0031:R:02"})
        assert mod.build()==0
        with zipfile.ZipFile(str(mod.OUTFILE)) as z:
            names=set(z.namelist())
            assert "review_report.html" in names
            assert "crops/D001.jpg" in names
            assert "review_decisions_template.csv" in names
            obj=json.loads(z.read("review_cases.json").decode("utf-8"))
            assert obj["summary"]["review_cases"]==1
            assert obj["cases"][0]["v2_text"]=="2 P 25"
            assert obj["cases"][0]["v3_text"]=="2 P 2 5"
            assert obj["cases"][0]["human_verified"] is False
        assert mod.V2.read_bytes()==v2old
    print("PASS: offline review pack includes scan crop, discrepancy, blank decisions, no v2 changes")

if __name__=="__main__":
    test()
