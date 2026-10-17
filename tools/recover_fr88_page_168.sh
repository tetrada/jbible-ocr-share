#!/usr/bin/env bash
# Recover page 168's pathological cached left verse output; no other cache removed.
set -euo pipefail
ROOT=https://raw.githubusercontent.com/tetrada/jbible-ocr-share
BASE=/opt/jbible/data/raw/jbible_fr88_integrated_v1
[[ $(id -u) == 0 ]] || { echo "Run as root" >&2; exit 2; }
[[ -d "$BASE" ]] || { echo "Integrated cache missing" >&2; exit 2; }
# Verify current state, and preserve original provider evidence if oversized.
python3 - "$BASE" <<'PY'
import json,sys,os
from pathlib import Path
d=Path(sys.argv[1]); p=d/"image_0168.verses_L.provider.json"
stage=d/"image_0168.verses_L.result.json"
if stage.exists():
    obj=json.loads(stage.read_text())
    markers=(obj.get("data") or {}).get("markers") or []
    if 0<len(markers)<=150:
        print("Valid existing page-168 left stage:",len(markers))
        raise SystemExit(0)
    raise SystemExit("Existing parsed stage is suspicious; manual inspection required")
if not p.exists():
    print("No provider checkpoint; left OCR will be requested")
    raise SystemExit(0)
obj=json.loads(p.read_text())
ch=(obj.get("response") or {}).get("choices") or []
raw=((ch[0].get("message") or {}).get("content")) if ch else None
if not isinstance(raw,str): raise SystemExit("Malformed provider response; stopping")
data=json.loads(raw); markers=data.get("markers")
if not isinstance(markers,list): raise SystemExit("Malformed marker array; stopping")
print("Cached page 168 left verse OCR markers:",len(markers))
if len(markers)<=150: raise SystemExit(0)
if len(markers)<=1000: raise SystemExit("Oversized but not known >1000 condition; stopping")
backup=d/"image_0168.verses_L.provider.invalid_over1000.json"
if backup.exists(): raise SystemExit("Quarantine backup already exists; inspect first")
os.rename(str(p),str(backup))
print("Quarantined oversized provider response; other stages untouched")
PY
# Use pinned tested runner; --max-new-calls is explicit budget, cached stages reused.
curl -fsSL "$ROOT/9f5813f711220ec3a8da49fc491ee5b29c2a583a/tools/run_fr88_integrated_page.sh" |
  bash -s -- --start 168 --end 168 --max-new-calls 5
# Check stage exists and isn't abnormally large before publication.
python3 - "$BASE" <<'PY'
import json,sys
from pathlib import Path
d=Path(sys.argv[1]); p=d/"image_0168.verses_L.result.json"
if not p.exists(): raise SystemExit("No parsed left verse stage")
markers=(json.loads(p.read_text()).get("data") or {}).get("markers") or []
print("Recovered left verse marker count:",len(markers))
if not (1<=len(markers)<=150):
    raise SystemExit("Stage requires inspection; not publishing")
bundle=d/"image_0168.bundle.json"
if not bundle.exists(): raise SystemExit("No completed page bundle")
print("Page 168 rebuilt. Note: unusual chapter sequence requires independent review.")
PY
curl -fsSL "$ROOT/main/tools/publish_fr88_integrated_page.sh" | bash
