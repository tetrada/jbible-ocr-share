#!/usr/bin/env bash
# Safe text-only V4 pilot publication to existing JBible Git checkout.
# Uses existing deploy key and same lock as scheduled OCR Git synchronization.
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root" >&2; exit 2; }
REPO=/opt/jbible/ocr-share-git
BASE=/opt/jbible/importer
URL=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/fr88_v4_git_export.py
SCRIPT="$BASE/fr88_v4_git_export.py"
[[ -d "$REPO/.git" ]] || { echo "Missing Git checkout: $REPO" >&2; exit 2; }
[[ -s /root/.ssh/jbible_ocr_share ]] || { echo "Missing existing JBible Git deploy key" >&2; exit 2; }
for exe in curl git flock python3; do command -v "$exe" >/dev/null; done
TMP="$(mktemp "$BASE/.v4_git_export_XXXXXXXX")"
trap 'rm -f "$TMP"' EXIT
curl -fsSL --retry 3 --connect-timeout 20 "$URL" -o "$TMP"
python3 -m py_compile "$TMP"
mv -f "$TMP" "$SCRIPT"
chmod 0644 "$SCRIPT"
export GIT_SSH_COMMAND='ssh -i /root/.ssh/jbible_ocr_share -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
(
  flock -x 9
  [[ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" == main ]] || {
    echo "Refusing to publish from non-main branch" >&2; exit 3;
  }
  if [[ -n "$(git -C "$REPO" status --porcelain --untracked-files=normal)" ]]; then
    echo "Unsynced changes in Git checkout; run existing jbible-github-sync then retry" >&2
    git -C "$REPO" status --short
    exit 3
  fi
  git -C "$REPO" fetch --quiet origin main
  git -C "$REPO" merge --ff-only origin/main
  python3 "$SCRIPT" "$REPO/fr88_v4_learning"
  git -C "$REPO" add -- fr88_v4_learning/pilot_summary.json fr88_v4_learning/readings_and_differences.json
  if git -C "$REPO" diff --cached --quiet; then
    if [[ "$(git -C "$REPO" rev-list --count origin/main..HEAD)" -gt 0 ]]; then
      git -C "$REPO" push origin HEAD:main
      echo "Pushed an existing unpublished commit"
    else
      echo "GitHub already has the latest v4 report"
    fi
    exit 0
  fi
  git -C "$REPO" commit -m "Publish text-only FR88 V4 OCR pilot comparisons"
  git -C "$REPO" push origin HEAD:main
  echo "PUBLISHED https://github.com/tetrada/jbible-ocr-share/tree/main/fr88_v4_learning"
) 9>/run/jbible-github-sync.lock
