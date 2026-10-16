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


def make_intervals(markers,header,book,limits,previous_page_last=None):
    """Read left column then right, recovering the verse at each column's top.

    The previous printed verse can legitimately occupy the top of a new
    page/column without reprinting its number. It is NOT an exception.
    A right-hand TOP RIGHT running header is the LAST verse, never the start.
    """
    bycol,issues=normalize_markers(markers,limits,book)
    if not any(bycol.values()):
        return {"L":[],"R":[]},issues+["NO_MAIN_TEXT_VERSE_MARKERS"]

    def seed(side,chapter,verse,evidence,confidence="MEDIUM"):
        return {
            "column":side,"chapter":chapter,"verse":verse,
            "y_fraction":0.0,"confidence":confidence,
            "printed_marker":"","marker_type":"INFERRED_CONTINUATION",
            "evidence":evidence,"synthetic":True
        }

    def next_verse(ch,verse):
        cap=limits.get((book,ch))
        if cap is not None and verse==cap:
            return (ch+1,1)
        return (ch,verse+1)

    def preceding(first,prior):
        """Prefer observed preceding-column/page boundary, otherwise -1."""
        ch,v=first["chapter"],first["verse"]
        candidate=None
        if prior and positive(prior.get("chapter")) and positive(prior.get("verse")):
            pch,pv=prior["chapter"],prior["verse"]
            if (ch,v)==next_verse(pch,pv):
                candidate=(pch,pv,"CONTINUES_PREVIOUS_BOUNDARY_VERSE")
            elif (ch,v)==next_verse(*next_verse(pch,pv)):
                ch2,v2=next_verse(pch,pv)
                candidate=(ch2,v2,"FIRST_UNPRINTED_VERSE_AFTER_PREVIOUS_BOUNDARY")
        if candidate is None and v>1:
            candidate=(ch,v-1,"BEFORE_FIRST_VISIBLE_VERSE_MARKER")
        return candidate

    # FIRST_ON_PAGE belongs at upper-left and is an authoritative seed.
    if (header["boundary_role"]=="FIRST_ON_PAGE" and header["visible"]
            and positive(header["chapter"]) and positive(header["verse"])):
        ch,v=header["chapter"],header["verse"]
        first=bycol["L"][0] if bycol["L"] else None
        if first and (first["chapter"],first["verse"])==(ch,v):
            # Move the FIRST boundary to 0 rather than duplicating this verse,
            # which previously created false DISCONTINUOUS warnings.
            first["y_fraction"]=0.0
            first["synthetic"]=True
            first["evidence"]="FIRST_ON_PAGE_HEADER_AND_VISIBLE_MARKER"
        else:
            bycol["L"].insert(0,seed("L",ch,v,"FIRST_ON_PAGE_RUNNING_HEAD",
                                     header["scan_confidence"]))
    elif bycol["L"] and bycol["L"][0]["y_fraction"]>0.005:
        top=preceding(bycol["L"][0],previous_page_last)
        if top:
            ch,v,evidence=top
            bycol["L"].insert(0,seed("L",ch,v,evidence))
            issues.append("PAGE_TOP_SOURCE_VERSE_RECOVERED")

    # Source verse at TOP OF RIGHT COLUMN is often the end of the left
    # column; do not default to the first numeral printed on the right.
    if bycol["R"] and bycol["R"][0]["y_fraction"]>0.005:
        left_last=bycol["L"][-1] if bycol["L"] else None
        top=preceding(bycol["R"][0],left_last)
        if top:
            ch,v,evidence=top
            bycol["R"].insert(0,seed("R",ch,v,evidence))
            issues.append("COLUMN_TOP_SOURCE_VERSE_RECOVERED")

    sequence=[(side,m) for side in ("L","R") for m in bycol[side]]
    intervals={"L":[],"R":[]}
    for i,(side,m) in enumerate(sequence):
        following=sequence[i+1][1] if i+1<len(sequence) else None
        next_in_side=(following if i+1<len(sequence)
                      and sequence[i+1][0]==side else None)
        y_end=next_in_side["y_fraction"] if next_in_side else 1.0
        if y_end<=m["y_fraction"]:
            issues.append("NONPOSITIVE_VERSE_INTERVAL")
            continue
        contiguous=follows(m,following,limits,book) if following else True
        item={
            "column":side,"chapter":m["chapter"],"verse":m["verse"],
            "y_start":m["y_fraction"],"y_end":y_end,
            "start_marker_confidence":m["confidence"],
            "from_header_seed":m["synthetic"] and
                                "FIRST_ON_PAGE" in m.get("evidence",""),
            "from_adjacent_context":m["synthetic"] and
                                "FIRST_ON_PAGE" not in m.get("evidence",""),
            "source_seed_evidence":m.get("evidence",""),
            "next_marker_contiguous":contiguous,
            "next_marker_chapter":following["chapter"] if following else None,
            "next_marker_verse":following["verse"] if following else None
        }
        intervals[side].append(item)
        if following and not contiguous:
            issues.append("DISCONTINUOUS_VERSE_SEQUENCE")

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


