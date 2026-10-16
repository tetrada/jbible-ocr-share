#!/usr/bin/env python3
"""Pure, deterministic French Jerusalem Bible page geometry -> atomic links.

An image contains L/R *text columns*. Printed running heads are PAGE metadata:
on a left-hand printed page the top-left pair can mark the FIRST verse, while
on a right-hand printed page the top-right pair can mark the LAST verse.
Do not mistake top-right LAST for page start.

Vision extracts observed marker positions once. This module never asks DeepSeek
to guess individual source verses. It assigns the row to the *interval* of the
visible preceding main-text verse marker, taking column order into account.

Every independently parsed marginal target produces ONE independent edge.
No AI calls, no database operations, no silent promotion to human-verified.
"""
import csv
import math
from collections import Counter
from pathlib import Path


def positive(v):
    return type(v) is int and v>=1


def fraction(v):
    return type(v) in (int,float) and math.isfinite(v) and 0<=v<=1


def catalog_limits(path):
    with Path(path).open(encoding="utf-8-sig",newline="") as f:
        return {(r["book_code"],int(r["chap_number"])):int(r["max_verse"])
                for r in csv.DictReader(f) if r["record_type"]=="C"}


def header_checked(head):
    """Validate headers without inferring whether left/right means first/last."""
    if not isinstance(head,dict):
        raise ValueError("Page header must be a JSON object")
    position=head.get("header_position","NONE")
    role=head.get("boundary_role","UNKNOWN")
    if position not in ("TOP_LEFT","TOP_RIGHT","NONE","UNREADABLE"):
        raise ValueError("Invalid printed running-head position")
    if role not in ("FIRST_ON_PAGE","LAST_ON_PAGE","UNKNOWN"):
        raise ValueError("Invalid printed running-head role")
    chapter,verse=head.get("chapter"),head.get("verse")
    if chapter is not None and not positive(chapter):
        raise ValueError("Invalid page running-head chapter")
    if verse is not None and not positive(verse):
        raise ValueError("Invalid page running-head verse")
    # Do NOT convert a top-right last-verse header into a first-verse seed.
    if position=="TOP_RIGHT" and role=="FIRST_ON_PAGE":
        raise ValueError("Top-right end-of-page marker cannot silently be a start")
    if position=="TOP_LEFT" and role=="LAST_ON_PAGE":
        raise ValueError("Top-left page-start marker cannot silently be a page end")
    return {"header_position":position,"boundary_role":role,
            "chapter":chapter,"verse":verse,
            "book_code":head.get("book_code"),
            "book_title":head.get("book_title"),
            "scan_confidence":head.get("confidence","LOW"),
            "raw":head.get("running_head_raw"),
            "visible":head.get("visible") is True}


def normalize_markers(markers,limits,book):
    """Require real chapter/verse markers, sorted within each text column."""
    if not isinstance(markers,list):
        raise ValueError("Missing main-text verse marker list")
    clean={"L":[],"R":[]}
    issues=[]
    for original in markers:
        if not isinstance(original,dict):
            issues.append("NON_OBJECT_MARKER")
            continue
        side=original.get("column")
        ch,v=original.get("chapter"),original.get("verse")
        y=original.get("y_fraction")
        if side not in clean or not positive(ch) or not positive(v) or not fraction(y):
            issues.append("INVALID_MARKER_FIELDS")
            continue
        if book and (book,ch) in limits and v>limits[book,ch]:
            issues.append("VERSE_OUT_OF_CATALOG")
            continue
        if book and (book,ch) not in limits:
            issues.append("CHAPTER_OUT_OF_CATALOG")
            continue
        clean[side].append({
            "column":side,"chapter":ch,"verse":v,"y_fraction":y,
            "confidence":original.get("confidence","LOW"),
            "printed_marker":str(original.get("printed_marker") or "")[:28],
            "marker_type":original.get("marker_type","VERSE"),
            "evidence":str(original.get("evidence") or "")[:90],
            "synthetic":False
        })
    for side in ("L","R"):
        clean[side].sort(key=lambda x:x["y_fraction"])
        unique=[]
        for marker in clean[side]:
            if (unique and
                (unique[-1]["chapter"],unique[-1]["verse"])==
                (marker["chapter"],marker["verse"]) and
                abs(marker["y_fraction"]-unique[-1]["y_fraction"])<0.012):
                if marker["confidence"]=="HIGH" and unique[-1]["confidence"]!="HIGH":
                    unique[-1]=marker
                continue
            unique.append(marker)
        clean[side]=unique
    return clean,issues


