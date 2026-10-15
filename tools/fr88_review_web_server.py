#!/usr/bin/env python3
"""Private, local-only JBible FR88 visual verification service (Python >=3.6).
Only original scanned pages are served to authenticated users; never to Git.
"""
import argparse
import base64
import binascii
import hmac
import json
import os
import re
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import urlsplit

APP = Path("/opt/jbible/review-web")
STATE = Path("/var/lib/jbible-review/decisions.json")
SCANS = Path("/opt/jbible/data/raw/fr_bible_1988")
PASSFILE = Path("/opt/jbible/review-web/password")
LOCK = threading.Lock()
CHOICES = ("v2", "v3", "neither", "uncertain")
MAX_BODY = 16000


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_json(path, default):
    if not path.is_file():
        return default
    with path.open(encoding="utf-8") as fp:
        return json.load(fp)


def save_atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as fp:
        fp.write(json_bytes(value))
        fp.flush()
        os.fsync(fp.fileno())
    os.replace(str(tmp), str(path))


def validate_review(body, cases):
    if not isinstance(body, dict):
        raise ValueError("Invalid review document")
    cid = body.get("case_id")
    if not isinstance(cid, str) or cid not in cases:
        raise ValueError("Unknown case ID")
    choice = body.get("choice")
    if choice not in CHOICES:
        raise ValueError("Choose V2, V3, Neither, or Unsure")
    verified = body.get("verified_against_scan")
    if type(verified) is not bool:
        raise ValueError("Specify whether you checked the scan")
    if verified and choice == "uncertain":
        raise ValueError("Cannot mark an uncertain reading confirmed")
    lines = body.get("corrected_lines")
    if not isinstance(lines, list) or len(lines) > 20 or any(
            not isinstance(s, str) or not s.strip() or len(s) > 250
            for s in lines):
        raise ValueError("Expected up to 20 nonblank reference lines")
    if choice == "uncertain":
        verified = False
    elif not lines:
        raise ValueError("Please enter the printed reference line(s)")
    notes = body.get("notes") or ""
    if not isinstance(notes, str) or len(notes) > 1600:
        raise ValueError("Notes are too long")
    return {
        "case_id": cid,
        "choice": choice,
        "corrected_lines": [s.strip() for s in lines],
        "verified_against_scan": verified,
        "verification_status": "SCAN_CONFIRMED" if verified else "PENDING",
        "notes": notes.strip(),
        "saved_at_utc": datetime.now(timezone.utc).isoformat()
    }


class ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    server_version = "JBibleReview/1"
    sys_version = ""

    def log_message(self, format, *args):
        # No raw credentials, query strings, or user-supplied body data.
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format % args))

    def send_data(self, body, ctype="application/json; charset=utf-8", status=200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, status=200):
        self.send_data(json_bytes(data), status=status)

    def authenticated(self):
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(authorization[6:].encode("ascii"),
                                       validate=True).decode("utf-8")
            username, supplied = decoded.split(":", 1)
        except (ValueError, UnicodeError, TypeError, binascii.Error):
            return False
        expected = self.server.password
        return username == "reviewer" and hmac.compare_digest(supplied, expected)

    def require_auth(self):
        if self.authenticated():
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="JBible scanned-reference review"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            self.send_json({"status": "ok"})
            return
        if not self.require_auth():
            return
        if path in ("/", "/index.html"):
            return self.file(APP / "index.html", "text/html; charset=utf-8")
        if path == "/app.js":
            return self.file(APP / "app.js", "text/javascript; charset=utf-8")
        if path == "/api/cases":
            data = read_json(APP / "priority.json", {})
            if data.get("schema") != "jbible.fr88.v3.prioritized-review.v1":
                return self.send_json({"error": "Invalid priority data"}, 500)
            state = read_json(STATE, {"reviews": {}})
            return self.send_json({
                "schema": data["schema"],
                "priorities": data.get("priorities", []),
                "counts": data.get("counts", {}),
                "reviews": state.get("reviews", {}),
                "source": "Scanned French 1988 Jerusalem Bible; user must visually confirm"
            })
        m = re.match(r"^/api/image/(\d{4})\.jpg$", path)
        if m:
            page = int(m.group(1))
            priority = read_json(APP / "priority.json", {})
            valid_pages = {int(c["page"]) for c in priority.get("priorities", [])}
            if page not in valid_pages:
                return self.send_json({"error": "Page not in review queue"}, 404)
            scan = SCANS / ("image_%04d.jpg" % page)
            if not scan.is_file():
                return self.send_json({"error": "Scan is missing or unreadable"}, 404)
            return self.file(scan, "image/jpeg")
        self.send_json({"error": "Not found"}, 404)

    def file(self, filepath, content_type):
        try:
            body = filepath.read_bytes()
        except OSError:
            return self.send_json({"error": "File cannot be read"}, 500)
        self.send_data(body, content_type)

    def do_POST(self):
        if urlsplit(self.path).path != "/api/review":
            return self.send_json({"error": "Not found"}, 404)
        if not self.require_auth():
            return
        if self.headers.get("X-JBible-Review") != "1":
            return self.send_json({"error": "Missing same-origin review header"}, 403)
        origin = self.headers.get("Origin", "")
        host = self.headers.get("Host", "").lower().split(":")[0]
        if origin and origin not in ("https://" + host,
                                    "http://localhost", "http://127.0.0.1"):
            return self.send_json({"error": "Invalid origin"}, 403)
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            return self.send_json({"error": "Expected application/json"}, 415)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= MAX_BODY:
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(size).decode("utf-8"))
            cases_doc = read_json(APP / "priority.json", {})
            cases = {c["case_id"]: c for c in cases_doc.get("priorities", [])}
            new_review = validate_review(data, cases)
            with LOCK:
                state = read_json(STATE, {"schema": "jbible.fr88.review.v1", "reviews": {}})
                state["schema"] = "jbible.fr88.review.v1"
                state.setdefault("reviews", {})
                state["reviews"][new_review["case_id"]] = new_review
                save_atomic(STATE, state)
            self.send_json({"ok": True, "review": new_review})
        except (ValueError, UnicodeError, TypeError) as exc:
            self.send_json({"error": str(exc)}, 400)
        except (OSError, KeyError) as exc:
            self.send_json({"error": "Unable to save review"}, 500)


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--host", default="127.0.0.1")
    cli.add_argument("--port", type=int, default=8765)
    args = cli.parse_args()
    if args.host != "127.0.0.1":
        cli.error("For safety, bind only to 127.0.0.1 behind the HTTPS Nginx proxy.")
    if not (APP / "priority.json").is_file():
        cli.error("Missing priority.json")
    if not PASSFILE.is_file():
        cli.error("Missing locally stored password")
    password = PASSFILE.read_text(encoding="utf-8").strip()
    if len(password) < 20:
        cli.error("Review password is too short")
    server = ThreadedServer((args.host, args.port), Handler)
    server.password = password
    print("JBible review ready on 127.0.0.1:%s (authenticated)" % args.port, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
