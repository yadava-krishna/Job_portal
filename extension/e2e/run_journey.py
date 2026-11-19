"""Smart Apply journey: scenarios A-F in real Chromium with the real extension and the real JobPilot web app.

    .venv/bin/python extension/e2e/run_journey.py --out <dir> [--headed]

Everything runs on this machine, with fabricated data:
  * a throwaway backend (SQLite in a temp dir, scheduler off, outbound internet blocked by a dead proxy) seeded by
    seed_journey.py;
  * the built web app (frontend/dist) served at http://localhost:3080 (one of the extension's allowed origins) by
    request interception, with config.json pointing at the throwaway backend;
  * employer application forms served at their real Greenhouse/Lever/Ashby addresses from local fixtures; the
    "submission" is answered locally (thank-you page, validation error, or no confirmation) so no employer is ever
    contacted; LinkedIn is a local stub page;
  * any other request leaving the machine is aborted and recorded, and the run fails if one happens.
Produces screenshots and a video of the browser in --out.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_e2e import EXT, FIXTURES, ROOT, extension_id, free_port, panel_click, panel_text  # noqa: E402

DIST = ROOT / "frontend" / "dist"
APP = "http://localhost:3080"
results: list[tuple[str, bool, str]] = []
shots: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail[:300]})" if detail and not ok else ""), flush=True)
    return bool(ok)


def start_backend(py: str, tmp: Path, port: int, ext_id: str) -> subprocess.Popen:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp / 'journey.db'}", "STORAGE_DIR": str(tmp / "storage"),
           "JWT_SECRET": secrets.token_hex(32), "CORS_ORIGINS": f"chrome-extension://{ext_id},{APP}", "SCHEDULER_ENABLED": "false",
           "DOCS_MODE": "off", "LLM_PROVIDER": "rule_based", "AUTH_RATE_LIMIT_PER_MINUTE": "1000", "ENVIRONMENT": "test",
           # No outbound internet from the backend: public job-board look-ups fail fast and are reported as such.
           "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "NO_PROXY": "127.0.0.1,localhost"}
    env.pop("REGISTRATION_INVITE_CODE", None)
    proc = subprocess.Popen([py, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=open(tmp / "backend.log", "w"), stderr=subprocess.STDOUT)
    for _ in range(80):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=1).status_code == 200:
                return proc
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise SystemExit("backend did not start; see backend.log")


THANKS = "<html><body><main id='application_confirmation'><h1>Thank you for applying!</h1><p>Your application has been received.</p></main></body></html>"
NEUTRAL = "<html><body><main><h1>Northwind careers</h1><p>We're processing your request.</p></main></body></html>"
LINKEDIN_STUB = ("<html><head><title>LinkedIn (local test stub)</title></head><body style='font-family:sans-serif;padding:40px'>"
                 "<h1>LinkedIn job page: local test stub</h1><p>This page stands in for a LinkedIn listing. No LinkedIn server is "
                 "contacted by this test, and Smart Apply never runs on LinkedIn.</p><button>Easy Apply (you would apply here yourself)</button></body></html>")
EXTRA_ASHBY = ("<div data-field-path='q_excel'><label class='ashby-application-form-question-title' for='q_excel'>"
               "How many years of Excel experience do you have?</label><input id='q_excel' name='q_excel' type='text' required></div>")


ASHBY_POST = ("<script>document.querySelector('.ashby-application-form-submit-button').addEventListener('click', (e) => {"
              "e.preventDefault(); const f = document.createElement('form'); f.method = 'POST'; f.action = location.href;"
              "document.body.appendChild(f); f.submit(); });</script>")


class Sim:
    """The local stand-in for employer servers: what each submission returns, and every request we refused."""

    def __init__(self) -> None:
        self.posts: list[str] = []
        self.blocked: list[str] = []
        self.reply: dict[str, list[str]] = {}

    def employer(self, route, request):
        url = request.url
        if request.method != "GET":
            self.posts.append(f"{request.method} {url.split('?')[0]}")
            queue = self.reply.get(_key(url)) or []
            body = queue.pop(0) if queue else THANKS
            return route.fulfill(status=200, content_type="text/html", body=body)
        name = "greenhouse" if "greenhouse.io" in url else "lever" if "lever.co" in url else "ashby"
        html = (FIXTURES / f"{name}.html").read_text()
        if name == "greenhouse":  # real Greenhouse forms POST; the synthetic fixture has no method
            html = html.replace('<form id="application-form">', '<form id="application-form" method="POST">', 1)
        if name == "ashby":  # real Ashby posts with JavaScript; the stand-in posts the page back to itself
            html = html.replace("<button type=\"submit\"", EXTRA_ASHBY + "<button type=\"submit\"", 1) + ASHBY_POST
        route.fulfill(status=200, content_type="text/html", body=html)

    def web_app(self, route, request, api: str):
        path = re.sub(r"^https?://[^/]+", "", request.url).split("?")[0].split("#")[0]
        if path.endswith("/config.json"):
            return route.fulfill(status=200, content_type="application/json", body=json.dumps({"apiBaseUrl": api}))
        rel = path.lstrip("/") or "index.html"
        f = DIST / rel
        if not f.is_file():
            f = DIST / "index.html"
        route.fulfill(status=200, content_type=mimetypes.guess_type(str(f))[0] or "application/octet-stream", body=f.read_bytes())

    def guard(self, route, request):
        u = request.url
        if u.startswith(("chrome-extension://", "http://127.0.0.1", "data:", "blob:", "about:")):
            return route.continue_()
        self.blocked.append(f"{request.method} {u[:160]}")
        return route.abort()


def _key(url: str) -> str:
    return url.split("?")[0].rstrip("/")


def shot(page: Page, out: Path, name: str, full: bool = False) -> None:
    p = out / f"{len(shots) + 1:02d}-{name}.png"
    page.screenshot(path=str(p), full_page=full)
    shots.append(p.name)


def app_state(c: httpx.Client, H: dict, app_id: int) -> dict:
    return c.get(f"/applications/{app_id}", headers=H).json()


PUMP: list = []  # the web app page; waiting through it keeps Playwright's route handlers running


def wait_state(c, H, app_id, states, timeout=40) -> dict:
    deadline, st = time.time() + timeout, {}
    while time.time() < deadline:
        st = app_state(c, H, app_id)
        if st.get("apply_state") in states:
            return st
        # Never time.sleep here: the sync Playwright API serves routed requests (the extension's calls to the backend)
        # only while a Playwright call is in progress, so a plain sleep stalls them.
        PUMP[0].wait_for_timeout(500) if PUMP else time.sleep(0.5)
    return st


def open_workspace(page: Page, uj: int) -> None:
    page.goto(f"{APP}/#/discover")
    page.wait_for_timeout(300)
    page.goto(f"{APP}/#/discover?job={uj}")
    detail = page.get_by_role("dialog").filter(has=page.get_by_role("button", name=re.compile(r"^(Apply|Continue application)$")))
    detail.get_by_role("button", name=re.compile(r"^(Apply|Continue application)$")).first.click(timeout=30000)
    page.get_by_test_id("workspace-primary").or_(page.get_by_test_id("ws-done")).or_(page.get_by_test_id("ws-uncertain")).first.wait_for(timeout=30000)
    page.wait_for_timeout(900)


def return_to_app(page: Page) -> None:
    """The user switches back to the JobPilot tab (headless Chromium doesn't fire the window focus event by itself)."""
    page.bring_to_front()
    page.evaluate("() => window.dispatchEvent(new Event('focus'))")
    page.wait_for_timeout(1500)


def close_workspace(page: Page) -> None:
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)


