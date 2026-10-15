# JBible FR88 — connect printed marginal references to source verses

**Only the existing DeepSeek Flash model is used.** No new model, no new scan pages, no SQL, and no changes to earlier OCR data.

## What this does

The saved French 1988 marginal OCR (pages 31–500) already contains target citations such as `Jn 1 5`. The missing part is the MAIN-TEXT source verse or passage beside which the reference was printed.

For the initial pages 31–40 pilot, this pipeline:
1. Loads the immutable V2 marginal OCR from `/opt/jbible/data/raw/jbible_fr1988_v2/interpreted_rows.json`.
2. Supplies to DeepSeek the actual scanned page half, enlarged upper/lower areas and the exact marginal row IDs/text with approximate positions. It asks **only** which source book/chapter/verse/passage is visibly aligned.
3. Validates each source proposal against printed book/verse-marker evidence, Bible catalog coordinates, side and approximate vertical layout; never infers a book or nearest verse solely from a y value.
4. Combines the source proposal with each target-reference *segment* already parsed within that marginal row, resulting in a **proposed source → target** record. One printed row can yield multiple target segments.
5. Quarantines ambiguous alignments, missing source books, unparsed targets, human-confirmed cut-off references and chapter-only targets. Every result is **unverified**, with `sql_ready=false`; no automatic SQL writes or citation import.
6. Uses cached provider/row checkpoints and keeps a progress percentage so runs can resume without repeating successful calls.

**Current limit: pilot pages 31–40 (20 margin halves).** Once the proposals have been inspected we can safely expand the same stage across the rest of the already-scanned pages 31–500.

## Run on your existing Ubuntu VPS as root

**Step 1 — preflight, no paid API calls:**

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/run_fr88_source_links.sh | bash -s -- --preflight
```

**Step 2 — small paid pilot, maximum four new margin jobs:**

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/run_fr88_source_links.sh | bash -s -- --max-new-jobs 4
```

**Step 3 — publish results as text-only Git data for inspection:**

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/publish_fr88_source_links.sh | bash
```

Text results appear under:
https://github.com/tetrada/jbible-ocr-share/tree/main/fr88_source_links_pilot

After reviewing initial quality, continue at most 20 additional margin jobs without rerunning existing completed margins:

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/run_fr88_source_links.sh | bash -s -- --max-new-jobs 20
```

Offline progress with no DeepSeek API calls:

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/run_fr88_source_links.sh | bash -s -- --report-only
```

Note: `--report-only` refreshes aggregate JSON from existing checkpoints and never runs OCR.

## Files on VPS

`/opt/jbible/data/raw/jbible_fr88_source_links/`

- `frozen_source_prompt.txt` — instructions frozen at the start of the batch to make restart signatures reproducible; kept private.
- `image_0031_L.provider.json` etc. — original DeepSeek responses, **private and not committed to Git**.
- `image_0031_L.result.json` etc. — per-margin proposed main-text source anchors.
- `progress.json` — live completion percentage, candidate and review counts.
- `proposed_links.json` — source-to-target segment suggestions with visible printed evidence. **All require review.**
- `source_link_review_queue.json` — ambiguous or incomplete proposed links and why they were rejected for straightforward matching.

A proposed record has two distinct objects: `source` for the actual Bible verse/passage where the marginal row sits, and `target` for the Bible verse/chapter printed in that marginal row. The catalog checker limits structural nonsense but does not prove either reading was accurate.

Human-confirmed cut-off rows D051 and D010 are specifically prevented from becoming candidate links by `fr88_source_visibility_overrides.json`, even if their saved V2 text appears syntactically valid.

## Safety

- Both original images and prior OCR are read-only Docker mounts.
- No scanned Bible pages, API keys or provider payloads are published to GitHub.
- No main-text source anchor is marked scan-verified just because DeepSeek says HIGH.
- Matching by vertical coordinate **alone** never verifies a source verse.
- Source-book evidence must be printed on the scanned half; missing book context remains unresolved rather than defaulting to Genesis.
- Missing book abbreviations on target rows are not inherited from other printed rows.
- No SQL import, no verified Bible graph edges, no other model.
- Tests: `python3 /opt/jbible/importer/test_fr88_source_links.py` after installing it from GitHub, or GitHub Actions `fr88-source-links-tests.yml`.
