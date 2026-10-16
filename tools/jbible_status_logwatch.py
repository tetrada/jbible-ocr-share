#!/usr/bin/env python3
"""Read JBible batch log and send sanitized operations to TETRADA Status Engine.

Non-intrusive: NEVER touches OCR inputs/checkpoints or SQL. Reuses existing
/opt/jbible/importer/jbible_status_bridge.py and official status_sdk.
Status delivery failures cannot stop the DeepSeek/import subprocess.
"""
import argparse
import fcntl
import os
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path("/opt/jbible/importer")
DEFAULT_LOG = Path("/root/jbible_101_200.log")
WIDGET_TOTAL = 100

def load_status_environment(filename=ROOT / ".env.status"):
    """Import only the two public SDK environment keys; never print secrets."""
    if not filename.is_file():
        return False
    for line in filename.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, sep, val = line.partition("=")
        if sep and key.strip() in ("TETRADA_STATUS_TOKEN", "TETRADA_STATUS_URL"):
            os.environ.setdefault(key.strip(), val.strip().strip("\"'"))
    return bool(os.getenv("TETRADA_STATUS_TOKEN", "").strip())

class BatchLog:
    """Deterministic semantic parser: no raw stderr, OCR text, or credentials posted."""
    def __init__(self, status, start=101, end=200):
        self.status = status
        self.start = start
        self.end = end
        self.total = end - start + 1
        self.finished = False
        self.completed = 0
        self.api_calls = 0
        self.accepted = 0
        self.exceptions = 0
        self.estimated = 0
        self.pass_no = 0
        self.errors = 0
        self.phase = "initializing"

    def update(self, message):
        self.status.update(message=message, phase=self.phase,
            current_page=self.start + self.completed - 1 if self.completed else None,
            processed=self.completed, total=self.total,
            remaining=self.total-self.completed,
            percent=round(100*self.completed/self.total, 2),
            api_calls=self.api_calls, valid_records=self.accepted,
            candidates=self.accepted+self.exceptions, errors=self.errors,
            exceptions=self.exceptions, estimated_links=self.estimated,
            batch_pass=self.pass_no)

    def record(self, text, level="info"):
        self.status.event(text,level=level)

    def consume(self, line):
        s=line.strip()
        if not s:
            return
        m=re.search(r"========== PASS (\d+) / (\d+)",s)
        if m:
            self.pass_no=int(m.group(1))
            self.phase="ocr"
            self.record("Started OCR pass %d/%s"%(self.pass_no,m.group(2)))
            self.update("Scanning pages %d-%d, pass %d"%
                        (self.start,self.end,self.pass_no))
            return
        m=re.match(r"^DEEPSEEK image_(\d{4})\.(header|verses_L|verses_R|margin_L|margin_R) call (\d+)$",s)
        if m:
            page,task=int(m.group(1)),m.group(2)
            self.api_calls+=1
            self.phase="ocr"
            self.record("Page %d: DeepSeek %s (operation %d)"%
                        (page,task,self.api_calls))
            self.update("DeepSeek %s, page %d"%(task,page))
            return
        m=re.match(r"^(PAGE|REBUILT PAGE) (\d+): (\d+) separate targets, (\d+) automatically accepted \((\d+) estimated\), (\d+) genuinely unresolved",s)
        if m:
            page,links,accepted,estimated,unresolved=map(int,m.groups()[1:])
            if self.start<=page<=self.end:
                self.completed=max(self.completed,page-self.start+1)
                self.accepted+=accepted
                self.estimated+=estimated
                self.exceptions+=unresolved
                self.record("Page %d complete: %d links, %d accepted, %d exceptions"%
                            (page,links,accepted,unresolved),
                            "warning" if unresolved else "success")
                self.update("Page %d complete"%page)
            return
        m=re.match(r"^PROGRESS pages=(\d+)/(\d+) \(([0-9.]+)%\), (\d+) atomic destinations, (\d+) accepted \((\d+) estimates\), (\d+) exceptions",s)
        if m:
            bundled=int(m.group(1))
            self.completed=max(self.completed,min(self.total,max(0,bundled-(self.start-31))))
            self.update("Cumulative OCR progress: %s/%s pages"%(m.group(1),m.group(2)))
            return
        if "API BUDGET STOP; safe to resume" in s:
            self.record("API call limit reached; continuing from cached checkpoints")
            return
        if "========== PUBLISH PASS" in s:
            self.phase="publishing"
            self.record("Publishing cumulative text-only report after pass %d"%self.pass_no)
            self.update("Publishing GitHub report")
            return
        if s.startswith("PUBLISHED https://github.com/tetrada/jbible-ocr-share/"):
            self.record("GitHub results published after pass %d"%self.pass_no,"success")
            return
        if s.startswith("PREFLIGHT OK"):
            self.record("Runner preflight passed")
            return
        if s.startswith("PASS:"):
            self.record("Regression suite checkpoint passed")
            return
        if "INTEGRATED OCR ERROR" in s or s.startswith(("ERROR:","INCOMPLETE:","Traceback")):
            self.errors+=1
            self.record("JBible batch error; see private VPS batch log","error")
            self.update("Batch error detected")
            if s.startswith(("INCOMPLETE:","ERROR:")):
                self.finish(False)
            return
        if s.startswith("SUCCESS: PAGES 31..200 COMPLETE"):
            self.completed=self.total
            self.finish(True)
            return
        if s.startswith("JOB STARTED"):
            self.record("JBible batch process started")
            self.update("Starting page batch")
            return
        if s.startswith("WARNING: Your kernel does not support swap limit"):
            return

    def finish(self, success):
        if self.finished:
            return
        self.finished=True
        self.phase="complete" if success else "failed"
        self.update("Batch completed" if success else "Batch failed")
        self.status.finish("completed" if success else "failed",
                           "JBible pages %d-%d %s: %d new pages processed; %d API operations observed"%
                           (self.start,self.end,"completed" if success else "failed",
                            self.completed,self.api_calls))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log",type=Path,default=DEFAULT_LOG)
    ap.add_argument("--start",type=int,default=101)
    ap.add_argument("--end",type=int,default=200)
    ap.add_argument("--idle-timeout",type=int,default=7200)
    args=ap.parse_args()
    lock=Path("/run/jbible-status-watch-%d-%d.lock"%(args.start,args.end))
    with lock.open("a+") as fd:
        try:
            fcntl.flock(fd.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print("[STATUS] A watcher for this range is already running",flush=True)
            return 0
        if not load_status_environment():
            print("[STATUS] No TETRADA_STATUS_TOKEN in .env.status; cannot publish.",flush=True)
            return 3
        sys.path.insert(0,str(ROOT))
        try:
            from jbible_status_bridge import AsyncStatus
        except (ImportError,ModuleNotFoundError) as exc:
            print("[STATUS] Existing official SDK/bridge not installed (%s)"%
                  type(exc).__name__,flush=True)
            return 3
        status=AsyncStatus(title="FR88 pages %d-%d"%(args.start,args.end),
            language="fr",book="Exodus and following",total=args.end-args.start+1,
            run_id="run_fr88_%d_%d_%s"%(args.start,args.end,uuid.uuid4().hex[:8]))
        watcher=BatchLog(status,args.start,args.end)
        watcher.record("Log watcher attached; tracking OCR, tests, publishing and errors")
        watcher.update("Watching JBible batch log")
        position=0
        buffer=""
        last_activity=time.monotonic()
        while not watcher.finished:
            try:
                with args.log.open("r",encoding="utf-8",errors="replace") as stream:
                    stream.seek(position)
                    chunk=stream.read()
                    position=stream.tell()
            except FileNotFoundError:
                chunk=""
            if chunk:
                last_activity=time.monotonic()
                buffer+=chunk
                while "\n" in buffer:
                    line,buffer=buffer.split("\n",1)
                    watcher.consume(line)
                    if watcher.finished:
                        break
            if not watcher.finished and time.monotonic()-last_activity>args.idle_timeout:
                watcher.errors+=1
                watcher.record("No output from batch log within idle timeout","error")
                watcher.finish(False)
                break
            time.sleep(1)
    return 0 if watcher.phase=="complete" else 1

if __name__=="__main__":
    raise SystemExit(main())
