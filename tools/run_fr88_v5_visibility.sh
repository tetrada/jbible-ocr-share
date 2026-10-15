#!/usr/bin/env bash
# FR88 v5 cut-off visibility test: only pages 31..50, default 32..32 (2 margins).
# Paid DeepSeek calls only after successful preflight; all older OCR data read-only.
set -euo pipefail
BASE=/opt/jbible/importer
RAW=/opt/jbible/data/raw
OUT="$RAW/jbible_fr1988_v5_visibility"
URL=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main
for f in fr88_v3_pilot.py fr88_v2_ocr.py fr88_v2_normalize.py fr88_v3_typography_prompt.txt; do
  [[ -s "$BASE/$f" ]] || { echo "Missing $f" >&2; exit 2; }
done
[[ -s "$BASE/.env.deepseek" ]] || { echo "Missing DeepSeek API environment" >&2; exit 2; }
mkdir -p "$OUT"
for name in fr88_learning_prompt.py fr88_v5_visibility_proxy.py fr88_v5_cutoff_eval.py fr88_v5_visibility_rules.txt; do
  temp="$(mktemp "$BASE/.v5_download_XXXXXXXX")"
  if ! curl -fsSL --retry 3 --connect-timeout 20 "$URL/tools/$name" -o "$temp"; then
    rm -f "$temp"
    exit 1
  fi
  test -s "$temp"
  mv -f "$temp" "$BASE/$name"
done
temp="$(mktemp "$BASE/.v5_gold_XXXXXXXX")"
curl -fsSL --retry 3 --connect-timeout 20 "$URL/training/fr88_ocr_gold.json" -o "$temp"
mv -f "$temp" "$BASE/fr88_ocr_gold.json"
python3 "$BASE/fr88_learning_prompt.py" \
  --base "$BASE/fr88_v3_typography_prompt.txt" \
  --gold "$BASE/fr88_ocr_gold.json" \
  --output "$OUT/visibility_prompt.txt" \
  --min-verified 13 --max-examples 20
cat "$BASE/fr88_v5_visibility_rules.txt" >> "$OUT/visibility_prompt.txt"
# D051 is held out: do not leak the exact hidden test text into the API prompt.
python3 - "$BASE/fr88_ocr_gold.json" "$OUT/visibility_prompt.txt" <<'PY'
import json,sys
from pathlib import Path
g=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
p=Path(sys.argv[2]).read_text(encoding="utf-8")
h=next((x for x in g["held_out_examples"] if x.get("case_id")=="D051"),None)
assert h is not None
assert not any(x.get("case_id")=="D051" and x.get("inclusion")=="prompt_example" for x in g["examples"])
assert h["expected_visible_prefix"] not in p, "Held-out scan text leaked into V5 prompt"
assert h.get("expected_full_reference") is None
print("PASS: held-out cut-off scan absent from V5 DeepSeek prompt")
PY
docker_args=(docker run --rm --memory=4g --env-file "$BASE/.env.deepseek"
  --entrypoint python
  -v "$BASE/fr88_v5_visibility_proxy.py:/app/fr88_v5_visibility_proxy.py:ro"
  -v "$BASE/fr88_v3_pilot.py:/app/fr88_v3_pilot.py:ro"
  -v "$BASE/fr88_v2_ocr.py:/app/fr88_v2_ocr.py:ro"
  -v "$BASE/fr88_v2_normalize.py:/app/fr88_v2_normalize.py:ro"
  -v "$RAW:/raw:ro"
  -v "$OUT:/raw/jbible_fr1988_v5_visibility:rw"
  jbible-ocr:1 /app/fr88_v5_visibility_proxy.py "$@")
if [[ "${1:-}" == "--preflight" || "${3:-}" == "--preflight" ]]; then
  exec flock -n /run/jbible-fr88-v2.lock flock -n /run/jbible-fr88-v5.lock "${docker_args[@]}"
fi
set +e
flock -n /run/jbible-fr88-v2.lock flock -n /run/jbible-fr88-v5.lock "${docker_args[@]}"
status=$?
set -e
if [[ -f "$OUT/image_0032_R.result.json" ]]; then
  echo "Running held-out cut-off visual transcription regression..."
  docker run --rm --memory=4g --entrypoint python \
    -v "$BASE/fr88_v5_cutoff_eval.py:/app/fr88_v5_cutoff_eval.py:ro" \
    -v "$BASE/fr88_ocr_gold.json:/app/fr88_ocr_gold.json:ro" \
    -v "$RAW:/raw:ro" \
    -v "$OUT:/raw/jbible_fr1988_v5_visibility:rw" \
    jbible-ocr:1 /app/fr88_v5_cutoff_eval.py
fi
exit "$status"
