#!/usr/bin/env bash
# Install isolated v3 pilot files and run offline tests in existing Docker image.
# Does NOT run the paid OCR pilot automatically.
set -euo pipefail
BASE="/opt/jbible/importer"
RAW="/opt/jbible/data/raw"
URL="https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools"
mkdir -p "$BASE"
command -v curl >/dev/null
command -v docker >/dev/null
for f in fr88_v3_pilot.py fr88_v3_typography_prompt.txt run_fr88_v3_pilot.sh test_fr88_v3_pilot.py README_fr88_v3_pilot.md; do
  temp="$(mktemp "$BASE/.fr88_v3_dl_XXXXXXXX")"
  if ! curl -fsSL --retry 3 --connect-timeout 20 "$URL/$f" -o "$temp"; then
    rm -f "$temp"
    echo "Download failed: $f" >&2
    exit 1
  fi
  test -s "$temp"
  chmod 0644 "$temp"
  mv -f "$temp" "$BASE/$f"
  echo "Installed $f"
done
chmod 0755 "$BASE/run_fr88_v3_pilot.sh"
python3 -m py_compile "$BASE/fr88_v3_pilot.py" "$BASE/test_fr88_v3_pilot.py"
bash -n "$BASE/run_fr88_v3_pilot.sh"
docker run --rm --memory=4g --entrypoint python \
  -v "$BASE/fr88_v3_pilot.py:/app/fr88_v3_pilot.py:ro" \
  -v "$BASE/test_fr88_v3_pilot.py:/app/test_fr88_v3_pilot.py:ro" \
  -v "$BASE/fr88_v3_typography_prompt.txt:/app/fr88_v3_typography_prompt.txt:ro" \
  -v "$BASE/fr88_v2_ocr.py:/app/fr88_v2_ocr.py:ro" \
  -v "$BASE/fr88_v2_normalize.py:/app/fr88_v2_normalize.py:ro" \
  -v "$RAW:/raw" \
  jbible-ocr:1 /app/test_fr88_v3_pilot.py
echo "OFFLINE TESTS PASSED. Next: $BASE/run_fr88_v3_pilot.sh --preflight"
