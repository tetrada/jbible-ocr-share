#!/usr/bin/env python3
"""Isolated FR88 OCR v4 few-shot runner, reusing the v3 engine without v3 writes.
The inherited v3 comparison labels are translated to v4 in saved JSON reports.
"""
import sys
from pathlib import Path
import fr88_v3_pilot as pilot

pilot.OUT=Path("/raw/jbible_fr1988_v4_learning")
pilot.PROMPT=pilot.OUT/"learned_prompt.txt"
previous_compare=pilot.compare

def compare_v4(start,end,gold=None):
    report=previous_compare(start,end,gold)
    if "v3" in report:
        report["v4"]=report.pop("v3")
        report["edition"]="FR1988-v4-few-shot"
        report["warning"] = (
            "v4 prompt uses verified in-context examples, NOT permanent model fine-tuning. "
            "Parser/canonical counts do not prove OCR accuracy.")
        pilot.save_json(pilot.OUT/"comparison.json",report)
        print("V4 COMPARISON SAVED:",pilot.OUT/"comparison.json",flush=True)
    return report

pilot.compare=compare_v4

if __name__=="__main__":
    sys.exit(pilot.main())
