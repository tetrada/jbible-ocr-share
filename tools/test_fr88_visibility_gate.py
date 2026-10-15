#!/usr/bin/env python3
"""Test conservative FR88 visibility gate without OCR/provider/network/SQL."""
import json
import tempfile
from pathlib import Path
import fr88_visibility_gate as gate


def test():
    data = [
        {"id":"1", "image_page":32, "side":"L", "kind":"REFERENCE",
         "raw_line":"Ps 8 3", "visibility_status":"COMPLETE",
         "typography_uncertain":False, "references":[{"status":"PARSED"}]},
        {"id":"2", "image_page":32, "side":"R", "kind":"REFERENCE",
         "raw_line":"↗ 1 Co 15 4", "visibility_status":"CUT_OFF",
         "visibility_note":"margin clip",
         "typography_uncertain":True, "references":[{"status":"PARSED"}]},
        {"id":"3", "image_page":32, "side":"L", "kind":"REFERENCE",
         "raw_line":"7 2", "visibility_status":"UNREADABLE"},
        {"id":"4", "image_page":32, "side":"L", "kind":"REFERENCE",
         "raw_line":"Ex 3 4"},
        {"id":"5", "image_page":32, "side":"R", "kind":"REFERENCE",
         "raw_line":"1 P 2 5", "visibility_status":"COMPLETE",
         "typography_uncertain":True},
        {"id":"6", "image_page":32, "side":"R", "kind":"SECTION_LABEL",
         "raw_line":"La tour de Babel", "visibility_status":"COMPLETE"},
    ]
    original = json.dumps(data)
    result = gate.gate_rows(data)
    assert len(result["candidates"]) == 1
    assert len(result["quarantine"]) == 4
    assert len(result["excluded"]) == 1
    assert result["summary"]["automatic_linking_authorized"] == 0
    assert result["candidates"][0]["automatic_linking_authorized"] is False
    clipped = next(r for r in result["quarantine"] if r["id"]=="2")
    assert clipped["raw_line"] is None
    assert clipped["unverified_ocr_proposal"]=="↗ 1 Co 15 4"
    assert clipped["complete_bible_reference_verified"] is False
    assert "references" not in clipped
    assert json.dumps(data) == original
    try:
        gate.gate_rows(data + [data[0]])
    except ValueError:
        pass
    else:
        raise AssertionError("Duplicated rows accepted")
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        gate.save(root/"out.json",result["summary"])
        assert json.loads((root/"out.json").read_text(encoding="utf-8"))["quarantined_rows"]==4
    print("PASS: complete-only candidates, truncated quarantine, all linking disabled, no mutations")


if __name__=="__main__":
    test()
