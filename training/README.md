# JBible FR88 OCR: learning from verified corrections

This repository stores a **human-confirmed OCR gold corpus** in [fr88_ocr_gold.json](fr88_ocr_gold.json). It is NOT a model checkpoint, and it does not modify the hosted DeepSeek model's weights.

## Current state

- 20-page OCR v3 pilot (pages 31–50) had 32 **disagreement groups**, but neither variant has been proven more accurate. v2 reported 2 invalid coordinates; v3 reported none and 3 more section labels.
- One scan-confirmed **typography** example is seeded: printed arrow + `2 P 2 5` means 2 Peter, chapter 2 (bold), verse 5 (regular). The uploaded close-up does **not** establish which page-37 row it came from, so no row ID was invented.
- Other examples need checking against the original image and correction before promoting to gold.
- **Never** treat grammar/catalog-valid results as verified scan readings. Separate prompt examples and holdout evaluations.

## Publish the 20-page text disagreement queue to GitHub

On the JBible VPS as root:

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/publish_fr88_v3_learning.sh | bash
```

This reads the existing saved v2/v3 pilot JSON and exports **text only** to the tracked `fr88_v3_learning/` folder. It uses the existing `/opt/jbible/ocr-share-git` checkout, its configured SSH deployment key and the shared Git sync lock, then fetches and fast-forwards from `main`, stages only those two JSON files, and pushes them. If the checkout is dirty it stops instead of making unsafe commits. No scanned JPEGs, copyright page crops, provider responses, secrets, SQL, or API calls are published.

Outputs:
- `fr88_v3_learning/pilot_summary.json` — pilot's known metrics, accuracy explicitly **NOT MEASURED**.
- `fr88_v3_learning/disagreements.json` — all discrepancy groups and V3's section labels, with row IDs, local original scan positions and status **PENDING_IMAGE_REVIEW**.

A reviewer checks each proposed change on its original VPS scan `/opt/jbible/data/raw/fr_bible_1988/image_####.jpg`, then commits confirmed examples to the gold file, using `human_confirmed_from_original_scan`. Include exact book abbreviation, bold chapter boundary and verse digits, and record why the previous OCR reading failed. **Do not copy unconfirmed V3 interpretations into the gold file.**

## Easy visual verification webpage (recommended)

Deploy the password-protected reviewer once:

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/install_fr88_review_web.sh | bash
```

Then open **https://status.tetrada.eu/jbible-review/** with the username/password printed during installation. For each page scan, choose V2/V3/Neither/Unsure, edit the exact physical printed lines if necessary, check the original-image confirmation box and save. Seven substantive cases are queued first. See [review web README](../tools/README_fr88_review_web.md) for implementation and security notes.

The server stores human decisions locally and its 2-minute publishing timer commits **text only** to `fr88_v3_learning/human_reviews.json`. The GitHub corpus still requires explicit curation to become DeepSeek few-shot training examples. No ZIPs, no public scan uploads and no automatic assumption that a model's guess is ground truth.

## Prioritized visual review: seven substantive differences

The 20-page V2/V3 comparison has **32 difference groups, but 25 are cosmetic arrow/spacing changes**. The seven meaningfully different groups are in [fr88_priority_review.json](fr88_priority_review.json):

- D003, page 32 right: physical-row split and number boundaries.
- D010, page 34 right: newly added number after comma.
- D012, page 37 left: missing `Si 16 7` in V3.
- D013 and D014, page 37 right: chapter/verse `2 P 2 5` typography.
- D016, page 40 left: bare `10 6` omitted by V3.
- D017, page 41 left: prose/label inclusion.

Review the original JPEGs, not only the two models' transcriptions. The priority file is a **review queue, not additional gold labels**. Once the exact printed rows are visually confirmed, add representative cases to the gold corpus; preserve a separate held-out validation set.

## Teach the API model for the next run

The tool [fr88_learning_prompt.py](../tools/fr88_learning_prompt.py) compiles only human-confirmed `inclusion: prompt_example` cases into the v3 typography instructions, rejects held-out examples and uncertain labels, and embeds the confirmed corrections into **every request** of the next isolated v4 experiment.

The [v4 launcher](../tools/run_fr88_v4_learning.sh) defaults to **at least 12 verified examples before any paid OCR**, to avoid spending again on a prompt with just our single known example. Its output folder is `/opt/jbible/data/raw/jbible_fr1988_v4_learning/`. Existing v2 and v3 checkpoints are not overwritten.

Once 12+ examples have been checked and committed to GitHub, on VPS:

```bash
cd /opt/jbible/importer
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/run_fr88_v4_learning.sh -o run_fr88_v4_learning.sh
chmod +x run_fr88_v4_learning.sh
./run_fr88_v4_learning.sh --preflight
# Initially re-test a small set; this calls the paid OCR API.
./run_fr88_v4_learning.sh --start 31 --end 34
```

The 12-example guard is intentionally strict: if no additional examples have been visually confirmed, **do not rerun 20 pages**.

## Evaluating actual learning

A useful metric is `exact_raw_transcription_accuracy_on_held_out_scan_verified_lines`, together with row recall and error rate for bold chapter/verse splits, book ordinals, multi-reference rows and suffixes.

Never show parsing percentage or zero catalog-invalid references as proof of OCR quality. Keep test/holdout labels out of the training prompt.

DeepSeek's hosted `deepseek-flash` chat API documents inference and in-context messages; it does not provide an established per-account model fine-tuning/training endpoint. Thus this pipeline performs **few-shot / in-context learning**, not weight updates. Real weight fine-tuning would require a supported trainable model in separate infrastructure.
