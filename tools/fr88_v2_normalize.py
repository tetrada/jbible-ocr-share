#!/usr/bin/env python3
"""JBible FR88 v2: conservative, deterministic citation interpretation.

Principles:
- One OCR record represents one PHYSICAL printed reference row.
- A printed book name changes book only inside that row.
- A semicolon within the SAME row keeps the most recent explicit book.
- A new printed row never inherits the preceding row's target book.
- Bare chapter ranges are retained without inventing a target book.
- The raw image OCR and exact transcription are immutable inputs.
- Parser ambiguity is not an OCR error and never verifies a reference.
"""
import csv
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

SOURCE_BARE = "NEEDS_BOOK_OR_LAYOUT_CONTEXT"
SIMPLE_VERSE = re.compile(
    r"^\s*(\d{1,3})\s*(?::\s*|,\s*|\s+)(\d{1,3})"
    r"(?:\s*[-–—]\s*(\d{1,3}))?"
    r"(s{1,2}|sp|p|\+)?\s*\.?\s*$", re.IGNORECASE
)
VERSE_LIST = re.compile(
    r"^\s*(\d{1,3})\s+(\d{1,3}(?:\s*,\s*\d{1,3})+)(s{1,2}|\+)?\s*$",
    re.IGNORECASE
)
CROSS_CHAPTER_VERSES = re.compile(
    r"^\s*(\d{1,3})\s+(\d{1,3})\s*[-–—]\s*(\d{1,3})\s+(\d{1,3})\s*$"
)
DOTTED_VERSE_LIST = re.compile(
    r"^\s*(\d{1,3})\s+(\d{1,3}(?:\.\d{1,3})+)\s*$"
)
CHAPTER_RANGE = re.compile(r"^\s*(\d{1,3})\s*[-–—]\s*(\d{1,3})\s*$")
CHAPTER_ONLY = re.compile(r"^\s*(\d{1,3})(s{1,2}|sp|p|\+)?\s*$", re.IGNORECASE)

@lru_cache(maxsize=8)
def alias_index(csv_path):
    by_alias = defaultdict(set)
    with Path(csv_path).open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("record_type") != "A":
                continue
            code = (row.get("book_code") or "").strip()
            alias = " ".join((row.get("bali_alias") or "").casefold().split())
            if code and alias:
                by_alias[alias].add(code)
    result = {a: next(iter(v)) for a, v in by_alias.items() if len(v) == 1}
    if not result:
        raise ValueError("Bible book alias catalog is empty")
    return result

@lru_cache(maxsize=8)
def alias_regex(csv_path):
    aliases = alias_index(csv_path)
    alternatives = [re.escape(a).replace(r"\ ", r"\s+")
                    for a in sorted(aliases, key=lambda x: (-len(x), x))]
    return re.compile(r"(?<![\w])(?:" + "|".join(alternatives) + r")(?=\s+\d)",
                      re.IGNORECASE)

