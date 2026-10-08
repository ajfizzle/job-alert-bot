"""
Turns a Jobright jobs response that YOU saved from your own browser into the
company board names your alert script can read directly.

It does not contact Jobright or any other site; it only reads the file.

How to save a response (Chrome):
  1. On jobright.ai, open your Jobs page with your filters applied.
  2. Press F12 -> Network tab -> type "jobs" in the filter box.
  3. Click the request named like  jobs?refresh=true&sortCondition=...
  4. Open the Response tab, right-click the text -> "Copy response".
  5. Paste it into a text file, e.g. jobright.json. (Scroll the job list and
     repeat to add more; paste each response one after another in the same file.)

Then run:
    python jobright_boards.py jobright.json

The file contains your Jobright data, so don't share it publicly.
"""

import json
import re
import sys
from collections import defaultdict
from urllib.parse import parse_qs, urlparse

URL_RE = re.compile(r"https?://[^\s\"'<>\\)]+")

TITLE_KEYS = ("jobTitle", "title", "positionName", "jobName")
COMPANY_KEYS = ("companyName", "company", "companyDisplayName")


def classify(url):
    """Returns (system, board_name) for a job application link."""
    parts = urlparse(url)
    host = parts.netloc.lower()
    path = [p for p in parts.path.split("/") if p]
    query = parse_qs(parts.query)

    if host.endswith("greenhouse.io"):
        if query.get("for"):
            return "Greenhouse", query["for"][0].lower()
        if path and path[0].lower() not in ("embed", "v1"):
            return "Greenhouse", path[0].lower()

    if host == "jobs.ashbyhq.com" and path:
        return "Ashby", path[0].lower()

    if host == "jobs.lever.co" and path:
        return "Lever", path[0].lower()

    if "gh_jid" in query:
        return "Greenhouse (company website)", host

    return "Other", host


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def load_documents(text):
    """Parse one JSON document, or several pasted one after another."""
    decoder = json.JSONDecoder()
    docs, index = [], 0
    text = text.strip()
    while index < len(text):
        try:
            doc, end = decoder.raw_decode(text, index)
        except ValueError:
            next_brace = min(
                (i for i in (text.find("{", index + 1), text.find("[", index + 1)) if i != -1),
                default=-1,
            )
            if next_brace == -1:
                break
            index = next_brace
            continue
        docs.append(doc)
        index = end
        while index < len(text) and text[index].isspace():
            index += 1
    return docs


def first(record, keys):
    for key in keys:
        value = record.get(key)
        if value:
            return str(value)
    return ""


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python jobright_boards.py jobright.json")

    with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
        text = f.read()

    jobs = []  # (system, board, title, company, remote, published)
    for doc in load_documents(text):
        for record in walk(doc):
            link = record.get("applyLink") or record.get("originalUrl")
            if not link or not str(link).startswith("http"):
                continue
            system, board = classify(str(link))
            jobs.append((
                system, board,
                first(record, TITLE_KEYS), first(record, COMPANY_KEYS),
                record.get("isRemote"), str(record.get("publishTime") or "")[:10],
            ))

    # Safety net: links in the text that were not inside a recognisable job record.
    known = {(s, b) for s, b, *_ in jobs}
    for url in URL_RE.findall(text):
        system, board = classify(url)
        if system != "Other" and (system, board) not in known:
            jobs.append((system, board, "", "", None, ""))
            known.add((system, board))

    if not jobs:
        sys.exit("No job links found. Check that you copied the Response tab of the jobs request.")

    by_system = defaultdict(lambda: defaultdict(list))
    for system, board, title, company, remote, published in jobs:
        by_system[system][board].append((title, company, remote, published))

    print(f"Found {len(jobs)} job link(s).\n")

    for system in ("Greenhouse", "Ashby", "Lever"):
        boards = by_system.get(system)
        if not boards:
            continue
        print(f"=== {system} ===")
        for board, items in sorted(boards.items(), key=lambda kv: -len(kv[1])):
            print(f"  {board}  ({len(items)} job{'s' if len(items) != 1 else ''})")
            for title, company, remote, published in items[:4]:
                if title or published:
                    flag = {True: "remote", False: "not remote"}.get(remote, "")
                    print(f"      - {title or '(title not in file)'} | {flag} | {published}".rstrip(" |"))
        print()

    for system in ("Greenhouse (company website)", "Other"):
        boards = by_system.get(system)
        if boards:
            names = ", ".join(f"{b} ({len(v)})" for b, v in sorted(boards.items(), key=lambda kv: -len(kv[1]))[:15])
            print(f"=== {system} (cannot be read by your alert script) ===")
            print(f"  {names}\n")

    gh = sorted(by_system.get("Greenhouse", {}))
    ab = sorted(by_system.get("Ashby", {}))
    lv = sorted(by_system.get("Lever", {}))

    print("-" * 70)
    print("Paste into ats_job_alert.py (merge with your existing lists):")
    print(f"COMPANIES = {json.dumps(gh)}")
    print(f"ASHBY_BOARDS = {json.dumps(ab)}")
    if lv:
        print(f"LEVER_BOARDS = {json.dumps(lv)}")


if __name__ == "__main__":
    main()
