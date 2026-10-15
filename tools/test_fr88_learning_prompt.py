#!/usr/bin/env python3
"""Offline gold-example tests: reject unverified guesses and holdout leakage."""
import copy
import fr88_learning_prompt as mod

def test():
    gold={"schema":"jbible.fr88.ocr.gold.v1","examples":[
       {"id":"E1","inclusion":"prompt_example",
        "verification":"human_confirmed_from_original_scan",
        "corrected_raw_line":"↗ 2 P 2 5",
        "baseline_ocr_error":"2 P 25",
        "typography":"Bold chapter 2; plain verse 5"},
       {"id":"E2","inclusion":"holdout",
        "verification":"human_confirmed_from_original_scan",
        "corrected_raw_line":"Ps 8 3",
        "baseline_ocr_error":"Ps 83",
        "typography":"Bold chapter 8"}],
       "held_out_examples":[{"id":"E2"}]}
    prompt,count=mod.build("ORIGINAL SYSTEM PROMPT",gold)
    assert count==1
    assert "2 P 2 5" in prompt
    assert "Ps 8 3" not in prompt
    assert "ORIGINAL SYSTEM PROMPT" in prompt
    multi=copy.deepcopy(gold)
    multi["examples"].append({
        "id":"E3","inclusion":"prompt_example",
        "verification":"human_confirmed_from_original_scan",
        "baseline_ocr_error":"Qo 3 20s; 12 7",
        "corrected_lines":["Qo 3 20s;","12 7"],
        "typography":"Two distinct printed lines, not a merged row"
    })
    enhanced,n=mod.build("ORIGINAL SYSTEM PROMPT",multi)
    assert n==2
    assert "ROW 1: Qo 3 20s;\\nROW 2: 12 7" in enhanced
    bad=copy.deepcopy(gold)
    bad["examples"][0]["verification"]="unverified_model_guess"
    try:
        mod.build("x",bad)
    except ValueError:
        pass
    else:
        raise AssertionError("Unverified model guess was accepted")
    bad=copy.deepcopy(gold)
    bad["held_out_examples"].append({"id":"E1"})
    try:
        mod.build("x",bad)
    except ValueError:
        pass
    else:
        raise AssertionError("Holdout leaked into prompt")
    print("PASS: human-verified prompt labels only, holdouts excluded")

if __name__=="__main__":
    test()
