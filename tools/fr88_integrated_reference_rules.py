#!/usr/bin/env python3
"""Edition-aware normalization into ONE destination record per target verse.

Keep printed raw_line unchanged. Per-row shorthand without an explicit book
uses the *source page's* book; shorthand within a semicolon row inherits the
last explicit printed book (handled already by fr88_v2_normalize).

The printed Croat/FR Jerusalem Bible notes establish:
 '=' literary doublet in same book, '||' parallel across different books,
 's' this + following verses, 'p' parallel passages, '+' additional footnote.
No extra verse numbers or endpoints are inferred from editorial suffixes.

One printed verse list "Si 43 6,7" => TWO independently addressable edges.
Heuristically restored missing first letter/ordinal is an AUDITED ASSUMPTION.
No SQL writes, provider calls, or mutation of original OCR text.
"""
import copy
import re
from fr88_v2_normalize import interpret_line, SOURCE_BARE


def marker_of(line):
    s=(line or "").lstrip()
    if s.startswith(("||","∥","Ⅱ","‖")):
        return "CROSS_BOOK_PARALLEL"
    if s.startswith("="):
        return "SAME_BOOK_DOUBLET"
    if s.startswith(("↗","→","↖","←")):
        return "SCRIPTURAL_QUOTATION"
    return "ORDINARY"


def canonicalize(row,page_book,catalog_path):
    """Return new dict with exact raw_line and flattened atomic destinations."""
    output=dict(row)
    if row.get("kind")!="REFERENCE":
        output["references"]=[]
        return output
    original=row.get("raw_line","")
    if not isinstance(original,str):
        raise ValueError("Invalid printed margin row")
    marker=marker_of(original)
    assumption=None
    # Restrict typo repair to leading, previously known OCR failure patterns.
    # Never claim that corrected text was literally printed.
    corrected=original
    if re.match(r"^\s*Ch\s+\d",original,re.IGNORECASE):
        corrected=re.sub(r"^(\s*)Ch(?=\s+\d)",r"\g<1>1 Ch",original,count=1,flags=re.I)
        assumption="PROVISIONAL_MISSING_BOOK_ORDINAL_1_CHR"
    elif re.match(r"^\s*s\s+\d",original):
        corrected=re.sub(r"^(\s*)s(?=\s+\d)",r"\g<1>Is",original,count=1)
        assumption="PROVISIONAL_MISSING_BOOK_INITIAL_ISA"
    # Parallel markers and editorial "cf." are not destination coordinates.
    # Preserve original typography in raw_line, normalize only the parser view.
    parse_text=re.sub(r"^\s*(?:\|\||∥|Ⅱ|‖)\s*", "",corrected)
    parse_text=re.sub(r"(?i)\bcf\s*\.\s*(?=[A-Za-z])","",parse_text)
    # Editorial "cf." and "cf. déjà" are NOT target numbers.
    parse_text=re.sub(r"(?i)^\s*cf\s*\.\s*(?:déjà\s+)?", "",parse_text)
    # End-of-coordinate full stops, not dotted verse lists, are punctuation.
    parse_text=re.sub(r"\.(?=\s*(?:;|$))", "",parse_text)
    # An editorial + suffix can end one bare reference followed by a new
    # chapter/verse in the SAME physical printed row. Keep the original raw
    # line unchanged; only insert a parser-view separator at that boundary.
    # Real scan p0063: "22 16-17+ 28 14" -> Gen 22:16-17+; Gen 28:14.
    parse_text=re.sub(r"(?<=\+)\s+(?=\d{1,3}\s+\d{1,3}(?:\b|[-–—]))",
                      "; ",parse_text)
    # Chapter-only editorial shorthand: 'ch. 27.' means the whole chapter,
    # not a malformed target. Never treat bare 'ch.' as a book code.
    chapter_note=bool(re.fullmatch(r"(?i)\s*ch(?:ap)?\.\s*\d{1,3}\.?\s*",parse_text))
    if chapter_note:
        parse_text=re.sub(r"(?i)^\s*ch(?:ap)?\.\s*(\d{1,3})\.?\s*$",
                          r"\1",parse_text)
    parsed=interpret_line(parse_text,str(catalog_path),
                          layout_uncertain=bool(row.get("layout_uncertain")))
    atomic=[]
    for outer_index,part in enumerate(parsed,1):
        item=copy.deepcopy(part)
        flags=[]
        if not item.get("book_code") and page_book and item.get("type")!="UNRESOLVED_NUMERIC":
            # Bare target without a preceding explicit book (within THIS row)
            # references the known PAGE BOOK, not the previous printed row.
            item["book_code"]=page_book
            item["status"]="PARSED" if not row.get("layout_uncertain") else "NEEDS_LAYOUT_REVIEW"
            item["book_resolution"]="SOURCE_PAGE_BOOK"
        elif item.get("book_code"):
            item["book_resolution"]=(
                "OCR_BOOK_REPAIR_ASSUMED" if assumption else
                "EXPLICIT_OR_INHERITED_WITHIN_ROW")
        else:
            item["book_resolution"]="UNRESOLVED"
        if assumption:
            flags.append(assumption)
        if chapter_note:
            flags.append("EDITORIAL_CHAPTER_ONLY_SHORTHAND")
        if item.get("status")!="PARSED":
            flags.append("DESTINATION_NOT_YET_PARSED")
        if item.get("book_code") is None:
            flags.append("DESTINATION_BOOK_UNKNOWN")
        item["relation_marker"]=marker
        item["ocr_book_assumption"]=assumption
        # Support verse-list expansion without dropping the original print:
        # "Si 43 6,7" represents independent Sir 43:6 and Sir 43:7 edges.
        if item.get("type")=="VERSE_LIST" and isinstance(item.get("verses"),list):
            verses=item.pop("verses")
            for sub_index,verse in enumerate(verses,1):
                ref=copy.deepcopy(item)
                ref["type"]="VERSE"
                ref["verse"]=verse
                ref["end_verse"]=None
                ref["parent_type"]="VERSE_LIST"
                ref["parent_segment_index"]=outer_index
                ref["member_index"]=sub_index
                ref["printed_target_group"]=part.get("literal")
                ref["interpretation_flags"]=list(flags)
                atomic.append(ref)
        elif item.get("type")=="VERSE_MIXED_LIST" and isinstance(item.get("members"),list):
            members=item.pop("members")
            for sub_index,member in enumerate(members,1):
                ref=copy.deepcopy(item)
                ref.update({key:member.get(key) for key in (
                    "type","verse","end_verse")})
                ref["parent_type"]="VERSE_MIXED_LIST"
                ref["parent_segment_index"]=outer_index
                ref["member_index"]=sub_index
                ref["printed_target_group"]=part.get("literal")
                ref["interpretation_flags"]=list(flags)
                atomic.append(ref)
        else:
            item["parent_segment_index"]=outer_index
            item["member_index"]=1
            item["printed_target_group"]=part.get("literal")
            item["interpretation_flags"]=list(flags)
            atomic.append(item)
    for n,ref in enumerate(atomic,1):
        ref["atomic_target_index"]=n
    output["references"]=atomic
    output["relation_marker"]=marker
    output["raw_line_original"]=original
    output["ocr_book_repair_proposal"]=corrected if assumption else None
    output["ocr_book_assumption"]=assumption
    return output

