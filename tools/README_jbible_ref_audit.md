# JBible FR88 v2 — Reference audit

Scripts in this directory provide a reusable **read-only** audit of the previously processed French 1988 Bible marginal-reference OCR.

No new OCR requests, DeepSeek/OpenAI calls, SQL writes, service restarts, automatic reference inheritance across printed rows, or changes to existing checkpoints.

## Install or update on VPS

Run as root:

~~~bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/install_jbible_ref_audit.sh | bash
~~~

This fetches only audit files to /opt/jbible/importer and runs the offline smoke tests.

## Pilot: Genesis and nearby pages

~~~bash
cd /opt/jbible/importer
./run_jbible_ref_audit.sh 31 40
~~~

Inspect the timestamped report folder printed on completion:

- audit_summary.json — counts by parse, catalog status, source-anchor state, and page.
- audit_report.html — sampled original reference rows with page images and approximate y positions.
- rows.csv — one record per physical printed OCR row.
- segments.csv, segments.jsonl — one record per parsed or ambiguous target-reference segment.
- review_queue.csv — records requiring further verification.
- target_interpretation_queue.csv — ONLY syntax/catalog problems, independent of source-verse alignment (31 segments in the pages 31–40 pilot).
- target_interpretation_context.json — each target problem with preceding/following two rows on the same page margin, for **visual review only**; never auto-inherit a book from those rows.
- review_decisions_template.csv — blank evidence/correction ledger, never auto-imported.
- sample_30_records.json — a stratified sample of 30 different printed rows.

Report location: /opt/jbible/data/raw/jbible_reference_audit/audit_p0031_0040_<UTC timestamp>/

## Reuse with any range

~~~bash
./run_jbible_ref_audit.sh 31 500
./run_jbible_ref_audit.sh 501 750
./run_jbible_ref_audit.sh all
~~~

To compare existing stored interpretations against the **current** local deterministic parser (without overwriting them):

~~~bash
./run_jbible_ref_audit.sh 31 40 --reparse
./run_jbible_ref_audit.sh all --reparse
~~~

## Meaning of results

- PARSED: deterministic syntax interpretation only. May still be wrong OCR.
- Catalog VALID: the target passage coordinates are possible within the catalog. Does not validate the printed source or edition-specific versification.
- MISSING_BOOK: a physical row did not establish a unique target book. No inheritance across printed rows.
- CHAPTER / CHAPTER_RANGE: chapter-scope reference, not a specific verse.
- OPEN_ENDED_SUFFIX_NOT_EXPANDED: printed suffix s, ss, p, + is kept unexpanded.
- TENTATIVE_OCR_NOT_VERIFIED or OCR_CLAIMED_CONFIDENT_NOT_VERIFIED: OCR proposed a source verse; not visually verified.
- MISSING: no claimed source verse. The current OCR focuses on margins, so this is expected.

**No source-to-target cross-reference edge is verified.** Linking source verses requires independent main-text verse positions, actual scanned-page evidence, and conservative review of cases such as Genesis 1:1–4. Do not assign verse anchors purely from y_fraction or semantics.

## Inputs and safety

- Input: /opt/jbible/data/raw/jbible_fr1988_v2/interpreted_rows.json
- Catalog: /opt/jbible/data/raw/jbible_catalog.csv
- Source JPEGs: /opt/jbible/data/raw/fr_bible_1988/
- Optional parser: /opt/jbible/importer/fr88_v2_normalize.py

Uses only Python 3 standard library. The audit writes only to its separate, timestamped audit output folder. Sample images are copied there if requested. No secret files are read, and it never writes to the existing FR88 output or SQL.

Tests: python3 /opt/jbible/importer/test_jbible_ref_audit.py