def answer(page: Page, question: str, value: str, remember: bool = True) -> None:
    row = page.locator("li[data-testid^='ws-answer-']", has=page.get_by_text(question, exact=True)).first
    yes_no = row.get_by_role("button", name=value, exact=True)
    if value in ("Yes", "No") and yes_no.count():
        yes_no.click()
    elif row.locator("select").count():
        row.locator("select").select_option(label=value)
    else:
        row.locator("input:not([type=checkbox]), textarea").first.fill(value)
    box = row.locator("input[type=checkbox]")
    if box.count() and box.is_checked() != remember:
        box.click()


def autofill_from_workspace(ctx, page: Page) -> Page:
    with ctx.expect_page(timeout=20000) as opened:
        page.get_by_test_id("workspace-primary").click()
    form = opened.value
    form.wait_for_load_state()
    deadline = time.time() + 40
    while time.time() < deadline and "Review" not in panel_text(form):
        form.wait_for_timeout(500)
    form.wait_for_timeout(1500)
    return form


def review_and_submit(form: Page) -> bool:
    panel_click(form, "Review")
    for _ in range(8):
        if not panel_click(form, aria="I checked:", attr=("data-confirmed", "no")):
            break
    panel_click(form, "I have reviewed this application")
    form.wait_for_timeout(600)
    return panel_click(form, "Submit this application")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-python", default=str(ROOT / ".venv" / "bin" / "python"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--only", default="", help="debug: run only these scenarios, e.g. 'd' or 'ab'")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if not (DIST / "index.html").is_file():
        raise SystemExit("Build the web app first: cd frontend && npx vite build")
    ext_id = extension_id()
    tmp = Path(tempfile.mkdtemp(prefix="jobpilot-journey-"))
    port = free_port()
    api = f"http://127.0.0.1:{port}"
    proc = start_backend(args.project_python, tmp, port, ext_id)
    try:
        subprocess.run([args.project_python, str(EXT / "e2e" / "seed_journey.py"), api, str(tmp / "seed.json")], cwd=ROOT, check=True,
                       env={**os.environ, "DATABASE_URL": f"sqlite:///{tmp / 'journey.db'}", "STORAGE_DIR": str(tmp / "storage")})
        seed = json.loads((tmp / "seed.json").read_text())
        c = httpx.Client(base_url=api + "/api/v1", timeout=30)
        jwt = c.post("/auth/login", json={"email": seed["email"], "password": seed["password"]}).json()["access_token"]
        H = {"Authorization": f"Bearer {jwt}"}
        run(args, out, tmp, ext_id, api, c, H, seed)
    finally:
        proc.terminate()
        proc.wait(timeout=20)
    passed = sum(ok for _, ok, _ in results)
    (out / "results.json").write_text(json.dumps({"passed": passed, "total": len(results), "checks": results, "screenshots": shots}, indent=1))
    print(f"\n{passed}/{len(results)} checks passed")
    if passed == len(results):
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print(f"kept {tmp} for inspection (backend.log)")
    sys.exit(0 if passed == len(results) else 1)


