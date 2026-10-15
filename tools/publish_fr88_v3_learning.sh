#!/usr/bin/env bash
# Publish text-only pilot comparison through existing GitHub sync checkout/key.
# Reuses jbible-github-sync.lock so scheduled sync cannot race with this push.
set -euo pipefail
REPO=/opt/jbible/ocr-share-git
BASE=/opt/jbible/importer
SCRIPT="$BASE/fr88_v3_git_export.py"
URL=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/fr88_v3_git_export.py
[[ $(id -u) -eq 0 ]] || { echo 'Run as root, like existing JBible Git sync' >&2; exit 2; }
[[ -d "$REPO/.git" ]] || { echo "Missing Git checkout: $REPO" >&2; exit 2; }
[[ -f /root/.ssh/jbible_ocr_share ]] || { echo 'JBible SSH key not configured' >&2; exit 2; }
command -v curl >/dev/null
command -v git >/dev/null
command -v flock >/dev/null
command -v python3 >/dev/null
TMP="$(mktemp "$BASE/.fr88_v3_export_XXXXXXXX")"
trap 'rm -f "$TMP"' EXIT
curl -fsSL --retry 3 --connect-timeout 20 "$URL" -o "$TMP"
python3 -m py_compile "$TMP"
mv "$TMP" "$SCRIPT"
chmod 0644 "$SCRIPT"
export GIT_SSH_COMMAND='ssh -i /root/.ssh/jbible_ocr_share -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
(
  flock -x 9
  [[ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" == main ]] || {
    echo 'Git checkout is not on main; refusing to update' >&2; exit 3;
  }
  if [[ -n "$(git -C "$REPO" status --porcelain --untracked-files=normal)" ]]; then
    echo 'Git checkout has outstanding changes. Run existing jbible-github-sync first.' >&2
    git -C "$REPO" status --short
    exit 3
  fi
  git -C "$REPO" fetch --quiet origin main
  git -C "$REPO" merge --ff-only origin/main
  python3 "$SCRIPT" "$REPO/fr88_v3_learning"
  git -C "$REPO" add -- fr88_v3_learning/pilot_summary.json fr88_v3_learning/disagreements.json
  if git -C "$REPO" diff --cached --quiet; then
    echo 'No changes to publish.'
    exit 0
  fi
  git -C "$REPO" commit -m 'Publish text-only FR88 v3 pilot discrepancies for learning'
  git -C "$REPO" push origin HEAD:main
  echo 'PUBLISHED https://github.com/tetrada/jbible-ocr-share/tree/main/fr88_v3_learning'
) 9>/run/jbible-github-sync.lock
