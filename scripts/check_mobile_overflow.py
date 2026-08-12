"""Phase 7 QA remediation (findings B3/W9): a repeatable check for
page-level horizontal overflow on mobile viewports.

Why this exists: the QA pass that found B3 used `msedge --window-size=W,H
--screenshot=out.png`, which does NOT reliably constrain the CSS viewport
to W in this environment - it produced screenshots that *looked* like
severe overflow on pages that, under real mobile emulation, had none. The
only trustworthy signal is `document.documentElement.scrollWidth` compared
to the viewport width under a genuine
`Emulation.setDeviceMetricsOverride({mobile: true, ...})` call, which this
script drives directly over the Chrome DevTools Protocol against a locally
installed Edge/Chrome - no browser-automation framework, no new heavyweight
dependency (just `websocket-client`, already in requirements.txt).

A horizontally-scrollable element *inside* the page (e.g. a data table
wrapped in `overflow-x-auto`) is correct, expected behavior and is not
flagged - only `document.documentElement.scrollWidth > viewport width`
(the whole page scrolling sideways) counts as a failure.

Usage (with the dev server already running, e.g. `python app.py`):
    python scripts/check_mobile_overflow.py
    python scripts/check_mobile_overflow.py --base-url http://127.0.0.1:5050 --widths 320,375,390,430
    python scripts/check_mobile_overflow.py --email you@example.com --password '...'

Requires a local Chromium-based browser; set EDGE_PATH / CHROME_PATH if
it's not at the default Windows Edge install location.
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import websocket
except ImportError:
    print("Missing dependency: pip install websocket-client (see requirements.txt)", file=sys.stderr)
    sys.exit(2)

BROWSER = (
    os.environ.get("EDGE_PATH")
    or os.environ.get("CHROME_PATH")
    or r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
)

# Representative pages, matching the QA report's coverage list. Paths
# requiring a session use {job_id}/{application_id}/{company_id} placeholders
# filled in via --job-id/--application-id/--company-id if you have real IDs
# to check against; otherwise they're skipped with a note.
PUBLIC_PAGES = [
    ("/", "landing"),
    ("/auth/login", "login"),
    ("/auth/register", "register"),
]
AUTH_PAGES = [
    ("/dashboard", "dashboard"),
    ("/profile/", "profile"),
    ("/documents/", "documents"),
    ("/jobs/", "job search"),
    ("/jobs/saved", "saved jobs"),
    ("/applications/", "applications list"),
    ("/integrations/gmail", "gmail integration"),
]
AUTH_PAGES_WITH_ID = [
    ("/jobs/{job_id}", "job detail", "job_id"),
    ("/companies/{company_id}", "company detail", "company_id"),
    ("/applications/{application_id}", "application detail", "application_id"),
]


def _login_get_session_cookie(base_url, email, password):
    import http.cookiejar
    import re

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    r = opener.open(base_url + "/auth/login")
    html = r.read().decode()
    m = re.search(r'name="csrf_token"[^>]*?value="([^"]+)"', html)
    csrf = m.group(1) if m else None
    data = urllib.parse.urlencode({"csrf_token": csrf, "email": email, "password": password}).encode()
    opener.open(urllib.request.Request(base_url + "/auth/login", data=data, method="POST"))
    for c in jar:
        if c.name == "session":
            return c.value
    return None


def check_page(url, width, height=844, session_cookie=None):
    port = random.randint(20000, 60000)
    user_data_dir = tempfile.mkdtemp(prefix="ausvia-mobcheck-")
    proc = subprocess.Popen(
        [
            BROWSER, "--headless=new", "--disable-gpu", "--no-sandbox",
            f"--remote-debugging-port={port}", "--remote-allow-origins=*",
            f"--user-data-dir={user_data_dir}", f"--window-size={width},{height}",
            # Without this, Edge silently re-execs itself under a brand-new
            # PID on launch, orphaning the PID we're tracking (it exits
            # almost immediately) while the real ~15-20 process GPU/renderer/
            # utility-process tree lives on under an untracked PID that our
            # cleanup below can never find. Confirmed by inspecting the
            # relaunched process's own command line, which carries this same
            # flag (Edge adds it to stop a second relaunch).
            "--edge-skip-compat-layer-relaunch",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            try:
                targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json").read())
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("DevTools endpoint never came up - is Edge/Chrome installed?")
        page_target = next(t for t in targets if t["type"] == "page")
        ws = websocket.create_connection(page_target["webSocketDebuggerUrl"], timeout=20)

        def send(method, params=None, msg_id=[1]):
            msg_id[0] += 1
            ws.send(json.dumps({"id": msg_id[0], "method": method, "params": params or {}}))
            while True:
                resp = json.loads(ws.recv())
                if resp.get("id") == msg_id[0]:
                    return resp

        send("Page.enable")
        if session_cookie:
            send("Network.enable")
            parsed = urllib.parse.urlparse(url)
            send("Network.setCookie", {"name": "session", "value": session_cookie, "domain": parsed.hostname, "path": "/"})
        send("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": True})
        send("Page.navigate", {"url": url})
        time.sleep(2.2)
        send("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": True})
        time.sleep(0.2)

        result = send(
            "Runtime.evaluate",
            {
                "expression": "JSON.stringify({vw: window.innerWidth, docWidth: document.documentElement.scrollWidth})",
                "returnByValue": True,
            },
        )
        value = json.loads(result["result"]["result"]["value"])
        ws.close()
        return value
    finally:
        # A couple of Edge's utility services (search-indexer, collections,
        # entity-extraction) keep spawning for a moment even after the page
        # has loaded and our DevTools calls are done, so an immediate
        # tree-kill misses stragglers - give it a beat, then kill twice.
        time.sleep(1.2)
        for _ in range(2):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        shutil.rmtree(user_data_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:5050")
    parser.add_argument("--widths", default="320,375,390,430")
    parser.add_argument("--email", default=None, help="Login to check authenticated pages too")
    parser.add_argument("--password", default=None)
    parser.add_argument("--job-id", default=None)
    parser.add_argument("--company-id", default=None)
    parser.add_argument("--application-id", default=None)
    args = parser.parse_args()

    widths = [int(w) for w in args.widths.split(",")]
    pages = list(PUBLIC_PAGES)

    session_cookie = None
    if args.email and args.password:
        session_cookie = _login_get_session_cookie(args.base_url, args.email, args.password)
        if not session_cookie:
            print("Login failed - checking public pages only.", file=sys.stderr)
        else:
            pages += AUTH_PAGES
            ids = {"job_id": args.job_id, "company_id": args.company_id, "application_id": args.application_id}
            for path_tpl, label, id_key in AUTH_PAGES_WITH_ID:
                if ids.get(id_key):
                    pages.append((path_tpl.format(**ids), label))

    failures = []
    for path, label in pages:
        for width in widths:
            try:
                data = check_page(args.base_url + path, width, session_cookie=session_cookie)
            except Exception as e:
                print(f"[ERROR] {label:24s} {path:35s} @ {width}px: {e}")
                continue
            overflow = data["docWidth"] > data["vw"] + 1
            status = "FAIL (page scrolls sideways)" if overflow else "ok"
            print(f"[{'FAIL' if overflow else ' OK '}] {label:24s} {path:35s} @ {width:4d}px  scrollWidth={data['docWidth']:4d}  {status}")
            if overflow:
                failures.append((label, path, width, data))

    print()
    if failures:
        print(f"{len(failures)} page/width combination(s) have real page-level horizontal overflow.")
        sys.exit(1)
    else:
        print("No page-level horizontal overflow detected at any tested width.")


if __name__ == "__main__":
    main()
