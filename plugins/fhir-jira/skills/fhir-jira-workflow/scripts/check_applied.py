#!/usr/bin/env python3
"""Collect evidence that a resolved FHIR JIRA ticket is applied in a build.

For one ticket, this script:
  1. reads the cached ticket JSON (fetch it first with fetch_ticket.py);
  2. determines the page(s) to inspect: --page values, otherwise the ticket's
     Related URL(s) mapped to the build (e.g. .../6.0.0-ballot5/medication.html
     -> medication.html);
  3. fetches each page from the chosen build and extracts:
       - the section at the page's #anchor (e.g. an element on a -definitions page),
       - every --expect snippet (found / not found),
       - the ticket's release-note entry ("FHIR-NNNN") on the resource page;
  4. writes a Markdown evidence report and prints it;
  5. optionally opens one browser window: the JIRA ticket, the inspected pages and
     the file diff of each PR given with --pr.

The verdict (applied / not applied / unclear) is NOT decided here: the agent
reads the report against the resolution and gives an opinion, which the user
reviews.

Build sources (--source):
  master          https://build.fhir.org/                 (CI build of master; merged changes)
  branch:<name>   https://build.fhir.org/branches/<name>/ (CI build of a branch, when it exists)
  local[:<dir>]   local generated site (default: publish/ for FHIR Core, output/ for IGs)
  auto (default)  master, plus local publish/ when it exists

Usage:
  check_applied.py --ticket-json .jira-cache/FHIR-54447.json \
     --page medicationrequest-definitions.html#MedicationRequest.basedOn \
     --expect "should be used" --source auto --open --out .jira-cache/jira-check/FHIR-54447.md
"""
import argparse
import html as htmllib
import json
import os
import pathlib
import re
import sys
import urllib.request

BUILD = "https://build.fhir.org/"


