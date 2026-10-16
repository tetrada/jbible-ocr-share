#!/usr/bin/env bash
# Publish ONLY one-source-one-target decisions (no scans or DeepSeek payloads).
# Legacy /var/lib/jbible-review/link_decisions.json remains untouched.
set -euo pipefail
REPO=/opt/jbible/ocr-share-git
DECISIONS=/var/lib/jbible-review/link_edge_decisions.json
TARGET=fr88_source_links_pilot/human_link_edge_reviews.json
[[ -s "$DECISIONS" ]] || { echo 'No individual link reviews yet.'; exit 0; }
[[ -d "$REPO/.git" && -s /root/.ssh/jbible_ocr_share ]] || {
  echo "JBible Git checkout or key missing" >&2; exit 2;
}
export GIT_SSH_COMMAND='ssh -i /root/.ssh/jbible_ocr_share -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
(
  flock -x 9
  [[ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" == main ]] || exit 3
  if [[ -n "$(git -C "$REPO" status --porcelain --untracked-files=normal)" ]]; then
    echo "Unsynchronized Git checkout: retry next timer" >&2
    exit 3
  fi
  git -C "$REPO" fetch --quiet origin main
  git -C "$REPO" merge --ff-only origin/main
  python3 - "$DECISIONS" "$REPO/$TARGET" <<'PY'
import json,os,re,sys
from pathlib import Path
source=Path(sys.argv[1])
destination=Path(sys.argv[2])
data=json.loads(source.read_text(encoding="utf-8"))
if data.get("schema")!="jbible.fr88.source-target-edge-decisions.v2":
    raise ValueError("Wrong individual link review schema")
items=data.get("reviews",{})
if not isinstance(items,dict):
    raise ValueError("Invalid edge reviews")
safe={}
for lid,r in items.items():
    if not re.fullmatch(r"fr88v2:p\d{4}:[LR]:\d{2,3}/target\d{2}",lid):
        raise ValueError("Invalid link ID")
    if not isinstance(r,dict) or r.get("link_id")!=lid:
        raise ValueError("Link review identity mismatch")
    source_data=r.get("source") or {}
    checked=r.get("checked") or {}
    safe[lid]={
        "row_id":r.get("row_id"),
        "target_segment_index":r.get("target_segment_index"),
        "choice":r.get("choice"),
        "source":{key:source_data.get(key) for key in
          ("book_code","source_book_basis","chapter","verse",
           "end_chapter","end_verse","scope")},
        "target_printed":r.get("target_printed"),
        "original_margin_raw_line":r.get("original_margin_raw_line"),
        "checked":{key:checked.get(key) is True for key in
          ("page_book","source_marker","target_print","alignment")},
        "scan_review_status":r.get("scan_review_status"),
        "canonical_target_verified":False,
        "sql_ready":False,"sql_writes":False,
        "notes":r.get("notes",""),
        "saved_at_utc":r.get("saved_at_utc")
    }
publication={
    "schema":"jbible.fr88.human-source-target-edge-review.v2",
    "notice":"One source-target relation per destination. Human scan checked, target canonicalization and SQL import remain separate.",
    "copyrighted_images_published":False,
    "reviews":safe
}
destination.parent.mkdir(parents=True,exist_ok=True)
tmp=destination.with_name(destination.name+".tmp")
tmp.write_text(json.dumps(publication,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
os.replace(str(tmp),str(destination))
print("Prepared",len(safe),"individual source-target decisions")
PY
  git -C "$REPO" add -- "$TARGET"
  if git -C "$REPO" diff --cached --quiet; then
    if [[ "$(git -C "$REPO" rev-list --count origin/main..HEAD)" -gt 0 ]]; then
      git -C "$REPO" push origin HEAD:main
    else
      echo "Individual source-target decisions already synchronized"
    fi
    exit 0
  fi
  git -C "$REPO" commit -m "Sync human-verified individual source-to-target Bible reference decisions"
  git -C "$REPO" push origin HEAD:main
  echo "PUBLISHED https://github.com/tetrada/jbible-ocr-share/blob/main/$TARGET"
) 9>/run/jbible-github-sync.lock
