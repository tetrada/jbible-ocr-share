#!/usr/bin/env bash
# One unattended JBible FR88 OCR job: 100 NEW image pages (101..200).
# Preserves cached stages, uses existing DeepSeek credentials, and never writes SQL.
# Start through: nohup bash -c 'set -o pipefail; curl -fsSL <raw URL> | bash' > /root/jbible_101_200.log 2>&1 < /dev/null &
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root on JBible VPS" >&2; exit 2; }

ROOT="https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main"
RUN="$ROOT/tools/run_fr88_integrated_page.sh"
PUBLISH="$ROOT/tools/publish_fr88_integrated_page.sh"
PROGRESS="/opt/jbible/data/raw/jbible_fr88_integrated_v1/progress.json"
BUNDLES="/opt/jbible/data/raw/jbible_fr88_integrated_v1"
LOCK="/run/jbible-fr88-101-200-batch.lock"

# A job lock is separate from the individual OCR's two existing locks.
exec 9>"$LOCK"
flock -n 9 || { echo "ERROR: JBible 101..200 job is already running"; exit 3; }

[[ -s "$BUNDLES/image_0100.bundle.json" ]] || {
    echo "ERROR: page 100's complete bundle is missing; do not start a new range" >&2
    exit 3
}

echo "JBIBLE 100 NEW PAGES: 101..200. Reporting cumulative 31..200."
echo "RUNNING INDEPENDENT OF SSH; 5 passes x at most 100 paid calls = at most 500 new tasks."
echo "Previous OCR stages and SQL are untouched."
echo "JOB STARTED $(date -u +'%Y-%m-%dT%H:%M:%SZ')"

# The underlying integrated runner enforces 100 max NEW paid calls PER run.
# It exits successfully on budget-stop and resumes from fingerprinted caches.
for pass in 1 2 3 4 5; do
    echo
    echo "========== PASS $pass / 5 ($(date -u +'%Y-%m-%dT%H:%M:%SZ')) =========="
    curl -fsSL --retry 3 "$RUN" |
        bash -s -- --start 31 --end 200 --max-new-calls 100

    # Publish partial cumulative progress after each pass, not only at the end.
    # The GitHub publisher writes safe text-only evidence, never scanned pages.
    echo "========== PUBLISH PASS $pass =========="
    curl -fsSL --retry 3 "$PUBLISH" | bash

    if python3 - "$PROGRESS" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
d=json.loads(p.read_text(encoding="utf-8"))
m=d["source_link_metrics"]
print("BATCH PROGRESS: {}/{} pages ({:.1f}%), {} accepted links, {} exceptions, {} paid calls in most recent pass".format(
    d["pages_bundled"],d["pages_requested"],d["percent"],
    m["accepted"],m["exceptions"],d["new_paid_tasks_this_run"]),flush=True)
if d["pages"] != [31,200]:
    raise SystemExit("Unexpected progress page range: {!r}".format(d["pages"]))
sys.exit(0 if d["pages_bundled"] == 170 else 1)
PY
    then
        echo "SUCCESS: PAGES 31..200 COMPLETE; NEW PAGES 101..200 PROCESSED."
        echo "JOB FINISHED $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
        exit 0
    fi
done

echo "INCOMPLETE: exhausted five passes; inspect page errors and cached progress before continuing." >&2
exit 1