def fetch(url_or_path):
    if url_or_path.startswith("http"):
        req = urllib.request.Request(url_or_path, headers={"User-Agent": "Mozilla/5.0 fhir-jira-check"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace"), None
        except Exception as e:  # noqa: BLE001
            return None, str(e)
    p = pathlib.Path(url_or_path)
    if not p.exists():
        return None, "file not found"
    return p.read_text(encoding="utf-8", errors="replace"), None


def to_text(h):
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</tr>|</h\d>|</div>", "\n", h)
    t = htmllib.unescape(re.sub(r"<[^>]+>", " ", h))
    t = re.sub(r"[ \t\xa0]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()


def section(h, anchor, size=2500):
    """Text of the part of the page starting at id/name=anchor."""
    if not anchor:
        return ""
    m = re.search(r'(?:id|name)="%s"' % re.escape(anchor), h)
    if not m:
        return "(anchor not found on the page)"
    start = h.rfind("<", 0, m.start())
    return to_text(h[start:start + size * 6])[:size]


def pages_from_ticket(t):
    out = []
    for u in re.findall(r"https?://\S+", t.get("fields", {}).get("Related URL", "")):
        u = u.rstrip(".,;)")
        m = re.search(r"hl7\.org/fhir/(?:[^/]+/)?([^/#?]+\.html)(#\S+)?$", u)
        if m:
            spec = m.group(1) + (m.group(2) or "")
            if spec not in out:
                out.append(spec)
    return out


def resource_page(page):
    name = page.split("#")[0]
    return re.sub(r"-(definitions|examples|search|mappings|profiles|operations)\.html$", ".html", name)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ticket-json", required=True)
    ap.add_argument("--page", action="append", default=[], help="page[#anchor] relative to the build root; repeatable")
    ap.add_argument("--expect", action="append", default=[], help="text expected on the page; repeatable")
    ap.add_argument("--absent", action="append", default=[], help="text that must no longer appear; repeatable")
    ap.add_argument("--source", default="auto", help="master | branch:<name> | local[:<dir>] | auto")
    ap.add_argument("--open", action="store_true", help="open JIRA and the inspected pages in a new browser window")
    ap.add_argument("--pr", action="append", default=[], help="number of the PR that applied the ticket; adds its file diff as a tab (repeatable)")
    ap.add_argument("--repo", default="HL7/fhir", help="GitHub org/repo of the PR(s) (default HL7/fhir)")
    ap.add_argument("--out", help="write the Markdown report here")
    a = ap.parse_args()

    t = json.load(open(a.ticket_json, encoding="utf-8"))
    key = t["key"]
    f = t.get("fields", {})
    rd = f.get("Resolution Description", "")
    rd = re.sub(r"^Hide\s+", "", rd)
    i = rd.find(" Show ")
    rd = (rd[:i] if i > 0 else rd).strip()

    pages = a.page or pages_from_ticket(t)
    if not pages:
        print("No page given and none derivable from Related URL; pass --page.", file=sys.stderr)
        return 2
    rp = resource_page(pages[0])
    if rp not in [p.split("#")[0] for p in pages]:
        pages.append(rp)

    sources = []
    s = a.source
    if s in ("auto", "master"):
        sources.append(("build.fhir.org (master)", BUILD))
    if s.startswith("branch:"):
        sources.append((f"build.fhir.org branch {s[7:]}", f"{BUILD}branches/{s[7:]}/"))
    if s.startswith("local") or (s == "auto" and pathlib.Path("publish").is_dir()):
        d = s.split(":", 1)[1] if s.startswith("local:") else ("publish" if pathlib.Path("publish").is_dir() else "output")
        sources.append((f"local {d}/", str(pathlib.Path(d).resolve()) + os.sep))

    lines = [f"# {key} – applied check", "",
             f"*Ticket:* https://jira.hl7.org/browse/{key} – {t.get('summary','')}",
             f"*Resolution:* {f.get('Resolution','')} – *Status:* {t.get('status') or f.get('Status','')}", "",
             "## Resolution", "", rd or "(no resolution description)", ""]
    urls = [f"https://jira.hl7.org/browse/{key}"]
    for label, base in sources:
        lines += [f"## Build: {label}", ""]
        for p in pages:
            name, _, anchor = p.partition("#")
            loc = base + name
            h, err = fetch(loc)
            shown = (pathlib.Path(loc).resolve().as_uri() if not loc.startswith("http") else loc) + (f"#{anchor}" if anchor else "")
            if label.startswith("build.fhir.org") or label.startswith("local"):
                urls.append(shown)
            lines.append(f"### {p}")
            lines.append(f"Location: {shown}")
            if h is None:
                lines += [f"**Not available:** {err}", ""]
                continue
            txt = to_text(h)
            lines.append(f"Release note '{key}' on this page: {'yes' if key in h else 'no'}")
            for e in a.expect:
                lines.append(f"Expected text {e!r}: {'FOUND' if e in txt else 'NOT FOUND'}")
            for e in a.absent:
                lines.append(f"Removed text {e!r}: {'still present' if e in txt else 'absent (ok)'}")
            sec = section(h, anchor)
            if sec:
                lines += ["", "Section excerpt:", "", "```", sec, "```"]
            lines.append("")
    for n in a.pr:
        diff = f"https://github.com/{a.repo}/pull/{n}/files"
        lines.insert(4, f"*PR:* {diff}")
        urls.append(diff)
    lines += ["## Verdict", "", "_To be filled in by the agent (applied / not applied / unclear, with reasons), subject to the user's final review._", ""]
    report = "\n".join(lines)
    if a.out:
        pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(a.out).write_text(report, encoding="utf-8")
    print(report)

    if a.open:
        here = pathlib.Path(__file__).resolve().parent
        sys.path.insert(0, str(here))
        from open_preview import launch  # noqa: E402
        seen = []
        for u in urls:
            if u not in seen:
                seen.append(u)
        used = launch(seen, "firefox") or launch(seen, "auto")
        print(f"\nOpened {len(seen)} tabs in a new {used} window." if used else "\nCould not open a browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
