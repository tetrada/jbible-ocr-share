# JBible FR88 → TETRADA Status Engine telemetry

Project: `jbible/importer`, one child run entity per execution.
Portal: https://status.tetrada.eu/
Official documentation: https://status.tetrada.eu/docs/

This status integration **does not modify** the OCR, geometry, parser, checkpoints, Bible data, DeepSeek credentials, GitHub publisher, or SQL. The original full terminal log remains private on the VPS. The monitor emits **sanitized operational metadata only** (page/task IDs, test pass, page counts, accepted/exceptions, publishing activity, errors and completion).

The active batch script `tools/run_fr88_pages_101_200.sh` installs and launches `tools/jbible_status_logwatch.py` automatically when started from the repo. If the OCR job was already started **before** this change, attach to its existing log **without interrupting OCR**:

```bash
bash -c 'set -e; B=/opt/jbible/importer; R=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main/tools; curl -fsSL --retry 3 "$R/jbible_status_logwatch.py" -o "$B/jbible_status_logwatch.py"; curl -fsSL --retry 3 "$R/test_jbible_status_logwatch.py" -o "$B/test_jbible_status_logwatch.py"; python3 "$B/test_jbible_status_logwatch.py"; nohup python3 -u "$B/jbible_status_logwatch.py" --log /root/jbible_101_200.log --start 101 --end 200 > /root/jbible_101_200_status.log 2>&1 < /dev/null &'
```

Then read any **sanitized local delivery errors** with `tail -n 25 /root/jbible_101_200_status.log`. Check the portal's JBible Importer parent entity and its child run.

The existing official Python Status SDK and `jbible_status_bridge.py` must be installed under `/opt/jbible/importer/status_sdk/` and `/opt/jbible/importer/` respectively (from the prior JBible v7.3 status integration). A private file `/opt/jbible/importer/.env.status` with mode 0600 must contain `TETRADA_STATUS_TOKEN` and optionally `TETRADA_STATUS_URL=https://status.tetrada.eu`. No secrets are published to GitHub. The log monitor **only imports** those keys; it never writes their values to logs or reports.

Expected status events: execution start, regression preflight, every new page's DeepSeek task, every completed page with counts, API budget checkpoint, publication attempts/results, errors and completed/failed state. Child entity includes live progress (0–100 new pages) and an activity feed. Parent is `jbible/importer`.

Best effort: portal outages/invalid tokens cannot stop OCR, and the official SDK does not offer durable retry queuing; the local log is the complete durable source. The monitoring process checks for terminal success/error markers, holds a one-per-batch flock lock, and uses an idle safety timeout. For subsequent page ranges, use the same watcher with matching `--start`, `--end`, `--log` arguments and add a hook to new batch scripts before starting the batch.
