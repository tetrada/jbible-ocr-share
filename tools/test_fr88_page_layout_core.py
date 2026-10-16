#!/usr/bin/env python3
"""Synthetic, fully offline correctness tests for page header geometry and links.

No scan images, API calls, databases or external packages needed.
"""
import fr88_page_layout_core as g


def test():
    limits={
       ("Gen",2):25,("Gen",3):24,("Gen",24):67,
       ("Exod",16):36,("Ps",78):72,("Ps",105):45,
       ("Rom",6):23,("Rev",16):21,
    }
    # Page 33: left-hand MAIN TEXT marker 2:17 starts above Rm 6:23;
    # verse 18 begins BELOW the target. It must map to Genesis 2:17.
    left=[
        {"column":"L","chapter":2,"verse":16,"y_fraction":.21,"confidence":"HIGH"},
        {"column":"L","chapter":2,"verse":17,"y_fraction":.335,"confidence":"HIGH"},
        {"column":"L","chapter":2,"verse":18,"y_fraction":.51,"confidence":"HIGH"},
        {"column":"L","chapter":2,"verse":19,"y_fraction":.65,"confidence":"HIGH"},
    ]
    head=g.header_checked({"header_position":"TOP_LEFT",
        "boundary_role":"FIRST_ON_PAGE","chapter":2,"verse":15,
        "book_code":"Gen","visible":True,"confidence":"HIGH"})
    intervals,issues=g.make_intervals(left,head,"Gen",limits)
    row={"id":"fr88i:p0033:L:006","image_page":33,"kind":"REFERENCE",
         "side":"L","raw_line":"Rm 6 23","y_fraction":.452,
         "visibility_status":"COMPLETE","layout_uncertain":False,
         "typography_uncertain":False,
         "references":[{"status":"PARSED","type":"VERSE","book_code":"Rom",
                        "chapter":6,"verse":23,"literal":"6 23","book_printed":"Rm"}]}
    src,flags=g.choose_source(row,intervals)
    assert (src["chapter"],src["verse"])==(2,17)
    assert not flags, flags
    edges=g.atomic_edges(33,"Gen",[row],intervals,limits,issues)
    assert len(edges)==1
    assert edges[0]["source"]["book_code"]=="Gen"
    assert edges[0]["source"]["chapter"]==2 and edges[0]["source"]["verse"]==17
    assert edges[0]["destination"]["book_code"]=="Rom"
    assert edges[0]["destination"]["verse"]==23
    assert edges[0]["status"]=="ACCEPTED"
    assert edges[0]["accepted_automatically"] is True
    assert edges[0]["human_review_required"] is False
    assert edges[0]["scan_human_verified"] is False
    assert edges[0]["database_written"] is False

    # THREE independent records with one common source, NEVER a combined link.
    many=dict(row,id="fr88i:p0033:L:007",
       raw_line="Ps 78 47s; 105 32; Ap 16 21",references=[
       {"status":"PARSED","type":"VERSE","book_code":"Ps","chapter":78,"verse":47,"suffix":"s"},
       {"status":"PARSED","type":"VERSE","book_code":"Ps","chapter":105,"verse":32},
       {"status":"PARSED","type":"VERSE","book_code":"Rev","chapter":16,"verse":21}])
    edges=g.atomic_edges(33,"Gen",[many],intervals,limits)
    assert len(edges)==3 and len({x["edge_id"] for x in edges})==3
    assert all(x["source"]["verse"]==17 and x["source"]["book_code"]=="Gen" for x in edges)
    assert [(x["destination"]["book_code"],x["destination"]["chapter"],
             x["destination"]["verse"]) for x in edges]==[
                ("Ps",78,47),("Ps",105,32),("Rev",16,21)]

    # RIGHT-HAND printed page top RIGHT means the LAST verse, never first.
    end=g.header_checked({"header_position":"TOP_RIGHT",
        "boundary_role":"LAST_ON_PAGE","chapter":24,"verse":45,
        "book_code":"Gen","visible":True,"confidence":"HIGH"})
    assert end["boundary_role"]=="LAST_ON_PAGE"
    # Page 47's observed top-right header was MISLABELED as FIRST
    # in the provider JSON. Interpret according to printed position,
    # retain the error and NEVER seed this as the page's first verse.
    wrong_model=g.header_checked({"header_position":"TOP_RIGHT",
        "boundary_role":"FIRST_ON_PAGE","chapter":24,"verse":45,
        "book_code":"Gen","visible":True,"confidence":"HIGH",
        "running_head_raw":"24 45"})
    assert wrong_model["boundary_role"]=="LAST_ON_PAGE"
    assert wrong_model["original_model_boundary_role"]=="FIRST_ON_PAGE"
    assert wrong_model["boundary_role_repaired"] is True
    assert "RUNNING_HEADER_ROLE_REPAIRED_TOP_RIGHT_IS_PAGE_END" in wrong_model["header_audit_warnings"]
    left_role_wrong=g.header_checked({"header_position":"TOP_LEFT",
        "boundary_role":"LAST_ON_PAGE","chapter":3,"verse":7,
        "book_code":"Gen","visible":True,"confidence":"MEDIUM"})
    assert left_role_wrong["boundary_role"]=="FIRST_ON_PAGE"
    assert left_role_wrong["boundary_role_repaired"] is True
    endmarkers=[
       {"column":"L","chapter":24,"verse":42,"y_fraction":.4,"confidence":"HIGH"},
       {"column":"R","chapter":24,"verse":43,"y_fraction":.06,"confidence":"HIGH"},
       {"column":"R","chapter":24,"verse":44,"y_fraction":.45,"confidence":"HIGH"},
       {"column":"R","chapter":24,"verse":45,"y_fraction":.81,"confidence":"HIGH"}]
    intervals,issues=g.make_intervals(endmarkers,end,"Gen",limits)
    assert not any(x["from_header_seed"] for side in ("L","R") for x in intervals[side])
    corrected_intervals,role_issues=g.make_intervals(endmarkers,wrong_model,
                                                     "Gen",limits)
    assert "PAGE_END_HEADER_DISAGREES_WITH_LAST_MARKER" not in role_issues
    assert not any(x["from_header_seed"] for side in ("L","R")
                   for x in corrected_intervals[side])
    assert "PAGE_END_HEADER_DISAGREES_WITH_LAST_MARKER" not in issues
    wrong=dict(end,verse=44)
    _,issues=g.make_intervals(endmarkers,wrong,"Gen",limits)
    assert "PAGE_END_HEADER_DISAGREES_WITH_LAST_MARKER" in issues

    # An inconsistent model role is REPAIRED, never used as a page start.
    repaired=g.header_checked({
        "header_position":"TOP_RIGHT","boundary_role":"FIRST_ON_PAGE",
        "chapter":24,"verse":45,"visible":True})
    assert repaired["boundary_role"]=="LAST_ON_PAGE"
    assert repaired["boundary_role_repaired"] is True
    # Restore page 33's left-column verse geometry after testing page 24.
    intervals,_=g.make_intervals(left,head,"Gen",limits)
    # If the source is visibly near a verse boundary, do not make the
    # user manually check thousands of 1-verse offsets. Keep one source
    # estimate plus nearby printed alternatives and a machine-readable flag.
    near=dict(row,id="fr88i:p0033:L:010",y_fraction=.506)
    estimated=g.atomic_edges(33,"Gen",[near],intervals,limits)
    assert len(estimated)==1
    assert estimated[0]["status"]=="ACCEPTED_ESTIMATED"
    assert estimated[0]["accepted_automatically"] is True
    assert estimated[0]["human_review_required"] is False
    assert estimated[0]["source"]["verse"]==17
    assert estimated[0]["possible_adjacent_source_verses"][0]["verse"]==16
    assert estimated[0]["possible_adjacent_source_verses"][1]["verse"]==18
    shifted=dict(row,id="fr88i:p0033:L:011",
                 shifted_down_possible=True,layout_uncertain=True)
    estimated=g.atomic_edges(33,"Gen",[shifted],intervals,limits)
    assert estimated[0]["status"]=="ACCEPTED_ESTIMATED"
    assert estimated[0]["accepted_automatically"] is True
    assert estimated[0]["human_review_required"] is False
    assert "MARGIN_MAY_BE_SHIFTED_BELOW_ITS_SOURCE" in estimated[0]["source_alignment_estimate_flags"]
    unstructured=dict(row,id="fr88i:p0033:L:012",layout_uncertain=True)
    assert g.atomic_edges(33,"Gen",[unstructured],intervals,limits)[0]["accepted_automatically"] is True

    # A marker gap MUST flag the candidate, not fill a guessed source.
    skip=[{"column":"L","chapter":2,"verse":17,"y_fraction":.3,"confidence":"HIGH"},
          {"column":"L","chapter":2,"verse":20,"y_fraction":.6,"confidence":"HIGH"}]
    intervals,issues=g.make_intervals(skip,{"header_position":"NONE",
        "boundary_role":"UNKNOWN","chapter":None,"verse":None,"visible":False},
        "Gen",limits)
    src,flags=g.choose_source(row,intervals)
    assert src["verse"]==17
    assert "INCOMPLETE_VERSE_MARKER_SEQUENCE" in flags
    assert g.atomic_edges(33,"Gen",[row],intervals,limits)[0]["status"]=="ACCEPTED_ESTIMATED"
    cut=dict(row,id="fr88i:p0033:L:009",visibility_status="CUT_OFF",
             typography_uncertain=True)
    # Partial margin cutoffs can still contain a FULL usable destination.
    cut_link=g.atomic_edges(33,"Gen",[cut],intervals,limits)[0]
    assert cut_link["status"] in ("ACCEPTED_FLAGGED","ACCEPTED_ESTIMATED")
    assert cut_link["accepted_automatically"] is True
    assert "MARGIN_TRUNCATED_BUT_THIS_TARGET_IS_READABLE" in cut_link["qa_reasons"]
    broken=dict(cut,id="fr88i:p0033:L:021",
        references=[dict(row["references"][0],type="UNRESOLVED_NUMERIC",
                         verse=None)])
    assert g.atomic_edges(33,"Gen",[broken],intervals,limits)[0]["status"]=="EXCEPTION"
    # Restore the normal full marker map after the deliberate missing-marker test.
    intervals,_=g.make_intervals(left,head,"Gen",limits)
    # A plausible repaired book abbreviation is ACCEPTED, with audit flags.
    fixed=dict(row,id="fr88i:p0033:L:013",references=[
        dict(row["references"][0],
             interpretation_flags=["PROVISIONAL_MISSING_BOOK_INITIAL_ISA"])],
         typography_uncertain=True)
    fixed_link=g.atomic_edges(33,"Gen",[fixed],intervals,limits)[0]
    assert fixed_link["status"]=="ACCEPTED_FLAGGED"
    assert fixed_link["accepted_automatically"] is True
    assert fixed_link["human_review_required"] is False
    # Pure warning on a running page header is not a veto of valid verses.
    head_notice=g.atomic_edges(33,"Gen",[row],intervals,limits,
        ["PAGE_END_HEADER_DISAGREES_WITH_LAST_MARKER"])[0]
    assert head_notice["status"]=="ACCEPTED_FLAGGED"
    assert head_notice["accepted_automatically"] is True

    # Invalid target book/chapter is genuinely unusable, not a +/-1 estimate.
    bad=dict(row,id="fr88i:p0033:L:020",references=[
        dict(row["references"][0],chapter=1001)])
    invalid=g.atomic_edges(33,"Gen",[bad],intervals,limits)[0]
    assert invalid["status"]=="EXCEPTION"
    assert "DESTINATION_UNRESOLVED_OR_OUTSIDE_CATALOG" in invalid["hard_exceptions"]
    assert invalid["human_review_required"] is True
    # Missing source book is a real blocker; a printed nearby verse is not.
    no_book=g.atomic_edges(33,None,[row],intervals,limits)[0]
    assert no_book["status"]=="EXCEPTION"
    assert no_book["accepted_automatically"] is False
    aggregate=g.summary([fixed_link,head_notice,invalid,no_book,
                         g.atomic_edges(33,"Gen",[shifted],intervals,limits)[0]])
    assert aggregate["accepted"]==3
    assert aggregate["exceptions"]==2
    assert aggregate["accepted_estimated"]==1
    # Real published page39: OCR transcribed TOP_LEFT header Gen 1:22,
    # while body main-text begins Gen 8:18 (previous page ends 8:17).
    # Never create an accepted source in the unrelated chapter 1.
    page39_header=g.header_checked({
        "header_position":"TOP_LEFT","boundary_role":"FIRST_ON_PAGE",
        "chapter":1,"verse":22,"visible":True,
        "book_code":"Gen","confidence":"HIGH"
    })
    page39_markers=[
        {"column":"L","chapter":8,"verse":18,"y_fraction":.14,"confidence":"HIGH"},
        {"column":"L","chapter":8,"verse":19,"y_fraction":.17,"confidence":"HIGH"},
        {"column":"R","chapter":9,"verse":7,"y_fraction":.25,"confidence":"HIGH"}
    ]
    page39_intervals,page39_issues=g.make_intervals(
        page39_markers,page39_header,"Gen",{},
        previous_page_last={"chapter":8,"verse":17})
    assert "PAGE_START_HEADER_CONTRADICTS_BODY" in page39_issues
    assert not any(i["chapter"]==1 and i["verse"]==22
                   for col in page39_intervals.values() for i in col)
    first,flags=g.choose_source({"side":"L","y_fraction":.08},
                                page39_intervals)
    assert first is not None and (first["chapter"],first["verse"])==(8,17)

    # Real published page42: the second column starts in chapter 11 while
    # the first column has already reached chapter 12. This is an OCR
    # contradiction; accept plausible links only as visibly estimated.
    page42_markers=[
        {"column":"L","chapter":11,"verse":26,"y_fraction":.07,"confidence":"HIGH"},
        {"column":"L","chapter":12,"verse":6,"y_fraction":.77,"confidence":"HIGH"},
        {"column":"R","chapter":11,"verse":30,"y_fraction":.072,"confidence":"HIGH"},
        {"column":"R","chapter":11,"verse":31,"y_fraction":.104,"confidence":"HIGH"}
    ]
    page42_header=g.header_checked({
        "header_position":"TOP_LEFT","boundary_role":"FIRST_ON_PAGE",
        "chapter":11,"verse":26,"visible":True,
        "book_code":"Gen","confidence":"HIGH"
    })
    page42_intervals,page42_issues=g.make_intervals(
        page42_markers,page42_header,"Gen",{})
    assert "COLUMN_VERSE_SEQUENCE_REWINDS" in page42_issues
    print("PASS: +/-1, layout, abbreviations and page-header warnings accepted; "
          "only illegible/impossible/unknown-source links excepted")


if __name__=="__main__":
    test()
