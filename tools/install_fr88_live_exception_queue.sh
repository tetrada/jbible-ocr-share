#!/usr/bin/env bash
# Add a two-minute live data refresh to EXISTING password-protected
# FR88 integrated exception review. Never restart review/OCR services.
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root" >&2; exit 2; }

REVIEW=/opt/jbible/review-web
REPO=/opt/jbible/ocr-share-git
DIR=/usr/local/lib/jbible
NAME=sync_fr88_integrated_review_queue.py
TEST=test_sync_fr88_integrated_review_queue.py
RAW=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools
[[ -s "$REVIEW/server.py" && -s "$REVIEW/password" &&
   -s "$REVIEW/fr88_integrated_exception_review.py" ]] || {
    echo "ERROR: existing protected integrated exception reviewer not installed" >&2; exit 3;
}
[[ -s "$REPO/fr88_integrated_v1/pilot_report.json" ]] || {
    echo "ERROR: GitHub OCR report has not been published to local checkout yet" >&2; exit 3;
}
install -d -m 0755 "$DIR"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -fsSL --retry 3 "$RAW/$NAME" -o "$TMP/$NAME"
curl -fsSL --retry 3 "$RAW/$TEST" -o "$TMP/$TEST"
python3 -m py_compile "$TMP/$NAME" "$TMP/$TEST"
install -m 0644 "$TMP/$NAME" "$DIR/$NAME"
install -m 0644 "$TMP/$TEST" "$DIR/$TEST"
python3 "$DIR/$TEST"

cat >/etc/systemd/system/jbible-fr88-review-queue-sync.service <<'SERVICE'
[Unit]
Description=Refresh JBible protected visual exception review from latest published OCR
After=network-online.target
[Service]
Type=oneshot
User=root
# Same flock file as GitHub report publisher: avoid partial reads/updates.
ExecStart=/usr/bin/flock -s /run/jbible-github-sync.lock /usr/bin/python3 /usr/local/lib/jbible/sync_fr88_integrated_review_queue.py
SERVICE

cat >/etc/systemd/system/jbible-fr88-review-queue-sync.timer <<'TIMER'
[Unit]
Description=Keep JBible protected exception viewer current with OCR results
[Timer]
OnBootSec=1min
OnUnitActiveSec=2min
AccuracySec=30s
Unit=jbible-fr88-review-queue-sync.service
[Install]
WantedBy=timers.target
TIMER

systemctl daemon-reload
systemctl enable --now jbible-fr88-review-queue-sync.timer >/dev/null
# Run once immediately too; never wait for a timer to expose the new cases.
systemctl start jbible-fr88-review-queue-sync.service
systemctl --quiet is-failed jbible-fr88-review-queue-sync.service && {
    echo "ERROR: queue sync job failed, see systemd journal" >&2
    exit 4
}
echo "JBIBLE REVIEW LIVE QUEUE READY:"
echo "https://status.tetrada.eu/jbible-review/exceptions/"
echo "Refreshes from the latest GitHub-published OCR results about every two minutes."
echo "Existing scanned images and saved human reviews retained; no API or SQL."
