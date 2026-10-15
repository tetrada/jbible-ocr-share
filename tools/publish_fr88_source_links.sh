#!/usr/bin/env bash
# Git-only publication of text-based source/target proposals, no scanned images.
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root" >&2; exit 2; }
REPO=/opt/jbible/ocr-share-git
SRC=/opt/jbible/data/raw/jbible_fr88_source_links
DEST=fr88_source_links_pilot
[[ -d "$REPO/.git" && -s /root/.ssh/jbible_ocr_share ]] || {
  echo "Missing existing JBible Git checkout or deployment key" >&2; exit 2;
}
for f in progress.json proposed_links.json source_link_review_queue.json; do
  [[ -s "$SRC/$f" ]] || { echo "Missing $SRC/$f (run pilot first)" >&2; exit 2; }
done
export GIT_SSH_COMMAND='ssh -i /root/.ssh/jbible_ocr_share -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
(
  flock -x 9
  [[ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" == main ]] || {
    echo "Not on main branch, refusing to publish" >&2; exit 3;
  }
  if [[ -n "$(git -C "$REPO" status --porcelain --untracked-files=normal)" ]]; then
    echo "Git checkout is dirty; finish existing sync then retry" >&2
    git -C "$REPO" status --short
    exit 3
  fi
  git -C "$REPO" fetch --quiet origin main
  git -C "$REPO" merge --ff-only origin/main
  mkdir -p "$REPO/$DEST"
  python3 - "$SRC" "$REPO/$DEST" <<'PY'
import json, sys
from pathlib import Path
src=Path(sys.argv[1])
out=Path(sys.argv[2])
safe={
    "schema":"jbible.fr88.source-link-review-public.v1",
    "progress":{},
    "proposed_links":[],
    "review_queue":[]
}
progress=json.loads((src/"progress.json").read_text(encoding="utf-8"))
proposals=json.loads((src/"proposed_links.json").read_text(encoding="utf-8"))
queue=json.loads((src/"source_link_review_queue.json").read_text(encoding="utf-8"))
if not isinstance(proposals,list) or not isinstance(queue,list):
    raise ValueError("Invalid link proposal output")
safe["progress"]={key:progress.get(key) for key in (
    "pages","model","margins_complete","margins_expected",
    "progress_percent","candidate_links_needing_review",
    "other_items_needing_review","verified_links","sql_writes","updated_utc"
)}
def limited(x):
    if not isinstance(x,dict):
        raise ValueError("Invalid staging entry")
    return {key:x.get(key) for key in (
        "row_id","image_page","side","margin_y_fraction","margin_raw_line",
        "target_segment_index","target","source","state",
        "source_reason","target_reason","source_verified","target_verified",
        "source_to_target_link_verified","sql_ready","reason"
    )}
safe["proposed_links"]=[limited(x) for x in proposals]
safe["review_queue"]=[limited(x) for x in queue]
safe["copyrighted_page_scans_published"]=False
safe["original_provider_bodies_published"]=False
safe["automatic_source_to_target_verification"]=False
tmp=out/"source_link_results.json.tmp"
target=out/"source_link_results.json"
tmp.write_text(json.dumps(safe,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
tmp.replace(target)
print("Prepared %d proposed links, %d pending reviews"%
      (len(proposals),len(queue)),flush=True)
PY
  git -C "$REPO" add -- "$DEST/source_link_results.json"
  if git -C "$REPO" diff --cached --quiet; then
    if [[ "$(git -C "$REPO" rev-list --count origin/main..HEAD)" -gt 0 ]]; then
      git -C "$REPO" push origin HEAD:main
    fi
    echo "GitHub already up to date"
    exit 0
  fi
  git -C "$REPO" commit -m "Publish read-only French Bible source-to-target link proposals"
  git -C "$REPO" push origin HEAD:main
  echo "PUBLISHED https://github.com/tetrada/jbible-ocr-share/tree/main/$DEST"
) 9>/run/jbible-github-sync.lock
