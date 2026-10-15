# JBible FR88 visual proofreader — protected VPS webpage

A small authenticated review app for **the seven substantive disagreements** in the completed pages 31–50 v2/v3 pilot. The **25 cosmetic spacing/arrow differences** are deliberately excluded.

## Install (one command on Ubuntu VPS as root)

```bash
curl -fsSL https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools/install_fr88_review_web.sh | bash
```

This installs a root-owned Python 3.6-compatible stdlib application and mobile-ready webpage in `/opt/jbible/review-web`, with an unprivileged service account `jbible-review`. It preserves previously saved reviews across reinstalls. A strong browser-login password is generated once and printed **only in the VPS terminal**. Keep it private; do not share or commit it.

The intended URL is:

**https://status.tetrada.eu/jbible-review/**

Sign in using `reviewer` and the generated password.

The installer attempts to add a dedicated reverse-proxy location to the existing `status.tetrada.eu` HTTPS Nginx server block. It first backs up the config and validates it with `nginx -t`; on validation failure it restores the original file. If it cannot unambiguously identify the HTTPS server block, it **does not edit Nginx**. Instead, include this inside your existing HTTPS server block:

```nginx
include /etc/nginx/snippets/jbible-review-locations.conf;
```

Then `nginx -t && systemctl reload nginx`.

## What the reviewer sees

For each of the seven cases on pages 32, 34, 37, 40 and 41:

1. Original Bible scan, initially cropped around the printed reference, with zoom, up/down crop position controls and full-page view.
2. V2 text and V3 text, exactly as recorded in GitHub's comparison.
3. Buttons for V2, V3, Neither/edit, or Unsure.
4. Editable exact transcription field with **one physical printed row per line**, plus optional comments.
5. Checkbox: "I checked the original scanned image" and **Save and next**.

The user must inspect the actual scan; the model's suggestion or catalog validity never counts as independent verification. Saving a case without checking is pending and cannot become a prompt-training label.

A manual review of two occurrences of `2 P 2 5` is still needed: the earlier standalone cropped image confirms the typography, **not which page-row occurrences it represents**.

## Data, security and Git sync

- Original JPEGs: read in place from `/opt/jbible/data/raw/fr_bible_1988/` by the restricted app service, only after HTTP Basic authentication.
- The service is bound to `127.0.0.1:8765`; HTTPS access uses Nginx on `status.tetrada.eu`.
- Password file: `/opt/jbible/review-web/password` (owner `jbible-review`, mode 0600). **Never place it in Git.**
- Edits are atomically stored in `/var/lib/jbible-review/decisions.json` (not in original OCR output).
- A root-owned systemd timer publishes **text decisions only** to `fr88_v3_learning/human_reviews.json` in the existing GitHub repo, about every two minutes. The publisher uses the existing SSH deployment key and `/run/jbible-github-sync.lock`, stages only one JSON file and aborts on a dirty working tree rather than risking OCR sync.
- Optional freeform notes are included in that text-only Git publication; **do not enter private information in notes**, because the repository is public.
- Bible page scans, cropped images, secrets, and original DeepSeek provider responses are never published to GitHub by this installer.
- Human labels do **not** automatically become gold examples. After review, approved examples may be curated from the published decisions into `training/fr88_ocr_gold.json`. That separation prevents guesswork being treated as model training.

## Check installation / publishing

```bash
systemctl status jbible-fr88-review-web.service --no-pager
systemctl list-timers --all | grep jbible-fr88-review-publish
journalctl -u jbible-fr88-review-publish.service --since "15 minutes ago" --no-pager
cat /opt/jbible/review-web/password  # root only; keep secret
```

Recover the browser login at any time on the VPS: username `reviewer` and password from the password file above. Re-running the installer does not reset it.

Review URL and code are part of the **learning** workflow only. No DeepSeek API call, database write, OCR checkpoint overwrite, status portal modification except the dedicated Nginx location, or automatic verified Bible link is performed.
