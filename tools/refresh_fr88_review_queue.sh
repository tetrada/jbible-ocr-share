#!/usr/bin/env bash
# Refresh GitHub-backed review cases on the existing VPS webpage.
# Preserves /var/lib/jbible-review/decisions.json; no OCR, Git push or SQL.
set -euo pipefail
[[ $(id -u) -eq 0 ]] || { echo "Run as root" >&2; exit 2; }
BASE=/opt/jbible/review-web
FILE="$BASE/priority.json"
URL=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/training/fr88_priority_review.json
[[ -s "$FILE" ]] || { echo "Review site not installed ($FILE missing)" >&2; exit 2; }
TEMP="$(mktemp "$BASE/.priority_refresh_XXXXXXXX")"
trap 'rm -f "$TEMP"' EXIT
curl -fsSL --retry 3 --connect-timeout 20 "$URL" -o "$TEMP"
python3 - "$FILE" "$TEMP" <<'PY'
import json,sys
from pathlib import Path
old=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
new=json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
assert new.get("schema")=="jbible.fr88.v3.prioritized-review.v1"
assert isinstance(new.get("priorities"),list)
a={c["case_id"]:c for c in old.get("priorities",[])}
b={c["case_id"]:c for c in new["priorities"]}
assert len(b)==len(new["priorities"]),"Duplicate case ID"
assert all(k in b and b[k]==v for k,v in a.items()),"Previously deployed cases changed; refusing"
assert len(new["priorities"])>=len(old.get("priorities",[]))
print("Review queue: %d existing, %d new, %d total"%(
    len(a),len(b)-len(a),len(b)))
PY
chmod 0644 "$TEMP"
mv -f "$TEMP" "$FILE"
JSTEMP="$(mktemp "$BASE/.app_refresh_XXXXXXXX")"
trap 'rm -f "$TEMP" "$JSTEMP"' EXIT
curl -fsSL --retry 3 --connect-timeout 20 \
  https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/fr88_review_web_app.js \
  -o "$JSTEMP"
test -s "$JSTEMP"
chmod 0644 "$JSTEMP"
mv -f "$JSTEMP" "$BASE/app.js"
echo 'QUEUE AND WEB REVIEW APP REFRESHED. Reload https://status.tetrada.eu/jbible-review/'
echo 'Previously saved scan confirmations remain untouched.'
