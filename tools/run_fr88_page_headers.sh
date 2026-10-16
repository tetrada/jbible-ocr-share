#!/usr/bin/env bash
# Scan only the top-of-page book + starting chapter:verse, once per page.
# Isolated DeepSeek-only 31..40 pilot, no SQL/previous OCR changes.
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root on JBible VPS" >&2; exit 2; }
BASE=/opt/jbible/importer
RAW=/opt/jbible/data/raw
OUT="$RAW/jbible_fr88_page_headers_pilot"
ROOT=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools
[[ -s "$BASE/.env.deepseek" ]] || { echo "DeepSeek API .env missing" >&2; exit 2; }
for cmd in curl docker flock python3; do command -v "$cmd" >/dev/null; done
mkdir -p "$OUT"
tmp="$(mktemp "$BASE/.page_header_script_XXXXXXXX")"
trap 'rm -f "$tmp"' EXIT
curl -fsSL --retry 3 --connect-timeout 20 "$ROOT/fr88_page_header_scan.py" -o "$tmp"
python3 -m py_compile "$tmp"
mv -f "$tmp" "$BASE/fr88_page_header_scan.py"
if [[ ! -s "$OUT/frozen_header_prompt.txt" ]]; then
  curl -fsSL --retry 3 --connect-timeout 20 "$ROOT/fr88_page_header_prompt.txt" \
    -o "$OUT/frozen_header_prompt.txt"
fi
docker_command=(docker run --rm --memory=4g --env-file "$BASE/.env.deepseek"
  --entrypoint python
  -v "$BASE/fr88_page_header_scan.py:/app/fr88_page_header_scan.py:ro"
  -v "$RAW:/raw:ro"
  -v "$OUT:/raw/jbible_fr88_page_headers_pilot:rw"
  jbible-ocr:1 /app/fr88_page_header_scan.py "$@")
exec flock -n /run/jbible-fr88-v2.lock \
     flock -n /run/jbible-fr88-page-headers.lock \
     "${docker_command[@]}"
