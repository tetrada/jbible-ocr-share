#!/usr/bin/env bash
# One command: inspect VPS, send sanitized diagnostic to TETRADA Status,
# and publish diagnostic JSON to existing private GitHub report repo.
# Never starts/stops OCR; no SQL, no DeepSeek API, no secret values in output.
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root on JBible VPS" >&2; exit 2; }
OUT="$(mktemp /tmp/jbible_status_diagnostic.XXXXXXXX)"
trap 'rm -f "$OUT"' EXIT
python3 - "$OUT" <<'PY'
import json
import os
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone

out=Path(sys.argv[1])
base=Path("/opt/jbible/data/raw/jbible_fr88_integrated_v1")
batch=Path("/root/jbible_101_200.log")
watch=Path("/root/jbible_101_200_status.log")
importer=Path("/opt/jbible/importer")
envfile=importer/".env.status"

def log_info(path):
    if not path.is_file():
        return {"exists":False}
    st=path.stat()
    return {"exists":True,"bytes":st.st_size,
            "modified_utc":datetime.fromtimestamp(st.st_mtime,timezone.utc).isoformat()}

def lines_from(path):
    if not path.is_file():
        return []
    # Stream only a bounded local logfile; never publish its raw contents.
    with path.open("r",encoding="utf-8",errors="replace") as f:
        return f.readlines()[-1800:]

def last_match(lines,pattern):
    rx=re.compile(pattern)
    for line in reversed(lines):
        m=rx.search(line)
        if m:
            return m.groups() if m.groups() else True
    return None

def processes():
    categories={"batch_runner":[],"ocr_runner":[],"status_watcher":[]}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name)==os.getpid():
            continue
        try:
            raw=(entry/"cmdline").read_bytes().replace(b"\0",b" ").decode("utf-8","replace")
        except (OSError,PermissionError):
            continue
        if "diagnose_fr88_101_200" in raw:
            continue
        if "jbible_status_logwatch.py" in raw:
            categories["status_watcher"].append(int(entry.name))
        elif "fr88_integrated_page.py" in raw:
            categories["ocr_runner"].append(int(entry.name))
        elif "run_fr88_pages_101_200.sh" in raw or (
            "bash -s -- --start 31 --end 200" in raw):
            categories["batch_runner"].append(int(entry.name))
    return {k:{"count":len(v),"pids":sorted(v)[:8]} for k,v in categories.items()}

ocr_lines=lines_from(batch)
status_lines=lines_from(watch)
bundle_files=sorted(base.glob("image_0???.bundle.json")) if base.is_dir() else []
new_bundles=[]
new_stage_count=0
for page in range(101,201):
    if (base/("image_%04d.bundle.json"%page)).is_file():
        new_bundles.append(page)
    for task in ("header","verses_L","verses_R","margin_L","margin_R"):
        if (base/("image_%04d.%s.result.json"%(page,task))).is_file():
            new_stage_count+=1
try:
    progress=json.loads((base/"progress.json").read_text(encoding="utf-8"))
except (OSError,ValueError):
    progress=None

p=processes()
started=bool(last_match(ocr_lines,r"^JOB STARTED "))
done=bool(last_match(ocr_lines,r"^SUCCESS: PAGES 31\.\.200 COMPLETE"))
fatal=bool(last_match(ocr_lines,r"^(?:INTEGRATED OCR ERROR|ERROR:|INCOMPLETE:|Traceback)"))
if done:
    batch_state="completed"
elif p["batch_runner"]["count"] or p["ocr_runner"]["count"]:
    batch_state="running"
elif started or fatal or batch.is_file():
    batch_state="not_running"
else:
    batch_state="not_started_or_log_missing"

status_class="none"
for label,pattern in [
    ("missing_token",r"No TETRADA_STATUS_TOKEN|missing token"),
    ("missing_sdk_or_bridge",r"official SDK/bridge not installed|ModuleNotFoundError"),
    ("authorization_http_error",r"HTTP_(?:400|401|403)"),
    ("rate_limited",r"HTTP_429"),
    ("connection_problem",r"CONNECTION_ERROR"),
    ("watcher_locked",r"watcher for this range is already running"),
    ("python_exception",r"Traceback|Exception|Error:")]:
    if any(re.search(pattern,line,re.I) for line in status_lines):
        status_class=label
        break