def run(args, out: Path, tmp: Path, ext_id: str, api: str, c, H, seed) -> None:
    sim = Sim()
    J = seed["jobs"]
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(tmp / "profile"), channel="chromium", headless=not args.headed, viewport={"width": 1366, "height": 860},
            record_video_dir=str(out / "video"), record_video_size={"width": 1366, "height": 860},
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}",
                  # The web app page is served by interception (no real address), so Chromium would treat calls to the
                  # throwaway backend on 127.0.0.1 as "public -> local network" and block them. Test-only switch.
                  "--disable-features=LocalNetworkAccessChecks,PrivateNetworkAccessSendPreflights,PrivateNetworkAccessRespectPreflightResults,BlockInsecurePrivateNetworkRequests"])
        ctx.route("**/*", sim.guard)
        ctx.route(f"{APP}/**", lambda r, q: sim.web_app(r, q, api))
        for pattern in ("https://job-boards.greenhouse.io/jobpilote2e/**", "https://jobs.lever.co/jobpilot-e2e/**",
                        "https://jobs.ashbyhq.com/jobpilot-e2e/**", "https://jobs.lever.co/test/**"):
            ctx.route(pattern, sim.employer)
        ctx.route("https://www.linkedin.com/**", lambda r, q: r.fulfill(status=200, content_type="text/html", body=LINKEDIN_STUB))
        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=15000)
        if os.environ.get("JOURNEY_DEBUG"):
            ctx.on("console", lambda m: print("CONSOLE", m.text) if "DBG" in m.text else None)

        # ---- connect the extension (a one-time code; never a password) ---------------------------------
        setup = ctx.new_page()
        setup.goto(f"chrome-extension://{ext_id}/src/popup/popup.html")
        setup.evaluate("(u) => new Promise(r => chrome.runtime.sendMessage({action: 'setApiBase', args: {url: u}}, r))", api)
        setup.reload()
        code = c.post("/extension/pairing-codes", headers=H).json()["code"]
        setup.locator("input.code").fill(code)
        setup.get_by_role("button", name="Connect").click()
        setup.wait_for_function("() => !document.querySelector('input.code')", timeout=20000)
        check("extension connected with a one-time code", len(c.get("/extension/devices", headers=H).json()) == 1)
        setup.close()

        # ---- sign in to the web app ----------------------------------------------------------------------
        page = ctx.new_page()
        PUMP[:] = [page]
        page.goto(f"{APP}/#/login")
        try:
            page.locator("#email").wait_for(timeout=30000)
        except Exception:
            shot(page, out, "debug-login")
            (out / "debug-login.txt").write_text(page.content()[:4000])
            raise
        page.locator("#email").fill(seed["email"])
        page.locator("#password").fill(seed["password"])
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_url(re.compile(r"#/(?!login)"), timeout=30000)
        page.wait_for_timeout(1500)
        page.keyboard.press("Escape")

        try:
            only = args.only.lower()
            for name, fn in [("a", scenario_a), ("b", scenario_b), ("c", scenario_c), ("d", None), ("e", scenario_e), ("f", scenario_f)]:
                if only and name not in only:
                    continue
                if fn is None:
                    scenario_d(ctx, sw, page, out, c, H, J, sim)
                else:
                    fn(ctx, page, out, c, H, J, sim)
        except Exception:
            for i, pg in enumerate(ctx.pages):
                try:
                    pg.screenshot(path=str(out / f"debug-fail-{i}.png"))
                except Exception:  # noqa: BLE001
                    pass
            raise

        # Remembered answers in Settings.
        page.goto(f"{APP}/#/settings?tab=answers")
        page.get_by_text("Remembered answers").first.wait_for(timeout=20000)
        page.get_by_text("Remembered answers").first.scroll_into_view_if_needed()
        page.wait_for_timeout(800)
        shot(page, out, "settings-remembered-answers")
        mem = c.get("/answers/memory", headers=H).json()
        check("Settings: remembered answers listed, salary hidden until shown", any(m["key"] == "expected_ctc" and m["masked"] for m in mem),
              json.dumps([m["key"] for m in mem]))
        check("privacy: no request left this machine", not sim.blocked, "; ".join(sim.blocked[:8]))
        page.wait_for_timeout(800)
        ctx.close()
    vids = sorted((out / "video").glob("*.webm"), key=lambda f: f.stat().st_size, reverse=True)
    for i, v in enumerate(vids):
        v.rename(out / "video" / f"journey-{i + 1}.webm")


