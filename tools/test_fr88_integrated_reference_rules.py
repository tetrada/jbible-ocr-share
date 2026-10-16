#!/usr/bin/env python3
"""Offline edition-rule tests: user-confirmed shorthand, comma edges and markers."""
import tempfile
from pathlib import Path
from fr88_integrated_reference_rules import canonicalize


def test():
    with tempfile.TemporaryDirectory() as tmp:
        cat=Path(tmp)/"catalog.csv"
        cat.write_text("\n".join([
          "record_type,book_code,bali_alias,chap_number,max_verse",
          "A,Gen,Gn,,","A,Ps,Ps,,","A,Sir,Si,,",
          "A,Rev,Ap,,","A,Isa,Is,,","A,1Chr,1 Ch,,","A,1Kgs,1 R,,",
          "A,Wis,Sg,,","A,Matt,Mt,,",
          "C,Gen,,5,32","C,Gen,,9,29","C,Gen,,15,21",
          "C,Gen,,18,33","C,Ps,,78,72","C,Ps,,105,45","C,Ps,,8,9",
          "C,Ps,,104,35","C,Sir,,43,36","C,Rev,,16,21",
          "C,Isa,,14,32","C,1Chr,,1,54","C,1Kgs,,10,29",
          "C,Wis,,15,19","C,Matt,,24,51"
        ])+"\n",encoding="utf-8")
        def run(t,book="Gen"):
            return canonicalize({"kind":"REFERENCE","raw_line":t,
                     "layout_uncertain":False,"typography_uncertain":False},book,cat)
        bare=run("5 1, 3; 9 6")
        assert [(r["book_code"],r["chapter"],r["verse"]) for r in bare["references"]]==[
                ("Gen",5,1),("Gen",5,3),("Gen",9,6)]
        assert all(r["book_resolution"]=="SOURCE_PAGE_BOOK" for r in bare["references"])
        several=run("Ps 78 47s; 105 32; Ap 16 21")
        assert len(several["references"])==3
        assert [(r["book_code"],r["chapter"],r["verse"]) for r in several["references"]]==[
            ("Ps",78,47),("Ps",105,32),("Rev",16,21)]
        assert several["references"][0]["suffix"]=="s"
        assert all(x["status"]=="PARSED" for x in several["references"])
        comma=run("Si 43 6,7")
        assert len(comma["references"])==2
        assert [r["verse"] for r in comma["references"]]==[6,7]
        assert [r["atomic_target_index"] for r in comma["references"]]==[1,2]
        assert all(r["parent_type"]=="VERSE_LIST" for r in comma["references"])
        chapters=run("Ps 8; 104")
        assert [(r["type"],r["chapter"]) for r in chapters["references"]]==[
               ("CHAPTER_ONLY",8),("CHAPTER_ONLY",104)]
        equal=run("= 18 9-15")
        assert equal["relation_marker"]=="SAME_BOOK_DOUBLET"
        assert len(equal["references"])==1
        assert equal["references"][0]["book_code"]=="Gen"
        assert equal["references"][0]["type"]=="VERSE_RANGE"
        assert equal["references"][0]["end_verse"]==15
        assert run("= 15")["references"][0]["type"]=="CHAPTER_ONLY"
        assert run("|| 1 R 10 1+")["references"][0]["book_code"]=="1Kgs"
        assert run("|| 1 R 10 1+")["relation_marker"]=="CROSS_BOOK_PARALLEL"
        assert run("↗ Ps 78 47s")["relation_marker"]=="SCRIPTURAL_QUOTATION"
        ch=run("Ch 1 1-4")
        assert ch["raw_line"]=="Ch 1 1-4"
        assert ch["references"][0]["book_code"]=="1Chr"
        assert "PROVISIONAL_MISSING_BOOK_ORDINAL_1_CHR" in ch["references"][0]["interpretation_flags"]
        isa=run("s 14 14+")
        assert isa["raw_line"]=="s 14 14+"
        assert isa["references"][0]["book_code"]=="Isa"
        assert isa["references"][0]["suffix"]=="+"
        assert "PROVISIONAL_MISSING_BOOK_INITIAL_ISA" in isa["references"][0]["interpretation_flags"]
        suffix=run("Ps 78 47p")
        assert suffix["references"][0]["suffix"]=="p"
        assert len(suffix["references"])==1
        # A new physical row MUST reset explicit-book inheritance.
        reset=run("7 11+")
        assert reset["references"][0]["book_code"]=="Gen"
        assert reset["references"][0]["suffix"]=="+"
        assert reset["references"][0]["book_resolution"]=="SOURCE_PAGE_BOOK"
        assert run("10 6",None)["references"][0]["status"]!="PARSED"
        sp=run("↗ Mt 24 37sp")
        assert len(sp["references"])==1
        assert sp["references"][0]["book_code"]=="Matt"
        assert sp["references"][0]["chapter"]==24
        assert sp["references"][0]["verse"]==37
        assert sp["references"][0]["suffix"]=="sp"
        cutfirst=run("↗ Sg 15 8,")
        assert len(cutfirst["references"])==1
        assert cutfirst["references"][0]["book_code"]=="Wis"
        assert cutfirst["references"][0]["chapter"]==15
        assert cutfirst["references"][0]["verse"]==8
        assert cutfirst["references"][0]["visible_coordinate_prefix"] is True
        trailing=run("↗ Ap 22 1s, 1")
        assert len(trailing["references"])==1
        assert trailing["references"][0]["book_code"]=="Rev"
        assert trailing["references"][0]["chapter"]==22
        assert trailing["references"][0]["verse"]==1
        assert trailing["references"][0]["suffix"]=="s"
        assert trailing["references"][0]["ignored_unreadable_or_following_tail"]=="1"
        print("PASS: same-page bare targets, inherited inline books, 2 comma edges, '=', '||', suffixes and flagged Ch/Is repairs")


if __name__=="__main__":
    test()
