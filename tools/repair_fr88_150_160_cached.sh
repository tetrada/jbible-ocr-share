#!/usr/bin/env bash
# Rebuild cached Leviticus source intervals, preserving saved OCR and human reviews.
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root on JBible VPS" >&2; exit 2; }
ROOT=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main
OUT=/opt/jbible/data/raw/jbible_fr88_integrated_v1
[[ -d "$OUT" ]] || { echo "Missing integrated OCR cache" >&2; exit 2; }
python3 - "$OUT" <<'PY'
import json,sys
from pathlib import Path
out=Path(sys.argv[1])
for page in range(150,161):
    stages=[out/("image_%04d.%s.result.json"%(page,task))
            for task in ("header","verses_L","verses_R","margin_L","margin_R")]
    missing=[x.name for x in stages if not x.is_file()]
    if missing:
        raise SystemExit("Refusing incomplete cached rebuild page %d: %s"%(page,missing))
for page in (150,151,152):
    a=out/("image_%04d.bundle.json"%page)
    if not a.is_file(): raise SystemExit("Missing original bundle "+str(a))
    doc=json.loads(a.read_text(encoding="utf-8"))
    print("BEFORE",page,doc.get("page_book"),doc.get("summary"))
PY
curl -fsSL "$ROOT/tools/run_fr88_integrated_page.sh" | bash -s -- \
  --start 150 --end 160 --max-new-calls 1 --rebuild-bundles
python3 - "$OUT" <<'PY'
import json,sys
from pathlib import Path
out=Path(sys.argv[1])
for page in (150,151,152):
    doc=json.loads((out/("image_%04d.bundle.json"%page)).read_text(encoding="utf-8"))
    code=(doc.get("page_book") or {}).get("book_code")
    intervals=doc.get("verse_intervals_by_column") or {}
    counts={s:len(intervals.get(s) or []) for s in ("L","R")}
    print("AFTER",page,code,counts,doc.get("summary"))
    if code!="Lev" or not all(counts.values()):
        raise SystemExit("Rebuild failed checks, refusing to publish page %d"%page)
PY
curl -fsSL "$ROOT/tools/publish_fr88_integrated_page.sh" | bash
echo "REPAIRED: regenerated source intervals from saved OCR; no new API calls or SQL writes."