def app_id_for(c, H, uj: int) -> int:
    apps = c.get("/applications", headers=H).json()
    return next(a["id"] for a in apps if a["user_job_id"] == uj)


def scenario_a(ctx, page, out, c, H, J, sim):
    """New user: answers asked once, resume chosen, autofill, review, confirmed submission."""
    a = J["A"]
    open_workspace(page, a["user_job_id"])
    shot(page, out, "A-workspace-first-application")
    app_id = app_id_for(c, H, a["user_job_id"])
    pkg = c.get(f"/applications/{app_id}/package", headers=H).json()["package"]
    needs = [x["question"] for x in pkg["answers"] if x["status"] == "NEEDS_INPUT"]
    check("A: first application asks for the reusable answers it doesn't know", {"Notice period", "Expected CTC"} <= set(needs), str(needs))
    check("A: honest readiness (employer form not inspected before opening)", not pkg["readiness"]["form_inspected"], str(pkg["readiness"]))
    by_key = {(x["key"] or "").split(".")[0]: x["question"] for x in pkg["answers"]}
    for k, v in (("notice_period", "30 days"), ("current_ctc", "7 LPA"), ("expected_ctc", "9 LPA"), ("willing_to_relocate", "Yes"),
                 ("work_authorization", "Yes"), ("requires_sponsorship", "No")):
        answer(page, by_key[k], v)
    page.get_by_role("button", name="Save answers").click()
    page.get_by_text("remembered for future applications").first.wait_for(timeout=15000)
    page.wait_for_timeout(600)
    shot(page, out, "A-answers-saved")
    # Choose the second resume for this application.
    page.get_by_role("radio", name=re.compile("Resume - Finance roles|Test_Candidate_Finance")).first.click()
    page.get_by_role("button", name="Use this resume").click()
    page.wait_for_timeout(1200)
    pkg = c.get(f"/applications/{app_id}/package", headers=H).json()["package"]
    check("A: chosen resume kept for this application", pkg["resume"]["selected_by"] == "you" and "Finance" in (pkg["resume"]["name"] or ""), str(pkg["resume"]))
    shot(page, out, "A-resume-chosen")
    form = autofill_from_workspace(ctx, page)
    shot(form, out, "A-employer-form-filled")
    st = app_state(c, H, app_id)
    check("A: autofill tracked as in progress, never as applied", st["status"] == "OPENED" and st["apply_state"] in ("ready_for_review", "needs_information"), str(st.get("apply_state")))
    check("A: remembered notice period filled on the employer's form", form.locator("#question_1002").input_value() == "30 days",
          form.locator("#question_1002").input_value())
    check("A: gender question left for the user", form.locator("#gender").input_value() in ("", None))
    sim.posts.clear()
    clicked = review_and_submit(form)
    st = wait_state(c, H, app_id, ("submitted_confirmed", "submission_uncertain"))
    shot(form, out, "A-employer-confirmation")
    check("A: one authorised click, one submission", clicked and len(sim.posts) == 1, str(sim.posts))
    check("A: confirmed from the employer's page (high-confidence evidence)", st.get("apply_state") == "submitted_confirmed" and
          (st.get("confirmation") or {}).get("confidence") == "high", json.dumps({k: st.get(k) for k in ("status", "apply_state", "confirmation")}))
    check("A: the chosen resume was the one attached", "Finance" in (st.get("resume_used") or ""), str(st.get("resume_used")))
    form.close()
    return_to_app(page)
    done = page.get_by_test_id("ws-done")
    check("A: back in JobPilot, the workspace shows the confirmed submission", done.count() == 1 and "employer" in done.inner_text().lower(),
          done.inner_text()[:200] if done.count() else "no done state")
    shot(page, out, "A-workspace-confirmed")
    close_workspace(page)