latest_task=last_match(ocr_lines,r"^DEEPSEEK image_(\d{4})\.(header|verses_L|verses_R|margin_L|margin_R) call (\d+)")
latest_page=last_match(ocr_lines,r"^PAGE (\d+): (\d+) separate targets, (\d+) automatically accepted")
latest_pass=last_match(ocr_lines,r"^========== PASS (\d+) / (\d+)")
result={
  "schema":"jbible.fr88.batch-diagnostic.v1",
  "captured_utc":datetime.now(timezone.utc).isoformat(),
  "page_range":[101,200],
  "batch_state":batch_state,
  "processes":p,
  "log_files":{"ocr":log_info(batch),"status":log_info(watch)},
  "ocr_observations":{
     "job_start_seen":started,"job_success_seen":done,
     "fatal_marker_seen":fatal,
     "latest_pass":int(latest_pass[0]) if latest_pass else None,
     "latest_completed_page":int(latest_page[0]) if latest_page else None,
     "latest_deepseek_task":{"page":int(latest_task[0]),"kind":latest_task[1],
                             "call_number_in_pass":int(latest_task[2])} if latest_task else None,
     "api_budget_stop_count":sum("API BUDGET STOP" in x for x in ocr_lines),
     "published_pass_count":sum("PUBLISHED https://github.com/tetrada/jbible-ocr-share/" in x for x in ocr_lines),
     "regression_pass_count":sum(x.startswith("PASS:") for x in ocr_lines)
  },
  "checkpoints":{
     "new_page_bundles":len(new_bundles),
     "new_page_stages_cached":new_stage_count,
     "last_new_page":max(new_bundles) if new_bundles else None,
     "first_missing_new_page":next((i for i in range(101,201) if i not in new_bundles),None),
     "base_dir_exists":base.is_dir()
  },
  "progress_file":{
     "exists":progress is not None,
     "range":progress.get("pages") if progress else None,
     "pages_bundled":progress.get("pages_bundled") if progress else None,
     "pages_requested":progress.get("pages_requested") if progress else None,
     "new_paid_tasks_this_run":progress.get("new_paid_tasks_this_run") if progress else None
  },
  "status_integration":{
      "status_env_file_exists":envfile.is_file(),
      "status_sdk_file_exists":(importer/"status_sdk/tetrada_status.py").is_file(),
      "bridge_file_exists":(importer/"jbible_status_bridge.py").is_file(),
      "watcher_file_exists":(importer/"jbible_status_logwatch.py").is_file(),
      "watcher_error_category":status_class
  },
  "note":"Sanitized operational metadata only. No logs, credentials, raw OCR, image content, command-line arguments or environment variable values."
}

# Probe the existing *official* Status Engine SDK independently.
portal={"attempted":False,"success":False,"error_category":None}
if envfile.is_file():
    for line in envfile.read_text(encoding="utf-8").splitlines():
        line=line.strip()
        if line.startswith("export "):
            line=line[7:].strip()
        key,sep,value=line.partition("=")
        if sep and key.strip() in ("TETRADA_STATUS_URL","TETRADA_STATUS_TOKEN"):
            os.environ.setdefault(key.strip(),value.strip().strip("\"'"))
if os.environ.get("TETRADA_STATUS_TOKEN") and (importer/"status_sdk/tetrada_status.py").is_file():
    portal["attempted"]=True
    try:
        sys.path.insert(0,str(importer))
        from status_sdk.tetrada_status import StatusClient
        client=StatusClient(entity="jbible/importer/diagnostic_101_200",
                            name="FR88 101-200 Diagnostics",kind="job",
                            parent="jbible/importer",stale_after=2592000,
                            heartbeat_interval=0,timeout=4,strict=False)
        message="Batch "+batch_state+"; "+str(len(new_bundles))+"/100 cached; status watcher "+str(p["status_watcher"]["count"])
        response=client.publish(status="completed",
                 message=message,
                 widgets=[{"type":"metric","title":"Cached pages","metric":"processed"},
                          {"type":"metric","title":"OCR processes","metric":"ocr_processes"},
                          {"type":"events","title":"Diagnostic history"}],
                 metrics={"processed":len(new_bundles),"total":100,
                          "percent":len(new_bundles),
                          "ocr_processes":p["ocr_runner"]["count"],
                          "status_watchers":p["status_watcher"]["count"],
                          "github_progress_last_page":(progress.get("pages") or [None,None])[-1] if progress else None,
                          "batch_state":batch_state})
        portal["success"]=response is not None
        if portal["success"]:
            client.log(message,level="warning" if batch_state!="running" and not done else "info")
        else:
            err=client.last_error or ""
            m=re.search(r"HTTP Error (\d{3})",err)
            portal["error_category"]="HTTP_"+m.group(1) if m else ("transport_or_invalid_response" if err else "unknown")
    except Exception as exc:
        portal["error_category"]="SDK_"+type(exc).__name__
elif not envfile.is_file():
    portal["error_category"]="status_env_missing"
else:
    portal["error_category"]="status_sdk_or_token_missing"
result["status_portal_probe"]=portal
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("DIAGNOSTIC: batch=%s, new_cached_pages=%d/100, status_portal=%s"%
      (batch_state,len(new_bundles),"OK" if portal["success"] else portal["error_category"]),flush=True)
PY

# Reuse the project's working deploy key, checkout and publication lock.
# Never print untrusted OCR logs or token values; fail without touching checkout
# when an unrelated edit is pending.
REPO=/opt/jbible/ocr-share-git
DEST=fr88_integrated_v1/diagnostic_101_200.json
[[ -d "$REPO/.git" && -s /root/.ssh/jbible_ocr_share ]] || {
  echo "ERROR: existing Git checkout or deploy key missing; diagnostic saved only temporarily" >&2
  exit 2
}
export GIT_SSH_COMMAND='ssh -i /root/.ssh/jbible_ocr_share -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
(
  flock -x 9
  [[ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD)" == main ]] || {
    echo "ERROR: JBible Git checkout not on main" >&2; exit 3;
  }
  [[ -z "$(git -C "$REPO" status --porcelain --untracked-files=normal)" ]] || {
    echo "ERROR: unsynced local changes; not overwriting" >&2; exit 3;
  }
  git -C "$REPO" fetch --quiet origin main
  git -C "$REPO" merge --ff-only origin/main
  mkdir -p "$REPO/fr88_integrated_v1"
  cp "$OUT" "$REPO/$DEST"
  git -C "$REPO" add -- "$DEST"
  if ! git -C "$REPO" diff --cached --quiet; then
    git -C "$REPO" commit -m "Publish sanitized JBible 101-200 VPS status diagnostics" --quiet
    git -C "$REPO" push origin HEAD:main --quiet
  fi
  echo "DIAGNOSTIC PUBLISHED: https://github.com/tetrada/jbible-ocr-share/blob/main/$DEST"
) 9>/run/jbible-github-sync.lock
