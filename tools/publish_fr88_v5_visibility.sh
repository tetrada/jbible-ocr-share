#!/usr/bin/env bash
# Publish only text-based V5 cut-off evaluation and OCR transcription rows.
set -euo pipefail
REPO=/opt/jbible/ocr-share-git
BASE=/opt/jbible/data/raw/jbible_fr1988_v5_visibility
DEST=fr88_v5_visibility
[[ "$(id -u)" -eq 0 ]] || { echo "Requires existing root Git deploy key" >&2; exit 2; }
[[ -d "$REPO/.git" && -s /root/.ssh/jbible_ocr_share ]] || { echo "Missing existing Git sync checkout/key" >&2; exit 2; }
for file in comparison.json cutoff_holdout_evaluation.json run_summary.json image_0032_R.result.json; do
  [[ -s "$BASE/$file" ]] || { echo "Missing completed V5 file: $file" >&2; exit 2; }
done
export GIT_SSH_COMMAND='ssh -i /root/.ssh/jbible_ocr_share -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
(
  flock -x 9
  [[ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" == main ]] || exit 3
  if [[ -n "$(git -C "$REPO" status --porcelain --untracked-files=normal)" ]]; then
    echo "Git checkout is dirty; run existing jbible-github-sync and retry" >&2
    exit 3
  fi
  git -C "$REPO" fetch --quiet origin main
  git -C "$REPO" merge --ff-only origin/main
  python3 - "$BASE" "$REPO/$DEST" <<'PY'
import json,sys
from pathlib import Path
src=Path(sys.argv[1]);dest=Path(sys.argv[2])
summary=json.loads((src/"comparison.json").read_text(encoding="utf-8"))
holdout=json.loads((src/"cutoff_holdout_evaluation.json").read_text(encoding="utf-8"))
run=json.loads((src/"run_summary.json").read_text(encoding="utf-8"))
rows=json.loads((src/"image_0032_R.result.json").read_text(encoding="utf-8"))["rows"]
if run.get("pages")!=[32,32] or not run.get("complete") or run.get("errors"):
    raise ValueError("V5 comparison is not the intended completed one-page pilot")
safe={
 "schema":"jbible.fr88.v5.visibility.public-report.v1",
 "pages":[32,32],
 "v5_counts":summary.get("v5"),
 "visibility_counts":summary.get("visibility_status_counts"),
 "cutoff_regression":holdout,
 "rows_page_32_right":[{
   "id":r.get("id"),"kind":r.get("kind"),
   "raw_line":r.get("raw_line"),"y_fraction":r.get("y_fraction"),
   "visibility_status":r.get("visibility_status"),
   "visually_truncated":r.get("visually_truncated"),
   "visibility_note":r.get("visibility_note")
 } for r in rows],
 "no_provider_response_or_scans":True,
 "sql_writes":False
}
dest.mkdir(parents=True,exist_ok=True)
target=dest/"visibility_report.json"
temp=dest/"visibility_report.json.tmp"
temp.write_text(json.dumps(safe,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
temp.replace(target)
print("Prepared V5 text-only cut-off scan report",flush=True)
PY
  git -C "$REPO" add -- "$DEST/visibility_report.json"
  if git -C "$REPO" diff --cached --quiet; then
    echo "Already published"
    exit 0
  fi
  git -C "$REPO" commit -m "Publish FR88 V5 cutoff-only scan accuracy check"
  git -C "$REPO" push origin HEAD:main
  echo "PUBLISHED https://github.com/tetrada/jbible-ocr-share/blob/main/fr88_v5_visibility/visibility_report.json"
) 9>/run/jbible-github-sync.lock
