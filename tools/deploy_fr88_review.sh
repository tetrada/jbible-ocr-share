#!/usr/bin/env bash
# Publish read-only FR1988 OCR review and selected marginal previews.
# Usage: bash deploy_fr88_review.sh [EXISTING_JBIBLE_SHARE_DIRECTORY]
set -euo pipefail
SRC="/opt/jbible/data/raw/jbible_fr1988_pilot"
SHARE_ROOT="/srv/jbible-share"

if [[ $# -gt 0 ]]; then
  DEST="$1"
else
  mapfile -d '' -t DIRS < <(find "$SHARE_ROOT" -mindepth 1 -maxdepth 1 -type d -print0)
  if [[ "${#DIRS[@]}" -ne 1 ]]; then
    echo "Expected one shared directory under $SHARE_ROOT; found ${#DIRS[@]}." >&2
    echo "Usage: $0 /srv/jbible-share/EXISTING_TOKEN" >&2
    exit 2
  fi
  DEST="${DIRS[0]}"
fi

[[ -d "$DEST" ]] || { echo "Not a directory: $DEST" >&2; exit 2; }
[[ -s "$SRC/comparison.json" ]] || { echo "No FR88 comparison: $SRC/comparison.json" >&2; exit 2; }
[[ -s "$SRC/summary.json" ]] || { echo "No FR88 summary: $SRC/summary.json" >&2; exit 2; }

install -d -m 755 "$DEST/fr88_margin_previews"
TMP="$(mktemp "$DEST/.fr88_review.XXXXXX")"
trap 'rm -f "$TMP"' EXIT

curl -fsSL --max-time 30 \
  https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/fr88_review.html \
  -o "$TMP"

python3 -m json.tool "$SRC/comparison.json" > /dev/null

install -m 644 "$TMP" "$DEST/fr88_review.html"
install -m 644 "$SRC/comparison.json" "$DEST/fr88_comparison.json"
install -m 644 "$SRC/summary.json" "$DEST/fr88_summary.json"

python3 - "$SRC" "$DEST" <<'PY'
import json
import shutil
import sys
from pathlib import Path

src = Path(sys.argv[1])
dest = Path(sys.argv[2]) / "fr88_margin_previews"
rows = json.loads((src / "comparison.json").read_text(encoding="utf-8"))

needed = set()
for row in rows:
    if row.get("kind") != "REFERENCE" or row.get("review_status") != "REVIEW":
        continue
    page = row.get("image_page")
    side = row.get("side")
    if type(page) is int and 0 < page < 10000 and side in ("L", "R"):
        needed.add((page, side))

copied = 0
missing = []
for page, side in sorted(needed):
    name = f"image_{page:04d}_{side}_full.jpg"
    path = src / "images" / name
    if not path.is_file():
        missing.append(name)
        continue
    shutil.copyfile(path, dest / name)
    (dest / name).chmod(0o644)
    copied += 1

print(f"FR88 review published: {len(rows)} records, {copied} margin previews")
if missing:
    print("Missing previews (OCR text still available): " + ", ".join(missing))
PY

echo "Open:"
echo "https://status.tetrada.eu/jbible-share/$(basename "$DEST")/fr88_review.html"