def follows(previous,next_,limits,book):
    """Is the observed next marker the next verse/chapter? Otherwise gap."""
    if previous["chapter"]==next_["chapter"]:
        return next_["verse"]==previous["verse"]+1
    if next_["chapter"]==previous["chapter"]+1 and next_["verse"]==1:
        maxv=limits.get((book,previous["chapter"]))
        return maxv is None or previous["verse"]==maxv
    return False


def make_intervals(markers,header,book,limits):
    """Read left column top-to-bottom, followed by right column top-to-bottom."""
    bycol,issues=normalize_markers(markers,limits,book)
    sequence=[(s,m) for s in ("L","R") for m in bycol[s]]
    # The left-hand-page running head gives the starting verse even if its
    # small main-text verse marker isn't reprinted at y=0.
    if (header["boundary_role"]=="FIRST_ON_PAGE" and header["visible"]
            and positive(header["chapter"]) and positive(header["verse"])):
        seed={"column":"L","chapter":header["chapter"],"verse":header["verse"],
              "y_fraction":0.0,"confidence":header["scan_confidence"],
              "printed_marker":str(header.get("raw") or ""),
              "marker_type":"RUNNING_START","evidence":"top-left first verse",
              "synthetic":True}
        if bycol["L"] and bycol["L"][0]["y_fraction"]<=0.055 and (
             bycol["L"][0]["chapter"],bycol["L"][0]["verse"])==(
             seed["chapter"],seed["verse"]):
            # A genuinely printed first verse marker is stronger evidence.
            pass
        else:
            sequence.insert(0,("L",seed))
    if not sequence:
        return {"L":[],"R":[]},issues+["NO_MAIN_TEXT_VERSE_MARKERS"]
    intervals={"L":[],"R":[]}
    for i,(side,m) in enumerate(sequence):
        # End is next printed verse start in the SAME column; a column
        # transition ends at image bottom and resumes at top of next column.
        following=sequence[i+1][1] if i+1<len(sequence) else None
        next_in_side=following if i+1<len(sequence) and sequence[i+1][0]==side else None
        y_end=next_in_side["y_fraction"] if next_in_side else 1.0
        if y_end<=m["y_fraction"]:
            issues.append("NONPOSITIVE_VERSE_INTERVAL")
            continue
        contiguous=follows(m,following,limits,book) if following else True
        item={"column":side,"chapter":m["chapter"],"verse":m["verse"],
              "y_start":m["y_fraction"],"y_end":y_end,
              "start_marker_confidence":m["confidence"],
              "from_header_seed":m["synthetic"],
              "next_marker_contiguous":contiguous,
              "next_marker_chapter":following["chapter"] if following else None,
              "next_marker_verse":following["verse"] if following else None}
        intervals[side].append(item)
        if following and not contiguous:
            issues.append("DISCONTINUOUS_VERSE_SEQUENCE")
    # On a right-hand book page the printed top-right header describes the
    # LAST verse, not the first. Validate the boundary; never use it to
    # anchor the first verse at the top of the page.
    if (header["boundary_role"]=="LAST_ON_PAGE" and header["visible"]
            and positive(header["chapter"]) and positive(header["verse"])):
        last=sequence[-1][1]
        if (header["chapter"],header["verse"])!=(
                last["chapter"],last["verse"]):
            issues.append("PAGE_END_HEADER_DISAGREES_WITH_LAST_MARKER")
    return intervals,sorted(set(issues))