# Canonical BOOK chapter ceilings prevent nonsense even if the local
# verse-limit CSV lacks an entire chapter. The original CSV is sparse in the
# OCR pilot; missing rows in that CSV must not reject Exodus/Hebrews/etc.
# Verse limits remain enforced strictly whenever a CSV row is available.
CANONICAL_CHAPTERS = {
    "Gen":50,"Exod":40,"Lev":27,"Num":36,"Deut":34,
    "Josh":24,"Judg":21,"Ruth":4,"1Sam":31,"2Sam":24,
    "1Kgs":22,"2Kgs":25,"1Chr":29,"2Chr":36,
    "Ezra":10,"Neh":13,"Tob":14,"Jdt":16,
    "Esth":16,"1Macc":16,"2Macc":15,"Job":42,
    "Ps":150,"Prov":31,"Eccl":12,"Song":8,
    "Wis":19,"Sir":51,"Isa":66,"Jer":52,"Lam":5,
    "Bar":6,"Ezek":48,"Dan":14,"Hos":14,
    "Joel":4,"Amos":9,"Obad":1,"Jonah":4,
    "Mic":7,"Nah":3,"Hab":3,"Zeph":3,
    "Hag":2,"Zech":14,"Mal":4,"Matt":28,
    "Mark":16,"Luke":24,"John":21,"Acts":28,
    "Rom":16,"1Cor":16,"2Cor":13,"Gal":6,
    "Eph":6,"Phil":4,"Col":4,"1Thess":5,
    "2Thess":3,"1Tim":6,"2Tim":4,"Titus":3,
    "Phlm":1,"Heb":13,"Jas":5,"1Pet":5,
    "2Pet":3,"1John":5,"2John":1,"3John":1,
    "Jude":1,"Rev":22
}


