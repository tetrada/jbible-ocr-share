#!/usr/bin/env python3
"""Offline regression for refreshing integrated exceptions without losing reviews."""
import importlib.util
import json
from pathlib import Path
import tempfile

spec=importlib.util.spec_from_file_location("sync","/usr/local/lib/jbible/sync_fr88_integrated_review_queue.py")
# Also usable from same GitHub tools directory during test installation.
if not Path(spec.origin).exists():
    spec=importlib.util.spec_from_file_location(
        "sync",str(Path(__file__).with_name("sync_fr88_integrated_review_queue.py")))
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def main():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        app=root/"review-web"
        app.mkdir()
        repo=root/"git"
        repo.mkdir()
        (app/"server.py").write_text("app=True\n")
        (app/"password").write_text("local-test-only\n")
        (app/"fr88_integrated_exception_review.py").write_text(
            "def cases_from_report(report):\n"
            "    return [edge for page in report['pages'] "
            "for edge in page.get('source_to_destination_edges',[]) "
            "if edge.get('status') == 'EXCEPTION']\n")
        original_reviews=app/"integrated_exception_decisions.json"
        original_reviews.write_text('{"reviews":{"historic":{"choice":"corrected"}}}')
        mod.APP=app
        mod.SRC=repo/"pilot_report.json"
        mod.DST=app/"integrated_report.json"
        sent=[]
        mod.portal_log=lambda message,pages,exceptions:sent.append((pages,exceptions))
        doc={"schema":mod.SCHEMA,"sql_writes":False,
             "progress":{"pages_bundled":2,"source_link_metrics":{"exceptions":1}},
             "pages":[{"image_page":31,"source_to_destination_edges":[]},
                      {"image_page":32,"source_to_destination_edges":[
                          {"status":"EXCEPTION","edge_id":"fr88i:p0032:L:001/target01"}]}]}
        mod.SRC.write_text(json.dumps(doc))
        assert mod.main()==0
        assert json.loads(mod.DST.read_text())==doc
        assert sent==[(2,1)]
        assert mod.main()==0
        assert sent==[(2,1)],"Should not republish an unchanged queue"
        assert "historic" in original_reviews.read_text()
        doc["progress"]["source_link_metrics"]["exceptions"]=99
        mod.SRC.write_text(json.dumps(doc))
        assert mod.main()!=0
        assert json.loads(mod.DST.read_text())["progress"]["source_link_metrics"]["exceptions"]==1
        assert "historic" in original_reviews.read_text()
    print("PASS: atomic queue sync, content-check, exception-count guard, and preserved human decisions")

if __name__=="__main__":
    main()
