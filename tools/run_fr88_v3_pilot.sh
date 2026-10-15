#!/usr/bin/env bash
# Isolated DeepSeek FR88 v3 pilot, up to 20 pages (31..50). Python runs in existing jbible-ocr:1 Docker image.
set -euo pipefail
BASE="/opt/jbible/importer"
RAW="/opt/jbible/data/raw"
for F in fr88_v3_pilot.py fr88_v3_typography_prompt.txt fr88_v2_ocr.py fr88_v2_normalize.py; do
  [[ -s "$BASE/$F" ]] || { echo "Missing $BASE/$F" >&2; exit 2; }
done
[[ -s "$BASE/.env.deepseek" ]] || { echo "Missing .env.deepseek" >&2; exit 2; }
[[ -s "$RAW/jbible_fr1988_v2/interpreted_rows.json" ]] || { echo "Missing v2 baseline" >&2; exit 2; }
OUT="$RAW/jbible_fr1988_v3_pilot_31_50"
mkdir -p "$OUT"
command -v docker >/dev/null
command -v flock >/dev/null
DOCKER=(docker run --rm --memory=4g
  --env-file "$BASE/.env.deepseek"
  --entrypoint python
  -v "$BASE/fr88_v3_pilot.py:/app/fr88_v3_pilot.py:ro"
  -v "$BASE/fr88_v3_typography_prompt.txt:/app/fr88_v3_typography_prompt.txt:ro"
  -v "$BASE/fr88_v2_ocr.py:/app/fr88_v2_ocr.py:ro"
  -v "$BASE/fr88_v2_normalize.py:/app/fr88_v2_normalize.py:ro"
  -v "$RAW:/raw:ro"
  -v "$OUT:/raw/jbible_fr1988_v3_pilot_31_50:rw"
  jbible-ocr:1
  /app/fr88_v3_pilot.py
  "$@")
# Prevent simultaneous use of the v2 source pipeline; own lock prevents duplicate v3 calls.
exec flock -n /run/jbible-fr88-v2.lock flock -n /run/jbible-fr88-v3.lock "${DOCKER[@]}"
