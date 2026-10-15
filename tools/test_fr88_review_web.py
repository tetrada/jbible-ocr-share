#!/usr/bin/env python3
"""Offline secured review-web tests; no VPS files, Git access, API calls, or SQL."""
import base64
import json
import tempfile
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import fr88_review_web_server as web


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        web.APP = root / "web"
        web.STATE = root / "state" / "decisions.json"
        web.SCANS = root / "images"
        web.APP.mkdir()
        web.SCANS.mkdir()
        (web.APP / "index.html").write_text("<h1>JBible review</h1>", encoding="utf-8")
        (web.APP / "app.js").write_text("console.log('test');", encoding="utf-8")
        priority = {
            "schema":"jbible.fr88.v3.prioritized-review.v1",
            "counts":{"reference_or_segmentation_changes":1},
            "priorities":[{
                "case_id":"D013","page":37,"side":"R","issue":"bold chapter",
                "v2":[{"id":"old","raw_line":"2 P 25","y_fraction":0.4}],
                "v3":[{"id":"new","raw_line":"↗ 2 P 2 5","y_fraction":0.4}]
            }]
        }
        (web.APP / "priority.json").write_text(json.dumps(priority),encoding="utf-8")
        (web.SCANS / "image_0037.jpg").write_bytes(b"test jpg content")
        server=web.ThreadedServer(("127.0.0.1",0),web.Handler)
        server.password="a_strong_password_for_this_test_only"
        port=server.server_address[1]
        thread=threading.Thread(target=server.serve_forever)
        thread.daemon=True
        thread.start()
        root_url="http://127.0.0.1:%d/"%port
        auth="Basic "+base64.b64encode(
            ("reviewer:"+server.password).encode("utf-8")).decode("ascii")

        def request(path,method="GET",body=None,authorized=True,headers=None):
            all_headers=dict(headers or {})
            if authorized: all_headers["Authorization"]=auth
            payload=json.dumps(body).encode("utf-8") if body is not None else None
            q=Request(root_url+path,data=payload,headers=all_headers,method=method)
            try:
                with urlopen(q,timeout=5) as res:
                    return res.status,res.read()
            except HTTPError as err:
                return err.code,err.read()

        try:
            assert request("healthz",authorized=False)[0]==200
            assert request("api/cases",authorized=False)[0]==401
            code,data=request("api/cases")
            assert code==200 and len(json.loads(data)["priorities"])==1
            assert request("api/image/0037.jpg")[1]==b"test jpg content"
            assert request("api/image/0099.jpg")[0]==404
            payload={"case_id":"D013","choice":"v3",
                     "corrected_lines":["↗ 2 P 2 5"],
                     "notes":"Bold chapter 2, regular verse 5",
                     "verified_against_scan":True}
            headers={"Content-Type":"application/json","X-JBible-Review":"1"}
            assert request("api/review","POST",payload,True,{"Content-Type":"application/json"})[0]==403
            assert request("api/review","POST",payload,False,headers)[0]==401
            code,_=request("api/review","POST",payload,True,headers)
            assert code==200
            state=json.loads(web.STATE.read_text(encoding="utf-8"))
            assert state["reviews"]["D013"]["verification_status"]=="SCAN_CONFIRMED"
            bad=dict(payload)
            bad["case_id"]="D999"
            assert request("api/review","POST",bad,True,headers)[0]==400
            bad=dict(payload)
            bad["choice"]="uncertain"
            assert request("api/review","POST",bad,True,headers)[0]==400
            bad=dict(payload)
            bad["corrected_lines"]=[]
            assert request("api/review","POST",bad,True,headers)[0]==400
            assert len(json.loads(request("api/cases")[1])["reviews"])==1
            print("PASS: secured login, authenticated page, protected scans, verified save, invalid saves blocked")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__=="__main__":
    main()
