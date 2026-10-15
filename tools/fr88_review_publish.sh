#!/usr/bin/env bash
# Publish ONLY human-entered text decisions into public JBible Git repository.
# Images, passwords, OCR provider responses and page scans NEVER leave VPS.
set -euo pipefail
REPO=/opt/jbible/ocr-share-git
DECISIONS=/var/lib/jbible-review/decisions.json
TARGET=fr88_v3_learning/human_reviews.json
[[ -f "$DECISIONS" ]] || { echo "No review decisions yet."; exit 0; }
[[ -d "$REPO/.git" ]] || { echo "Missing configured JBible Git checkout" >&2; exit 2; }
[[ -s /root/.ssh/jbible_ocr_share ]] || { echo "Missing existing JBible Git deploy key" >&2; exit 2; }
export GIT_SSH_COMMAND='ssh -i /root/.ssh/jbible_ocr_share -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
(
  flock -x 9
  [[ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" == main ]] || {
    echo 'Not on main branch; refusing publication' >&2; exit 3;
  }
  if [[ -n "$(git -C "$REPO" status --porcelain --untracked-files=normal)" ]]; then
    echo 'Git checkout has unsynchronized changes; skipping this timer run' >&2
    exit 3
  fi
  git -C "$REPO" fetch --quiet origin main
  git -C "$REPO" merge --ff-only origin/main
  python3 - "$DECISIONS" "$REPO/$TARGET" <<'PY'
import json, os, sys
from pathlib import Path
source=Path(sys.argv[1])
target=Path(sys.argv[2])
data=json.loads(source.read_text(encoding="utf-8"))
reviews=data.get("reviews",{})
if not isinstance(reviews,dict):
    raise ValueError("Invalid review storage")
safe={}
for case_id, r in reviews.items():
    if not isinstance(case_id,str) or not case_id.startswith("D") or not isinstance(r,dict):
        raise ValueError("Invalid review ID")
    safe[case_id]={
        "choice":r.get("choice"),
        "corrected_lines":r.get("corrected_lines",[]),
        "verified_against_scan":r.get("verified_against_scan") is True,
        "verification_status":r.get("verification_status","PENDING"),
        "notes":r.get("notes",""),
        "saved_at_utc":r.get("saved_at_utc")
    }
publication={
    "schema":"jbible.fr88.human-review.v1",
    "source":"Authenticated human verification of French Bible reference scans",
    "notice":"Text-only public GitHub data; original copyrighted scanned pages remain on VPS",
    "reviews":safe
}
target.parent.mkdir(parents=True,exist_ok=True)
tmp=target.with_name(target.name+".tmp")
tmp.write_text(json.dumps(publication,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
os.replace(str(tmp),str(target))
print("Review decisions prepared:",len(safe))
PY
  git -C "$REPO" add -- "$TARGET"
  if git -C "$REPO" diff --cached --quiet; then
    if [[ "$(git -C "$REPO" rev-list --count origin/main..HEAD)" -gt 0 ]]; then
      echo 'Retrying previous human-review Git push'
      git -C "$REPO" push origin HEAD:main
    else
      echo 'Human review Git publication already up to date'
    fi
    exit 0
  fi
  git -C "$REPO" commit -m 'Sync human-verified JBible OCR review decisions'
  git -C "$REPO" push origin HEAD:main
  echo 'PUBLISHED https://github.com/tetrada/jbible-ocr-share/blob/main/fr88_v3_learning/human_reviews.json'
) 9>/run/jbible-github-sync.lock
