#!/usr/bin/env python3
"""Fast offline tests for JBible status telemetry; no API, secrets or Docker."""
import importlib.util
from pathlib import Path

module=Path(__file__).with_name("jbible_status_logwatch.py")
spec=importlib.util.spec_from_file_location("jbible_status_logwatch",module)
impl=importlib.util.module_from_spec(spec)
spec.loader.exec_module(impl)

class Stub:
    def __init__(self):
        self.events=[]
        self.snapshots=[]
        self.terminal=None
    def event(self,message,level="info",details=None):
        self.events.append((message,level))
    def update(self,**data):
        self.snapshots.append(data)
    def finish(self,state,message):
        self.terminal=(state,message)

def test():
    status=Stub()
    monitor=impl.BatchLog(status,101,200)
    monitor.consume("========== PASS 1 / 5 (timestamp) ==========")
    monitor.consume("PREFLIGHT OK, 170 scanned pages; five separate visual tasks per page; no SQL")
    monitor.consume("PASS: tests have passed")
    monitor.consume("DEEPSEEK image_0101.header call 1")
    monitor.consume("DEEPSEEK image_0101.verses_L call 2")
    monitor.consume("PAGE 101: 8 separate targets, 7 automatically accepted (3 estimated), 1 genuinely unresolved; foo")
    monitor.consume("PROGRESS pages=71/170 (41.8%), 800 atomic destinations, 750 accepted (500 estimates), 16 exceptions")
    monitor.consume("API BUDGET STOP; safe to resume")
    monitor.consume("========== PUBLISH PASS 1 ==========")
    monitor.consume("PUBLISHED https://github.com/tetrada/jbible-ocr-share/blob/main/fr88_integrated_v1/pilot_report.json")
    monitor.consume("Authorization: Bearer SECRET_DO_NOT_LEAK")  # ignored
    assert status.terminal is None
    assert monitor.completed==1 and monitor.api_calls==2
    assert monitor.accepted==7 and monitor.exceptions==1 and monitor.estimated==3
    assert all("SECRET_DO_NOT_LEAK" not in e[0] for e in status.events)
    assert any("Publishing" in e[0] for e in status.events)
    monitor.consume("SUCCESS: PAGES 31..200 COMPLETE; NEW PAGES 101..200 PROCESSED.")
    assert status.terminal[0]=="completed"
    assert monitor.completed==100 and monitor.finished
    assert status.snapshots[-1]["processed"]==100

    failed=Stub()
    crash=impl.BatchLog(failed,101,200)
    crash.consume("Traceback (most recent call last):")
    assert crash.finished and failed.terminal[0]=="failed"
    assert all("Traceback" not in e[0] for e in failed.events)

    for line in ["ERROR: backend failed", "INTEGRATED OCR ERROR RuntimeError: test"]:
        failed=Stub()
        crash=impl.BatchLog(failed,101,200)
        crash.consume(line)
        assert crash.finished and failed.terminal[0]=="failed"
    print("PASS: TETRADA status receives scrubbed OCR stages, progress, publishing and completion; errors fail independently")

if __name__=="__main__":
    test()