def reference_assessment(ref,limits):
    """Validate real coordinates; distinguish sparse catalog from nonsense.

    A verse absent from the *local chapter lookup* is only provisionally
    checked against known book chapter limits + global verse 1..176.
    Do not mistake this for fully verified verse limits.
    """
    book=ref.get("book_code")
    ch=ref.get("chapter")
    typ=ref.get("type")
    if not book or book not in CANONICAL_CHAPTERS:
        return False,["UNKNOWN_CANONICAL_BOOK"]
    if not positive(ch) or ch>CANONICAL_CHAPTERS[book]:
        return False,["INVALID_BIBLE_CHAPTER"]
    if typ not in ("VERSE","VERSE_RANGE","VERSE_LIST",
                   "CHAPTER_ONLY","CHAPTER_RANGE"):
        return False,["UNPARSED_DESTINATION"]
    last_ch=ref.get("end_chapter") if typ=="CHAPTER_RANGE" else ch
    if not positive(last_ch) or last_ch<ch or last_ch>CANONICAL_CHAPTERS[book]:
        return False,["INVALID_END_CHAPTER"]
    values=[]
    if typ in ("VERSE","VERSE_RANGE"):
        values=[ref.get("verse")]
        if typ=="VERSE_RANGE":
            values.append(ref.get("end_verse"))
        if len(values)==2 and all(positive(v) for v in values) and values[0]>values[1]:
            return False,["REVERSED_VERSE_RANGE"]
    elif typ=="VERSE_LIST":
        values=ref.get("verses")
        if not isinstance(values,list) or not values:
            return False,["INVALID_VERSE_LIST"]
    if any(not positive(verse) or verse>176 for verse in values):
        return False,["IMPOSSIBLE_VERSE_NUMBER"]
    warnings=[]
    if typ=="CHAPTER_RANGE":
        checked_chapters=range(ch,last_ch+1)
    else:
        checked_chapters=(ch,)
    for chapter in checked_chapters:
        cap=limits.get((book,chapter))
        if cap is None:
            warnings.append("CHAPTER_VERSE_LIMIT_UNAVAILABLE_IN_LOCAL_CATALOG")
            continue
        if chapter==ch and any(v>cap for v in values):
            return False,["VERSE_OUTSIDE_KNOWN_CHAPTER"]
    if ref.get("status")!="PARSED":
        warnings.append("REFERENCE_PARSE_STATUS_"+str(ref.get("status")))
    return True,sorted(set(warnings))


def target_valid(ref,limits):
    return reference_assessment(ref,limits)[0]


def adjacent_verse_candidates(row,intervals,source):
    """Offer nearby PRINTED verse markers as uncertainty metadata, not new edges."""
    if source is None:
        return []
    side=row.get("side")
    found=intervals.get(side,[])
    original=next((i for i,x in enumerate(found)
                   if x["chapter"]==source["chapter"] and x["verse"]==source["verse"]
                   and x["y_start"]==source["source_verse_interval"][0]),None)
    if original is None:
        return []
    output=[]
    for j in (original-1,original+1):
        if 0<=j<len(found):
            candidate=found[j]
            output.append({"chapter":candidate["chapter"],"verse":candidate["verse"],
                           "y_start":candidate["y_start"],
                           "source":"ADJACENT_PRINTED_VERSE_MARKER",
                           "human_verified":False})
    return output