def choose_source(row,intervals):
    """Find source solely by column/y interval; never by target reference."""
    col=row.get("side")
    y=row.get("y_fraction")
    if col not in ("L","R") or not fraction(y):
        return None,["MISSING_MARGIN_GEOMETRY"]
    candidates=[it for it in intervals.get(col,[])
                if it["y_start"]<=y<it["y_end"] or
                   (y==1 and it["y_end"]==1)]
    if len(candidates)!=1:
        return None,["VERSE_INTERVAL_NOT_UNIQUE" if candidates else "NO_VERSE_INTERVAL_AT_MARGIN"]
    it=candidates[0]
    issues=[]
    if it["start_marker_confidence"] not in ("HIGH","MEDIUM"):
        issues.append("LOW_VERSE_MARKER_CONFIDENCE")
    if not it["next_marker_contiguous"]:
        issues.append("INCOMPLETE_VERSE_MARKER_SEQUENCE")
    if min(y-it["y_start"],it["y_end"]-y)<0.018:
        issues.append("NEAR_VERSE_BOUNDARY")
    return {"chapter":it["chapter"],"verse":it["verse"],
            "column":col,"source_verse_interval":[it["y_start"],it["y_end"]],
            "source_marker_from_page_header":it["from_header_seed"],
            "source_evidence":"PRINTED_VERSE_POSITION_INTERVAL"},issues


def target_valid(ref,limits):
    if ref.get("status")!="PARSED":
        return False
    book=ref.get("book_code")
    ch=ref.get("chapter")
    if not book or (book,ch) not in limits:
        return False
    typ=ref.get("type")
    if typ in ("VERSE","VERSE_RANGE"):
        a=ref.get("verse")
        b=ref.get("end_verse") if typ=="VERSE_RANGE" else a
        return positive(a) and positive(b) and a<=b<=limits[book,ch]
    if typ=="VERSE_LIST":
        verses=ref.get("verses")
        return isinstance(verses,list) and bool(verses) and all(
            positive(x) and x<=limits[book,ch] for x in verses)
    if typ=="CHAPTER_ONLY":
        return True
    if typ=="CHAPTER_RANGE":
        b=ref.get("end_chapter")
        return positive(b) and b>=ch and all(
            (book,k) in limits for k in range(ch,b+1))
    return False


def atomic_edges(page,book,rows,intervals,limits,page_issues=None,overrides=None):
    """Flatten one margin printed ROW into N independent destination edges."""
    pages=set(page_issues or [])
    overrides=set(overrides or [])
    output=[]
    used=set()
    for row in rows:
        if row.get("kind")!="REFERENCE":
            continue
        source,position_issues=choose_source(row,intervals)
        for idx,ref in enumerate(row.get("references") or [],1):
            eid="%s/target%02d"%(row["id"],idx)
            if eid in used:
                raise ValueError("Duplicate atomic source-target edge: "+eid)
            used.add(eid)
            reasons=list(position_issues)
            if not book: reasons.append("SOURCE_BOOK_UNRESOLVED")
            if not target_valid(ref,limits): reasons.append("DESTINATION_UNRESOLVED")
            if row.get("visibility_status") in ("CUT_OFF","UNREADABLE"):
                reasons.append("MARGINAL_TEXT_NOT_FULLY_VISIBLE")
            if row.get("layout_uncertain") or row.get("typography_uncertain"):
                reasons.append("MARGINAL_TYPOGRAPHY_UNCERTAIN")
            if row["id"] in overrides:
                reasons.append("HUMAN_CONFIRMED_CUT_OFF")
            if any(q in pages for q in ("PAGE_BOOK_CONFLICT",
                                        "BOOK_TRANSITION_ON_PAGE",
                                        "PAGE_END_HEADER_DISAGREES_WITH_LAST_MARKER",
                                        "NONPOSITIVE_VERSE_INTERVAL")):
                reasons.append("PAGE_LAYOUT_CONFLICT")
            status="REVIEW_REQUIRED" if reasons else "AUTO_PROPOSED"
            output.append({
                "edge_id":eid,"image_page":page,"column":row.get("side"),
                "row_id":row["id"],"margin_y_fraction":row.get("y_fraction"),
                "printed_margin_line":row.get("raw_line"),
                "target_segment_index":idx,"destination":ref,
                "source":{"book_code":book,
                          "chapter":source["chapter"] if source else None,
                          "verse":source["verse"] if source else None,
                          "source_verse_interval":source["source_verse_interval"] if source else None},
                "status":status,"qa_reasons":sorted(set(reasons)),
                "scan_human_verified":False,"database_written":False
            })
    return output


def summary(links):
    c=Counter(x["status"] for x in links)
    return {"atomic_links":len(links),"auto_proposed":c["AUTO_PROPOSED"],
            "needs_review":c["REVIEW_REQUIRED"],
            "human_verified":0,"sql_writes":False}
