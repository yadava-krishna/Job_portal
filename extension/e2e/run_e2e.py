"""End-to-end test of the real extension in Chromium against a throwaway local JobPilot backend.

    python extension/e2e/run_e2e.py --project-python .venv/bin/python [--live]

* Starts a local backend (SQLite in a temp dir, fabricated data, scheduler off) and seeds it (seed.py).
* Loads the unpacked extension into Playwright's Chromium and drives its real popup page.
* Offline mode (default): the three application pages are served at their real Greenhouse/Lever/Ashby addresses
  from the synthetic fixtures by request interception, so nothing leaves this machine.
* --live: additionally opens live public application forms (one per platform) and fills them with the fabricated
  test profile. Never submits: every POST/PUT to the platform is aborted and recorded, and the test fails if any
  submission request is attempted.
Requires `pip install playwright httpx` and `playwright install chromium` in the Python running this script.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import BrowserContext, Page, sync_playwright

EXT = Path(__file__).resolve().parents[1]
ROOT = EXT.parent
FIXTURES = EXT / "tests" / "fixtures" / "synthetic"
LIVE = {
    "greenhouse": "https://job-boards.greenhouse.io/gleanwork/jobs/4702832005",
    "lever": "https://jobs.lever.co/meesho/22c4a7a0-43be-439e-9473-2f8074b3e8d5/apply",
    "ashby": "https://jobs.ashbyhq.com/headout/742de92e-9068-480b-81fc-8e65dafbb135/application",
}
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def extension_id() -> str:
    import hashlib

    key = base64.b64decode(json.loads((EXT / "manifest.json").read_text())["key"])
    return "".join(chr(ord("a") + int(c, 16)) for c in hashlib.sha256(key).hexdigest()[:32])


def start_backend(py: str, tmp: Path, port: int, ext_id: str) -> subprocess.Popen:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp / 'e2e.db'}", "STORAGE_DIR": str(tmp / "storage"),
           "JWT_SECRET": secrets.token_hex(32), "CORS_ORIGINS": f"chrome-extension://{ext_id}", "SCHEDULER_ENABLED": "false",
           "DOCS_MODE": "off", "LLM_PROVIDER": "rule_based", "AUTH_RATE_LIMIT_PER_MINUTE": "1000", "ENVIRONMENT": "test"}
    env.pop("REGISTRATION_INVITE_CODE", None)
    proc = subprocess.Popen([py, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=open(tmp / "backend.log", "w"), stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=1).status_code == 200:
                return proc
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise SystemExit("backend did not start; see backend.log")


class Popup:
    """The extension's real popup page, opened as a tab and pointed at the tab under test."""

    def __init__(self, ctx: BrowserContext, ext_id: str, tab_id: int):
        self.page = ctx.new_page()
        self.page.goto(f"chrome-extension://{ext_id}/src/popup/popup.html?tab={tab_id}")

    def text(self) -> str:
        return self.page.locator("#app").inner_text()

    def click(self, name: str, timeout: float = 30000) -> None:
        self.page.get_by_role("button", name=name, exact=True).click(timeout=timeout)

    def wait_text(self, needle: str, timeout: float = 30000) -> None:
        self.page.locator("#app").get_by_text(needle, exact=False).first.wait_for(timeout=timeout)


def tab_id_of(ctx: BrowserContext, sw, url_prefix: str) -> int:
    return sw.evaluate("(p) => chrome.tabs.query({}).then(ts => ts.find(t => (t.url||'').startsWith(p)).id)", url_prefix)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-python", default=str(ROOT / ".venv" / "bin" / "python"))
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    ext_id = extension_id()
    tmp = Path(tempfile.mkdtemp(prefix="jobpilot-e2e-"))
    port = free_port()
    api = f"http://127.0.0.1:{port}"
    backend = start_backend(args.project_python, tmp, port, ext_id)
    try:
        subprocess.run([args.project_python, str(EXT / "e2e" / "seed.py"), api, str(tmp / "seed.json")], cwd=ROOT, check=True,
                       env={**os.environ, "DATABASE_URL": f"sqlite:///{tmp / 'e2e.db'}", "STORAGE_DIR": str(tmp / "storage"),
                            "JWT_SECRET": "unused-" + "x" * 40})
        seed = json.loads((tmp / "seed.json").read_text())
        c = httpx.Client(base_url=f"{api}/api/v1", timeout=30)
        jwt = c.post("/auth/login", json={"email": seed["email"], "password": seed["password"]}).json()["access_token"]
        H = {"Authorization": f"Bearer {jwt}"}
        run_browser(args, ext_id, api, c, H, seed, tmp)
    finally:
        backend.terminate()
        backend.wait(10)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    (tmp / "results.json").write_text(json.dumps(results, indent=1))
    sys.exit(1 if failed else 0)


