#!/usr/bin/env bash
# One-time FR88 v2 fresh start: preflight 32-500, archive old output, change
# existing GitHub sync to v2, and launch a systemd service.
# Does NOT delete raw images, OCR backups, Bible catalog, API credentials, or SQL.
set -euo pipefail
START=32
END=500
BASE="/opt/jbible/importer"
RAW="/opt/jbible/data/raw"
URL="https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools"
SYNC="/usr/local/bin/jbible-github-sync"
GITDIR="/opt/jbible/ocr-share-git"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root." >&2; exit 1
fi
if systemctl is-active --quiet jbible-fr88-v2.service; then
  echo "JBible FR88 v2 is already running. Not resetting results." >&2; exit 1
fi
command -v docker >/dev/null
command -v curl >/dev/null
command -v python3 >/dev/null
command -v systemd-run >/dev/null
command -v flock >/dev/null
command -v git >/dev/null

cd "$BASE"
echo "[1/6] Download the three new standalone v2 scripts..."
for NAME in fr88_v2_normalize.py fr88_v2_ocr.py run_fr88_v2.sh; do
  TMP="$(mktemp "$BASE/.fr88v2.XXXXXXXX")"
  if ! curl -fsSL --retry 3 --connect-timeout 20 "$URL/$NAME" -o "$TMP"; then
    rm -f "$TMP"; exit 1
  fi
  install -m 700 "$TMP" "$BASE/$NAME"
  rm -f "$TMP"
done
python3 -m py_compile "$BASE/fr88_v2_normalize.py" "$BASE/fr88_v2_ocr.py"
bash -n "$BASE/run_fr88_v2.sh"

echo "[2/6] Verify catalog, row-parser examples, and ALL 469 JPEG files..."
"$BASE/run_fr88_v2.sh" "$START" "$END" --preflight

echo "[3/6] Archive old OCR results, never erase originals..."
ARCHIVE="$RAW/jbible_archives"
install -d -m 700 "$ARCHIVE"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -d "$RAW/jbible_fr1988_pilot" ]]; then
  mv "$RAW/jbible_fr1988_pilot" "$ARCHIVE/fr88_v1_$STAMP"
  echo "Archived: $ARCHIVE/fr88_v1_$STAMP"
fi
if [[ -d "$RAW/jbible_fr1988_v2" ]]; then
  mv "$RAW/jbible_fr1988_v2" "$ARCHIVE/fr88_v2_reset_$STAMP"
  echo "Archived incomplete v2: $ARCHIVE/fr88_v2_reset_$STAMP"
fi

echo "[4/6] Create clean v2 output before changing live sync..."
"$BASE/run_fr88_v2.sh" "$START" "$END" --initialize

echo "[5/6] Redirect existing GitHub sync to fresh FR88 v2 data..."
if [[ -f "$SYNC" ]]; then
  python3 - "$SYNC" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
mapping = {
    '"fr88_records.json"': '"fr88_v2_manifest.json"',
    '"fr88_comparison.json"': '"fr88_v2_parse_review.json"',
    '"fr88_summary.json"': '"fr88_v2_summary.json"',
    '"$SRC/jbible_fr1988_pilot/all_records.json"':
        '"$SRC/jbible_fr1988_v2/manifest.json"',
    '"$SRC/jbible_fr1988_pilot/comparison.json"':
        '"$SRC/jbible_fr1988_v2/parse_review.json"',
    '"$SRC/jbible_fr1988_pilot/summary.json"':
        '"$SRC/jbible_fr1988_v2/summary.json"',
}
if '"fr88_v2_manifest.json"' in s and '"fr88_v2_summary.json"' in s:
    print("GitHub sync already uses v2.")
else:
    for old, new in mapping.items():
        if s.count(old) != 1:
            raise SystemExit("Unexpected GitHub sync script: " + old)
        s = s.replace(old, new, 1)
    anchor = 'git -C "$DST" add -- "${FILES[@]}"'
    if s.count(anchor) != 1:
        raise SystemExit("Unexpected git add section in sync script.")
    shard_sync = '''mkdir -p "$DST/fr88_v2_shards"
cp -a "$SRC/jbible_fr1988_v2/shards/." "$DST/fr88_v2_shards/"
git -C "$DST" add -A -- fr88_v2_shards
'''
    s = s.replace(anchor, shard_sync + anchor, 1)
    backup = p.with_name(p.name + ".before_fr88_v2")
    backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    p.write_text(s, encoding="utf-8")
    print("Updated sync script, including 20-page shards; backup: " + str(backup))
PY
  bash -n "$SYNC"

  # Synchronize as one transaction against the existing cron lock.
  (
    flock -x 9
    "$SYNC"
    # Remove obsolete root-level FR88 OCR snapshots. Historical versions
    # remain accessible in Git history and in the VPS archive.
    if [[ -d "$GITDIR/.git" ]]; then
      git -C "$GITDIR" rm -f --ignore-unmatch \
        fr88_records.json fr88_comparison.json fr88_summary.json
      if ! git -C "$GITDIR" diff --cached --quiet; then
        git -C "$GITDIR" commit -m "Archive previous FR88 OCR snapshots; use clean v2"
        GIT_SSH_COMMAND="ssh -i /root/.ssh/jbible_ocr_share -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
          git -C "$GITDIR" push origin HEAD:main
      fi
    fi
  ) 9>/run/jbible-github-sync.lock
else
  echo "WARNING: GitHub sync script absent; v2 output stays on VPS until configured."
fi

echo "[6/6] Start persistent OCR task for pages 32..500..."
systemctl reset-failed jbible-fr88-v2.service 2>/dev/null || true
systemd-run --unit=jbible-fr88-v2 --collect \
  --description="JBible French 1988 v2 OCR pages 32-500" \
  --property=WorkingDirectory="$BASE" \
  "$BASE/run_fr88_v2.sh" "$START" "$END"

echo
echo "STARTED: FR88 v2 pages 32..500 (469 pages, up to 938 first-time margin calls)"
echo "Live logs: journalctl -u jbible-fr88-v2 -f"
echo "Service:   systemctl status jbible-fr88-v2"
echo "Live portal: https://status.tetrada.eu/jbible/importer"
echo "Published data: https://github.com/tetrada/jbible-ocr-share"
echo "NO SQL writes; verified=0. Old OCR results archived on VPS."
