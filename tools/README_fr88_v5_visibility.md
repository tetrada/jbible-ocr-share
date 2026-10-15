# FR88 V5: stop inventing unreadable verse numbers

The page 32 right-hand scan was human-reviewed: only the prefix `↗ 1 Co 15` is visible. V2/V3 claimed verse 45, V4 claimed verse 2. Neither full reading is supported.

V5 is a **small prompt experiment**, not model fine-tuning. It uses the page-34 cut-off review as a teaching example and keeps page 32 entirely outside the prompt as a holdout.

Free preflight:

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/run_fr88_v5_visibility.sh | bash -s -- --start 32 --end 32 --preflight
```

Paid test: only page 32 (two margins):

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/run_fr88_v5_visibility.sh | bash -s -- --start 32 --end 32 --max-new-margins 2
```

Publish text-only results to existing Git repository:

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/publish_fr88_v5_visibility.sh | bash
```

Outputs are isolated in `/opt/jbible/data/raw/jbible_fr1988_v5_visibility/`. The scorer requires both an exact visible prefix and an explicit CUT_OFF or UNREADABLE flag. Additional invented verse digits fail the test. The complete hidden reference remains unknown. V2/V3/V4 source data is read-only, with no SQL writes. Scanned images and provider payloads stay on the VPS.
