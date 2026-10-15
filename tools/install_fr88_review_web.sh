#!/usr/bin/env bash
# One-command authenticated visual OCR review on https://status.tetrada.eu/jbible-review/
# No OCR API calls, no SQL writes, no public image uploads, no v2/v3 mutations.
set -euo pipefail
[[ $(id -u) -eq 0 ]] || { echo 'Run as root' >&2; exit 2; }
command -v curl >/dev/null
command -v systemctl >/dev/null
command -v python3 >/dev/null
BASE=/opt/jbible/review-web
DATA=/var/lib/jbible-review
SRC=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main
mkdir -p "$BASE"
chmod 0755 "$BASE"
if ! id -u jbible-review >/dev/null 2>&1; then
  useradd --system --user-group --home-dir "$DATA" --shell /usr/sbin/nologin jbible-review
fi
install -d -m 0750 -o jbible-review -g jbible-review "$DATA"
get_file() {
  local remote="$1" destination="$2"
  local temp
  temp="$(mktemp "$BASE/.download_XXXXXXXX")"
  if ! curl -fsSL --retry 3 --connect-timeout 20 "$SRC/$remote" -o "$temp"; then
    rm -f "$temp"
    echo "Could not fetch $remote" >&2
    exit 1
  fi
  test -s "$temp"
  chmod 0644 "$temp"
  mv -f "$temp" "$destination"
  echo "Installed $destination"
}
get_file tools/fr88_review_web_server.py "$BASE/server.py"
get_file tools/fr88_review_web_index.html "$BASE/index.html"
get_file tools/fr88_review_web_app.js "$BASE/app.js"
get_file training/fr88_priority_review.json "$BASE/priority.json"
get_file tools/fr88_review_publish.sh /usr/local/bin/jbible-review-publish
get_file tools/fr88_review_nginx.py "$BASE/configure_nginx.py"
chmod 0750 /usr/local/bin/jbible-review-publish
python3 -m py_compile "$BASE/server.py" "$BASE/configure_nginx.py"
if [[ ! -s "$BASE/password" ]]; then
  python3 - "$BASE/password" <<'PY'
import secrets,sys
from pathlib import Path
p=Path(sys.argv[1])
p.write_text(secrets.token_urlsafe(27)+"\n",encoding="utf-8")
PY
fi
if ! runuser -u jbible-review -- test -r "$BASE/priority.json"; then
  echo "Review service account cannot access $BASE. Check parent directory permissions." >&2
  exit 1
fi
chown jbible-review:jbible-review "$BASE/password"
chmod 0600 "$BASE/password"
# The current review involves five pages only; do not chmod or copy scans.
for PAGE in 0032 0034 0037 0040 0041; do
  IMG="/opt/jbible/data/raw/fr_bible_1988/image_$PAGE.jpg"
  [[ -s "$IMG" ]] || { echo "Missing scanned image $IMG" >&2; exit 1; }
  if ! runuser -u jbible-review -- test -r "$IMG"; then
    echo "Review account cannot read $IMG; fix directory read permissions/ACL first" >&2
    exit 1
  fi
done
cat > /etc/systemd/system/jbible-fr88-review-web.service <<'SERVICE'
[Unit]
Description=JBible FR88 protected OCR visual review
After=network.target
[Service]
Type=simple
User=jbible-review
Group=jbible-review
WorkingDirectory=/opt/jbible/review-web
ExecStart=/usr/bin/python3 /opt/jbible/review-web/server.py --host 127.0.0.1 --port 8765
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=/var/lib/jbible-review
[Install]
WantedBy=multi-user.target
SERVICE

if [[ -d /opt/jbible/ocr-share-git/.git && -s /root/.ssh/jbible_ocr_share ]]; then
cat > /etc/systemd/system/jbible-fr88-review-publish.service <<'PUBLISH'
[Unit]
Description=Publish text-only JBible human OCR review decisions to GitHub
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/jbible-review-publish
PUBLISH
cat > /etc/systemd/system/jbible-fr88-review-publish.timer <<'TIMER'
[Unit]
Description=Sync JBible human OCR review decisions to Git every two minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=2min
Unit=jbible-fr88-review-publish.service
[Install]
WantedBy=timers.target
TIMER
fi
systemctl daemon-reload
systemctl enable --now jbible-fr88-review-web.service
systemctl restart jbible-fr88-review-web.service
if [[ -f /etc/systemd/system/jbible-fr88-review-publish.timer ]]; then
  systemctl enable --now jbible-fr88-review-publish.timer
fi
curl -fsS --max-time 10 http://127.0.0.1:8765/healthz >/dev/null || {
  echo 'Review web health check failed. Run systemctl status jbible-fr88-review-web.service' >&2
  exit 1
}
echo 'Local authenticated review service is working.'
mkdir -p /etc/nginx/snippets
cat >/etc/nginx/snippets/jbible-review-locations.conf <<'NGINX'
# Authenticated Python backend serves scans ONLY after a per-user password challenge.
location = /jbible-review { return 301 /jbible-review/; }
location ^~ /jbible-review/ {
    proxy_pass http://127.0.0.1:8765/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 60s;
    client_max_body_size 24k;
}
NGINX
if command -v nginx >/dev/null; then
  if python3 "$BASE/configure_nginx.py"; then
    systemctl reload nginx
    echo 'Nginx reloaded and HTTPS review route enabled.'
  else
    echo 'Nginx was not modified automatically. See configuration guidance above.'
  fi
else
  echo 'Nginx not found on host. Configure HTTPS reverse proxy to 127.0.0.1:8765 yourself.'
fi
echo
echo '==========================================================='
echo 'JBIBLE VISUAL REVIEW: https://status.tetrada.eu/jbible-review/'
echo 'Username: reviewer'
echo "Password: $(cat "$BASE/password")"
echo 'Save this password privately. Do not paste it into chat/Git.'
echo 'Your reviewed text syncs to GitHub periodically; images stay on VPS.'
echo '==========================================================='
