# FR88 integrated OCR: pages 31–70 audit and corrections

**Date:** 2026-10-16. **Source:** published `fr88_integrated_v1/pilot_report.json` before this audit's corrective rebuild.

## Reported initial results

- 40/40 pages finished; 100 new DeepSeek Flash visual tasks for the 20 additional pages 51–70.
- 448 atomic links, 438 accepted (97.77% acceptance, **not measured accuracy**), 10 exceptions.
- 21 individually human-reviewed and accepted links (all inherited from the original 31–37 pilot).
- Pages 51–70: 175 links, 166 accepted, 9 exceptions; legacy V2 152 printed rows and 173 parsed segments, new integrated scan 159 row IDs before fixing split lines.
- No SQL writes.

## Real deficiencies uncovered

**Improperly rejected readable notations**:

- Page 55: `‖ 1 Ch 1 29-31` = 1 Chronicles 1:29–31, cross-book parallel.
- Page 58: `= 27 46-28 5` = Genesis 27:46–28:5, cross-chapter doublet.
- Page 59: `ch. 27.` = editorial chapter-only pointer to Genesis chapter 27.
- Page 59: `Jg 14 12, 17; cf. Tb 8` = Judges 14:12, Judges 14:17, and Tobit chapter 8; `cf.` must not create a phantom fourth citation.
- Page 62: `31 24.29` = Genesis 31:24 and Genesis 31:29 as two independent links.
- Page 66: `29 31 - 30 24` = Genesis 29:31–30:24.
- Page 68: `Lc 2 19.51` = Luke 2:19 and Luke 2:51 as two independent links.

**Page 51 source chapter OCR error (two exceptions, plus other potential bad geometry)**:
Previous scanned page (50) ends in Genesis 21:23, while the next page's model markers displayed a contiguous `20:24…20:34` sequence followed by `22:1`. Genesis chapter 20 ends at 18, so those markers are impossible. The structurally supported repair is Genesis **21:24–21:34**. The code now requires prior-page verse continuity, invalid old-chapter maximum, valid candidate-chapter maximum, and the next chapter's first printed marker, before correcting a whole prefix. The original model response stays unchanged. No loose book-memory inference.

**Split physical reference rows incorrectly acquired another book or chapter**:
- Page 54 V2 `II 1 Ch 1 32-33` was split as `|| 1 Ch 1` + `32-33`, misparsing the latter as Genesis chapters 32–33 instead of 1 Chronicles 1:32–33.
- Page 57 V2 `25 26, 29-34` was split as `25 26,` + `29-34`, misparsing a Genesis chapter range instead of Genesis 25:26 and 25:29–34.
- Page 59 one multi-part margin reference was split into three nearby pieces.
- Page 63 `22 16-17+ 28 14` was split into two nearby pieces.

The updated importer rejoins **only** 2–4 neighboring printed row fragments with at most 0.07 total normalized vertical displacement **and** an exact normalized concatenation match to an earlier V2 row. It records the original fragment IDs and flags accepted links as estimated. All old source scans, stage responses, and existing human reviews remain immutable. Additional mixed comma-plus-range numeric parsing returns independent target edges.

## Other unresolved precision issues

- Pages 53, 63, 64, 65 contain running-header / body verse inconsistencies. Page 55 and page 68 have cross-column verse-sequence reversals.
- Some verse-marker coordinates are non-monotonic or coincident (60, 63, 64). These are **source-position uncertainty**, not evidence of an unreadable destination.
- Page 61 source-book identification was inherited provisionally from page 60 because its header was unavailable.
- No new human corrections were claimed, and no source-link accuracy percentage can be inferred from acceptance.

## Deployment required

Offline regression CI passes, including all 24 earlier reviewed cases, page-51 chapter repair, dotted and cross-chapter citations, and close-by wrapped margin rows. Run the cached `--rebuild-bundles` path for 31–70 and republish the text-only report. **No new DeepSeek calls**. Then inspect the new exceptions, source chapter mapping and target counts before further scanning or SQL import.
