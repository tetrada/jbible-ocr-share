#!/usr/bin/env bash
# Add 24 integrated OCR exceptions to the EXISTING password-protected JBible
# reviewer. Never change existing OCR/source-link decisions or copy scans.
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root on JBible VPS" >&2; exit 2; }
BASE=/opt/jbible/review-web
STORE=/var/lib/jbible-review
BIN=/usr/local/bin/jbible-integrated-exception-publish
ROOT=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main
[[ -s "$BASE/server.py" && -s "$BASE/priority.json" && -s "$BASE/password" ]] || {
  echo "Existing private JBible review site is required" >&2; exit 2;
}
for name in curl python3 systemctl runuser; do command -v "$name" >/dev/null; done
STAGE="$(mktemp -d "$BASE/.integrated_review_staging_XXXXXXXX")"
BACKUP=""
cleanup() {
  rm -rf "$STAGE"
}
trap cleanup EXIT
download() {
  local remote="$1" localname="$2"
  curl -fsSL --retry 3 --connect-timeout 20 "$ROOT/$remote" -o "$STAGE/$localname"
  [[ -s "$STAGE/$localname" ]] || { echo "Empty download $remote" >&2; exit 2; }
  chmod 0644 "$STAGE/$localname"
}
download tools/fr88_review_web_server.py server.py
download tools/fr88_link_edges.py fr88_link_edges.py
download tools/fr88_integrated_exception_review.py fr88_integrated_exception_review.py
download tools/fr88_integrated_exceptions_index.html integrated_exceptions.html
download tools/fr88_integrated_exceptions_app.js integrated_exceptions.js
download tools/test_fr88_integrated_exception_review.py test_integrated_review.py
download tools/fr88_integrated_exception_publish.sh publish_exceptions.sh
download fr88_integrated_v1/pilot_report.json integrated_report.json
python3 -m py_compile "$STAGE/server.py" "$STAGE/fr88_link_edges.py" \
  "$STAGE/fr88_integrated_exception_review.py" "$STAGE/test_integrated_review.py"
(cd "$STAGE" && PYTHONPATH="$STAGE" python3 test_integrated_review.py)
python3 - "$STAGE" <<'PY'
import importlib.util,json,sys
from pathlib import Path
p=Path(sys.argv[1])
sys.path.insert(0,str(p))
spec=importlib.util.spec_from_file_location("server",str(p/"server.py"))
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
doc=json.loads((p/"integrated_report.json").read_text(encoding="utf-8"))
cases=mod.cases_from_report(doc)
assert len(cases)==24,"Expected exactly 24 current exceptions, got "+str(len(cases))
assert all(31<=c["page"]<=37 for c in cases)
assert all(c["edge_id"] and c["reason_codes"] for c in cases)
print("PRECHECK OK:",len(cases),"one-to-one destination exceptions")
PY
for page in 0032 0033 0034 0035 0037; do
  image="/opt/jbible/data/raw/fr_bible_1988/image_$page.jpg"
  [[ -s "$image" ]] || { echo "Source scan missing: $image" >&2; exit 2; }
  runuser -u jbible-review -- test -r "$image" || {
    echo "Review site account cannot read original scan: $image" >&2; exit 2;
  }
done
BACKUP="$(mktemp -d "$BASE/.integrated_review_backup_XXXXXXXX")"
for file in server.py fr88_link_edges.py fr88_integrated_exception_review.py \
            integrated_exceptions.html integrated_exceptions.js integrated_report.json; do
  if [[ -f "$BASE/$file" ]]; then
    cp -p "$BASE/$file" "$BACKUP/$file"
  fi
done
rollback() {
  echo "Restoring earlier review service after failed checks" >&2
  for file in server.py fr88_link_edges.py fr88_integrated_exception_review.py \
              integrated_exceptions.html integrated_exceptions.js integrated_report.json; do
    if [[ -s "$BACKUP/$file" ]]; then
      cp -p "$BACKUP/$file" "$BASE/$file"
    else
      rm -f "$BASE/$file"
    fi
  done
  systemctl restart jbible-fr88-review-web.service || true
  exit 1
}
for file in server.py fr88_link_edges.py fr88_integrated_exception_review.py \
            integrated_exceptions.html integrated_exceptions.js integrated_report.json; do
  install -m 0644 "$STAGE/$file" "$BASE/$file"
done
systemctl restart jbible-fr88-review-web.service
sleep 1
curl -fsS --max-time 10 http://127.0.0.1:8765/healthz | grep -q '"status": "ok"' || rollback
status="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/exceptions/ || true)"
[[ "$status" == "401" ]] || { echo "Unauthenticated review returned HTTP $status" >&2; rollback; }
# Confirm the actual page list works WITH existing credentials without exposing
# the password on a shell command line.
python3 - "$BASE/password" <<'PY' || rollback
import base64,json,sys
import urllib.request,urllib.error
secret=open(sys.argv[1],encoding="utf-8").read().strip()
auth=base64.b64encode(("reviewer:"+secret).encode("utf8")).decode("ascii")
root="http://127.0.0.1:8765"
for route in ("/exceptions/","/exceptions/integrated_exceptions.js",
              "/api/integrated-exceptions","/api/image/0033.jpg"):
    req=urllib.request.Request(root+route,headers={"Authorization":"Basic "+auth})
    with urllib.request.urlopen(req,timeout=10) as res:
        assert res.status==200,(route,res.status)
        if route=="/api/integrated-exceptions":
            obj=json.load(res)
            assert len(obj["cases"])==24,("Unexpected exception count",len(obj["cases"]))
            assert isinstance(obj["reviews"],dict)
print("AUTHENTICATED UI/API/SCAN: OK, 24 exception records available")
PY
rm -rf "$BACKUP"
# Keep exception review persistence distinct from all earlier review JSON.
if [[ -d /opt/jbible/ocr-share-git/.git && -s /root/.ssh/jbible_ocr_share ]]; then
  install -m 0750 "$STAGE/publish_exceptions.sh" "$BIN"
  cat >/etc/systemd/system/jbible-fr88-exception-publish.service <<'SERVICE'
[Unit]
Description=Publish private-scan JBible exception review conclusions (text only)
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/jbible-integrated-exception-publish
SERVICE
  cat >/etc/systemd/system/jbible-fr88-exception-publish.timer <<'TIMER'
[Unit]
Description=Sync JBible integrated OCR exception decisions every two minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=2min
Unit=jbible-fr88-exception-publish.service
[Install]
WantedBy=timers.target
TIMER
  systemctl daemon-reload
  systemctl enable --now jbible-fr88-exception-publish.timer
  echo "Human conclusions will sync as text-only records to GitHub every ~2 minutes."
else
  echo "Existing SSH Git deploy key unavailable; local review decisions still persist securely."
fi
echo "============================================================"
echo "JBIBLE OCR EXCEPTION REVIEW READY:"
echo "https://status.tetrada.eu/jbible-review/exceptions/"
echo "Same Basic auth reviewer login/password as your original JBible site."
echo "24 individual exceptions, original page scans, editable source and target."
echo "No DeepSeek calls, no SQL writes, no changes to earlier OCR review files."
echo "============================================================"