def scenario_b(ctx, page, out, c, H, J, sim):
    """Returning user: remembered answers reused, nothing to type."""
    b = J["B"]
    open_workspace(page, b["user_job_id"])
    shot(page, out, "B-workspace-returning-user")
    app_id = app_id_for(c, H, b["user_job_id"])
    pkg = c.get(f"/applications/{app_id}/package", headers=H).json()["package"]
    by = {x["question"]: x for x in pkg["answers"]}
    check("B: remembered answers reused as verified", all(by[q]["status"] == "VERIFIED" and by[q]["source"] == "memory"
                                                         for q in ("Notice period", "Expected CTC", "Willing to relocate?")),
          json.dumps({q: (by[q]["status"], by[q]["source"]) for q in ("Notice period", "Expected CTC")}))
    check("B: nothing left to answer", pkg["readiness"]["needs_input"] == 0, str(pkg["readiness"]))
    form = autofill_from_workspace(ctx, page)
    shot(form, out, "B-lever-form-filled")
    sim.posts.clear()
    review_and_submit(form)
    st = wait_state(c, H, app_id, ("submitted_confirmed", "submission_uncertain"))
    check("B: submitted once and confirmed by the employer's page", st.get("apply_state") == "submitted_confirmed" and len(sim.posts) == 1,
          f"{st.get('apply_state')} {sim.posts}")
    form.close()
    return_to_app(page)
    close_workspace(page)


