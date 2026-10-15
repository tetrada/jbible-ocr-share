#!/usr/bin/env bash
# Offline report only: no DeepSeek/API/SQL, only v3 pilot directory writable.
set -euo pipefail
BASE="/opt/jbible/importer"
RAW="/opt/jbible/data/raw"
OUT="$RAW/jbible_fr1988_v3_pilot_31_50"
[[ -s "$BASE/fr88_v3_review_pack.py" ]] || { echo "Missing fr88_v3_review_pack.py" >&2; exit 2; }
[[ -s "$RAW/jbible_fr1988_v2/interpreted_rows.json" ]] || { echo "Missing v2 baseline" >&2; exit 2; }
[[ -f "$OUT/comparison.json" ]] || { echo "Missing v3 pilot comparison" >&2; exit 2; }
docker run --rm --memory=4g --entrypoint python \
  -v "$BASE/fr88_v3_review_pack.py:/app/fr88_v3_review_pack.py:ro" \
  -v "$RAW:/raw:ro" \
  -v "$OUT:/raw/jbible_fr1988_v3_pilot_31_50:rw" \
  jbible-ocr:1 /app/fr88_v3_review_pack.py
