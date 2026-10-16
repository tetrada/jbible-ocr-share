#!/usr/bin/env python3
"""Respect authenticated scan-reviewed corrections, without guessing new rules.

The original OCR row and immutable original source/target remain in the edge.
One reviewed EDGE replaces only that edge, not sibling comma/semicolon links.
No scanned pages, model calls, SQL or Git writes.
"""
from copy import deepcopy
from fr88_page_layout_core import reference_assessment


def apply_reviews(edges,document,limits):
    if not document:
        return edges
    if document.get("schema")!="jbible.fr88.integrated-human-exception-review.v1":
        raise ValueError("Unexpected integrated reviewer document schema")
    reviews=document.get("reviews") or {}
    if not isinstance(reviews,dict):
        raise ValueError("Invalid saved human review map")
    for edge in edges:
        e=reviews.get(edge["edge_id"])
        if not e:
            continue
        if e.get("checked_original_scan") is not True or (
                e.get("human_review_status") not in (
                    "SCAN_CONFIRMED_LINK","SCAN_CONFIRMED_CUT_OFF","UNRESOLVED")):
            continue
        edge["original_automated_link"]={
            "source":deepcopy(edge["source"]),
            "destination":deepcopy(edge["destination"]),
            "status":edge["status"],
            "hard_exceptions":deepcopy(edge.get("hard_exceptions",[]))
        }
        edge["user_review"]={
            "choice":e.get("choice"),
            "cause":e.get("cause"),
            "notes":e.get("notes") or "",
            "reviewed_utc":e.get("reviewed_utc"),
            "human_review_status":e.get("human_review_status"),
            "checked_original_scan":True
        }
        choice=e.get("choice")
        src=e.get("source") or {}
        dst=e.get("destination") or {}
        if choice=="cut_off":
            edge["status"]="EXCEPTION"
            edge["accepted_automatically"]=False
            edge["human_review_required"]=False
            edge["hard_exceptions"]=["SCAN_CONFIRMED_UNUSABLE_CUT_OFF"]
            edge["qa_reasons"]=sorted(set(edge.get("qa_reasons",[])+
                                           ["SCAN_CONFIRMED_UNUSABLE_CUT_OFF"]))
            edge["scan_human_verified"]=True
            continue

        # Even an 'as_printed' review may contain a corrected SOURCE verse.
        # Do not ignore hand-edited source coordinates because of choice label.
        book,ch,v=src.get("book_code"),src.get("chapter"),src.get("verse")
        if book and type(ch) is int and ch>0 and type(v) is int and v>0:
            edge["source"].update({"book_code":book,"chapter":ch,"verse":v})
            edge["source"]["source_verse_interval"]=None
            edge.setdefault("source_alignment_estimate_flags",[]).append(
                "SCAN_REVIEWER_SOURCE_VERSE_CORRECTION")

        new_book,new_ch,new_verse=(
            dst.get("book_code"),dst.get("chapter"),dst.get("verse"))
        if new_book and type(new_ch) is int and new_ch>0:
            transformed=deepcopy(edge["destination"])
            transformed.update({
                "book_code":new_book,"chapter":new_ch,
                "verse":new_verse,
                "type":dst.get("type") or transformed.get("type"),
                "suffix":dst.get("suffix") if isinstance(dst.get("suffix"),str)
                         else transformed.get("suffix",""),
                "end_verse":dst.get("end_verse"),
                "end_chapter":dst.get("end_chapter"),
                "status":"PARSED"
            })
            # A reviewer may leave type UNKNOWN for a visibly complete
            # numeric prefix because the line is cut off after the comma.
            # Do not invent the unseen remainder or discard the visible verse.
            if (choice=="unresolved" and transformed.get("type")=="UNKNOWN"
                    and type(new_verse) is int and new_verse>0):
                transformed["type"]="VERSE"
                transformed.setdefault("interpretation_flags",[]).append(
                    "USER_IDENTIFIED_USABLE_VERSE_PREFIX")
            edge["destination"]=transformed

        valid,destination_warnings=reference_assessment(edge["destination"],limits)
        source_ok=(
            edge["source"].get("book_code") and
            type(edge["source"].get("chapter")) is int and
            type(edge["source"].get("verse")) is int and
            edge["source"]["chapter"]>0 and edge["source"]["verse"]>0)
        if choice in ("as_printed","corrected") and valid and source_ok:
            edge["status"]="ACCEPTED_HUMAN_CORRECTED"
            edge["accepted_automatically"]=True
            edge["human_review_required"]=False
            edge["hard_exceptions"]=[]
            edge["scan_human_verified"]=True
            edge["qa_reasons"]=sorted(set(destination_warnings+[
                "USER_SCAN_CONFIRMED_THIS_EXACT_EDGE"]))
        elif choice=="unresolved" and valid and source_ok:
            # For scanned cut-offs containing a clearly usable first target,
            # retain the recovered edge as an ESTIMATE, *not* as confirmed.
            # This is specifically the user's preference to recover visible
            # prefixes without inventing invisible continuation references.
            edge["status"]="ACCEPTED_ESTIMATED"
            edge["accepted_automatically"]=True
            edge["human_review_required"]=False
            edge["hard_exceptions"]=[]
            edge["scan_human_verified"]=False
            edge["qa_reasons"]=sorted(set(destination_warnings+[
                "VISIBLE_COORDINATE_RECOVERED_FROM_PARTIAL_ROW",
                "USER_DID_NOT_MARK_THIS_LINK_FULLY_CONFIRMED"]))
        else:
            edge["status"]="EXCEPTION"
            edge["accepted_automatically"]=False
            edge["human_review_required"]=False
            edge["hard_exceptions"]=["SCAN_REVIEWED_BUT_NO_USABLE_REFERENCE"]
            edge["qa_reasons"]=sorted(set(edge.get("qa_reasons",[])+
                                           edge["hard_exceptions"]))
    return edges
