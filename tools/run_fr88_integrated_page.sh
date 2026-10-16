#!/usr/bin/env bash
# JBible French 1988: integrated, resumable ALL-IN-ONE page OCR.
# Existing DeepSeek Flash API and jbible-ocr:1 Docker; zero SQL writes.
# Default free preflight or 5-call pilot on page 33; don't process 470 pages yet.
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root on the JBible VPS" >&2; exit 2; }
BASE=/opt/jbible/importer
RAW=/opt/jbible/data/raw
OUT="$RAW/jbible_fr88_integrated_v1"
ROOT=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main
[[ -s "$BASE/.env.deepseek" ]] || { echo "Missing existing DeepSeek env file" >&2; exit 2; }
[[ -s "$RAW/jbible_catalog.csv" ]] || { echo "Missing Bible catalog" >&2; exit 2; }
for bin in curl docker python3 flock; do command -v "$bin" >/dev/null; done
mkdir -p "$BASE" "$OUT"
get() {
  local remote="$1" local_name="$2" temp
  temp="$(mktemp "$BASE/.integrated_download_XXXXXXXX")"
  if ! curl -fsSL --retry 3 --connect-timeout 25 "$ROOT/$remote" -o "$temp"; then
    rm -f "$temp"; echo "Download failed: $remote" >&2; exit 1
  fi
  [[ -s "$temp" ]] || { rm -f "$temp"; exit 1; }
  chmod 0644 "$temp"
  mv -f "$temp" "$BASE/$local_name"
}
get tools/fr88_integrated_page.py fr88_integrated_page.py
get tools/fr88_page_layout_core.py fr88_page_layout_core.py
get tools/fr88_integrated_reference_rules.py fr88_integrated_reference_rules.py
get tools/fr88_integrated_human_replay.py fr88_integrated_human_replay.py
get tools/test_fr88_integrated_human_replay.py test_fr88_integrated_human_replay.py
get fr88_integrated_v1/human_exception_reviews.json fr88_human_exception_reviews.json
get tools/fr88_v2_normalize.py fr88_v2_normalize.py
get tools/fr88_link_edges.py fr88_link_edges.py
get tools/fr88_learning_prompt.py fr88_learning_prompt.py
get tools/test_fr88_page_layout_core.py test_fr88_page_layout_core.py
get tools/test_fr88_integrated_reference_rules.py test_fr88_integrated_reference_rules.py
get tools/test_fr88_integrated_page.py test_fr88_integrated_page.py
get training/fr88_page_book_registry.json fr88_page_book_registry.json
get training/fr88_ocr_gold.json fr88_ocr_gold.json
python3 -m py_compile "$BASE/fr88_integrated_page.py" "$BASE/fr88_page_layout_core.py" \
  "$BASE/fr88_v2_normalize.py" "$BASE/fr88_link_edges.py" \
  "$BASE/test_fr88_page_layout_core.py" "$BASE/test_fr88_integrated_page.py" \
  "$BASE/fr88_integrated_reference_rules.py" "$BASE/test_fr88_integrated_reference_rules.py" \
  "$BASE/fr88_integrated_human_replay.py" "$BASE/test_fr88_integrated_human_replay.py"
# Tests always run before any DeepSeek-paid OCR.
docker run --rm --memory=2g --entrypoint python \
  -v "$BASE/fr88_page_layout_core.py:/app/fr88_page_layout_core.py:ro" \
  -v "$BASE/fr88_integrated_human_replay.py:/app/fr88_integrated_human_replay.py:ro" \
  -v "$BASE/test_fr88_integrated_human_replay.py:/app/test_fr88_integrated_human_replay.py:ro" \
  -v "$BASE/fr88_human_exception_reviews.json:/app/fr88_human_exception_reviews.json:ro" \
  jbible-ocr:1 /app/test_fr88_integrated_human_replay.py

docker run --rm --memory=2g --entrypoint python \
  -v "$BASE/fr88_integrated_reference_rules.py:/app/fr88_integrated_reference_rules.py:ro" \
  -v "$BASE/fr88_v2_normalize.py:/app/fr88_v2_normalize.py:ro" \
  -v "$BASE/test_fr88_integrated_reference_rules.py:/app/test_fr88_integrated_reference_rules.py:ro" \
  jbible-ocr:1 /app/test_fr88_integrated_reference_rules.py