def scenario_c(ctx, page, out, c, H, J, sim):
    """Complex form: radios and ranges, a new required question learned on the page, a validation error, a fix."""
    cj = J["C"]
    open_workspace(page, cj["user_job_id"])
    app_id = app_id_for(c, H, cj["user_job_id"])
    form = autofill_from_workspace(ctx, page)
    shot(form, out, "C-ashby-filled-new-question")
    check("C: relocation radio answered from memory", form.locator("#r0").is_checked())
    check("C: unknown required question left empty (never invented)", form.locator("#q_excel").input_value() == "")
    form.locator("#q_excel").fill("5")
    form.wait_for_timeout(300)
    panel_click(form, "Re-check") or panel_click(form, "Review")
    form.wait_for_timeout(800)
    text = panel_text(form)
    check("C: panel offers to save the new answer", "Save answers for next time" in text and "Excel" in text, text[:400])
    panel_click(form, "Save selected")
    form.wait_for_timeout(1200)
    shot(form, out, "C-answer-saved-for-next-time")
    mem = {m["key"]: m for m in c.get("/answers/memory", headers=H).json()}
    check("C: the new answer was remembered only after Save selected", mem.get("experience_years.excel", {}).get("answer") == "5", json.dumps(list(mem)))
    # First submission: the employer's form reports a validation error.
    sim.reply[_key(cj["url"] + "/application")] = [(FIXTURES / "ashby.html").read_text().replace(
        '<div class="ashby-application-form-container">',
        '<div class="ashby-application-form-container"><div role="alert">Please enter a valid phone number.</div>', 1), THANKS]
    sim.posts.clear()
    review_and_submit(form)
    st = wait_state(c, H, app_id, ("needs_information", "submitted_confirmed", "submission_uncertain"), timeout=45)
    shot(form, out, "C-validation-error")
    check("C: a validation error from the employer is shown, not counted as applied", st.get("apply_state") in ("needs_information", "submission_uncertain")
          and st.get("status") != "SUBMITTED", str(st.get("apply_state")))
    form.close()
    return_to_app(page)
    close_workspace(page)
    # The user fixes it and submits again from a fresh form.
    open_workspace(page, cj["user_job_id"])
    form = autofill_from_workspace(ctx, page)
    form.locator("#q_excel").fill("5") if form.locator("#q_excel").input_value() == "" else None
    review_and_submit(form)
    st = wait_state(c, H, app_id, ("submitted_confirmed",), timeout=45)
    check("C: after the fix the submission is confirmed", st.get("apply_state") == "submitted_confirmed", str(st.get("apply_state")))
    form.close()
    return_to_app(page)
    close_workspace(page)


DUMP_SESSIONS = """() => new Promise((res) => { const r = indexedDB.open('jobpilot', 1); r.onsuccess = () => {
  const t = r.result.transaction('vault', 'readonly').objectStore('vault'); const out = {};
  const c = t.openCursor(); c.onsuccess = () => { const k = c.result; if (!k) { r.result.close(); res(JSON.stringify(out)); return; }
  if (String(k.key).startsWith('session:') || String(k.key).startsWith('handoff:')) out[k.key] = {state: k.value.state, app: k.value.applicationId, running: k.value.running}; k.continue(); }; }; })"""


def scenario_d(ctx, sw, page, out, c, H, J, sim):
    """Interrupted: the tab is closed mid-way, the application resumes safely and is submitted exactly once."""
    d = J["D"]
    open_workspace(page, d["user_job_id"])
    app_id = app_id_for(c, H, d["user_job_id"])
    form = autofill_from_workspace(ctx, page)
    sim.posts.clear()
    if os.environ.get("JOURNEY_DEBUG"):
        print("D sessions before close:", sw.evaluate(DUMP_SESSIONS))
    form.close()
    st = wait_state(c, H, app_id, ("interrupted",), timeout=20)
    if os.environ.get("JOURNEY_DEBUG"):
        print("D sessions after close:", sw.evaluate(DUMP_SESSIONS))
    check("D: closing the tab marks the application interrupted (not applied, not failed)", st.get("apply_state") == "interrupted" and st["status"] == "OPENED",
          str(st.get("apply_state")))
    return_to_app(page)
    close_workspace(page)
    open_workspace(page, d["user_job_id"])
    shot(page, out, "D-resume-application")
    head = page.get_by_role("dialog").last.inner_text()
    check("D: reopened workspace shows the interrupted state, not a cached one", "Interrupted" in head and "Employer page opened" not in head)
    check("D: workspace offers Resume application", "Resume application" in page.get_by_test_id("workspace-primary").inner_text())
    form = autofill_from_workspace(ctx, page)
    st = app_state(c, H, app_id)
    check("D: resuming refills and waits for review; nothing submitted", st.get("apply_state") in ("ready_for_review", "needs_information") and not sim.posts,
          f"{st.get('apply_state')} {sim.posts}")
    review_and_submit(form)
    st = wait_state(c, H, app_id, ("submitted_confirmed",))
    check("D: submitted exactly once after resuming", st.get("apply_state") == "submitted_confirmed" and len(sim.posts) == 1, str(sim.posts))
    form.close()
    return_to_app(page)
    r = c.post(f"/applications/{app_id}/handoff", headers=H, params={"smart": True})
    check("D: a submitted application can't be started again", r.status_code == 409, str(r.status_code))
    close_workspace(page)


