#!/usr/bin/env bash
# Install source-to-verse verification inside EXISTING authenticated JBible site.
# Preserves all existing OCR reviews, login, Nginx and historical scan files.
set -euo pipefail
[[ "$(id -u)" == 0 ]] || { echo "Run as root on JBible VPS" >&2; exit 2; }
BASE=/opt/jbible/review-web
STATE=/var/lib/jbible-review
PUB=/usr/local/bin/jbible-link-review-publish
ROOT=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main
[[ -s "$BASE/server.py" && -s "$BASE/priority.json" && -s "$BASE/password" ]] || {
  echo "Existing https://status.tetrada.eu/jbible-review/ must be installed first" >&2
  exit 2
}
[[ -s "$STATE/decisions.json" ]] || echo "No previous OCR decisions file (this is OK)"
for utility in curl python3 systemctl; do command -v "$utility" >/dev/null; done
STAGE="$(mktemp -d "$BASE/.link_review_install_XXXXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
download() {
  local remote="$1" name="$2"
  curl -fsSL --retry 3 --connect-timeout 20 "$ROOT/$remote" -o "$STAGE/$name"
  [[ -s "$STAGE/$name" ]] || { echo "Empty downloaded file $name" >&2; exit 1; }
  chmod 0644 "$STAGE/$name"
}
download tools/fr88_review_web_server.py server.py
cp "$STAGE/server.py" "$STAGE/fr88_review_web_server.py"
download tools/fr88_review_web_index.html index.html
download tools/fr88_link_review_index.html link_review.html
download tools/fr88_link_review_app.js link_review.js
download tools/test_fr88_link_review_web.py test_link_review.py
download tools/fr88_link_review_publish.sh publish_link_review.sh
download fr88_source_links_pilot/source_link_results.json link_results.json

# Validate the queue and all server endpoints before touching the live service.
python3 -m py_compile "$STAGE/server.py" "$STAGE/test_link_review.py"
python3 - "$STAGE" <<'PY'
import json,sys
from pathlib import Path
import importlib.util
base=Path(sys.argv[1])
document=json.loads((base/"link_results.json").read_text(encoding="utf-8"))
progress=document.get("progress",{})
assert progress.get("pages")==[31,40], "Review data must be pages 31-40"
assert progress.get("margins_complete")==20, "Incomplete pilot not accepted for review"
spec=importlib.util.spec_from_file_location("jbible_staged_review",str(base/"server.py"))
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
cases=mod.link_cases_from_export(document)
assert len(cases)>=20, "Not enough published margin rows"
ids={c["row_id"] for c in cases}
assert len(ids)==len(cases), "Duplicate margin row IDs"
assert all(31<=c["page"]<=40 for c in cases)
print("VALID QUEUE:",len(cases),"unique printed margin rows")
PY
# The smoke tests need to be imported from this staging directory.
(cd "$STAGE" && PYTHONPATH="$STAGE" python3 test_link_review.py)
# Check live review account can read source scans; never copy scans to public assets.
for pp in 0031 0032 0033 0034 0035 0036 0037 0038 0039 0040; do
  img="/opt/jbible/data/raw/fr_bible_1988/image_$pp.jpg"
  [[ -s "$img" ]] || { echo "Missing source scan: $img" >&2; exit 2; }
  runuser -u jbible-review -- test -r "$img" || {
    echo "Review account cannot read image_$pp.jpg; fix filesystem permissions first" >&2
    exit 2
  }
done
# Preserve backup of the original server and index until health-check succeeds.
BACKUP="$(mktemp -d "$BASE/.link_review_backup_XXXXXXXX")"
cp -p "$BASE/server.py" "$BACKUP/server.py"
cp -p "$BASE/index.html" "$BACKUP/index.html"
for file in server.py index.html link_review.html link_review.js link_results.json; do
  install -m 0644 "$STAGE/$file" "$BASE/$file"
done
install -m 0750 "$STAGE/publish_link_review.sh" "$PUB"
systemctl restart jbible-fr88-review-web.service
sleep 1
if ! curl -fsS --max-time 12 http://127.0.0.1:8765/healthz | grep -q '"status": "ok"'; then
  echo "New review service failed health check; restoring original server and OCR index" >&2
  cp -p "$BACKUP/server.py" "$BASE/server.py"
  cp -p "$BACKUP/index.html" "$BASE/index.html"
  systemctl restart jbible-fr88-review-web.service
  exit 1
fi
# The new review route should demand the existing Basic credentials.
code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/links/ || true)"
if [[ "$code" != "401" ]]; then
  echo "Security check FAILED: unauthenticated source-link review returned HTTP $code" >&2
  cp -p "$BACKUP/server.py" "$BASE/server.py"
  cp -p "$BACKUP/index.html" "$BASE/index.html"
  systemctl restart jbible-fr88-review-web.service
  exit 1
fi
rm -rf "$BACKUP"

if [[ -d /opt/jbible/ocr-share-git/.git && -s /root/.ssh/jbible_ocr_share ]]; then
  cat >/etc/systemd/system/jbible-fr88-link-review-publish.service <<'SERVICE'
[Unit]
Description=Publish text-only JBible human source-link review decisions
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/jbible-link-review-publish
SERVICE
  cat >/etc/systemd/system/jbible-fr88-link-review-publish.timer <<'TIMER'
[Unit]
Description=Sync human JBible source-link decisions every two minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=2min
Unit=jbible-fr88-link-review-publish.service
[Install]
WantedBy=timers.target
TIMER
  systemctl daemon-reload
  systemctl enable --now jbible-fr88-link-review-publish.timer
  echo "Text-only human source-link decisions will sync to GitHub every ~2 minutes."
else
  echo "No Git deploy key; the review UI works, but automatic decision sync needs existing Git setup."
fi
echo "=========================================================="
echo "SOURCE-LINK REVIEW READY:"
echo "https://status.tetrada.eu/jbible-review/links/"
echo "Use the SAME reviewer login and password as the OCR review site."
echo "Original OCR decisions, scan images and SQL remain untouched."
echo "=========================================================="
