#!/usr/bin/env bash
# Usage: ./run_fr1988.sh 37 60
set -euo pipefail

START="${1:-37}"
END="${2:-60}"
[[ "$START" =~ ^[0-9]+$ && "$END" =~ ^[0-9]+$ ]] || { echo "Expected numeric pages: START END"; exit 2; }
(( 10#$START >= 1 && 10#$END >= 10#$START )) || { echo "Invalid page range"; exit 2; }

BASE="/opt/jbible/importer"
RAW="/opt/jbible/data/raw"
SOURCE_DIR="$RAW/fr_bible_1988"

[[ -f "$BASE/jbible_fr1988_pilot.py" ]] || { echo "Missing $BASE/jbible_fr1988_pilot.py"; exit 1; }
[[ -s "$SOURCE_DIR/image_$(printf '%04d' "$START").jpg" ]] || { echo "Missing first JPEG"; exit 1; }
[[ -s "$SOURCE_DIR/image_$(printf '%04d' "$END").jpg" ]] || { echo "Missing last JPEG"; exit 1; }
[[ -s "$RAW/jbible_dual_v1/en/all_records.json" ]] || { echo "Missing EN dataset"; exit 1; }

exec docker run --rm \
  --memory=4g \
  --network bridge \
  --env-file "$BASE/.env.deepseek" \
  --env-file "$BASE/.env.status" \
  --entrypoint python \
  -v "$BASE/jbible_fr1988_pilot.py:/app/jbible_fr1988_pilot.py:ro" \
  -v "$BASE/fr88_multibook.py:/app/fr88_multibook.py:ro" \
  -v "$BASE/jbible_dual.py:/app/jbible_dual.py:ro" \
  -v "$BASE/jbible_v79_typography.py:/app/jbible_v79_typography.py:ro" \
  -v "$BASE/jbible_v710_validate.py:/app/jbible_v710_validate.py:ro" \
  -v "$BASE/jbible_v711_catalog.py:/app/jbible_v711_catalog.py:ro" \
  -v "$BASE/jbible_status_bridge.py:/app/jbible_status_bridge.py:ro" \
  -v "$BASE/status_sdk:/app/status_sdk:ro" \
  -v "$RAW:/raw" \
  jbible-ocr:1 /app/jbible_fr1988_pilot.py \
  --start "$START" --end "$END"
