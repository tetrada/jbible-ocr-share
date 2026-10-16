# FR88 integrated OCR: pages 31–50 completed pilot audit

Published test run: `fr88_integrated_v1/pilot_report.json`, 2026-10-16.

## Measured acceptance (not independently measured accuracy)

- 20/20 page bundles completed; resumed last 4 pages with 19 new DeepSeek Flash visual requests.
- 273 atomic source→destination links, 272 automatically accepted (99.63% operational acceptance), 1 excluded.
- 71 plain accepted, 21 flagged, 159 estimated, 21 human-reviewed corrected, 1 exception.
- **Only 21 individual accepted edges have independent scan-reviewed provenance.** The 99.63% operational acceptance rate is NOT a claim of 99.63% correct Bible links.
- The one excluded record is the genuinely cropped `↗ 1 Co 15` on page 32 whose unreadable continuation had been wrongly inferred as `45`.

## Marginal reference OCR comparison

Earlier V2 shards for image pages 31–50: **251 printed marginal rows, 265 parsed destination segments**. Integrated report: **252 distinct printed-row IDs, 273 atomic target links**. The greater atomic target count reflects parsing improvements including comma-separated verse lists and partial-prefix recovery; it is not itself proof all destinations are correct.

Normalized printed-row text comparison between the passes:
- Page 32 R: V2 `Qo 3 20s; 12 7` vs integrated `Qo 3 20s;` and `12 7`; both references remain represented.
- Page 34 R: V2 `Ps 90 3; 104` vs integrated `Ps 90 3; 104 2`. Difference in the second target extent remains **unconfirmed from scan**.
- Page 34 R: V2 `Ap 22 1s,` vs integrated `↗ Ap 22 1s, 1`; the later scan review recorded a specific corrected target `Rev 1:1`, not a general editing rule.
- All other rows have matching normalized text between V2 and the integrated report (comparison only; either pass may still err).

## Structural checks: important failures invisible in accepted percentage

1. **Image page 39 running header contradiction.** The header OCR reported `TOP_LEFT / FIRST_ON_PAGE / Gen 1:22`, while the actual body verse markers on the same page begin `Gen 8:18` and the preceding scanned page ends `Gen 8:17`. Previously the wrong chapter-1 header was seeded as a source, producing at least one obviously wrong accepted source link. Fixed: `make_intervals` now rejects the conflicting HEADER as a source seed, uses preceding page and body marker context, raises `PAGE_START_HEADER_CONTRADICTS_BODY`, and marks that page's links as **accepted estimates**.
2. **Image page 42 column-order rewind.** The L-column OCR ends at `Gen 12:6` but the R-column OCR begins at `Gen 11:30`, a contradiction for normal left-to-right reading order. The present data cannot establish which printed marker is misassigned without rescanning or visually checking body coordinates. Fixed: `COLUMN_VERSE_SEQUENCE_REWINDS` is raised and all page links are classified as **accepted estimates**, not falsely `ACCEPTED`. This is NOT a correction of the underlying OCR text.
3. **Image page 35 non-monotonic vertical marker.** Left column `Gen 4:14@y=.916` is followed by `Gen 4:15@y=.062` in model sequence. Already flagged as estimated, no source text invented.
4. **Coincident y-values and nonpositive verse intervals** on pages 38, 39, 41, 50. These arise from imperfect numeric marker coordinate estimates (e.g. two markers at y=1.0); do not silently count as exact alignment.
5. **Page 47 end header** reads `Gen 18:25` but the last printed body verse marker extracted is `Gen 18:24`; the next page starts at `Gen 18:26`. This may reflect an omitted final body marker, not necessarily a wrong running head. A QA flag is retained, and no fabricated verse coordinate is claimed.

## Policy and next step

The user explicitly permits plausible ±1-verse source estimates and does **not** want routine manual review. Do not turn these structural warnings into broad review queues. Preserve all accepted connections as estimates where relevant, and exclude only truly uninterpretable/cropped references.

**Required:** rebuild the 20 cached page bundles using the current code with `--rebuild-bundles` and publish the revised text report. This takes **zero new DeepSeek calls** and no SQL writes. Verify that page 39's incorrect `Gen 1:22` source is gone, page 42's cross-column warning is present, and the accepted/exception counts remain internally consistent. Do not mistake the corrected summary for proof of 99% real precision/recall.

Further work: strengthen main-text marker y-coordinate extraction / cross-column physical continuity before scaling to all 470 scans, and evaluate a random independent sample of **whole source→target edges**, rather than checking just target OCR or acceptance rates.