def run_browser(args, ext_id, api, c, H, seed, tmp):
    submissions: list[str] = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(tmp / "profile"), channel="chromium", headless=not args.headed,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=15000)
        check("extension loads with the fixed ID (matches the backend CORS origin)", sw.url.startswith(f"chrome-extension://{ext_id}/"), sw.url)

        # Serve the synthetic forms at the platforms' real addresses; block every submission attempt.
        def serve(route, request):
            if request.method != "GET":
                submissions.append(f"{request.method} {request.url}")
                return route.abort()
            url = request.url
            name = "greenhouse" if "greenhouse.io" in url else "lever" if "lever.co" in url else "ashby"
            route.fulfill(status=200, content_type="text/html", body=(FIXTURES / f"{name}.html").read_text())

        for pattern in ("https://job-boards.greenhouse.io/jobpilote2e/**", "https://jobs.lever.co/jobpilot-e2e/**", "https://jobs.ashbyhq.com/jobpilot-e2e/**"):
            ctx.route(pattern, serve)

        # ---- connect -------------------------------------------------------------------------------
        setup = ctx.new_page()
        setup.goto(f"chrome-extension://{ext_id}/src/popup/popup.html")
        setup.evaluate("(u) => new Promise(r => chrome.runtime.sendMessage({action: 'setApiBase', args: {url: u}}, r))", api)
        setup.reload()
        setup.get_by_text("Connect to JobPilot").wait_for()
        check("popup asks for a connection code (never a password)", setup.locator("input[type=password]").count() == 0)
        bad = setup.locator("input.code")
        bad.fill("ZZZZ-ZZZZ")
        setup.get_by_role("button", name="Connect").click()
        setup.get_by_text("not valid or has expired").wait_for()
        check("a wrong code is rejected", True)
        code = c.post("/extension/pairing-codes", headers=H).json()["code"]
        setup.locator("input.code").fill(code)
        setup.get_by_role("button", name="Connect").click()
        setup.wait_for_function("() => !document.querySelector('input.code')", timeout=20000)
        devices = c.get("/extension/devices", headers=H).json()
        check("pairing creates one connected browser in Settings", len(devices) == 1, str(devices))
        storage = sw.evaluate("() => chrome.storage.local.get(null)")
        check("credential is not in chrome.storage (content scripts cannot reach it)", "jpx_" not in json.dumps(storage))
        setup.close()

        # ---- per platform (offline copies) ---------------------------------------------------------
        for ats in ("lever", "greenhouse", "ashby"):
            job = seed["jobs"][ats]
            page = ctx.new_page()
            page.goto(job["url"] + ("/apply" if ats == "lever" else "/application" if ats == "ashby" else ""))
            tab = tab_id_of(ctx, sw, job["url"])
            pop = Popup(ctx, ext_id, tab)
            pop.wait_text("Fill with JobPilot")
            check(f"{ats}: platform detected and job recognised as yours", "In your JobPilot jobs" in pop.text(), pop.text()[:200])
            if ats == "lever":
                pop.click("Attach my resume")
                pop.wait_text("Attached")
                name = page.evaluate("() => document.querySelector('input[type=file][name=resume]').files[0]?.name")
                check("lever: resume attached from JobPilot after an explicit click", name == "Test_Candidate_Resume.pdf", str(name))
            pop.click("Fill with JobPilot")
            pop.wait_text("filled ·")
            values = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('input[type=text],input[type=email],input[type=tel],input:not([type])')]
                                       .filter(e => e.value).map(e => [e.name || e.id, e.value]))""")
            expect = {"lever": {"name": "Test Candidate", "email": "test.candidate@example.com", "urls[LinkedIn]": "https://www.linkedin.com/in/test-candidate-e2e"},
                      "greenhouse": {"first_name": "Test", "last_name": "Candidate", "email": "test.candidate@example.com", "question_1002": "30 days"},
                      "ashby": {"_systemfield_name": "Test Candidate", "_systemfield_email": "test.candidate@example.com"}}[ats]
            check(f"{ats}: fields filled from the JobPilot profile", all(values.get(k) == v for k, v in expect.items()), json.dumps(values)[:300])
            panel = page.evaluate("() => !!document.querySelector('jobpilot-review')")
            check(f"{ats}: review panel shown on the page", panel)
            leaked = page.evaluate("""() => { const s = document.documentElement.outerHTML + JSON.stringify(localStorage) + JSON.stringify(sessionStorage)
                                      + Object.keys(window).join(','); return /jpx_/.test(s) || '__jobpilot' in window; }""")
            check(f"{ats}: nothing from the extension is visible to the page's own scripts", leaked is False)
            if ats == "lever":
                sens = page.evaluate("() => [...document.querySelectorAll('[name=\"cards[c1][field0]\"]')].some(e => e.checked)")
                check("lever: gender question left untouched", sens is False)
            # Tracking: in progress, never applied, until the user confirms.
            apps = c.get("/applications", headers=H).json()
            app = next((a for a in apps if a["user_job_id"] == job["user_job_id"]), None)
            check(f"{ats}: filling marks the application in progress, not applied", app and app["status"] == "OPENED", str(app)[:200])
            if ats == "greenhouse":
                pop.page.locator("input[aria-label='Reference ID']").fill("GH-E2E-1")
                pop.click("I submitted it")
                pop.wait_text("Recorded as applied")
                d = c.get(f"/applications/{app['id']}", headers=H).json()
                check("greenhouse: user confirmation records Applied once, from the extension",
                      d["status"] == "SUBMITTED" and d["confirmation_source"] == "extension_user_confirmed" and d["reference_id"] == "GH-E2E-1", str(d)[:200])
                pop.click("I submitted it")
                pop.wait_text("Already recorded")
                d2 = c.get(f"/applications/{app['id']}", headers=H).json()
                check("greenhouse: a second confirmation changes nothing",
                      d2["submitted_at"] == d["submitted_at"] and [e["event_type"] for e in d2["events"]].count("SUBMISSION_CONFIRMED") == 1)
            pop.page.close()
            page.close()
        check("offline: no submission request was ever sent", not submissions, "; ".join(submissions))

        # ---- revocation from JobPilot Settings ---------------------------------------------------
        dev = c.get("/extension/devices", headers=H).json()[0]
        c.delete(f"/extension/devices/{dev['id']}", headers=H)
        page = ctx.new_page()
        page.goto(seed["jobs"]["ashby"]["url"] + "/application")
        pop = Popup(ctx, ext_id, tab_id_of(ctx, sw, seed["jobs"]["ashby"]["url"]))
        pop.page.get_by_text("disconnected").or_(pop.page.get_by_text("Connect to JobPilot")).first.wait_for(timeout=20000)
        check("after Disconnect in Settings the extension can no longer read anything", "Fill with JobPilot" not in pop.text() or "Connect" in pop.text())
        pop.page.close(); page.close()

        if args.live:
            run_live(ctx, sw, ext_id, c, H, submissions)
        ctx.close()


def run_live(ctx, sw, ext_id, c, H, submissions):
    """Live public forms, fabricated profile, never submitted (all non-GET requests to the platform are aborted)."""
    code = c.post("/extension/pairing-codes", headers=H).json()["code"]
    setup = ctx.new_page()
    setup.goto(f"chrome-extension://{ext_id}/src/popup/popup.html")
    setup.locator("input.code").fill(code)
    setup.get_by_role("button", name="Connect").click()
    setup.wait_for_function("() => !document.querySelector('input.code')", timeout=20000)
    setup.close()
    blocked: list[str] = []
    submissions_live: list[str] = []
    APP_HOSTS = ("job-boards.greenhouse.io", "boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com")

    def guard(route, request):
        """Let pages load; block every write to the application hosts; flag anything that is an application submission."""
        url, method = request.url, request.method
        host = url.split("/")[2]
        if method in ("GET", "HEAD", "OPTIONS") or host not in APP_HOSTS:
            return route.continue_()
        body = request.post_data or "" if "graphql" in url else ""
        if "graphql" in url and "mutation" not in body:
            return route.continue_()  # Ashby loads the posting and form definition with GraphQL queries
        if "/cdn-cgi/challenge-platform/" in url:
            return route.continue_()  # Cloudflare bot check that Lever's page runs on load
        path = url.split("?")[0]
        is_submit = (re.search(r"jobs\.lever\.co/.+/apply/?$", path) is not None
                     or (("greenhouse.io" in host) and re.search(r"/(jobs/\d+|applications?)(/|$)", path) is not None)
                     or ("graphql" in url and re.search(r"submit", body, re.I) is not None))
        (submissions_live if is_submit else blocked).append(f"{method} {path}")
        return route.abort()

    ctx.route("**/*", guard)
    for ats, url in LIVE.items():
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        pop = Popup(ctx, ext_id, tab_id_of(ctx, sw, url.split("?")[0]))
        try:
            pop.wait_text("Fill with JobPilot", timeout=40000)
        except Exception:
            check(f"live {ats}: form detected", False, pop.text()[:200]); pop.page.close(); page.close(); continue
        check(f"live {ats}: form detected", True)
        if ats == "lever":
            pop.click("Attach my resume")
            pop.page.locator("#app").get_by_text("Attached").or_(pop.page.locator("#app").get_by_text("Download resume")).first.wait_for(timeout=30000)
            page.wait_for_timeout(5000)
            check("live lever: resume attachment handled", True, pop.text()[-200:])
        pop.click("Fill with JobPilot", timeout=60000)
        pop.wait_text("filled ·", timeout=90000)
        summary = pop.page.locator("#app strong").filter(has_text="filled ·").inner_text()
        filled = int(summary.split(" filled")[0])
        check(f"live {ats}: fields filled ({summary})", filled >= 2, summary)
        frame_vals = []
        for fr in page.frames:
            try:
                frame_vals += fr.evaluate("() => [...document.querySelectorAll('input')].map(e => e.value).filter(Boolean)")
            except Exception:
                pass
        check(f"live {ats}: test e-mail present in the form", "test.candidate@example.com" in frame_vals)
        page.screenshot(path=str(Path(tempfile.gettempdir()) / f"jobpilot-live-{ats}.png"), full_page=True)
        pop.page.close()
        page.close()
    check("live: no application submission request was ever made", not submissions_live, "; ".join(submissions_live[:5]))
    print("live: other writes to the application hosts that were blocked (uploads, autosave):", blocked or "none")


if __name__ == "__main__":
    main()
