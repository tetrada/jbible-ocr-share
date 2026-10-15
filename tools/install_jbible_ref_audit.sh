#!/usr/bin/env bash
# Installs/updates only the JBible reference audit files.
# DOES NOT restart services, modify OCR output, call DeepSeek, or write SQL.
set -euo pipefail
DEST="/opt/jbible/importer"
BASE_URL="https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools"
mkdir -p "$DEST"
for name in jbible_ref_audit.py run_jbible_ref_audit.sh test_jbible_ref_audit.py README_jbible_ref_audit.md; do
  tmp="$(mktemp "$DEST/.audit_download_XXXXXXXX")"
  if ! curl --fail --location --silent --show-error --retry 3 --connect-timeout 20 \
    "$BASE_URL/$name" --output "$tmp"; then
    rm -f "$tmp"
    echo "Download failed: $name" >&2
    exit 1
  fi
  test -s "$tmp"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$DEST/$name"
  echo "Installed $name"
done
chmod 0755 "$DEST/run_jbible_ref_audit.sh"
python3 -m py_compile "$DEST/jbible_ref_audit.py" "$DEST/test_jbible_ref_audit.py"
python3 "$DEST/test_jbible_ref_audit.py"
echo "Installed successfully. Try: cd $DEST && ./run_jbible_ref_audit.sh 31 40"
