"""Production check: the real web app (GitHub Pages) + production backend + the real extension, with a temporary account
holding fabricated data. Fills one live public Lever form and never submits it.

    python extension/e2e/prod_check.py --resume /path/to/synthetic.pdf

* registers a temporary account (the invite code is read from .env, never printed);
* fabricated profile from a synthetic resume, then a saved search over one employer's official Lever board,
  so a real job enters the account's feed the normal way;
* in Chromium with the extension: log in to the web app, create a connection code in Settings, connect the extension
  (backend address found automatically from config.json), open the live application form, Fill, check the fields,
  record "I didn't submit", then Disconnect from Settings and check the extension is cut off;
* every write request to the application platforms is blocked; the test fails if one is a submission.
Prints the temporary account's id so it can be deleted afterwards.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

EXT = Path(__file__).resolve().parents[1]
ROOT = EXT.parent
WEB = "https://yadava-krishna.github.io/Job_portal/"
BOARD = "https://jobs.lever.co/meesho"
JOB_URL = "https://jobs.lever.co/meesho/22c4a7a0-43be-439e-9473-2f8074b3e8d5"
results: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""), flush=True)


def env_value(key: str) -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", required=True)
    args = ap.parse_args()
    api_base = json.loads(httpx.get(WEB + "config.json", params={"t": time.time()}, timeout=20).text)["apiBaseUrl"]
    api = httpx.Client(base_url=api_base + "/api/v1", timeout=60, headers={"ngrok-skip-browser-warning": "true"})
    email = f"extension.check+{secrets.token_hex(3)}@example.com"
    password = "Tmp-" + secrets.token_urlsafe(12) + "9a"
    r = api.post("/auth/register", json={"email": email, "password": password, "full_name": "Test Candidate",
                                         "invite_code": env_value("REGISTRATION_INVITE_CODE") or None})
    r.raise_for_status()
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = api.get("/auth/me", headers=h).json()["id"]
    print(f"temporary account id={uid}")
    try:
        prof = api.post("/profile/resume", headers=h, files={"file": ("Test_Candidate_Resume.pdf", Path(args.resume).read_bytes(), "application/pdf")}).json()["parsed"]
        prof.update(full_name="Test Candidate", linkedin_url="https://www.linkedin.com/in/test-candidate-e2e")
        for e in prof["experience"][:1]:
            e["is_current"] = True
        api.put("/profile", headers=h, json=prof).raise_for_status()
        api.put("/profile/verified-facts", headers=h, json={"notice_period": "30 days", "expected_ctc": "9 LPA"}).raise_for_status()
        api.put("/preferences", headers=h, json={"job_titles": ["Business Finance"], "locations": ["Bangalore"], "min_match_score": 0}).raise_for_status()
        api.put("/notifications/preferences", headers=h, json={"new_matches": False}).raise_for_status()
        api.put("/platforms/preferences", headers=h, json={"platforms": [{"platform": "LinkedIn", "enabled": True,
                                                                          "discovery_sources": ["user_job_url"]}]}).raise_for_status()
        assert api.get("/onboarding", headers=h).json()["completed"], "onboarding not complete"
        api.post("/companies/watchlist", headers=h, json={"url": BOARD}).raise_for_status()
        sid = api.post("/saved-searches", headers=h, json={"name": "check", "schedule": "manual", "min_match_score": 0,
                                                           "criteria": {"keywords": ["Business Finance"], "locations": ["Bangalore"],
                                                                        "include_suggested": False, "sources": ["lever"]}}).json()["id"]
        run_id = api.post(f"/saved-searches/{sid}/run", headers=h).json()["id"]
        for _ in range(60):
            run = api.get(f"/jobs/runs/{run_id}", headers=h).json()
            if run["status"] != "running":
                break
            time.sleep(3)
        items = api.get("/jobs", headers=h, params={"page_size": 100}).json()["items"]
        target = next((i for i in items if i["job"]["job_url"] and i["job"]["job_url"].startswith(JOB_URL)), None)
        check("production discovery put the live Lever job into the temporary account's feed", target is not None,
              f"run {run['status']}, {len(items)} jobs")
        browser(email, password, api, h, target)
    finally:
        failed = [x for x in results if not x[1]]
        print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed. Delete temporary account id={uid} now.")


def browser(email, password, api, h, target):
    blocked, submissions = [], []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(prefix="jp-prod-"), channel="chromium", headless=True,
                                                   args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])

        def guard(route, request):
            host = request.url.split("/")[2]
            if request.method in ("GET", "HEAD", "OPTIONS") or host not in ("jobs.lever.co",) or "/cdn-cgi/challenge-platform/" in request.url:
                return route.continue_()
            path = request.url.split("?")[0]
            (submissions if re.search(r"/apply/?$", path) else blocked).append(f"{request.method} {path}")
            return route.abort()

        ctx.route("**/*", guard)
        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=15000)
        ext_id = sw.url.split("/")[2]

        web = ctx.new_page()
        web.goto(WEB + "#/login")
        web.get_by_label("Email").fill(email)
        web.get_by_label("Password").fill(password)
        web.get_by_role("button", name=re.compile("sign in|log in", re.I)).click()
        web.wait_for_url(re.compile(r"#/(dashboard|onboarding|discover)"), timeout=60000)
        web.goto(WEB + "#/settings?tab=extension")
        web.get_by_role("button", name="Create connection code").click()
        code = web.locator("div.font-mono").inner_text(timeout=30000).strip()
        check("web app Settings creates a connection code", bool(re.fullmatch(r"[0-9A-Z]{4}-[0-9A-Z]{4}", code)), code[:2] + "…")

        pop = ctx.new_page()
        pop.goto(f"chrome-extension://{ext_id}/src/popup/popup.html")
        pop.locator("input.code").fill(code)
        pop.get_by_role("button", name="Connect").click()
        pop.wait_for_function("() => !document.querySelector('input.code')", timeout=60000)
        check("extension connects to production (address found from config.json)", True)
        pop.close()

        form = ctx.new_page()
        form.goto(JOB_URL + "/apply", wait_until="domcontentloaded", timeout=60000)
        form.wait_for_timeout(4000)
        tab = sw.evaluate("(p) => chrome.tabs.query({}).then(ts => ts.find(t => (t.url||'').startsWith(p)).id)", JOB_URL)
        pop = ctx.new_page()
        pop.goto(f"chrome-extension://{ext_id}/src/popup/popup.html?tab={tab}")
        pop.locator("#app").get_by_text("Fill with JobPilot").first.wait_for(timeout=60000)
        check("live Lever form recognised as a job in the account", "In your JobPilot jobs" in pop.locator("#app").inner_text(),
              pop.locator("#app").inner_text()[:150])
        pop.get_by_role("button", name="Fill with JobPilot", exact=True).click()
        pop.locator("#app").get_by_text("filled ·").first.wait_for(timeout=90000)
        vals = form.evaluate("() => Object.fromEntries(['name','email','urls[LinkedIn]'].map(n => [n, document.querySelector(`[name=\"${n}\"]`)?.value]))")
        check("fields filled from the production profile", vals.get("name") == "Test Candidate" and vals.get("email") == "test.candidate@example.com"
              and vals.get("urls[LinkedIn]") == "https://www.linkedin.com/in/test-candidate-e2e", json.dumps(vals))
        apps = api.get("/applications", headers=h).json()
        app = next((a for a in apps if target and a["user_job_id"] == target["user_job_id"]), None)
        check("application is in progress, not applied", app is not None and app["status"] == "OPENED", str(app)[:120])
        pop.get_by_role("button", name="I didn't submit", exact=True).click()
        pop.locator("#app").get_by_text("not submitted").first.wait_for(timeout=30000)
        app = api.get(f"/applications/{app['id']}", headers=h).json() if app else None
        check("'I didn't submit' leaves it unapplied", app is not None and app["status"] == "PREPARED" and app["submitted_at"] is None)

        web.goto(WEB + "#/settings?tab=extension")
        web.reload()
        web.get_by_role("button", name=re.compile("Disconnect")).first.click()
        web.get_by_text("No browser is connected").wait_for(timeout=30000)
        pop.reload()
        pop.get_by_text("Connect to JobPilot").or_(pop.get_by_text("disconnected")).first.wait_for(timeout=60000)
        check("Disconnect in Settings cuts the extension off immediately", True)
        check("no application was submitted", not submissions, "; ".join(submissions))
        print("other blocked writes:", blocked or "none")
        ctx.close()


if __name__ == "__main__":
    main()