def _parse_numbers(text):
    text = text.strip(" \t\r\n=↗↖→←")
    m = CROSS_CHAPTER_VERSES.fullmatch(text)
    if m:
        ch,verse,end_ch,end_verse=map(int,m.groups())
        if (end_ch,end_verse)<(ch,verse):
            return {"type":"UNRESOLVED_NUMERIC","literal":text,
                    "reason":"reversed_cross_chapter_range"}
        return {"type":"VERSE_CROSS_CHAPTER_RANGE",
                "chapter":ch,"verse":verse,
                "end_chapter":end_ch,"end_verse":end_verse,
                "literal":text,"suffix":""}
    m = DOTTED_VERSE_LIST.fullmatch(text)
    if m:
        return {"type":"VERSE_LIST","chapter":int(m.group(1)),
                "verses":[int(v) for v in m.group(2).split(".")],
                "literal":text,"suffix":"",
                "notation":"PRINTED_DOTTED_VERSE_LIST"}
    m = SIMPLE_VERSE.fullmatch(text)
    if m:
        ch, v, end, suffix = m.groups()
        ch, v = int(ch), int(v)
        if end is not None and int(end) < v:
            return {"type": "UNRESOLVED_NUMERIC", "literal": text,
                    "reason": "reversed_verse_range"}
        return {"type": "VERSE_RANGE" if end else "VERSE",
                "chapter": ch, "verse": v,
                "end_verse": int(end) if end else None,
                "suffix": suffix or "", "literal": text}
    m = VERSE_LIST.fullmatch(text)
    if m:
        chapter = int(m.group(1))
        return {"type": "VERSE_LIST", "chapter": chapter,
                "verses": [int(x.strip()) for x in m.group(2).split(",")],
                "suffix": m.group(3) or "", "literal": text}
    m = CHAPTER_RANGE.fullmatch(text)
    if m:
        ch, end = map(int, m.groups())
        return {"type": "CHAPTER_RANGE" if end >= ch else "UNRESOLVED_NUMERIC",
                "chapter": ch, "end_chapter": end, "literal": text}
    m = CHAPTER_ONLY.fullmatch(text)
    if m:
        return {"type": "CHAPTER_ONLY", "chapter": int(m.group(1)),
                "suffix": m.group(2) or "", "literal": text}
    # Some Bible cross-reference rows are genuinely cut off at the outer
    # page edge. The leading book/chapter/verse can remain unequivocal even
    # if a comma/semicolon continues into invisible text. Keep ONE usable
    # destination from the visible prefix; never invent unseen citations.
    prefix = re.match(
        r"^\s*(\d{1,3})\s+(\d{1,3})(s{1,2}|sp|p|\+)?\s*[,;]\s*(.*)$",
        text, re.IGNORECASE)
    if prefix:
        chapter,verse,suffix,remainder=prefix.groups()
        return {"type":"VERSE","chapter":int(chapter),"verse":int(verse),
                "end_verse":None,"suffix":suffix or "",
                "literal":text,
                "visible_coordinate_prefix":True,
                "ignored_unreadable_or_following_tail":remainder[:100],
                "reason":"visible_coordinate_prefix_retained"}
    return {"type": "UNRESOLVED_NUMERIC", "literal": text,
            "reason": "notation_not_covered"}

def interpret_line(raw_line, csv_path, layout_uncertain=False):
    """Return ordered child segments; never promote ambiguous text to verified."""
    raw_line = (raw_line or "").strip()
    matcher = alias_regex(str(csv_path))
    mapping = alias_index(str(csv_path))
    marks = list(matcher.finditer(raw_line))
    # Split on both explicit book transitions AND semicolons.
    boundaries = sorted(set([0, len(raw_line)] +
                            [m.start() for m in marks] +
                            [m.end() for m in marks] +
                            [i for i, ch in enumerate(raw_line) if ch == ";"] +
                            [i + 1 for i, ch in enumerate(raw_line) if ch == ";"]))
    current_book = None
    current_alias = None
    parts = []
    segment = ""
    for a, b in zip(boundaries, boundaries[1:]):
        span = raw_line[a:b]
        if not span:
            continue
        mark = next((m for m in marks if m.start() == a and m.end() == b), None)
        if mark:
            if segment.strip(" \t\r\n=↗↖→←"):
                ref = _parse_numbers(segment)
                ref["book_code"] = current_book
                ref["book_printed"] = current_alias
                ref["status"] = ("PARSED" if current_book and
                                 ref["type"] != "UNRESOLVED_NUMERIC"
                                 else SOURCE_BARE if not current_book
                                 else "NEEDS_NOTATION_REVIEW")
                parts.append(ref)
                segment = ""
            current_alias = " ".join(mark.group(0).split())
            current_book = mapping.get(current_alias.casefold())
            continue
        if span == ";":
            if segment.strip(" \t\r\n=↗↖→←"):
                ref = _parse_numbers(segment)
                ref["book_code"] = current_book
                ref["book_printed"] = current_alias
                ref["status"] = ("PARSED" if current_book and
                                 ref["type"] != "UNRESOLVED_NUMERIC"
                                 else SOURCE_BARE if not current_book
                                 else "NEEDS_NOTATION_REVIEW")
                parts.append(ref)
            segment = ""
        else:
            segment += span
    if segment.strip(" \t\r\n=↗↖→←"):
        ref = _parse_numbers(segment)
        ref["book_code"] = current_book
        ref["book_printed"] = current_alias
        ref["status"] = ("PARSED" if current_book and
                         ref["type"] != "UNRESOLVED_NUMERIC"
                         else SOURCE_BARE if not current_book
                         else "NEEDS_NOTATION_REVIEW")
        parts.append(ref)
    # If the line has multiple book markers, each part independently tracks
    # its own canonical book; never validate all parts against the first book.
    if layout_uncertain:
        for part in parts:
            if part["status"] == "PARSED":
                part["status"] = "NEEDS_LAYOUT_REVIEW"
    if not parts and raw_line:
        parts.append({"type": "UNRESOLVED_NUMERIC", "literal": raw_line,
                      "book_code": None, "book_printed": None,
                      "status": SOURCE_BARE})
    return parts

