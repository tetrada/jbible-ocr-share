# JBible FR88 — v3 typography OCR pilot (20 pages)

This is an **isolated experiment**, not a replacement for the v2 pipeline. It uses the SAME DeepSeek model (`deepseek-flash`) and same four cropped images as FR88 v2, changing the recognition instructions to emphasize bold chapter numerals, normal verse digits, book ordinals and physical printed rows.

The test covers **scanned pages 31 through 50 inclusive**, 20 pages / 40 page-margins.

## Install (no API calls)

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/install_fr88_v3_pilot.sh | bash
```

The installer compiles the scripts and runs offline tests inside the already installed `jbible-ocr:1` Docker image. Works even when host Python is 3.6.

## First preflight (no API calls)

```bash
cd /opt/jbible/importer
./run_fr88_v3_pilot.sh --preflight
```

The preflight checks existing scans and Bible catalog, plus the saved v2 interpreted dataset, and runs the established parser self-test.

## Paid v3 pilot (DeepSeek)

```bash
./run_fr88_v3_pilot.sh 2>&1 | tee /root/jbible_fr88_v3_pilot_31_50.log
```

This sends at most **40 new margin jobs** (each may retry transient network failures). Every successful response is checkpointed, so rerunning continues without paying twice for completed margins. There is no automatic retry loop of the entire batch. Source images, v2 checkpoints, v2 aggregate output, GitHub sync, and SQL remain untouched.

You can test one page first, without forfeiting the 20-page test:

```bash
./run_fr88_v3_pilot.sh --start 31 --end 31
./run_fr88_v3_pilot.sh --start 31 --end 50
```

Re-running with the same image and prompt uses cached v3 margin checkpoints. Changing prompt/model/image fingerprint will stop on mismatched checkpoints rather than overwrite them. To experiment with another prompt, create a separately named v4 output pipeline, don't delete v3.

## Output (VPS only)

`/opt/jbible/data/raw/jbible_fr1988_v3_pilot_31_50/`

- `image_####_L.result.json` and `image_####_R.result.json` — recognized physical rows, typography evidence and deterministic references, all `verified: false`
- `image_####_L.provider.json` and right equivalents — saved original API replies, without API credentials
- `comparison.json` — v2/v3 row totals, parser/canonical validity, completion and optional human-gold counts
- `comparison_by_margin.csv` — v2/v3 parser and catalog counts per margin
- `transcription_disagreements.csv` — transcription differences, NOT ground-truth mistakes
- `gold_review_template.csv` — blank human visual-check sheet for v2 reference rows, created once and never overwritten
- `run_summary.json` — completed margins, errors, timestamps

At any point, regenerate comparisons offline:

```bash
./run_fr88_v3_pilot.sh --compare-only
```

To measure genuine OCR improvement: copy `gold_review_template.csv` to a review file (e.g., `gold_confirmed.csv`). On rows actually checked against the image, supply `expected_raw_line` and `verified_from_scan=YES`. Then run:

```bash
./run_fr88_v3_pilot.sh --compare-only --gold /raw/jbible_fr1988_v3_pilot_31_50/gold_confirmed.csv
```

Note: the `--gold` path is inside Docker (`/raw/...`), not the host path (`/opt/jbible/data/raw/...`). The evaluator uses nearby y coordinates to pair rows; ambiguous/unpaired rows are excluded and must be reviewed.

## Interpretation safety

- A chapter/verse split like **2 P 2 5** should be preserved because the scanned bold chapter **2** and ordinary verse **5** are distinct. No structural plausibility-based changes to raw_line.
- Semicolons on the same physical row are retained, and book context is never inherited from an adjacent printed row.
- `catalog VALID` and `PARSED` only mean the notation is interpretable and within chapter/verse bounds. They are not OCR accuracy.
- Main-text source verse linking is NOT performed in this pilot; all source anchors remain unverified.
- This pipeline does not change the v2 importer, call SQL, or publish to the status portal automatically.

## Future decision

We should deploy v3 to larger batches **only after** its accuracy on human-confirmed scans is demonstrably better than v2, especially on bold chapter boundaries, suffixes, and multi-book rows. Otherwise revisit image crops and prompt.
