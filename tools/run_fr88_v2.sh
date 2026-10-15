#!/usr/bin/env bash
# JBible FR88 v2 Docker runner. Example: ./run_fr88_v2.sh 32 500
# Other modes: ./run_fr88_v2.sh 32 500 --preflight|--initialize
set -euo pipefail
START="${1:-32}"
END="${2:-500}"
MODE="${3:-}"
[[ "$START" =~ ^[0-9]+$ && "$END" =~ ^[0-9]+$ ]] || {
  echo "Pages must be integers." >&2; exit 2;
}
(( 10#$START >= 1 && 10#$END >= 10#$START )) || {
  echo "Invalid page range." >&2; exit 2;
}
[[ -z "$MODE" || "$MODE" == "--preflight" || "$MODE" == "--initialize" ]] || {
  echo "Unknown mode: $MODE" >&2; exit 2;
}
BASE="/opt/jbible/importer"
RAW="/opt/jbible/data/raw"
for FILE in fr88_v2_normalize.py fr88_v2_ocr.py jbible_status_bridge.py; do
  [[ -s "$BASE/$FILE" ]] || { echo "Missing $BASE/$FILE"; exit 2; }
done
for FILE in .env.deepseek .env.status; do
  [[ -s "$BASE/$FILE" ]] || { echo "Missing $BASE/$FILE"; exit 2; }
done
[[ -d "$BASE/status_sdk" ]] || { echo "Missing status SDK"; exit 2; }
[[ -d "$RAW/fr_bible_1988" ]] || { echo "Missing JPEG directory"; exit 2; }
[[ -f "$RAW/jbible_catalog.csv" ]] || { echo "Missing Bible catalog"; exit 2; }

DOCKER=(docker run --rm --memory=4g
  --env-file "$BASE/.env.deepseek"
  --env-file "$BASE/.env.status"
  --entrypoint python
  -v "$BASE/fr88_v2_ocr.py:/app/fr88_v2_ocr.py:ro"
  -v "$BASE/fr88_v2_normalize.py:/app/fr88_v2_normalize.py:ro"
  -v "$BASE/jbible_status_bridge.py:/app/jbible_status_bridge.py:ro"
  -v "$BASE/status_sdk:/app/status_sdk:ro"
  -v "$RAW:/raw"
  jbible-ocr:1
  /app/fr88_v2_ocr.py --start "$START" --end "$END")
if [[ -n "$MODE" ]]; then
  DOCKER+=("$MODE")
fi
exec flock -n /run/jbible-fr88-v2.lock "${DOCKER[@]}"
