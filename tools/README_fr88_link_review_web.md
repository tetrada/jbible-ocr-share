# JBible FR88 — source-to-destination verification (corrected v2)

The corrected review model is **one source verse/passage → one destination reference per record**. A SINGLE physically printed marginal line can contain several destination references separated by semicolons. Each parsed destination has its own distinct review ID; the original printed OCR row ID stays as provenance.

The completed pages 31–40 pilot contains **151 target segments from 140 marginal OCR lines**. Therefore the protected reviewer displays **151 separate source→target review entries**, not 140. None is SQL-ready or canonically verified merely because the DeepSeek source match is plausible.

See [corrected source anchoring and page-header plan](README_fr88_source_links_v2.md).

## Upgrade existing private review page

Run on VPS as root:

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/install_fr88_source_link_review.sh | bash
```

Then use your existing reviewer password at:

https://status.tetrada.eu/jbible-review/links/

The page displays an original scan, one specific target reference from the margin, the complete printed row it came from, a proposed source book/chapter/verse, and source-page context. It supports correct/confirm/reject/uncertain per individual destination with scan checks. A red marker indicates the marginal OCR row, a green marker the proposed source location. Both geometric positions must be checked visually.

Existing OCR transcription decisions and any previous legacy row-based link decisions are retained unchanged:
- `/var/lib/jbible-review/decisions.json`
- `/var/lib/jbible-review/link_decisions.json`

New 1:1 edge decisions:
- `/var/lib/jbible-review/link_edge_decisions.json`
- `fr88_source_links_pilot/human_link_edge_reviews.json` on GitHub (text only)

## Source books and running-head chapter/verse

Source BOOK identity belongs to the page; it is not supposed to appear beside each margin reference. The page book registry is `training/fr88_page_book_registry.json`. It currently assigns working Genesis context for scanned pilot pages 31–40 and records the user's explicit page-102 example: **Exodus 16:21 at the top of the page**.

The small numeric pair printed at the top-left, such as `24 45` next to `LA GENÈSE` in the sample, provides the **starting source chapter and verse on that page**. Subsequent bold main-text chapter changes and verse markers determine which verse each marginal row physically aligns with. We must NOT assume the source verse is the page-start verse.

An independent, optional DeepSeek Flash extractor to read these page-start header pairs ONCE PER PAGE (not per margin) is at `tools/fr88_page_header_scan.py`. Do not treat its unverified output as confirmed until sampled against source images.

No scanned images or provider responses go to GitHub. No SQL writes. No other AI models.
