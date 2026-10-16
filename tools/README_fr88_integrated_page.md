# JBible FR1988 — complete image-page scanner (integrated v1)

## Why a clean new processing version

Earlier V2/V3/V4 margin OCR found printed destination references and approximate y positions, but did **not** store the y coordinate of **every main-text verse marker**. The source-link experiment then asked DeepSeek separately for each marginal source verse, which caused unnecessary ambiguity and sometimes confused page and margin context.

This independent, versioned scanner is a **rebuild of the OCR workflow, not deletion of the previous work**. Historical scans, margins, human review decisions, and all SQL databases remain untouched. It only writes under:

`/opt/jbible/data/raw/jbible_fr88_integrated_v1/`

### One page processed in five cached vision tasks (DeepSeek Flash only)

1. **Running head:** inspect both TOP LEFT and TOP RIGHT; identify printed physical page side, chapter and verse, and whether it means **FIRST_ON_PAGE** or **LAST_ON_PAGE**. This is critical: right-hand printed pages can place their *last verse* at the upper right. The scanner never treats this as the first verse.
2. **Main-text verse markers, left text column:** read EACH printed chapter and verse marker and its `y_fraction` on the original full-page image (with enlarged overlapping crops). Do not OCR entire copyrighted Bible paragraphs.
3. **Main-text verse markers, right text column:** same for the other column; preserve reading order and identify in-body chapter transitions.
4. **Marginal cross-references, left:** transcribe ALL visible physical lines, typography, position and cut-off status.
5. **Marginal cross-references, right:** same.

Then pure deterministic code (no AI) builds verse intervals within the correct column and links a marginal row by its y position to the verse interval it occupies. A verse can span many printed lines, so the nearest **number** is not necessarily the correct source. Target citations are split by the existing Bible interpreter (semicolon-separated references, new printed book abbreviations etc.).

**One atomic record per destination.** For a physical line `Ps 78 47s; 105 32; Ap 16 21`, the parser creates three separate edge IDs `row/target01`, `row/target02`, `row/target03`, each pointing from the same geometrically identified source verse to ONE target.

Example target to demonstrate on REAL scan page 33:
`Gen 2:17 → Rom 6:23` (printed marginal `Rm 6 23`, original V2 y=0.452).

Example supplied by user (page 102):
`Exod 16:31 → Num 11:7`, with right/left physical page's appropriate running-head boundary considered. Page 102's stated running-head pair is `16 21`. The source is verse 31, **not** necessarily the header's verse 21.

### Confirmed edition notation and practical ±1-verse tolerance

The user provided photographs of the printed **Napomene / Rubne naznake ili referencije** explanations and confirmed all five editorial questions. Machine-readable rules are in [training/fr88_integrated_editorial_rules.json](../training/fr88_integrated_editorial_rules.json). In particular:

- Bare destination without a book refers to this **page's source book**, unless it follows an explicitly named destination book within that same physical row, in which case it inherits that named book.
- `=` identifies a literary parallel in the **same book**; `||` denotes a parallel in another book; `↗` marks a scriptural quotation. Treat as relation metadata, NOT target verses.
- `Si 43 6,7` means **two atomic destination records**; `Ps 8; 104` means **two distinct chapter-level destinations**.
- Keep `s`, `ss`, `p`, `+` literally and do not create invented target ranges.
- OCR-only book restorations such as `Ch` → `1 Ch` or `s` → `Is` are **assumed and flagged**, not routinely escalated to user review.
- Edition paragraph 7: a margin reference may be shifted **below** the line it belongs to when the margin is crowded. A blank margin line ordinarily divides groups aligned with different source lines.

The user explicitly accepts occasional source-verse estimates **off by one verse**. Therefore a margin close to a source-verse boundary or marked as possibly shifted down is assigned **one provisional source** with separately recorded adjacent printed-verse alternatives and status `AUTO_PROPOSED_ADJACENT`, rather than being automatically sent to manual review. Real failures—missing book/chapter, unreadable target, nonsequential markers, and genuine layout contradictions—still need a review/error bucket. *An estimated ±1 match is not silently marked visually confirmed or SQL-imported.*

For evaluation, report **exact source-verse agreement and agreement within ±1 verse separately**. Neither score has been established on real integrated-page scans yet; 99% remains a target, not a measured claim.

### Auto QA to avoid thousands of human reviews

Clear links are marked `AUTO_PROPOSED`; unusual cases are `REVIEW_REQUIRED` with actionable reasons:

- Missing/duplicate/invalid main-text verse markers, nonsequential chapters/verses or a margin position that cannot be assigned.
- Marginal OCR with cut-off/unreadable glyphs, uncertain typography or unsupported target notation.
- Bible target book/chapter/verse outside the catalog.
- Vertical margin/source alignment near the boundary between verses.
- Contradiction between known page-level book and model reading.
- Top-right LAST header inconsistent with observed last verse.
- A fresh margin pass detects fewer physical rows than the previously saved V2 OCR.

These checks reduce needless human verification but **no vision model can guarantee zero OCR mistakes**, especially with cropped print, faint verse markers and edition-specific notation. `AUTO_PROPOSED` is explicitly **not** the same as `HUMAN_VERIFIED`, and nothing is written to SQL automatically. For trustworthy final bulk import we should visually sample some apparently clear links to calibrate precision and audit the true exception rate.

### Stage checkpoints and resumption

Each of five DeepSeek provider answers is saved **privately on VPS** as `image_0033.header.provider.json`, `image_0033.verses_L.provider.json`, etc., and parsed checkpoints as `image_0033.header.result.json` etc. Every checkpoint includes a fingerprint of the JPEG, stage, model and frozen prompt to prevent accidental cross-version reuse. If one stage fails parsing, rerun: the saved API response is reparsed WITHOUT making another paid request.

A finished page gets `image_0033.bundle.json` with page header, all main-text verse markers, all marginal OCR rows, **atomic source→destination edges**, QA flags and summary. No SQL writes.

### First run, on existing page 33 only

Free test/preflight (also runs offline regression tests in the installed Docker image):

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/run_fr88_integrated_page.sh | bash -s -- --preflight
```

If that passes, process page 33 (up to five distinct paid DeepSeek tasks; API requests may retry transient failures):

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/run_fr88_integrated_page.sh | bash -s -- --start 33 --end 33 --max-new-calls 5
```

To publish a **sanitized, text-only** report for inspection:

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/publish_fr88_integrated_page.sh | bash
```

Git output: `fr88_integrated_v1/pilot_report.json`. This report includes no original scan JPEGs, full Bible paragraphs, provider responses, keys or prompt corpus.

Once the actual page-33 source assignment and verse-marker coverage have been checked, the same script can scan pages 31–40 and then pages 31–500:

```bash
# Example AFTER the page-33 pilot succeeds:
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/run_fr88_integrated_page.sh | bash -s -- --start 31 --end 40 --max-new-calls 50
```

Large batches have an explicit API budget cap and resumable checkpoints. Never delete historical OCR until replacement results have been proven complete and consistent.
