# FR1988 integrated OCR — lessons from all 24 scan-reviewed exceptions

**Reviewed:** 2026-10-16, pages 32–37, authenticated human exception queue.  
**Original decisions:** `fr88_integrated_v1/human_exception_reviews.json`.  
**Original pilot report:** `fr88_integrated_v1/pilot_report.json`.  
**Preservation:** no scanned source images in public repo; no SQL updates.

## Human review outcomes

- 10 marked `as_printed`, including several corrected *source* verse coordinates.
- 11 marked `corrected`.
- 2 marked `unresolved` with explicit remarks that an unambiguous visible destination should still be retained when its continuation is clipped.
- 1 marked `cut_off`: page 32 `fr88i:p0032:R:017/target01`, the text `↗ 1 Co 15 45` was **over-read**, and only a partial head was actually visible. Do **not** accept 1 Corinthians 15:45 based on this scan.

**Replayed individual decisions:** 21 scan-confirmed usable links + 2 estimated partial-prefix links + 1 human-confirmed unusable cut-off. Original machine outputs and raw OCR remain intact.

## Root causes and corresponding code changes

### 1. The source at the TOP of a page or text column

A printed main-text verse continues across physical page or text-column boundaries without reprinting its number. The old method assigned nothing before the first detected verse marker. The new interval builder uses the preceding physical page's last verse, or the previous text column's final verse, then checks the next visible marker.

- Page 33: first visible left-column marker is Genesis 2:10; review confirmed the references above it apply to **Genesis 2:9**.
- Page 34: before the first marker Genesis 3:17 in the right column, the verse is **Genesis 3:16**, which ended the left column.
- Page 37: first left-column marker Genesis 6:5; source above it is **Genesis 6:4**.
- Page 37 right margin `Dt 1 28+`: reviewer explicitly selected **Genesis 6:4** despite the generic previous-column heuristic; retain the exact reviewed edge override, do not generalize the page-specific association to other pages.

### 2. Local catalog completeness is NOT canonical Bible completeness

The local CSV `jbible_catalog.csv` omits some legitimate destination book/chapter rows. Exodus 20:8, Hebrews 4:4, Genesis 31:12, Psalms 104:29, Hosea 4:3 and Isaiah 11:6 were wrongly rejected as outside the Bible. Now:

- Enforce exact verse maximum when the local book/chapter row is present.
- Where missing, check the canonical book's chapter count and a conservative possible verse ceiling; **accept with a warning** `CHAPTER_VERSE_LIMIT_UNAVAILABLE_IN_LOCAL_CATALOG`.
- Missing local catalog data is **not** proof a reference is invalid. This fallback does **not** independently establish actual maximum verse counts; full catalog coverage is a separate future validation task.

### 3. A cut-off margin row may contain a COMPLETE earlier reference

A partly clipped line can contain one or more unmistakable references. Save every complete visible destination independently, leave the invisible remainder unguessed.

- Page 32 `Qo 3 11; 7 2`: 2 destinations, user notes the second is mostly clipped but recognizable.
- Page 32 `↗ Ex 20 11s`: the destination is readable, additional continuation clipped.
- Page 32 `↗ Sg 15 8,`: preserve Wisdom 15:8 and flag the unseen continuation; do not manufacture the comma's next target.
- Page 32 `Jb 34 14s;`: retain Job 34:14s.
- Page 32 `↗ 1 Co 15 45`: genuinely unreadable verse digits per human reviewer, **exception**, do not trust OCR's fabricated 45.

### 4. Additional legitimate typography

- Printed `sp` suffix exists and must be preserved, like `s`, `ss`, `p` and `+`.
- Page 37 `↗ Mt 24 37sp` OCR and reviewer-specified `Matt 24:27sp` disagree on verse 37 versus 27. The individual reviewed correction is preserved **for this edge only**; the parser must not globally replace 37 with 27.
- Page 34 printed OCR `↗ Ap 22 1s, 1` and user-specified `Rev 1:1` also differ. Preserve that explicit user correction only for the reviewed edge. The general parser extracts the unambiguous visible leading `Rev 22:1s` for *other* contexts and never infers a book/chapter change without evidence.

### 5. OCR omission, wrong column label, vertical alignment

- Page 36: integrated OCR missed the printed `Ch 1 1-4` row previously observed by V2. Its source is Genesis 5 and its book abbreviation may be restored as `1 Ch` (1 Chronicles). A missing row is recovered from the prior OCR as an estimated edge, rather than discarded.
- Page 38 `verses_R` was stopped by an incorrect JSON `column` label. Because the script submits *only* the right half-page for that task, its authoritative column is R; the parser now corrects a wrong label while recording an audit warning. The saved DeepSeek provider response is reparsed without a new call.
- **Do not assume one global margin-to-text vertical offset.** Measured against corrected printed verse markers, page 32 right-margin references often fall about 0.10–0.15 normalized page height *above* the reviewed source marker, while page 34 right-margin references have the opposite sign. Some individual notes break these patterns. Keep human-specific edge overrides and mark future geometry estimates conservatively; acceptance is not measured truth.

## Data flow and verification

`tools/fr88_integrated_page.py` rebuilds from the cached five-stage page observations, normalizes destination references, recovers preceding verse boundaries and omitted legacy margin rows, runs Bible-coordinate checks, then overlays individual **scan-reviewed** human corrections using `tools/fr88_integrated_human_replay.py`.

`--rebuild-bundles` performs this without DeepSeek calls, without invalidating previous provider payloads and without changing old OCR datasets. Stage caches are reused during subsequent normal runs. The latest offline GitHub regression tests exercise all 24 saved decisions and the omitted margin row.

**Critical distinction:** 23/24 recoverable *reviewed exceptions* does not demonstrate 99% accuracy of the whole corpus. The 111 originally automatically accepted links remain unverified; the 10-page pilot is still incomplete until pages 38–40 are processed and analyzed. Never write SQL without separate authorization.