def interpret_ocr_row(row, catalog_path):
    """Non-destructive interpretation attached beside exact OCR transcription."""
    result = dict(row)
    kind = row.get("kind", "REFERENCE")
    if kind == "REFERENCE":
        result["references"] = interpret_line(
            row.get("raw_line", ""), str(catalog_path),
            layout_uncertain=bool(row.get("layout_uncertain", False)))
    else:
        result["references"] = []
    result["verified"] = False
    return result

def self_test(catalog_path):
    cases = [
        ("Ne 9 18 Ps 106 19s 1 R 12 28",
         [("Neh", "VERSE", 9, 18), ("Ps", "VERSE", 106, 19),
          ("1Kgs", "VERSE", 12, 28)]),
        ("Nb 3 17s", [("Num", "VERSE", 3, 17)]),
        ("↗ 1 Co 11 7", [("1Cor", "VERSE", 11, 7)]),
        ("↗ Ps 78 47s; 105 32", [("Ps", "VERSE", 78, 47),
                                   ("Ps", "VERSE", 105, 32)]),
        ("Sg 16-18", [("Wis", "CHAPTER_RANGE", 16, None)]),
        ("Sg 11 14-20", [("Wis", "VERSE_RANGE", 11, 14)]),
        ("Ps 78 47s; 105 32; Ap 16 21; 8 7",
         [("Ps", "VERSE", 78, 47), ("Ps", "VERSE", 105, 32),
          ("Rev", "VERSE", 16, 21), ("Rev", "VERSE", 8, 7)]),
    ]
    for text, expected in cases:
        found = interpret_line(text, catalog_path)
        actual = [(x.get("book_code"), x.get("type"), x.get("chapter"),
                   x.get("verse")) for x in found]
        assert actual == expected, (text, actual, expected)
        assert all(x["status"] == "PARSED" for x in found), (text, found)
    bare = interpret_line("16-18", catalog_path)
    assert len(bare) == 1 and bare[0]["type"] == "CHAPTER_RANGE"
    assert bare[0]["book_code"] is None and bare[0]["status"] == SOURCE_BARE
    assert interpret_line("Sg 11 14-20", catalog_path)[0]["book_code"] == "Wis"
    assert interpret_line("16-18", catalog_path)[0]["book_code"] is None
    assert interpret_line("Ps 106 19s", catalog_path)[0]["suffix"] == "s"
    assert interpret_line("Sg 16-18", catalog_path)[0]["end_chapter"] == 18
    assert interpret_line("↗ 1 Co 11 7", catalog_path)[0]["status"] == "PARSED"
    assert len(interpret_line("↗ Mt 19 4p", catalog_path)) == 1
    return "OK: multi-book, inherited same-row books, s, ranges, row reset"

if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser()
    cli.add_argument("--catalog", default="/raw/jbible_catalog.csv")
    cli.add_argument("--self-test", action="store_true")
    cli.add_argument("--line", default=None)
    args = cli.parse_args()
    if args.self_test:
        print(self_test(args.catalog))
    elif args.line is not None:
        import json
        print(json.dumps(interpret_line(args.line, args.catalog),
                         indent=2, ensure_ascii=False))
