#!/usr/bin/env python3
"""Compile human-verified FR88 OCR examples into DeepSeek in-context prompt.
Never fine-tunes model weights; no API, SQL, or image writes. Python 3.6.
"""
import argparse
import json
from pathlib import Path

def build(base,gold,max_examples=20):
    if gold.get("schema")!="jbible.fr88.ocr.gold.v1":
        raise ValueError("Invalid gold corpus schema")
    examples=[]
    for row in gold.get("examples",[]):
        if row.get("inclusion")!="prompt_example":
            continue
        if row.get("verification") not in (
            "human_confirmed_from_user_image","human_confirmed_from_original_scan"):
            raise ValueError("Unverified example attempted as training: "+str(row.get("id")))
        correct=row.get("corrected_raw_line")
        lines=row.get("corrected_lines")
        if lines is not None:
            if (not isinstance(lines,list) or not lines or len(lines)>20 or
                    any(not isinstance(item,str) or not item.strip() for item in lines)):
                raise ValueError("Invalid corrected physical rows")
        elif not isinstance(correct,str) or not correct.strip():
            raise ValueError("Empty correct transcription")
        examples.append(row)
        if len(examples)>=max_examples:
            break
    holdouts={x.get("id") for x in gold.get("held_out_examples",[])}
    if any(x["id"] in holdouts for x in examples):
        raise ValueError("Evaluation leakage: a holdout is included in prompt!")
    if not examples:
        raise ValueError("No verified examples available")
    prompt=[base.rstrip(),"","SCAN-VERIFIED FR88 OCR CORRECTIONS:",
        "These are typography transcription examples, NOT a reason to guess missing text."]
    for x in examples:
        correct_lines=x.get("corrected_lines") or [x["corrected_raw_line"]]
        prompt.extend(["", "Gold "+x["id"]+":"])
        if x.get("baseline_ocr_error"):
            prompt.append("PREVIOUS OCR ERROR: "+str(x["baseline_ocr_error"]))
        else:
            prompt.append("SCAN-CONFIRMED TRANSCRIPTION (not a measured OCR improvement)")
        prompt.extend([
            "CORRECT PHYSICAL REFERENCE ROWS (one per line):",
            "\n".join("ROW %d: %s" % (i+1, line) for i,line in enumerate(correct_lines)),
            "VISIBLE TYPOGRAPHY / INCLUSION RULE: "+str(x.get("typography") or "")])
    prompt.extend(["","When something similar appears, read the actual BOLD chapter and",
                   "regular verse typography. Never alter raw text just to make a valid Bible coordinate."])
    return "\n".join(prompt).strip()+"\n",len(examples)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base",type=Path,required=True)
    p.add_argument("--gold",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--min-verified",type=int,default=1)
    p.add_argument("--max-examples",type=int,default=20)
    args=p.parse_args()
    if args.max_examples<1 or args.min_verified<1:
        p.error("Counts must be positive")
    gold=json.loads(args.gold.read_text(encoding="utf-8"))
    prompt,n=build(args.base.read_text(encoding="utf-8"),gold,args.max_examples)
    if n<args.min_verified:
        raise RuntimeError("Need %d human-verified examples, currently %d"%
                           (args.min_verified,n))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(prompt,encoding="utf-8")
    print("Compiled %d verified prompt examples to %s"%(n,args.output))
    print("This is few-shot prompting, NOT permanent model training.")

if __name__=="__main__":
    main()
