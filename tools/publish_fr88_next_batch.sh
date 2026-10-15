#!/usr/bin/env bash
# Publish DeepSeek-only 501..750 progress or final sanitized OCR staging JSON to Git.
# Does NOT publish scanned images, provider responses, DeepSeek key, or prompts.
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root" >&2; exit 2; }
REPO=/opt/jbible/ocr-share-git
SRC=/opt/jbible/data/raw/jbible_fr1988_deepseek_p0501_0750
DEST=fr88_deepseek_p0501_0750
[[ -d "$REPO/.git" && -s /root/.ssh/jbible_ocr_share ]] || {
  echo "Missing existing JBible Git checkout/deploy key" >&2; exit 2;
}
[[ -s "$SRC/progress.json" ]] || {
  echo "No progress file yet; run next-batch preflight or OCR first." >&2; exit 2;
}
export GIT_SSH_COMMAND='ssh -i /root/.ssh/jbible_ocr_share -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
(
  flock -x 9
  [[ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" == main ]] || {
    echo "Non-main branch; refusing to publish" >&2; exit 3;
  }
  if [[ -n "$(git -C "$REPO" status --porcelain --untracked-files=normal)" ]]; then
    echo "Existing Git sync checkout has uncommitted changes; retry after normal sync" >&2
    git -C "$REPO" status --short
    exit 3
  fi
  git -C "$REPO" fetch --quiet origin main
  git -C "$REPO" merge --ff-only origin/main
  mkdir -p "$REPO/$DEST"
  cp "$SRC/progress.json" "$REPO/$DEST/progress.json"
  files=("$DEST/progress.json")
  if [[ -s "$SRC/completion_summary.json" ]]; then
    for f in completion_summary.json staging_candidates.json staging_quarantine.json staging_excluded.json staging_candidate_segments.json; do
      [[ -s "$SRC/$f" ]] || { echo "Completed staging missing $f" >&2; exit 2; }
      cp "$SRC/$f" "$REPO/$DEST/$f"
      files+=("$DEST/$f")
    done
  fi
  git -C "$REPO" add -- "${files[@]}"
  if git -C "$REPO" diff --cached --quiet; then
    if [[ "$(git -C "$REPO" rev-list --count origin/main..HEAD)" -gt 0 ]]; then
      git -C "$REPO" push origin HEAD:main
    fi
    echo "Git already up to date"
    exit 0
  fi
  git -C "$REPO" commit -m "Publish safe FR88 DeepSeek OCR progress and review staging"
  git -C "$REPO" push origin HEAD:main
  echo "PUBLISHED https://github.com/tetrada/jbible-ocr-share/tree/main/$DEST"
) 9>/run/jbible-github-sync.lock