def scenario_e(ctx, page, out, c, H, J, sim):
    """Submission uncertain: no confirmation after submitting; kept uncertain, never retried automatically."""
    e = J["E"]
    open_workspace(page, e["user_job_id"])
    app_id = app_id_for(c, H, e["user_job_id"])
    form = autofill_from_workspace(ctx, page)
    sim.reply[_key("https://jobs.lever.co/test/apply")] = [NEUTRAL]
    sim.posts.clear()
    review_and_submit(form)
    st = wait_state(c, H, app_id, ("submission_uncertain", "submitted_confirmed"), timeout=50)
    check("E: no confirmation seen -> submission uncertain", st.get("apply_state") == "submission_uncertain" and st["status"] == "CONFIRMATION_PENDING",
          str(st.get("apply_state")))
    form.wait_for_timeout(1500)
    check("E: not retried automatically", len(sim.posts) == 1, str(sim.posts))
    form.close()
    return_to_app(page)
    close_workspace(page)
    open_workspace(page, e["user_job_id"])
    shot(page, out, "E-submission-uncertain")
    check("E: workspace asks what happened, with no resubmit button", page.get_by_test_id("ws-uncertain").count() == 1 and
          page.get_by_role("button", name=re.compile("Review and autofill|Resume application")).count() == 0)
    close_workspace(page)


def scenario_f(ctx, page, out, c, H, J, sim):
    """Unsupported platform (LinkedIn): prepared answers to copy, native page opened, the user's own report recorded."""
    f = J["F"]
    open_workspace(page, f["user_job_id"])
    app_id = app_id_for(c, H, f["user_job_id"])
    pkg = c.get(f"/applications/{app_id}/package", headers=H).json()["package"]
    check("F: LinkedIn gets a native hand-off, no autofill", pkg["action"] == "open_native" and not pkg["capabilities"]["autofill"], pkg["action"])
    answer(page, "How many years of accounts receivable experience do you have?", "6")
    page.get_by_role("button", name="Save answers").click()
    page.wait_for_timeout(1500)
    shot(page, out, "F-linkedin-handoff-prepared", full=False)
    with ctx.expect_page(timeout=15000) as opened:
        page.get_by_test_id("workspace-primary").click()
    li = opened.value
    li.wait_for_load_state()
    li.wait_for_timeout(1200)
    shot(li, out, "F-linkedin-stub-opened")
    check("F: the extension never runs on LinkedIn", "Review" not in panel_text(li) and "JobPilot" not in panel_text(li))
    li.close()
    return_to_app(page)
    page.wait_for_timeout(800)
    st = app_state(c, H, app_id)
    check("F: opening LinkedIn is recorded as 'employer page opened', not applied", st["apply_state"] == "form_opened" and st["status"] == "OPENED",
          str(st.get("apply_state")))
    yes = page.get_by_role("button", name="Yes, I submitted it")
    if not yes.count():
        page.get_by_role("button", name=re.compile("I already applied|I applied")).first.click()
    page.locator("#ref").fill("LI-APP-2041")
    page.get_by_role("button", name="Yes, I submitted it").click()
    page.get_by_test_id("ws-done").wait_for(timeout=15000)
    page.wait_for_timeout(600)
    shot(page, out, "F-user-reported")
    st = app_state(c, H, app_id)
    check("F: recorded as the user's report, not as verified", st["status"] == "SUBMITTED" and st["apply_state"] == "user_reported", str(st.get("apply_state")))
    close_workspace(page)


if __name__ == "__main__":
    main()
