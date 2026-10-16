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
    assert edges[0]["status"]=="AUTO_PROPOSED"
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
    endmarkers=[
       {"column":"L","chapter":24,"verse":42,"y_fraction":.4,"confidence":"HIGH"},
       {"column":"R","chapter":24,"verse":43,"y_fraction":.06,"confidence":"HIGH"},
       {"column":"R","chapter":24,"verse":44,"y_fraction":.45,"confidence":"HIGH"},
       {"column":"R","chapter":24,"verse":45,"y_fraction":.81,"confidence":"HIGH"}]
    intervals,issues=g.make_intervals(endmarkers,end,"Gen",limits)
    assert not any(x["from_header_seed"] for side in ("L","R") for x in intervals[side])
    assert "PAGE_END_HEADER_DISAGREES_WITH_LAST_MARKER" not in issues
    wrong=dict(end,verse=44)
    _,issues=g.make_intervals(endmarkers,wrong,"Gen",limits)
    assert "PAGE_END_HEADER_DISAGREES_WITH_LAST_MARKER" in issues

    # Don't use a top-right LAST verse as a synthetic starting verse.
    try:
        g.header_checked({"header_position":"TOP_RIGHT","boundary_role":"FIRST_ON_PAGE",
                          "chapter":24,"verse":45,"visible":True})
    except ValueError:
        pass
    else:
        raise AssertionError("Incorrect top-right FIRST role accepted")
    # A marker gap MUST flag the candidate, not fill a guessed source.
    skip=[{"column":"L","chapter":2,"verse":17,"y_fraction":.3,"confidence":"HIGH"},
          {"column":"L","chapter":2,"verse":20,"y_fraction":.6,"confidence":"HIGH"}]
    intervals,issues=g.make_intervals(skip,{"header_position":"NONE",
        "boundary_role":"UNKNOWN","chapter":None,"verse":None,"visible":False},
        "Gen",limits)
    src,flags=g.choose_source(row,intervals)
    assert src["verse"]==17
    assert "INCOMPLETE_VERSE_MARKER_SEQUENCE" in flags
    assert g.atomic_edges(33,"Gen",[row],intervals,limits)[0]["status"]=="REVIEW_REQUIRED"
    cut=dict(row,id="fr88i:p0033:L:009",visibility_status="CUT_OFF",
             typography_uncertain=True)
    assert g.atomic_edges(33,"Gen",[cut],intervals,limits)[0]["status"]=="REVIEW_REQUIRED"
    print("PASS: Gen 2:17 → Rom 6:23, 3 atomic destinations, RIGHT header is LAST, gaps & cuts quarantined")


if __name__=="__main__":
    test()
