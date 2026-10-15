#!/usr/bin/env python3
"""Offline continuation test. No network, DeepSeek, SQL, Git or page images."""
import json
import tempfile
from pathlib import Path

import fr88_deepseek_continue as batch


def test():
    original=batch.engine.provider_rows
    def fake_provider(provider,page,side):
        return ([
            {"id":"old:01","image_page":page,"side":side,
             "kind":"REFERENCE","raw_line":"Ps 8 5",
             "typography_uncertain":False,
             "references":[{"type":"VERSE","status":"PARSED","book_code":"Ps","chapter":8,"verse":5}]},
            {"id":"old:02","image_page":page,"side":side,
             "kind":"REFERENCE","raw_line":"1 Co 15 4",
             "typography_uncertain":False,
             "references":[{"type":"VERSE","status":"PARSED","book_code":"1Cor","chapter":15,"verse":4}]},
            {"id":"old:03","image_page":page,"side":side,
             "kind":"SECTION_LABEL","raw_line":"Section",
             "typography_uncertain":False,"references":[]},
        ],[])
    batch.engine.provider_rows=fake_provider
    try:
        sample={"choices":[{"message":{"content":json.dumps({"items":[
            {"raw_line":"Ps 8 5","visibility_status":"COMPLETE"},
            {"raw_line":"1 Co 15 4","visibility_status":"CUT_OFF",
             "visibility_note":"right edge"},
            {"raw_line":"Section","kind":"SECTION_LABEL",
             "visibility_status":"COMPLETE"}
        ]})}}]}
        rows,warnings=batch.decode_rows(sample,501,"R")
        assert not warnings and len(rows)==3
        assert rows[0]["id"]=="fr88ds:p0501:R:01"
        assert rows[0]["references"][0]["status"]=="PARSED"
        assert rows[1]["id"]=="fr88ds:p0501:R:02"
        assert rows[1]["visually_truncated"] is True
        assert rows[1]["references"][0]["status"]=="NEEDS_SCAN_VISIBILITY_REVIEW"
        assert rows[1]["references"][0]["original_parse_status"]=="PARSED"
        gate=batch.gate.gate_rows(rows)
        assert len(gate["candidates"])==1
        assert len(gate["quarantine"])==1
        assert len(gate["excluded"])==1
        assert gate["quarantine"][0]["raw_line"] is None
        assert gate["summary"]["automatic_linking_authorized"]==0
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"example.json"
            batch.save(out,{"rows":rows})
            assert len(json.loads(out.read_text(encoding="utf-8"))["rows"])==3
        print("PASS: original OCR candidate, CUT_OFF quarantine, no source link, separate checkpoint")
    finally:
        batch.engine.provider_rows=original


if __name__=="__main__":
    test()
