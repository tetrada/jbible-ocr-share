# JBible FR88 — human verification of source→margin links

The first source-to-target pilot has processed all scanned page margins 31–40 using DeepSeek Flash. It emitted 23 proposed source-target *segments* and 128 segments requiring further review, and 64 separate context suggestions. Those are **151 target segments across 140 unique printed marginal rows**. None has been human-verified or imported into SQL.

## Activate the existing authenticated VPS review page

Run as root on the existing VPS:

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/install_fr88_source_link_review.sh | bash
```

Open:

**https://status.tetrada.eu/jbible-review/links/**

Use your EXISTING OCR review username/password. The original **https://status.tetrada.eu/jbible-review/** remains accessible and its decisions are never overwritten.

The installer downloads and validates the completed text-only source-link pilot, new HTML/JS, and enhanced protected Python server. It tests server logic before restarting the existing local-only 127.0.0.1 service, and checks that an anonymous request is rejected with HTTP 401. It reuses the existing Nginx HTTPS route. No new API calls or scanned Bible uploads.

## How the review works

Each entry is ONE physical printed marginal row, even when it contains several target references separated by semicolons.

The left pane shows the original scanned French 1988 Jerusalem Bible half-page, enlarged and centered on the reference; **red** shows the printed margin row position, **green** shows the model's proposed main-text source marker. Zoom, full page and navigation to adjacent scan pages are included (to inspect page headers and book transitions). Red and green lines are approximate OCR/DeepSeek coordinates, not human-verified anchors.

The right pane shows:
- the exact saved marginal text and parsed candidate target references;
- DeepSeek's proposed book, chapter, verse/passage, evidence and reason;
- any **neighboring-page book suggestion**, clearly labeled UNVERIFIED;
- editable source-book code, chapter, verse, passage range and target raw-line text;
- book evidence: printed on this page, neighboring page, checked book continuation, or unknown;
- separate scan checkboxes for source marker, marginal target print and their alignment;
- Confirm / Corrected / Uncertain / Reject and Save (or Save & Next).

The server refuses to accept Confirm/Corrected unless all three scan checkboxes are checked, a source book/chapter/scope is specified, and a verse number is specified for verse links. Corrected text is never silently reinterpreted as a verified canonical target.

The queue offers proposed matches, uncertain matches, reviewed entries and outstanding-first views. These are **human visual decisions** only: `sql_ready=false`, `biblical_target_canonically_verified=false`.

### Why page 40 is Genesis, even if other entries lack source book

Page 40 right actually contains a printed `GENÈSE` header and DeepSeek proposed `Gen 10:8` for one margin row. The initial matching script deliberately demanded a **visible book name on each analyzed page half**, so it left other main-text verses with no visible book header as unresolved. **96 review entries** had `SOURCE_BOOK_NOT_PRINTED` under this deliberately strict rule; they represent link segments, not 96 different pages. There were **64 context suggestions** from nearby printed pages; they are possible aids, not independently verified main-text links.

For human verification, a clearly checked running header, a neighboring printed book header, or an inspected continuation can be recorded explicitly. That is different from guessing an unsupported book by textual similarity or accepting a DeepSeek HIGH-confidence claim.

## Results & safety

Link decisions stay separate from the original OCR decisions:
- Existing: `/var/lib/jbible-review/decisions.json`
- New: `/var/lib/jbible-review/link_decisions.json`
- GitHub text-only: `fr88_source_links_pilot/human_link_reviews.json`

The installer enables `jbible-fr88-link-review-publish.timer` to sync the decisions approximately every two minutes using the existing SSH deploy key and Git lock, **only when the first new decision has been saved**.

**No scanned images, passwords, API provider payloads, or copyright book pages are published**. The service binds only to localhost behind the existing HTTPS Nginx proxy with Basic auth.

No DeepSeek calls, no change to original V2 OCR data, and **no SQL writes**. Source and target canonicals remain pending until separately validated against the catalog and corresponding physical scan evidence.

### Files

- `tools/fr88_link_review_index.html` and `tools/fr88_link_review_app.js`: authenticated user interface
- `tools/fr88_review_web_server.py`: existing OCR-review server extended with isolated source-link API and state
- `tools/test_fr88_link_review_web.py`: offline input validation and one-row/multi-segment tests
- `tools/fr88_link_review_publish.sh`: publish only checked text-only decisions
- `tools/install_fr88_source_link_review.sh`: no-API installation with backup and health/security checks
