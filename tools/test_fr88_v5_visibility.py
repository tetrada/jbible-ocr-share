#!/usr/bin/env python3
"""Small offline regression for v5 prefix abstention and metadata."""
import json
import fr88_v5_cutoff_eval as evaluator
import fr88_v5_visibility_proxy as runner

def test():
    expected="Ab 12"
    assert evaluator.assess(expected,[{"raw_line":"Ab 12 9"}])["result"]=="UNVERIFIED_COMPLETION_BEYOND_VISIBLE_TEXT"
    assert evaluator.assess(expected,[{"raw_line":"Ab 12","visibility_status":"CUT_OFF"}])["result"]=="VISIBLE_PREFIX_PRESERVED_AND_FLAGGED"
    assert evaluator.assess(expected,[{"raw_line":"Ab 12"}])["result"]=="VISIBLE_PREFIX_PRESERVED_BUT_NOT_FLAGGED"
    assert evaluator.assess(expected,[])["result"]=="VISIBLE_PREFIX_MISSING"
    assert runner.pilot.OUT.name=="jbible_fr1988_v5_visibility"
    print("PASS: incomplete-source abstention metrics")

if __name__=="__main__":
    test()