def atomic_edges(page,book,rows,intervals,limits,page_issues=None,overrides=None):
    """One printed marginal destination -> one automatically accepted edge.

    The user accepts plausible source-verse offsets of +/-1 (and other
    non-fatal OCR/layout uncertainty) WITHOUT human approval. We preserve
    uncertainty flags, but reserve EXCEPTION for genuinely unusable
    source/destination coordinates or cut-off/unreadable print.
    """
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
            blockers=[]
            notices=list(position_issues)
            if not book:
                blockers.append("SOURCE_BOOK_UNRESOLVED")
            if source is None:
                blockers.append("SOURCE_VERSE_UNRESOLVED")
            if book and source is not None and (
                    book,source["chapter"]) not in limits:
                blockers.append("SOURCE_COORDINATES_NOT_IN_CATALOG")
            elif book and source is not None and source["verse"]>limits.get(
                    (book,source["chapter"]),0):
                blockers.append("SOURCE_VERSE_OUTSIDE_CATALOG")
            destination_ok,destination_assessment=reference_assessment(ref,limits)
            if not destination_ok:
                blockers.append("DESTINATION_UNRESOLVED_OR_OUTSIDE_CATALOG")
            # A cut-off at the margin edge may truncate a *later* citation,
            # while this individual destination is fully readable. Accept the
            # usable target and record the typography/visibility caveat.
            if row.get("visibility_status") in ("CUT_OFF","UNREADABLE"):
                if not destination_ok:
                    blockers.append("MARGINAL_DESTINATION_UNREADABLE")
                else:
                    notices.append("MARGIN_TRUNCATED_BUT_THIS_TARGET_IS_READABLE")
            if row["id"] in overrides:
                blockers.append("HUMAN_CONFIRMED_CUT_OFF")
            if "BOOK_TRANSITION_ON_PAGE" in pages:
                blockers.append("SOURCE_BOOK_CHANGES_WITHIN_PAGE")
            if "PAGE_BOOK_CONFLICT" in pages:
                blockers.append("CONFLICTING_SOURCE_BOOK_EVIDENCE")

            estimate_flags=[]
            if row.get("typography_uncertain"):
                notices.append("MARGINAL_TYPOGRAPHY_ASSUMED")
            if row.get("layout_uncertain"):
                estimate_flags.append("MARGINAL_LAYOUT_ESTIMATED")
            if row.get("shifted_down_possible"):
                estimate_flags.append("MARGIN_MAY_BE_SHIFTED_BELOW_ITS_SOURCE")
            if "NEAR_VERSE_BOUNDARY" in notices:
                notices.remove("NEAR_VERSE_BOUNDARY")
                estimate_flags.append("SOURCE_WITHIN_1_8_PERCENT_OF_VERSE_BOUNDARY")
            for marker in ("LOW_VERSE_MARKER_CONFIDENCE",
                           "INCOMPLETE_VERSE_MARKER_SEQUENCE"):
                if marker in notices:
                    notices.remove(marker)
                    estimate_flags.append(marker)
            warnings=sorted(set(list(ref.get("interpretation_flags") or [])+
                                (destination_assessment if destination_ok else [])))
            for issue in sorted(pages):
                if issue in ("PAGE_END_HEADER_DISAGREES_WITH_LAST_MARKER",
                             "NONPOSITIVE_VERSE_INTERVAL",
                             "BOOK_INHERITED_FROM_PRIOR_PAGE"):
                    notices.append(issue)

            if blockers:
                status="EXCEPTION"
            elif estimate_flags:
                status="ACCEPTED_ESTIMATED"
            elif warnings or notices:
                status="ACCEPTED_FLAGGED"
            else:
                status="ACCEPTED"
            is_accepted=status!="EXCEPTION"
            output.append({
                "edge_id":eid,"image_page":page,"column":row.get("side"),
                "row_id":row["id"],"margin_y_fraction":row.get("y_fraction"),
                "printed_margin_line":row.get("raw_line"),
                "target_segment_index":idx,"destination":ref,
                "editorial_relation_marker":ref.get("relation_marker") or
                                             row.get("relation_marker","ORDINARY"),
                "destination_interpretation_flags":warnings,
                "source_alignment_estimate_flags":sorted(set(estimate_flags)),
                "possible_adjacent_source_verses":(
                    adjacent_verse_candidates(row,intervals,source)
                    if estimate_flags and source else []),
                "source":{"book_code":book,
                          "chapter":source["chapter"] if source else None,
                          "verse":source["verse"] if source else None,
                          "source_verse_interval":source["source_verse_interval"]
                                                  if source else None},
                "status":status,
                "accepted_automatically":is_accepted,
                "human_review_required":not is_accepted,
                "hard_exceptions":sorted(set(blockers)),
                "qa_reasons":sorted(set(blockers+notices)),
                "scan_human_verified":False,"database_written":False
            })
    return output


def summary(links):
    c=Counter(x["status"] for x in links)
    accepted=sum(c[status] for status in (
        "ACCEPTED","ACCEPTED_FLAGGED","ACCEPTED_ESTIMATED",
        "ACCEPTED_HUMAN_CORRECTED"))
    human=sum(1 for e in links if e.get("scan_human_verified") is True
              and e.get("accepted_automatically") is True)
    return {"atomic_links":len(links),
            "accepted":accepted,
            "accepted_plain":c["ACCEPTED"],
            "accepted_flagged":c["ACCEPTED_FLAGGED"],
            "accepted_estimated":c["ACCEPTED_ESTIMATED"],
            "accepted_human_corrected":c["ACCEPTED_HUMAN_CORRECTED"],
            "exceptions":c["EXCEPTION"],
            "acceptance_percent":round(100.0*accepted/len(links),2)
                                  if links else 0.0,
            "human_verified":human,"sql_writes":False}
