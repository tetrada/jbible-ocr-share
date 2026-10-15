#!/usr/bin/env python3
"""Offline FR88 v3 tests. No network, DeepSeek calls, SQL, or modifications to v2."""
import csv
import json
import tempfile
from pathlib import Path

import fr88_v3_pilot as v3


def test():
    assert "BOLD" in v3.PROMPT.read_text(encoding="utf-8").upper()
    assert "2 P 2 5" in v3.PROMPT.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        catalog = root / "catalog.csv"
        with catalog.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["record_type", "book_code", "chap_number", "max_verse", "bali_alias"])
            writer.writerows([
                ["A", "2Pet", "", "", "2 P"],
                ["A", "Gen", "", "", "Gn"],
                ["C", "2Pet", "1", "21", ""],
                ["C", "2Pet", "2", "22", ""],
                ["C", "2Pet", "3", "18", ""],
                ["C", "Gen", "7", "24", ""],
            ])
        v3.CATALOG = catalog
        v3.OUT = root / "v3"
        v3.V2 = root / "v2.json"
        provider = {"choices":[{"message":{"content":json.dumps({"items":[
            {"kind":"REFERENCE", "raw_line":"↗ 2 P 2 5", "y_fraction":0.42,
             "typography_evidence":"bold chapter 2; regular verse 5",
             "typography_uncertain":False},
            {"kind":"REFERENCE", "raw_line":"7 11+", "y_fraction":0.7,
             "typography_uncertain":True}
        ],"warnings":[]})}}]}
        interpreted, warns = v3.provider_rows(provider, 31, "L")
        assert len(interpreted) == 2 and not warns
        first = interpreted[0]
        assert first["references"][0]["book_code"] == "2Pet"
        assert first["references"][0]["chapter"] == 2
        assert first["references"][0]["verse"] == 5
        assert first["raw_line"] == "↗ 2 P 2 5"
        assert first["source_chapter"] is None and first["verified"] is False
        assert first["typography_evidence"] == "bold chapter 2; regular verse 5"
        assert interpreted[1]["references"][0]["book_code"] is None
        limits = v3.catalog_limits()
        assert v3.catalog_status(first["references"][0], limits) == "VALID"
        wrong = {"type":"CHAPTER_ONLY","book_code":"2Pet","chapter":25}
        assert v3.catalog_status(wrong, limits) == "INVALID"
        assert v3.signature(31,"L",{"half":b"a","full":b"b","upper":b"c","lower":b"d"},"p") != v3.signature(31,"L",{"half":b"a","full":b"b","upper":b"c","lower":b"d"},"p2")
        v2line = {
            "id":"fr88v2:p0031:L:01", "image_page":31,"side":"L",
            "raw_line":"↗ 2 P 25","kind":"REFERENCE","y_fraction":0.42,
            "references":[{"book_code":"2Pet","chapter":25,"type":"CHAPTER_ONLY","status":"PARSED"}]
        }
        v3line = first
        v3line["id"] = "fr88v3:p0031:L:01"
        v3.V2.write_text(json.dumps([v2line]), encoding="utf-8")
        before = v3.V2.read_bytes()
        v3.save_json(v3.OUT / "image_0031_L.result.json", {"rows":[v3line]})
        v3.save_json(v3.OUT / "image_0031_R.result.json", {"rows":[]})
        summary = v3.compare(31,31)
        assert summary["margins_complete"] == 2
        assert summary["v2"]["catalog_INVALID"] == 1
        assert summary["v3"].get("catalog_INVALID", 0) == 0
        assert summary["transcription_difference_hunks"] == 1
        assert before == v3.V2.read_bytes(), "Original baseline changed!"
        gold = root / "reviewed.csv"
        with gold.open("w",newline="",encoding="utf-8") as fh:
            w=csv.DictWriter(fh,fieldnames=["page","side","v2_row_id","expected_raw_line","verified_from_scan"])
            w.writeheader()
            w.writerow({"page":31,"side":"L","v2_row_id":v2line["id"],
                        "expected_raw_line":"↗ 2 P 2 5","verified_from_scan":"YES"})
        verified = v3.compare(31,31,gold)
        assert verified["gold_evaluation"]["human_verified_rows_matched"] == 1
        assert verified["gold_evaluation"]["v2_exact_raw_matches"] == 0
        assert verified["gold_evaluation"]["v3_exact_raw_matches"] == 1
        assert before == v3.V2.read_bytes()
    print("PASS: v3 typography, book ordinal, no inherited book, catalog check, v2 comparison and reviewed gold")


if __name__ == "__main__":
    test()
