#!/usr/bin/env python3
"""Safely attach JBible review proxy only to status.tetrada.eu HTTPS Nginx server.
Idempotent; backup and nginx -t rollback. Python 3.6 compatible.
"""
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

INCLUDE = "include /etc/nginx/snippets/jbible-review-locations.conf;"
MARKER = "# jbible-review-web (managed, authenticated localhost backend)"


def server_blocks(text):
    # Works on conventional nginx conf: comments removed for discovery; brace
    # nesting tracks server blocks and their inner locations.
    starts = list(re.finditer(r"\bserver\s*\{", text))
    blocks = []
    for m in starts:
        start = m.start()
        opened = text.find("{", start)
        depth = 1
        pos = opened + 1
        quoted = False
        quote = None
        comment = False
        while pos < len(text) and depth:
            ch = text[pos]
            if comment:
                if ch == "\n": comment = False
                pos += 1
                continue
            if quoted:
                if ch == "\\":
                    pos += 2
                    continue
                if ch == quote:
                    quoted = False
                pos += 1
                continue
            if ch == "#":
                comment = True
            elif ch in ("'", '"'):
                quoted, quote = True, ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            pos += 1
        if depth == 0:
            blocks.append((start, opened, pos, text[start:pos]))
    return blocks


def select_site():
    files = []
    for folder in (Path("/etc/nginx/sites-enabled"), Path("/etc/nginx/conf.d")):
        if folder.is_dir():
            files += [x for x in folder.iterdir() if x.is_file() or x.is_symlink()]
    possibilities = []
    seen = set()
    for path in files:
        try:
            actual = path.resolve()
            if actual in seen or not actual.is_file():
                continue
            seen.add(actual)
            source = actual.read_text(encoding="utf-8")
        except OSError:
            continue
        for start, opened, end, block in server_blocks(source):
            # Ignore comment-only mentions.
            lines = "\n".join(line.split("#")[0] for line in block.splitlines())
            match = re.search(r"\bserver_name\s+([^;]+);", lines)
            listens = re.findall(r"\blisten\s+([^;]+);", lines)
            if (match and "status.tetrada.eu" in match.group(1).split() and
                    any(re.search(r"(?<!\d)443(?!\d)", x) for x in listens)):
                possibilities.append((actual, source, opened, end, block))
    return possibilities


def main():
    choices = select_site()
    if len(choices) != 1:
        print("NGINX CONFIGURATION SKIPPED: expected exactly one active HTTPS server")
        print("for status.tetrada.eu; found %d. Avoiding unsafe automatic edits." % len(choices))
        print("Add this inside the site's HTTPS 'server' block manually:")
        print("    " + INCLUDE)
        return 2
    path, source, opened, end, block = choices[0]
    if INCLUDE in block:
        print("Nginx HTTPS review location already installed in:", path)
        return 0
    backup = path.with_name(path.name + ".before_jbible_review_" +
                            datetime.utcnow().strftime("%Y%m%d%H%M%S"))
    shutil.copy2(str(path), str(backup))
    insert = "\n    " + MARKER + "\n    " + INCLUDE + "\n"
    updated = source[:opened + 1] + insert + source[opened + 1:]
    path.write_text(updated, encoding="utf-8")
    try:
        subprocess.check_call(["nginx", "-t"])
    except Exception:
        shutil.copy2(str(backup), str(path))
        print("NGINX TEST FAILED: original site configuration RESTORED.", file=sys.stderr)
        return 1
    print("NGINX SITE CONFIGURED:", path)
    print("Saved backup:", backup)
    print("Configured path: https://status.tetrada.eu/jbible-review/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
