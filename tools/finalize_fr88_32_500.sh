#!/usr/bin/env bash
# Restore only missing FR88 v2 margins, then rebuild all interpretations offline.
# Original OCR checkpoints remain untouched. No SQL writes or verification.
set -euo pipefail
BASE=/opt/jbible/importer
RAW=/opt/jbible/data/raw
URL=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools

[[ "$(id -u)" == "0" ]] || { echo "Run as root" >&2; exit 2; }
if systemctl is-active --quiet jbible-fr88-v2.service; then
  echo "The original FR88 OCR service is still running; wait for it to finish." >&2
  exit 2
fi
[[ -d "$RAW/jbible_fr1988_v2" ]] || { echo "V2 results not found" >&2; exit 2; }
[[ -s "$RAW/jbible_fr1988_v2/summary.json" ]] || { echo "V2 summary missing" >&2; exit 2; }
[[ -s "$RAW/jbible_catalog.csv" ]] || { echo "Book catalog missing" >&2; exit 2; }
[[ -s "$BASE/.env.deepseek" ]] || { echo "DeepSeek API env file missing" >&2; exit 2; }
cd "$BASE"
for NAME in fr88_v2_ocr.py fr88_v2_normalize.py fr88_v2_finalize.py; do
  TEMP="$(mktemp "$BASE/.fr88final.XXXXXXXX")"
  if ! curl -fsSL --retry 3 --connect-timeout 20 "$URL/$NAME" -o "$TEMP"; then
    rm -f "$TEMP"; exit 1
  fi
  install -m 644 "$TEMP" "$BASE/$NAME"
  rm -f "$TEMP"
done
python3 -m py_compile "$BASE/fr88_v2_ocr.py" \
  "$BASE/fr88_v2_normalize.py" "$BASE/fr88_v2_finalize.py"
echo "Starting FR88 v2 finalization: repair max 3 missing margins, re-interpret all rows."
exec flock -n /run/jbible-fr88-v2.lock \
  docker run --rm --memory=4g --env-file "$BASE/.env.deepseek" \
  --entrypoint python \
  -v "$BASE/fr88_v2_ocr.py:/app/fr88_v2_ocr.py:ro" \
  -v "$BASE/fr88_v2_normalize.py:/app/fr88_v2_normalize.py:ro" \
  -v "$BASE/fr88_v2_finalize.py:/app/fr88_v2_finalize.py:ro" \
  -v "$RAW:/raw" \
  jbible-ocr:1 \
  /app/fr88_v2_finalize.py --start 32 --end 500 --repair-missing --max-missing 3
