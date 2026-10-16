#!/usr/bin/env bash
# JBible: link saved FR1988 marginal OCR rows to main-text verse positions.
# Existing scans 31..40 only, DeepSeek Flash. Zero SQL, zero verified links.
# Usage: curl -fsSL <URL> | bash -s -- --preflight
#        curl -fsSL <URL> | bash -s -- --max-new-jobs 4
#        curl -fsSL <URL> | bash -s -- --report-only
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root on the JBible VPS" >&2; exit 2; }
BASE=/opt/jbible/importer
RAW=/opt/jbible/data/raw
OUT="$RAW/jbible_fr88_source_links"
URL=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools
for binary in curl docker flock python3; do command -v "$binary" >/dev/null; done
[[ -s "$BASE/.env.deepseek" ]] || { echo "DeepSeek env missing" >&2; exit 2; }
[[ -s "$RAW/jbible_fr1988_v2/interpreted_rows.json" ]] || { echo "V2 OCR input missing" >&2; exit 2; }
[[ -s "$RAW/jbible_catalog.csv" ]] || { echo "Bible catalog missing" >&2; exit 2; }
for p in 0031 0032 0033 0034 0035 0036 0037 0038 0039 0040; do
  [[ -s "$RAW/fr_bible_1988/image_$p.jpg" ]] || {
    echo "Missing image_$p.jpg — cannot run linking pilot" >&2; exit 2;
  }
done
mkdir -p "$BASE" "$OUT"
for name in fr88_source_links.py fr88_source_book_context.py fr88_source_visibility_overrides.json test_fr88_source_links.py test_fr88_source_book_context.py; do
  temp="$(mktemp "$BASE/.source_links_download_XXXXXXXX")"
  if ! curl -fsSL --retry 3 --connect-timeout 20 "$URL/$name" -o "$temp"; then
    rm -f "$temp"
    echo "Download failed: $name" >&2
    exit 1
  fi
  test -s "$temp"
  chmod 0644 "$temp"
  mv -f "$temp" "$BASE/$name"
done
python3 -m py_compile "$BASE/fr88_source_links.py" "$BASE/fr88_source_book_context.py" "$BASE/test_fr88_source_links.py" "$BASE/test_fr88_source_book_context.py"
# Before any paid vision request, test source/target association and all safeguards.
docker run --rm --memory=2g --entrypoint python \
  -v "$BASE/fr88_source_links.py:/app/fr88_source_links.py:ro" \
  -v "$BASE/fr88_source_book_context.py:/app/fr88_source_book_context.py:ro" \
  -v "$BASE/test_fr88_source_links.py:/app/test_fr88_source_links.py:ro" \
  jbible-ocr:1 /app/test_fr88_source_links.py
# Separate tests for inferencing from visibly printed *neighbor* headers.
docker run --rm --memory=2g --entrypoint python \
  -v "$BASE/fr88_source_book_context.py:/app/fr88_source_book_context.py:ro" \
  -v "$BASE/test_fr88_source_book_context.py:/app/test_fr88_source_book_context.py:ro" \
  jbible-ocr:1 /app/test_fr88_source_book_context.py
if [[ ! -s "$OUT/frozen_source_prompt.txt" ]]; then
  temp="$(mktemp "$OUT/.prompt_download_XXXXXXXX")"
  curl -fsSL --retry 3 --connect-timeout 20 \
    "$URL/fr88_source_anchor_prompt.txt" -o "$temp"
  [[ -s "$temp" ]] || { echo "Empty source prompt" >&2; exit 2; }
  mv -f "$temp" "$OUT/frozen_source_prompt.txt"
  chmod 0644 "$OUT/frozen_source_prompt.txt"
  echo "Installed and frozen source matching instructions"
else
  echo "Reusing frozen source matching instructions"
fi
docker_command=(docker run --rm --memory=4g --env-file "$BASE/.env.deepseek"
  --entrypoint python
  -v "$BASE/fr88_source_links.py:/app/fr88_source_links.py:ro"
  -v "$BASE/fr88_source_book_context.py:/app/fr88_source_book_context.py:ro"
  -v "$BASE/fr88_source_visibility_overrides.json:/app/fr88_source_visibility_overrides.json:ro"
  -v "$RAW:/raw:ro"
  -v "$OUT:/raw/jbible_fr88_source_links:rw"
  jbible-ocr:1 /app/fr88_source_links.py "$@")
exec flock -n /run/jbible-fr88-v2.lock \
     flock -n /run/jbible-fr88-source-links.lock \
     "${docker_command[@]}"
