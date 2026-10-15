#!/usr/bin/env python3
"""Offline smoke tests for JBible reference audit. No API or SQL access."""
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

AUDIT = Path(__file__).with_name("jbible_ref_audit.py")


def run_tests():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        catalog = d / "catalog.csv"
        with catalog.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["record_type", "book_code", "chap_number", "max_verse", "bali_alias"])
            w.writerows([
                ("C", "Gen", 1, 31, ""),
                ("C", "Gen", 7, 24, ""),
                ("C", "Job", 38, 41, ""),
                ("C", "Job", 39, 30, ""),
                ("C", "Ps", 8, 9, ""),
                ("C", "Ps", 104, 35, ""),
                ("C", "John", 1, 51, ""),
                ("C", "Rev", 22, 21, ""),
                ("C", "Wis", 15, 19, ""),
                ("A", "Job", "", "", "Jb"),
                ("A", "Ps", "", "", "Ps"),
                ("A", "John", "", "", "Jn"),
                ("A", "Rev", "", "", "Ap"),
                ("A", "Wis", "", "", "Sg"),
            ])
        def ref(book, status, typ, ch=None, v=None, endch=None, endv=None, suffix="", literal=""):
            return {"book_code":book, "status":status, "type":typ,
                    "chapter":ch, "verse":v, "end_chapter":endch,
                    "end_verse":endv, "suffix":suffix, "literal":literal}
        def row(num, raw, refs, kind="REFERENCE"):
            return {
                "id":"fr88v2:p0031:L:%02d" % num,
                "image_page":31, "side":"L", "kind":kind, "raw_line":raw,
                "y_fraction":min(.30 + num * .03,.95),
                "source_chapter":1, "source_verse":1,
                "source_anchor_confident":False,
                "references":refs,
            }
        rows = [
            row(1, "Jb 38-39", [ref("Job","PARSED","CHAPTER_RANGE",38,endch=39,literal="38-39")]),
            row(2, "Ps 8; 104", [
                ref("Ps","PARSED","CHAPTER_ONLY",8,literal="8"),
                ref("Ps","PARSED","CHAPTER_ONLY",104,literal="104")]),
            row(3, "7 11+", [ref(None,"NEEDS_BOOK_OR_LAYOUT_CONTEXT","VERSE",7,11,suffix="+",literal="7 11+")]),
            row(4, "Jn 1 200", [ref("John","PARSED","VERSE",1,200,literal="1 200")]),
            row(5, "Sg 15 8,", [ref("Wis","NEEDS_NOTATION_REVIEW","UNRESOLVED_NUMERIC",literal="15 8,")]),
            row(6, "LABEL", [], kind="SECTION_LABEL"),
        ]
        source = d / "interpreted.json"
        source.write_text(json.dumps(rows), encoding="utf-8")
        before = source.read_bytes()
        p = subprocess.run([
            sys.executable, str(AUDIT),
            "--data",str(source), "--catalog",str(catalog),
            "--images",str(d / "missing_images"), "--out-dir",str(d / "outputs"),
            "--start-page","31", "--end-page","31", "--sample","30",
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert p.returncode == 0, p.stdout + "\n" + p.stderr
        assert before == source.read_bytes(), "Audit mutated input!"
        report = next((d / "outputs").iterdir())
        summary = json.loads((report / "audit_summary.json").read_text())
        assert summary["rows"] == 6
        assert summary["reference_rows"] == 5
        assert summary["segments"] == 6
        assert summary["invalid_target_segments"] == 1
        assert summary["verified"] == 0
        assert summary["sql_writes"] is False
        assert summary["api_calls"] == 0
        assert summary["counts_by_catalog_status"] == {
            "INVALID":1, "MISSING_BOOK":1, "NOT_CHECKABLE":1, "VALID":3
        }, summary["counts_by_catalog_status"]
        with (report / "segments.csv").open(newline="", encoding="utf-8") as f:
            segs = list(csv.DictReader(f))
        assert len(segs) == 6
        assert segs[0]["target"] == "Job 38-39"
        assert segs[3]["catalog_status"] == "MISSING_BOOK"
        assert segs[4]["catalog_status"] == "INVALID"
        assert not any(s["verified"] == "True" for s in segs)
        assert "NOT verified verse alignment" in (report / "audit_report.html").read_text()
        assert len(json.loads((report / "sample_30_records.json").read_text())) == 6
        assert (report / "review_decisions_template.csv").exists()
        print("PASS: six rows and six reference segments; original unchanged, no API or SQL")


if __name__ == "__main__":
    run_tests()
