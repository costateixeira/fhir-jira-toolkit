#!/usr/bin/env python3
"""Open a pre-PR review window: the JIRA ticket, the generated page, and the diff.

Opens one new browser window with three tabs, in this order:
  1. the JIRA ticket (https://jira.hl7.org/browse/<KEY>)
  2. the locally generated page for the changed artifact (file:// URL into
     publish/ for FHIR Core or output/ for IGs), optionally with an #anchor
  3. the GitHub compare view for the pushed branch against the base branch

Usage:
  open_preview.py --ticket FHIR-54374 \
      --page publish/medicationdispense-definitions.html#MedicationDispense.partOf \
      --repo HL7/fhir --base master --branch fhir-54374-dispense-partof-comment

Use --page more than once to open several generated pages (each gets a tab
after the ticket). --browser chooses chrome, edge, firefox or auto (default).
The URLs are always printed, so they can be opened by hand if no browser is
found. Exit code 0 when a browser was launched, 3 when only the URLs were
printed.
"""
import argparse
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import webbrowser


def page_url(spec: str) -> str:
    """Turn 'path/file.html#anchor' into a file:// URL (http(s) URLs pass through)."""
    if spec.startswith(("http://", "https://", "file://")):
        return spec
    path, _, anchor = spec.partition("#")
    p = pathlib.Path(path).resolve()
    if not p.exists():
        print(f"warning: generated page not found: {p}", file=sys.stderr)
    url = p.as_uri()
    return url + ("#" + anchor if anchor else "")


def candidates(choice: str):
    system = platform.system()
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    win = {
        "chrome": [rf"{pf}\Google\Chrome\Application\chrome.exe", rf"{pf86}\Google\Chrome\Application\chrome.exe",
                   rf"{local}\Google\Chrome\Application\chrome.exe"],
        "edge": [rf"{pf86}\Microsoft\Edge\Application\msedge.exe", rf"{pf}\Microsoft\Edge\Application\msedge.exe"],
        "firefox": [rf"{pf}\Mozilla Firefox\firefox.exe", rf"{pf86}\Mozilla Firefox\firefox.exe"],
    }
    unix = {
        "chrome": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"],
        "edge": ["microsoft-edge", "microsoft-edge-stable"],
        "firefox": ["firefox"],
    }
    mac_apps = {"chrome": "Google Chrome", "edge": "Microsoft Edge", "firefox": "Firefox"}
    order = ["firefox", "chrome", "edge"] if choice == "auto" else [choice]
    for name in order:
        if system == "Windows":
            for exe in win[name]:
                if exe and os.path.exists(exe):
                    yield name, [exe]
        elif system == "Darwin":
            app = mac_apps[name]
            if os.path.exists(f"/Applications/{app}.app"):
                yield name, ["open", "-na", app, "--args"]
        else:
            for exe in unix[name]:
                found = shutil.which(exe)
                if found:
                    yield name, [found]


def launch(urls, choice):
    for name, cmd in candidates(choice):
        flag = "-new-window" if name == "firefox" else "--new-window"
        try:
            if name == "firefox":
                # Open the window first, then add each further URL as a tab once Firefox is up
                # (passing everything at once is unreliable when Firefox is not yet running).
                import time
                subprocess.Popen(cmd + [flag, urls[0]])
                time.sleep(3)
                for u in urls[1:]:
                    subprocess.Popen(cmd + ["-new-tab", u])
                    time.sleep(0.5)
            else:
                subprocess.Popen(cmd + [flag] + urls)
            return name
        except OSError:
            continue
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ticket", required=True, help="JIRA key, e.g. FHIR-12345")
    ap.add_argument("--page", action="append", default=[], help="generated page (path[#anchor] or URL); repeatable")
    ap.add_argument("--repo", required=True, help="GitHub org/repo, e.g. HL7/fhir")
    ap.add_argument("--base", required=True, help="base branch, e.g. master")
    ap.add_argument("--branch", required=True, help="pushed ticket branch")
    ap.add_argument("--browser", default="auto", choices=["auto", "chrome", "edge", "firefox"])
    a = ap.parse_args()

    urls = [f"https://jira.hl7.org/browse/{a.ticket}"]
    urls += [page_url(p) for p in a.page]
    urls.append(f"https://github.com/{a.repo}/compare/{a.base}...{a.branch}")

    print("Preview tabs:")
    for i, u in enumerate(urls, 1):
        print(f"  {i}. {u}")
    used = launch(urls, a.browser)
    if used:
        print(f"Opened in a new {used} window.")
        return 0
    # Last resort: default browser, one tab per URL (may not be a new window).
    try:
        webbrowser.open_new(urls[0])
        for u in urls[1:]:
            webbrowser.open_new_tab(u)
        print("No supported browser found; opened with the system default browser.")
        return 0
    except Exception:
        print("Could not launch a browser; open the URLs above by hand.", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
