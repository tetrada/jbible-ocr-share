#!/usr/bin/env bash
# Quarantine one pathological saved provider reply, not the whole OCR batch.
set -euo pipefail
[[ $(id -u) -eq 0 ]] || { echo 'Run as root' >&2; exit 2; }
OUT=/opt/jbible/data/raw/jbible_fr88_integrated_v1
python3 - "$OUT" <<'PY'
import json,sys,os
from pathlib import Path
from datetime import datetime,timezone
out=Path(sys.argv[1])
p=out/"image_0168.verses_L.provider.json"
parsed=out/"image_0168.verses_L.result.json"
if parsed.exists(): raise SystemExit("Parsed stage already exists; refusing to alter")
doc=json.loads(p.read_text(encoding="utf-8"))
response=doc.get("response") or {}
choices=response.get("choices") or []
raw=(choices[0].get("message") or {}).get("content") if choices else None
if not isinstance(raw,str): raise SystemExit("Missing provider content; do not change cache")
data=json.loads(raw)
markers=data.get("markers")
if not isinstance(markers,list): raise SystemExit("Expected marker array missing; do not change cache")
print("PAGE 168 LEFT OCR: marker count =",len(markers))
print("Marker types:",sorted(set(type(x).__name__ for x in markers)))
if len(markers)<=1000:
    raise SystemExit("Not the expected >1000-marker failure. Do not quarantine.")
backup=out/"image_0168.verses_L.provider.invalid_over1000.json"
if backup.exists(): raise SystemExit("Audit backup already exists. Refusing to overwrite")
os.rename(str(p),str(backup))
print("QUARANTINED",p.name,"as",backup.name)
print("Original saved reply retained privately; next scan will redo only this stage.")
PY
