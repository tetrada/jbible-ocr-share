#!/usr/bin/env bash
# Human-verified few-shot OCR experiment; defaults to 12 scan-confirmed examples.
# Does not overwrite v2/v3. Use --preflight first; later --start 31 --end 35.
set -euo pipefail
BASE=/opt/jbible/importer
RAW=/opt/jbible/data/raw
OUT="$RAW/jbible_fr1988_v4_learning"
URL=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools
GOLDURL=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/training/fr88_ocr_gold.json
MIN_EXAMPLES="${JBIBLE_MIN_GOLD_EXAMPLES:-12}"
[[ "$MIN_EXAMPLES" =~ ^[0-9]+$ ]] && (( MIN_EXAMPLES > 0 )) || {
  echo 'Invalid verified-example minimum' >&2; exit 2;
}
for f in fr88_v3_pilot.py fr88_v3_typography_prompt.txt fr88_v2_ocr.py fr88_v2_normalize.py; do
  [[ -s "$BASE/$f" ]] || { echo "Missing $BASE/$f" >&2; exit 2; }
done
[[ -s "$BASE/.env.deepseek" ]] || { echo 'Missing DeepSeek env file' >&2; exit 2; }
[[ -s "$RAW/jbible_fr1988_v2/interpreted_rows.json" ]] || {
  echo 'Missing v2 baseline' >&2; exit 2;
}
mkdir -p "$OUT"
for f in fr88_learning_prompt.py fr88_v4_learning_proxy.py fr88_v4_holdout_eval.py; do
  temp="$(mktemp "$BASE/.fr88_v4_download_XXXXXXXX")"
  curl -fsSL --retry 3 "$URL/$f" -o "$temp" || { rm -f "$temp"; exit 1; }
  mv "$temp" "$BASE/$f"
done
temp="$(mktemp "$BASE/.fr88_gold_XXXXXXXX")"
curl -fsSL --retry 3 "$GOLDURL" -o "$temp" || { rm -f "$temp"; exit 1; }
mv "$temp" "$BASE/fr88_ocr_gold.json"
python3 "$BASE/fr88_learning_prompt.py" \
  --base "$BASE/fr88_v3_typography_prompt.txt" \
  --gold "$BASE/fr88_ocr_gold.json" \
  --output "$OUT/learned_prompt.txt" \
  --min-verified "$MIN_EXAMPLES" --max-examples 20
# v3's hash checkpoint protection prevents overwriting if prompt changes.
DOCKER=(docker run --rm --memory=4g --env-file "$BASE/.env.deepseek"
  --entrypoint python
  -v "$BASE/fr88_v4_learning_proxy.py:/app/fr88_v4_learning_proxy.py:ro"
  -v "$BASE/fr88_v3_pilot.py:/app/fr88_v3_pilot.py:ro"
  -v "$BASE/fr88_v2_ocr.py:/app/fr88_v2_ocr.py:ro"
  -v "$BASE/fr88_v2_normalize.py:/app/fr88_v2_normalize.py:ro"
  -v "$RAW:/raw:ro"
  -v "$OUT:/raw/jbible_fr1988_v4_learning:rw"
  jbible-ocr:1 /app/fr88_v4_learning_proxy.py "$@")
if [[ "${1:-}" == "--preflight" ]]; then
  exec flock -n /run/jbible-fr88-v2.lock flock -n /run/jbible-fr88-v4.lock "${DOCKER[@]}"
fi

set +e
flock -n /run/jbible-fr88-v2.lock flock -n /run/jbible-fr88-v4.lock "${DOCKER[@]}"
RUN_STATUS=$?
set -e
if [[ -f "$OUT/comparison.json" ]]; then
  echo "Running independent, read-only holdout regression check..."
  docker run --rm --memory=4g --entrypoint python \
    -v "$BASE/fr88_v4_holdout_eval.py:/app/fr88_v4_holdout_eval.py:ro" \
    -v "$BASE/fr88_ocr_gold.json:/app/fr88_ocr_gold.json:ro" \
    -v "$RAW:/raw:ro" \
    -v "$OUT:/raw/jbible_fr1988_v4_learning:rw" \
    jbible-ocr:1 /app/fr88_v4_holdout_eval.py || {
      echo "WARNING: Holdout regression evaluation failed; OCR checkpoints remain saved." >&2
    }
fi
exit "$RUN_STATUS"
