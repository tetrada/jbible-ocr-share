#!/usr/bin/env python3
"""Offline five-case holdout evaluation tests, no DeepSeek, no Git, no SQL."""
import json
import tempfile
from pathlib import Path
import fr88_v4_holdout_eval as m


def run():
    with tempfile.TemporaryDirectory() as temp:
        t=Path(temp)
        m.V2=t/"v2.json"; m.V3=t/"v3"; m.V4=t/"v4"
        m.GOLD=t/"gold.json"; m.OUTPUT=m.V4/"heldout_comparison.json"
        m.V3.mkdir(); m.V4.mkdir()
        examples=[{"id":"T1","case_id":"CASE-TRAIN","inclusion":"prompt_example"}]
        h=[]; rows=[]
        for number in range(5):
            page=31+number
            case="H%03d"%number
            raw="Ps %d 4"%page
            h.append({"id":case,"case_id":case,
                      "verification":"human_confirmed_from_original_scan",
                      "image_page":page,"side":"L",
                      "baseline_y_fraction":0.5,
                      "expected_raw_line":raw,"v2_row_id":"old-"+case})
            rows.append({"id":"old-"+case,"image_page":page,"side":"L",
                         "raw_line":raw,"y_fraction":0.5})
            v3raw=raw if number!=1 else "Ps %d 5"%page
            v4raw=raw if number!=2 else "Ps %d 6"%page
            for folder, literal in ((m.V3,v3raw),(m.V4,v4raw)):
                target=folder/("image_%04d_L.result.json"%page)
                target.write_text(json.dumps({"rows":[
                    {"id":"r%02d"%number,"image_page":page,"side":"L",
                     "raw_line":literal,"y_fraction":0.49}]}),encoding="utf-8")
        m.GOLD.write_text(json.dumps({
            "schema":"jbible.fr88.ocr.gold.v1",
            "examples":examples,
            "held_out_examples":h
        }),encoding="utf-8")
        m.V2.write_text(json.dumps(rows),encoding="utf-8")
        baseline=m.V2.read_bytes()
        result=m.evaluate()
        assert result["holdouts_total"]==5
        assert result["results_by_model"]["v2"]["EXACT_TEXT_NEAR_ANCHOR"]==5
        assert result["results_by_model"]["v3"]["EXACT_TEXT_NEAR_ANCHOR"]==4
        assert result["results_by_model"]["v3"]["TEXT_NOT_FOUND"]==1
        assert result["results_by_model"]["v4"]["EXACT_TEXT_NEAR_ANCHOR"]==4
        assert result["results_by_model"]["v4"]["TEXT_NOT_FOUND"]==1
        assert m.OUTPUT.exists()
        assert m.V2.read_bytes()==baseline
        contaminated=json.loads(m.GOLD.read_text(encoding="utf-8"))
        contaminated["examples"].append({"id":"T2","case_id":"H001",
                                          "inclusion":"prompt_example"})
        m.GOLD.write_text(json.dumps(contaminated),encoding="utf-8")
        try:
            m.evaluate()
        except ValueError as ex:
            assert "CONTAMINATION" in str(ex)
        else:
            raise AssertionError("Failed to detect evaluation leakage")
    print("PASS: v2-v3-v4 five-case holdout scores, no source mutation and no prompt leakage")


if __name__ == "__main__":
    run()
