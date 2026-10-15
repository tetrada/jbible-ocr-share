#!/usr/bin/env bash
# Continue FR1988 marginal OCR pages 501..750 using DeepSeek Flash only.
# Usage:
#  ./run_fr88_next_batch.sh --preflight
#  ./run_fr88_next_batch.sh --max-new-margins 500
#  ./run_fr88_next_batch.sh --report-only
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root on JBible VPS" >&2; exit 2; }
BASE=/opt/jbible/importer
RAW=/opt/jbible/data/raw
OUT="$RAW/jbible_fr1988_deepseek_p0501_0750"
URL=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main
for name in fr88_v3_pilot.py fr88_v2_ocr.py fr88_v2_normalize.py fr88_v3_typography_prompt.txt; do
  [[ -s "$BASE/$name" ]] || { echo "Missing $BASE/$name" >&2; exit 2; }
done
[[ -s "$BASE/.env.deepseek" ]] || { echo "Missing existing .env.deepseek" >&2; exit 2; }
[[ -s "$RAW/jbible_catalog.csv" ]] || { echo "Missing local Bible catalog" >&2; exit 2; }
[[ -s "$RAW/jbible_fr1988_v2/interpreted_rows.json" ]] || { echo "Missing previous V2 reference data" >&2; exit 2; }
mkdir -p "$OUT"
for name in fr88_deepseek_continue.py fr88_visibility_gate.py fr88_learning_prompt.py fr88_v5_visibility_rules.txt; do
  temp="$(mktemp "$BASE/.fr88_next_download_XXXXXXXX")"
  if ! curl -fsSL --retry 3 --connect-timeout 20 "$URL/tools/$name" -o "$temp"; then
    rm -f "$temp"
    echo "Could not download $name" >&2
    exit 1
  fi
  test -s "$temp"
  mv "$temp" "$BASE/$name"
  chmod 0644 "$BASE/$name"
done
if [[ ! -s "$OUT/batch_prompt.txt" ]]; then
  temp="$(mktemp "$BASE/.fr88_next_gold_XXXXXXXX")"
  curl -fsSL --retry 3 --connect-timeout 20 \
    "$URL/training/fr88_ocr_gold.json" -o "$temp"
  mv "$temp" "$BASE/fr88_ocr_gold.json"
  python3 "$BASE/fr88_learning_prompt.py" \
    --base "$BASE/fr88_v3_typography_prompt.txt" \
    --gold "$BASE/fr88_ocr_gold.json" \
    --output "$OUT/batch_prompt.txt" \
    --min-verified 13 --max-examples 20
  cat "$BASE/fr88_v5_visibility_rules.txt" >> "$OUT/batch_prompt.txt"
  echo "PROMPT FROZEN for this batch; reruns reuse the same instructions."
else
  echo "Reusing existing frozen DeepSeek batch prompt."
fi
# Gate and crop inputs never gain write access; only the new batch directory is writable.
docker_command=(docker run --rm --memory=4g --env-file "$BASE/.env.deepseek"
  --entrypoint python
  -v "$BASE/fr88_deepseek_continue.py:/app/fr88_deepseek_continue.py:ro"
  -v "$BASE/fr88_visibility_gate.py:/app/fr88_visibility_gate.py:ro"
  -v "$BASE/fr88_v3_pilot.py:/app/fr88_v3_pilot.py:ro"
  -v "$BASE/fr88_v2_ocr.py:/app/fr88_v2_ocr.py:ro"
  -v "$BASE/fr88_v2_normalize.py:/app/fr88_v2_normalize.py:ro"
  -v "$RAW:/raw:ro"
  -v "$OUT:/raw/jbible_fr1988_deepseek_p0501_0750:rw"
  jbible-ocr:1 /app/fr88_deepseek_continue.py "$@")
exec flock -n /run/jbible-fr88-v2.lock \
     flock -n /run/jbible-fr88-deepseek-continuation.lock \
     "${docker_command[@]}"