docker run --rm --memory=2g --entrypoint python \
  -v "$BASE/fr88_page_layout_core.py:/app/fr88_page_layout_core.py:ro" \
  -v "$BASE/test_fr88_page_layout_core.py:/app/test_fr88_page_layout_core.py:ro" \
  jbible-ocr:1 /app/test_fr88_page_layout_core.py
docker run --rm --memory=2g --entrypoint python \
  -v "$BASE/fr88_integrated_page.py:/app/fr88_integrated_page.py:ro" \
  -v "$BASE/fr88_page_layout_core.py:/app/fr88_page_layout_core.py:ro" \
  -v "$BASE/fr88_v2_normalize.py:/app/fr88_v2_normalize.py:ro" \
  -v "$BASE/fr88_link_edges.py:/app/fr88_link_edges.py:ro" \
  -v "$BASE/fr88_integrated_reference_rules.py:/app/fr88_integrated_reference_rules.py:ro" \
  -v "$BASE/fr88_integrated_human_replay.py:/app/fr88_integrated_human_replay.py:ro" \
  -v "$BASE/test_fr88_integrated_page.py:/app/test_fr88_integrated_page.py:ro" \
  jbible-ocr:1 /app/test_fr88_integrated_page.py

# Freeze each stage's prompt once: reruns never silently change OCR prompts.
if [[ ! -s "$OUT/header_prompt.txt" ]]; then
  curl -fsSL --retry 3 "$ROOT/tools/fr88_integrated_header_prompt.txt" \
    -o "$OUT/header_prompt.txt"
fi
if [[ ! -s "$OUT/verses_prompt.txt" ]]; then
  curl -fsSL --retry 3 "$ROOT/tools/fr88_integrated_verse_prompt.txt" \
    -o "$OUT/verses_prompt.txt"
fi
if [[ ! -s "$OUT/margin_prompt.txt" ]]; then
  tmp="$(mktemp "$BASE/.integrated_margin_prompt_XXXXXXXX")"
  curl -fsSL --retry 3 "$ROOT/tools/fr88_integrated_margin_prompt.txt" -o "$tmp"
  python3 "$BASE/fr88_learning_prompt.py" --base "$tmp" \
    --gold "$BASE/fr88_ocr_gold.json" \
    --output "$OUT/margin_prompt.txt" \
    --min-verified 13 --max-examples 20
  rm -f "$tmp"
fi
for name in header_prompt.txt verses_prompt.txt margin_prompt.txt; do
  [[ -s "$OUT/$name" ]] || { echo "Empty prompt $name" >&2; exit 2; }
done
# Future pages may receive a better page registry; currently 31-40 Gen,
# and user confirmed page102 Exod 16:21. NEVER fill unknown book from thin air.
docker_command=(docker run --rm --memory=4g --env-file "$BASE/.env.deepseek"
  --entrypoint python
  -v "$BASE/fr88_integrated_page.py:/app/fr88_integrated_page.py:ro"
  -v "$BASE/fr88_page_layout_core.py:/app/fr88_page_layout_core.py:ro"
  -v "$BASE/fr88_v2_normalize.py:/app/fr88_v2_normalize.py:ro"
  -v "$BASE/fr88_link_edges.py:/app/fr88_link_edges.py:ro"
  -v "$BASE/fr88_integrated_reference_rules.py:/app/fr88_integrated_reference_rules.py:ro"
  -v "$BASE/fr88_integrated_human_replay.py:/app/fr88_integrated_human_replay.py:ro"
  -v "$BASE/fr88_human_exception_reviews.json:/app/fr88_human_exception_reviews.json:ro"
  -v "$BASE/fr88_page_book_registry.json:/app/fr88_page_book_registry.json:ro"
  -v "$RAW:/raw:ro"
  -v "$OUT:/raw/jbible_fr88_integrated_v1:rw"
  jbible-ocr:1 /app/fr88_integrated_page.py "$@")
exec flock -n /run/jbible-fr88-v2.lock \
     flock -n /run/jbible-fr88-integrated.lock \
     "${docker_command[@]}"