def canonicalize_contiguous_rows(rows,page_book,catalog_path):
    """Resolve book shorthand when the OCR split one semicolon group into rows.

    Only a same-side, <=2.5%-page-height next line with a bare numeric
    citation after a trailing semicolon can inherit the previous line's
    final destination book. Preserve both printed rows and their stable IDs.
    Ordinary new rows still reset the target book to this page's source book.
    """
    output=[]
    for raw in rows:
        current=canonicalize(raw,page_book,catalog_path)
        previous=output[-1] if output else None
        if previous and previous.get("kind")=="REFERENCE" and \
                current.get("kind")=="REFERENCE" and \
                previous.get("side") in ("L","R") and \
                previous.get("side")==current.get("side") and \
                str(previous.get("raw_line") or "").rstrip().endswith(";") and \
                re.match(r"^\s*(?:[=↗↖→←]\s*)?\d{1,3}\s+\d{1,3}",
                         str(current.get("raw_line") or "")):
            y1,y2=previous.get("y_fraction"),current.get("y_fraction")
            if (type(y1) in (float,int) and type(y2) in (float,int) and
                    0 <= y2-y1 <= 0.025 and previous.get("references")):
                inherited=previous["references"][-1].get("book_code")
                # Only fill references that otherwise default to PAGE_BOOK.
                if inherited and any(r.get("book_resolution")=="SOURCE_PAGE_BOOK"
                                     for r in current.get("references",[])):
                    current=canonicalize(raw,inherited,catalog_path)
                    for ref in current.get("references",[]):
                        if ref.get("book_resolution")=="SOURCE_PAGE_BOOK":
                            ref["book_resolution"]="ADJACENT_SEMICOLON_ROW"
                            ref["book_inheritance_source_row_id"]=previous.get("id")
                            ref["interpretation_flags"]=sorted(set(
                                ref.get("interpretation_flags",[])+[
                                    "TARGET_BOOK_INHERITED_FROM_ADJACENT_SEMICOLON_ROW"]))
                    current["wrapped_book_inheritance_from_row_id"]=previous.get("id")
        output.append(current)
    return output
