# JBible FR1988 — corrected source → destination relationship model

## Data semantics

A single PHYSICALLY PRINTED marginal line may contain multiple Bible cross-references:

`Ps 78 47s; 105 32; Ap 16 21`

The OCR line is one evidence object, but the target interpreter returns THREE target segments. A relation is ONE source Bible verse/passage → ONE target segment. When such a line sits beside the same main-text source verse, it creates THREE independent rows with the same source coordinates and source OCR row ID and unique `target_segment_index`.

One-to-one here is the structure of *each link record*, NOT a claim that a source verse can have only one target.

Example: user-provided page 102 is Exodus, with printed top-left running head 16 21. The left marginal `Nb 11 7` visually aligns with Exodus 16:31, giving one link `Exod 16:31 → Num 11:7`. The printed pair `16 21` anchors the START of the page, not every subsequent link's verse.

Page 40 has Genesis as source book. The prior pilot mistakenly treated absence of a repeated book title on EACH margin or page half as unresolvable, producing 96 review SEGMENTS with `SOURCE_BOOK_NOT_PRINTED`. These are not 96 different pages and do not mean the book is unknown.

## Correct anchoring algorithm

1. Identify source book at PAGE level using the page-to-book registry, running headers and actual book boundaries. Do not require a repeated book name next to each reference.
2. Scan top-left running head ONCE PER PAGE for `page_start_chapter` and `page_start_verse` (e.g. `24 45` on the example Genesis page).
3. Scan MAIN TEXT in BOTH columns for inline verse numbers and bold chapter transitions; store `(column,chapter,verse,y_start)` in page coordinates. Because passages can cross a page or continue for several lines, a marginal row may align midway through the interval of one verse, NOT necessarily the same line as the small printed verse marker.
4. For each printed marginal row, use its LEFT/RIGHT column and baseline `y_fraction` to propose the source verse or passage spanning that vertical interval. Escalate section-level references, multiline verses and ambiguous boundaries to review. Do not use topical similarities between the texts as proof.
5. Split the marginal line into individual parsed destination segments; one persisted edge per segment.
6. Human review uses the actual scan and may confirm/correct/reject each edge separately; source verse, margin target and their alignment must be visibly checked. No automatic SQL writes.

Page-level book mapping is in `training/fr88_page_book_registry.json`. It records Genesis as the source book for the already studied pages 31–40 (provisional range until every page header is checked) and the user-supplied page 102 = Exodus with start 16:21. Other pages must be populated from scans/book-boundary verification, **not** guessed by extrapolating ranges.

## Live-source-link verifier updated to one relation per item

The initial source-link pilot had **151 parsed target segments across 140 printed marginal rows**, all unverified. The revised verifier displays **151 review entries** at the same protected URL:

https://status.tetrada.eu/jbible-review/links/

Run on VPS as root:

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/install_fr88_source_link_review.sh | bash
```

The installer preserves:
- `/var/lib/jbible-review/decisions.json`: original OCR transcription reviews.
- `/var/lib/jbible-review/link_decisions.json`: any previous legacy *row-based* link review decisions.

New per-destination decisions use a different file:
- `/var/lib/jbible-review/link_edge_decisions.json`
- GitHub text-only `fr88_source_links_pilot/human_link_edge_reviews.json`

The original scans never leave the protected VPS; no SQL writes or API calls are made by reviewer deployment.

## Separate top-header scanner (prepared, not run automatically)

DeepSeek Flash ONLY, one API job per PAGE instead of per margin row, `/raw/jbible_fr88_page_headers_pilot` output, no SQL. It reads the page's top-left chapter/verse running head, marks uncertainty explicitly, and saves isolated resumable JSON.

Free preflight:

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/run_fr88_page_headers.sh | bash -s -- --preflight
```

Two-page paid header pilot:

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/run_fr88_page_headers.sh | bash -s -- --max-new-pages 2
```

**Important:** A starting chapter/verse alone does NOT locate all source verses on that page: subsequent visible verse numbers and in-body chapter transitions must still be scanned and positioned. The 31–40 source-link suggestions from the original DeepSeek experiment remain UNVERIFIED and will be corrected using this newer interval-based method before any large import.
