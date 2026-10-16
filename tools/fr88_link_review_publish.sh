#!/usr/bin/env bash
# Publish text-only human source-to-target alignment reviews; NEVER scanned images.
set -euo pipefail
REPO=/opt/jbible/ocr-share-git
DECISIONS=/var/lib/jbible-review/link_decisions.json
TARGET=fr88_source_links_pilot/human_link_reviews.json
[[ -s "$DECISIONS" ]] || { echo 'No source-link decisions yet.'; exit 0; }
[[ -d "$REPO/.git" && -s /root/.ssh/jbible_ocr_share ]] || {
  echo "JBible Git checkout or deploy key is missing" >&2; exit 2;
}
export GIT_SSH_COMMAND='ssh -i /root/.ssh/jbible_ocr_share -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
(
  flock -x 9
  [[ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" == main ]] || {
    echo "Git checkout is not on main" >&2; exit 3;
  }
  if [[ -n "$(git -C "$REPO" status --porcelain --untracked-files=normal)" ]]; then
    echo "Unsynchronized Git checkout, retry at next timer tick" >&2
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
if data.get("schema")!="jbible.fr88.source-link-decisions.v1":
    raise ValueError("Unexpected source-link decision schema")
items=data.get("reviews",{})
if not isinstance(items,dict):
    raise ValueError("Invalid source-link decisions")
safe={}
for rid,r in items.items():
    if not re.match(r"^fr88v2:p\d{4}:[LR]:\d{2,3}$",rid) or not isinstance(r,dict):
        raise ValueError("Invalid human review ID")
    src=r.get("source") or {}
    ch=r.get("checked") or {}
    safe[rid]={
        "choice":r.get("choice"),
        "source":{name:src.get(name) for name in (
            "book_code","source_book_basis","scope","chapter","verse","end_chapter","end_verse")},
        "target_raw_line":r.get("target_raw_line"),
        "checked":{name:ch.get(name) is True for name in (
            "source_verse","target_print","alignment")},
        "scan_review_status":r.get("scan_review_status"),
        "biblical_target_canonically_verified":False,
        "sql_ready":False,
        "sql_writes":False,
        "notes":r.get("notes",""),
        "saved_at_utc":r.get("saved_at_utc")
    }
result={
    "schema":"jbible.fr88.human-source-link-review.v1",
    "notice":"Human-checked printed source/target relationship only. No SQL import or canonical target verification.",
    "provenance":"Authenticated JBible review website; original copyright scans remain private on VPS",
    "reviews":safe
}
destination.parent.mkdir(parents=True,exist_ok=True)
temp=destination.with_name(destination.name+".tmp")
temp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
os.replace(str(temp),str(destination))
print("Prepared %d text-only source-link decisions" % len(safe))
PY
  git -C "$REPO" add -- "$TARGET"
  if git -C "$REPO" diff --cached --quiet; then
    if [[ "$(git -C "$REPO" rev-list --count origin/main..HEAD)" -gt 0 ]]; then
      git -C "$REPO" push origin HEAD:main
    else
      echo "Human source-link reviews already synchronized"
    fi
    exit 0
  fi
  git -C "$REPO" commit -m "Sync human JBible source-to-target scan review decisions"
  git -C "$REPO" push origin HEAD:main
  echo 'PUBLISHED https://github.com/tetrada/jbible-ocr-share/blob/main/fr88_source_links_pilot/human_link_reviews.json'
) 9>/run/jbible-github-sync.lock
