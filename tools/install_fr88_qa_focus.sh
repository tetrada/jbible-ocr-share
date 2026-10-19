#!/usr/bin/env bash
# Safe review-only updater: 3 curated human decisions on existing /exceptions.
# Preserves scanned images, OCR results, SQL, credentials, saved review decisions.
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root" >&2; exit 2; }
BASE=/opt/jbible/review-web
URL=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main
PUBLISH=/usr/local/bin/jbible-integrated-exception-publish
[[ -s "$BASE/server.py" && -s "$BASE/password" && -s "$BASE/integrated_report.json" ]] || {
  echo "Existing reviewer installation not found; no files changed" >&2; exit 2;
}
for cmd in curl python3 systemctl runuser; do command -v "$cmd" >/dev/null; done
STAGE="$(mktemp -d /tmp/jbible_qa_stage.XXXXXXXX)"
BACKUP="$(mktemp -d /tmp/jbible_qa_backup.XXXXXXXX)"
cleanup() { rm -rf "$STAGE" "$BACKUP"; }
trap cleanup EXIT
get() {
  curl -fsSL --retry 3 --connect-timeout 20 "$URL/$1" -o "$STAGE/$2"
  test -s "$STAGE/$2"
}
get tools/fr88_review_web_server.py server.py
get tools/fr88_integrated_exception_review.py fr88_integrated_exception_review.py
get tools/fr88_integrated_exceptions_app.js integrated_exceptions.js
get tools/fr88_integrated_exceptions_index.html integrated_exceptions.html
get tools/fr88_integrated_exception_publish.sh publish_exceptions.sh
get training/fr88_curated_qa_focus.json qa_focus.json
get tools/test_fr88_integrated_exception_review.py test_integrated.py

python3 -m py_compile "$STAGE/server.py" "$STAGE/fr88_integrated_exception_review.py"
bash -n "$STAGE/publish_exceptions.sh"
(cd "$STAGE" && PYTHONPATH="$STAGE" python3 test_integrated.py)
(cd "$STAGE" && PYTHONPATH="$STAGE" python3 - <<'PY'
import json
from pathlib import Path
from fr88_integrated_exception_review import focused_cases
manifest=json.loads(Path("qa_focus.json").read_text(encoding="utf8"))
doc=json.loads(Path("/opt/jbible/review-web/integrated_report.json").read_text(encoding="utf8"))
cases=focused_cases(doc,manifest)
focus=[c for c in cases if c.get("curated_focus")]
assert len(focus)==3
assert {c["page"] for c in focus}=={102,107,378}
assert len(set(c["edge_id"] for c in cases))==len(cases)
print("PRECHECK:",len(focus),"selected +",len(cases)-3,"historic cases preserved")
PY
)
for page in 0102 0107 0378; do
  scan="$(printf '/opt/jbible/data/raw/fr_bible_1988/image_%s.jpg' "$page")"
  [[ -s "$scan" ]] || { echo "Missing source scan: $scan" >&2; exit 2; }
  runuser -u jbible-review -- test -r "$scan" || {
    echo "Protected reviewer cannot read: $scan" >&2; exit 2;
  }
done

FILES="server.py fr88_integrated_exception_review.py integrated_exceptions.js integrated_exceptions.html qa_focus.json"
for name in $FILES; do
  if [[ -f "$BASE/$name" ]]; then
    cp -p "$BASE/$name" "$BACKUP/$name"
    touch "$BACKUP/$name.existed"
  fi
done
STATE=/var/lib/jbible-review/integrated_exception_decisions.json
before=""
if [[ -f "$STATE" ]]; then before="$(sha256sum "$STATE" | cut -d' ' -f1)"; fi
rollback() {
  echo "Site validation failed: restoring earlier files" >&2
  for name in $FILES; do
    if [[ -f "$BACKUP/$name.existed" ]]; then
      cp -p "$BACKUP/$name" "$BASE/$name"
    else
      rm -f "$BASE/$name"
    fi
  done
  systemctl restart jbible-fr88-review-web.service || true
  exit 1
}
for name in $FILES; do install -m 0644 "$STAGE/$name" "$BASE/$name" || rollback; done
systemctl restart jbible-fr88-review-web.service || rollback
sleep 1
curl -fsS --max-time 10 http://127.0.0.1:8765/healthz |
  grep -q '"status": "ok"' || rollback
# Authenticated live verification; password never printed or passed as argv.
python3 - "$BASE/password" <<'PY' || rollback
import base64,json,sys,urllib.request
pwd=open(sys.argv[1],encoding="utf8").read().strip()
header=base64.b64encode(("reviewer:"+pwd).encode("utf8")).decode("ascii")
base="http://127.0.0.1:8765"
def get(path):
    request=urllib.request.Request(base+path,headers={"Authorization":"Basic "+header})
    with urllib.request.urlopen(request,timeout=15) as res:
        assert res.status==200,(path,res.status)
        return res.read()
data=json.loads(get("/api/integrated-exceptions").decode("utf8"))
focus=data.get("focus_ids",[])
assert len(focus)==3,focus
assert all(any(c["edge_id"]==i for c in data["cases"]) for i in focus)
assert b'value="focus"' in get("/exceptions/")
assert b"focusIds" in get("/exceptions/integrated_exceptions.js")
for page in (102,107,378):
    jpg=get("/api/image/%04d.jpg" % page)
    assert jpg[:3]==b"\xff\xd8\xff",page
print("LIVE VERIFIED: 3 focused cases, scan images, unchanged historic reviews")
PY
if [[ -n "$before" ]]; then
  after="$(sha256sum "$STATE" | cut -d' ' -f1)"
  [[ "$before" == "$after" ]] || rollback
fi
if [[ -f "$PUBLISH" ]]; then
  install -m 0755 "$STAGE/publish_exceptions.sh" "$PUBLISH"
fi

# Optional official portal event; secret stays inside private VPS .env.status.
python3 - <<'PY' || true
import os,sys
from pathlib import Path
env=Path("/opt/jbible/importer/.env.status")
if env.is_file():
    for line in env.read_text(encoding="utf8").splitlines():
        s=line.strip()
        if s.startswith("export "): s=s[7:]
        key,sep,val=s.partition("=")
        if sep and key.strip() in ("TETRADA_STATUS_TOKEN","TETRADA_STATUS_URL"):
            os.environ.setdefault(key.strip(),val.strip().strip("\"'"))
try:
    if os.environ.get("TETRADA_STATUS_TOKEN"):
        sys.path.insert(0,"/opt/jbible/importer")
        from status_sdk.tetrada_status import StatusClient
        client=StatusClient(entity="jbible/importer/review_queue",
            name="Integrated OCR Exception Review Queue",kind="service",
            parent="jbible/importer",heartbeat_interval=0,strict=False)
        client.log("FR88 focused human QA queue ready: 3 decisions, no SQL writes",level="info")
except Exception as exc:
    print("STATUS: nonblocking portal event not confirmed (%s)" % type(exc).__name__)
PY
echo
echo "READY: https://status.tetrada.eu/jbible-review/exceptions/"
echo "Focus queue: 3 cases (pages 102, 107, 378)."
echo "All older exceptions remain available under 'All exceptions'."
echo "Original scans, OCR JSON, SQL and review decisions unchanged."
