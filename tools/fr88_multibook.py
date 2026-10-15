#!/usr/bin/env python3
"""Conservative offline splitter for FR88 OCR entries containing several printed books.

Only split when every detected explicit book marker maps to precisely one existing
parsed clause, and its chapter/verse agree with the printed text. The raw OCR
checkpoints are never changed. Unclear entries stay unchanged for human review.
"""
import copy
import csv
import re
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=4)
def _catalog_aliases(filename):
    mapping = {}
    with Path(filename).open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("record_type") != "A":
                continue
            alias = (row.get("bali_alias") or "").strip()
            code = (row.get("book_code") or "").strip()
            if not alias or not code:
                continue
            key = " ".join(alias.casefold().split())
            if key in mapping and mapping[key] != code:
                mapping.pop(key, None)  # Ambiguous aliases must never be guessed.
            else:
                mapping[key] = code
    return mapping

@lru_cache(maxsize=4)
def _book_regex(filename):
    names = _catalog_aliases(filename)
    # Longer aliases precede shorter ones (e.g., "1 R" vs "R").
    alternatives = []
    for alias in sorted(names, key=lambda x: (-len(x), x)):
        alternatives.append(re.escape(alias).replace(r"\ ", r"\s+"))
    return re.compile(
        r"(?<!\w)(?:" + "|".join(alternatives) + r")(?=\s+\d)",
        flags=re.IGNORECASE,
    )

def _render(clause, book):
    ch = clause.get("chapter")
    v = clause.get("verse")
    end_ch = clause.get("end_chapter")
    end_v = clause.get("end_verse")
    suffix = clause.get("suffix") or ""
    if not isinstance(ch, int):
        return None
    if v is None:
        ref = str(ch)
    elif isinstance(v, int):
        ref = "%d:%d" % (ch, v)
    else:
        return None
    if isinstance(end_v, int):
        ref += "-" + (str(end_ch) + ":" if isinstance(end_ch, int) and end_ch != ch else "") + str(end_v)
    return book + " " + ref + suffix

def _split_one(row, alias_map, token_re):
    if row.get("kind") != "REFERENCE":
        return None, "not_reference"
    raw = row.get("literal") or ""
    matches = list(token_re.finditer(raw))
    if len(matches) < 2:
        return None, "single_or_no_explicit_book"
    clauses = row.get("clauses") or []
    if len(matches) != len(clauses):
        return None, "book_marker_clause_count_mismatch"
    if raw[:matches[0].start()].strip(" =↗↖→←;,."):
        return None, "unexpected_prefix"
    pieces = []
    for i, marker in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        explicit = " ".join(marker.group(0).split())
        book_code = alias_map.get(explicit.casefold())
        if not book_code:
            return None, "unresolved_alias"
        text = raw[marker.end():end].strip()
        # Only accept segments with one simple leading chapter:verse reference.
        # Prevents conflating semicolon continuations or ranges into one clause.
        numeric = re.match(r"^(\d+)\s*(?::\s*|,\s*|\s+)(\d+)(?!\d)", text)
        clause = clauses[i]
        if (not numeric
                or type(clause.get("chapter")) is not int
                or type(clause.get("verse")) is not int
                or clause["chapter"] != int(numeric.group(1))
                or clause["verse"] != int(numeric.group(2))):
            return None, "clause_not_aligned_with_book"
        # At most one clause within each printed book span. A separate
        # book marker is mandatory for each additional derived record.
        if re.search(r"[,;]\s*\d+\s*(?::\s*|\s+)\d+", text):
            return None, "additional_verse_in_book_span"
        piece = copy.deepcopy(row)
        piece["id"] = row["id"] + ":b%02d" % (i + 1)
        piece["literal"] = raw[marker.start():end].strip()
        piece["book_printed"] = explicit
        piece["book_resolved"] = explicit
        piece["book_explicit"] = True
        piece["book_resolution"] = "PRINTED"
        piece["clauses"] = [copy.deepcopy(clause)]
        piece["normalized_structure"] = _render(clause, explicit)
        if piece["normalized_structure"] is None:
            return None, "unable_to_render_clause"
        piece["split_from"] = row["id"]
        piece["split_index"] = i + 1
        piece["split_count"] = len(matches)
        # Force normal validation to recalculate per-book outcomes.
        for name in ("validation_status", "target_book_code", "en_support_ids",
                     "en_possible_ids", "review_status", "within_requested_chapters"):
            piece.pop(name, None)
        pieces.append(piece)
    return pieces, "split"

def normalize_records(records, catalog_path):
    filename = str(Path(catalog_path))
    aliases = _catalog_aliases(filename)
    token_re = _book_regex(filename)
    result = []
    audit = {
        "split_parent_ids": [],
        "split_children": 0,
        "unsplit_multibook_candidates": [],
        "policy": "Each explicit book must align with one original parsed clause",
        "original_checkpoints_changed": False,
        "verified": 0,
        "sql_writes": False,
    }
    for row in records:
        children, reason = _split_one(row, aliases, token_re)
        if children:
            result.extend(children)
            audit["split_parent_ids"].append(row["id"])
            audit["split_children"] += len(children)
        else:
            result.append(row)
            if reason not in ("not_reference", "single_or_no_explicit_book"):
                audit["unsplit_multibook_candidates"].append({
                    "id": row["id"], "reason": reason, "literal": row.get("literal", "")
                })
    ids = [r.get("id") for r in result]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate IDs after multi-book normalization")
    audit["raw_records"] = len(records)
    audit["derived_records"] = len(result)
    return result, audit
