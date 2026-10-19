#!/usr/bin/env bash
# Publish individual human exception decisions as TEXT only, every timer tick.
# Never upload scanned Bible images, provider replies, passwords, or any SQL.
set -euo pipefail
REPO=/opt/jbible/ocr-share-git
SRC=/var/lib/jbible-review/integrated_exception_decisions.json
DST=fr88_integrated_v1/human_exception_reviews.json
[[ -s "$SRC" ]] || { echo "No integrated exception decisions yet"; exit 0; }
[[ -d "$REPO/.git" && -s /root/.ssh/jbible_ocr_share ]] || {
  echo "Missing JBible Git checkout or deployment SSH key" >&2; exit 2;
}
export GIT_SSH_COMMAND='ssh -i /root/.ssh/jbible_ocr_share -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
(
  flock -x 9
  [[ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" == main ]] || {
    echo "Not on main branch" >&2; exit 3;
  }
  if [[ -n "$(git -C "$REPO" status --porcelain --untracked-files=normal)" ]]; then
    echo "Another unsynced Git task exists; retry at next timer tick" >&2; exit 3;
  fi
  git -C "$REPO" fetch --quiet origin main
  git -C "$REPO" merge --ff-only origin/main
  python3 - "$SRC" "$REPO/$DST" <<'PY'
import json,os,re,sys
from pathlib import Path
src,dst=Path(sys.argv[1]),Path(sys.argv[2])
document=json.loads(src.read_text(encoding="utf-8"))
if document.get("schema")!="jbible.fr88.integrated-exception-decisions.v1":
    raise ValueError("Unexpected exception-review schema")
reviews=document.get("reviews",{})
if not isinstance(reviews,dict): raise ValueError("Bad review map")
safe={}
for eid,item in reviews.items():
    if not re.fullmatch(r"(?:fr88i:p\d{4}:[LR]:\d{3}/target\d{2}|fr88:p\d{4}:ref\d{3})",eid):
        raise ValueError("Bad exception edge ID")
    if not isinstance(item,dict) or item.get("edge_id")!=eid:
        raise ValueError("Review identity mismatch")
    if item.get("sql_writes") is not False:
        raise ValueError("Refusing a review that claims SQL writes")
    safe[eid]={key:item.get(key) for key in (
        "edge_id","image_page","choice","cause","source","destination",
        "checked_original_scan","original_margin_text",
        "original_exception_reasons","human_review_status",
        "notes","sql_ready","sql_writes","reviewed_utc")}
dst.parent.mkdir(parents=True,exist_ok=True)
body={
    "schema":"jbible.fr88.integrated-human-exception-review.v1",
    "source":"Authenticated private scan viewer; text-only reviewer conclusions",
    "no_scanned_pages_published":True,"no_sql_writes":True,
    "reviews":safe
}
tmp=dst.with_name(dst.name+".tmp")
tmp.write_text(json.dumps(body,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
os.replace(str(tmp),str(dst))
print("Prepared",len(safe),"human classifications")
PY
  git -C "$REPO" add -- "$DST"
  if git -C "$REPO" diff --cached --quiet; then
    if [[ "$(git -C "$REPO" rev-list --count origin/main..HEAD)" -gt 0 ]]; then
      git -C "$REPO" push origin HEAD:main
    fi
    echo "Review decisions already synchronized"
    exit 0
  fi
  git -C "$REPO" commit -m "Sync human review of integrated French Bible OCR exceptions"
  git -C "$REPO" push origin HEAD:main
  echo "PUBLISHED https://github.com/tetrada/jbible-ocr-share/blob/main/$DST"
) 9>/run/jbible-github-sync.lock
