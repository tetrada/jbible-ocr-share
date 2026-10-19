#!/usr/bin/env python3
"""Offline edition-rule tests: user-confirmed shorthand, comma edges and markers."""
import tempfile
from pathlib import Path
from fr88_integrated_reference_rules import canonicalize, canonicalize_contiguous_rows


def test():
    with tempfile.TemporaryDirectory() as tmp:
        cat=Path(tmp)/"catalog.csv"
        cat.write_text("\n".join([
          "record_type,book_code,bali_alias,chap_number,max_verse",
          "A,Gen,Gn,,","A,Ps,Ps,,","A,Sir,Si,,","A,Num,Nb,,",
          "A,Rev,Ap,,","A,Isa,Is,,","A,1Chr,1 Ch,,","A,1Kgs,1 R,,",
          "A,Wis,Sg,,","A,Matt,Mt,,","A,Luke,Lc,,",
          "A,Judg,Jg,,","A,Tob,Tb,,",
          "A,Jer,Jr,,","A,John,Jn,,","A,Exod,Ex,,","A,Obad,Ab,,",
          "A,Deut,Dt,,",
          "C,Gen,,5,32","C,Gen,,9,29","C,Gen,,15,21",
          "C,Gen,,18,33","C,Ps,,78,72","C,Ps,,105,45","C,Ps,,8,9",
          "C,Ps,,104,35","C,Sir,,43,36","C,Rev,,16,21",
          "C,Isa,,14,32","C,1Chr,,1,54","C,1Kgs,,10,29",
          "C,Wis,,15,19","C,Wis,,8,21","C,Matt,,24,51",
          "C,Matt,,5,48","C,Num,,20,29"
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
        # 2026-10-19: user reviewed broken tail and requested SINGLE verses.
        # Preserve the printed original; never infer an unseen final verse.
        for text_,bk,ch,v in (
                ("|| Nb 20 1-1","Num",20,1),
                ("↗ Mt 5 38-4","Matt",5,38),
                ("Sg 8 19 – 9","Wis",8,19)):
            recovered=run(text_)["references"]
            assert len(recovered)==1, (text_,recovered)
            ref=recovered[0]
            assert (ref["book_code"],ref["chapter"],ref["verse"],ref["type"])==(
                bk,ch,v,"VERSE"),(text_,ref)
            assert ref["end_verse"] is None
            assert ref["status"]=="PARSED"
            assert "MALFORMED_RANGE_VISIBLE_START_ONLY_NO_INVENTED_ENDPOINT" in ref["interpretation_flags"]
            assert ref["original_malformed_range"]
        correct_range=run("Mt 5 38-40")["references"][0]
        assert correct_range["type"]=="VERSE_RANGE"
        assert correct_range["end_verse"]==40
        assert "MALFORMED_RANGE_VISIBLE_START_ONLY_NO_INVENTED_ENDPOINT" not in correct_range["interpretation_flags"]
        assert run("Mt 5 40-??")["references"][0]["status"]!="PARSED"
        # Source and destination coordinates that are impossible in the catalog
        # are not rescued just because a start number is present.
        impossible=run("Mt 5 58-4")["references"][0]
        assert impossible["type"]=="UNRESOLVED_NUMERIC",impossible

        # New October 16 pilot cases: no manual review needed for notation.
        parallel=run("‖ 1 Ch 1 29-31")
        assert parallel["relation_marker"]=="CROSS_BOOK_PARALLEL"
        assert len(parallel["references"])==1
        assert parallel["references"][0]["book_code"]=="1Chr"
        assert parallel["references"][0]["chapter"]==1
        assert parallel["references"][0]["verse"]==29
        assert parallel["references"][0]["end_verse"]==31

        cross=run("= 27 46-28 5")
        assert cross["relation_marker"]=="SAME_BOOK_DOUBLET"
        assert len(cross["references"])==1
        assert cross["references"][0]["book_code"]=="Gen"
        assert cross["references"][0]["type"]=="VERSE_CROSS_CHAPTER_RANGE"
        assert (cross["references"][0]["chapter"],cross["references"][0]["verse"],
                cross["references"][0]["end_chapter"],cross["references"][0]["end_verse"])==(27,46,28,5)
        other_cross=run("29 31 - 30 24")
        assert other_cross["references"][0]["end_chapter"]==30
        assert other_cross["references"][0]["end_verse"]==24

        dots=run("31 24.29")
        assert [(r["book_code"],r["chapter"],r["verse"])
                for r in dots["references"]]==[("Gen",31,24),("Gen",31,29)]
        dotted_book=run("Lc 2 19.51")
        assert [(r["book_code"],r["chapter"],r["verse"])
                for r in dotted_book["references"]]==[("Luke",2,19),("Luke",2,51)]
        # An editorial 'cf.' must not generate a fictitious Judg target.
        with_connector=run("Jg 14 12, 17; cf. Tb 8")
        assert [(x.get("book_code"),x.get("type"),x.get("chapter"),x.get("verse"))
                for x in with_connector["references"]]==[
                    ("Judg","VERSE",14,12),
                    ("Judg","VERSE",14,17),
                    ("Tob","CHAPTER_ONLY",8,None)]
        # Exodus p89 commentary: recover real numeric references, not "cf".
        deja=run("cf. déjà 3 18,", "Exod")
        assert [(x["book_code"],x["chapter"],x["verse"]) for x in deja["references"]]==[("Exod",3,18)]
        many_cf=run("cf. 7 16, 26; 8 4, 16, 23; 9 1, 13; 10 3, 24.", "Exod")
        assert [(x["chapter"],x["verse"]) for x in many_cf["references"]]==[
            (7,16),(7,26),(8,4),(8,16),(8,23),(9,1),(9,13),(10,3),(10,24)]
        final_cf=run("cf. 12 1+.", "Exod")
        assert [(x["book_code"],x["chapter"],x["verse"]) for x in final_cf["references"]]==[("Exod",12,1)]
        # Exodus p100: a verse range followed by a separate single verse.
        mixed_order=run("Dt 2 1-9, 18", "Exod")
        assert [(x.get("book_code"),x.get("chapter"),x.get("type"),
                 x.get("verse"),x.get("end_verse")) for x in
                 mixed_order["references"]]==[
            ("Deut",2,"VERSE_RANGE",1,9),
            ("Deut",2,"VERSE",18,None)]
        # Single-chapter Abdias: explicit 'Ab 18' is verse 18.
        obad=run("Ab 18","Exod")
        assert len(obad["references"])==1
        assert (obad["references"][0]["book_code"],
                obad["references"][0]["chapter"],
                obad["references"][0]["verse"],
                obad["references"][0]["type"])==("Obad",1,18,"VERSE")
        assert "SINGLE_CHAPTER_OBADIAH_VERSE_SHORTHAND" in (
                obad["references"][0]["interpretation_flags"])
        assert obad["raw_line"]=="Ab 18"
        assert run("Ab 1", "Exod")["references"][0]["type"]=="CHAPTER_ONLY"
        # Real rejoined Genesis p0063 row: two bare destinations separated
        # by an editorial plus suffix, without an actual printed semicolon.
        plus=run("22 16-17+ 28 14")
        assert plus["raw_line"]=="22 16-17+ 28 14"
        assert [(r["book_code"],r["type"],r["chapter"],r["verse"],
                 r["end_verse"],r["suffix"]) for r in plus["references"]]==[
            ("Gen","VERSE_RANGE",22,16,17,"+"),
            ("Gen","VERSE",28,14,None,"")]
        assert all(r["status"]=="PARSED" for r in plus["references"])
        explicit=run("Gn 22 16-17+ 28 14")
        assert [r["book_code"] for r in explicit["references"]]==["Gen","Gen"]
        assert [r["atomic_target_index"] for r in plus["references"]]==[1,2]
        # Real semicolon-wrapped rows at pages 36,37,41,72,79,80:
        # do NOT turn the next numeric target into a Genesis target.
        def two_rows(before,after,y2=.214,side="R"):
            raw=[
              {"id":"prior","side":"R","kind":"REFERENCE","y_fraction":.20,
               "raw_line":before},
              {"id":"next","side":side,"kind":"REFERENCE","y_fraction":y2,
               "raw_line":after}]
            return canonicalize_contiguous_rows(raw,"Gen",cat)
        for before,after,expected in [
            ("Si 44 16;","49 14","Sir"),
            ("Jr 18 10;","26 3","Jer"),
            ("Jn 11 52;","10 16","John"),
            ("Ex 7 11,22;","8 1-3","Exod"),
            ("Ex 1 11;","12 37","Exod"),
            ("Ps 23 1;","80 2-3","Ps")]:
            normalized=two_rows(before,after)
            assert normalized[1]["raw_line"]==after
            assert normalized[1]["id"]=="next"
            assert normalized[1]["references"][0]["book_code"]==expected
            assert normalized[1]["references"][0]["book_resolution"]=="ADJACENT_SEMICOLON_ROW"
            assert normalized[1]["wrapped_book_inheritance_from_row_id"]=="prior"
        assert two_rows("Ps 23 1","80 2-3")[1]["references"][0]["book_code"]=="Gen"
        assert two_rows("Ps 23 1;","80 2-3",y2=.26)[1]["references"][0]["book_code"]=="Gen"
        assert two_rows("Ps 23 1;","80 2-3",side="L")[1]["references"][0]["book_code"]=="Gen"
        assert two_rows("Ps 23 1;","Jn 8 1")[1]["references"][0]["book_code"]=="John"
        mixed=run("25 26, 29-34")
        assert len(mixed["references"])==2
        assert [(r["book_code"],r["chapter"],r["verse"],r["end_verse"],r["type"])
                for r in mixed["references"]]==[
                    ("Gen",25,26,None,"VERSE"),
                    ("Gen",25,29,34,"VERSE_RANGE")]
        chnote=run("ch. 27.")
        assert len(chnote["references"])==1
        assert chnote["references"][0]["book_code"]=="Gen"
        assert chnote["references"][0]["type"]=="CHAPTER_ONLY"
        assert chnote["references"][0]["chapter"]==27
        assert "EDITORIAL_CHAPTER_ONLY_SHORTHAND" in chnote["references"][0]["interpretation_flags"]
        print("PASS: same-page bare targets, inherited inline books, 2 comma edges, '=', '||', suffixes and flagged Ch/Is repairs")


if __name__=="__main__":
    test()
