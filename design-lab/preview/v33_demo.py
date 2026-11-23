"""V3.3 local walkthrough: the redesigned Portal Connections (cards, details, admin setup, guided import, Naukri
hand-off, preparing and tracking an application).

    .venv/bin/python design-lab/preview/v33_demo.py

Everything is local:
  * two throwaway backends on SQLite in a temp dir (never the production database or containers):
      "plain"  no portal credentials (a new server: LinkedIn/Indeed not configured), PUBLIC_APP_URL set;
      "sim"    LinkedIn/Indeed pointed at a SIMULATED sign-in server on 127.0.0.1 (OAUTH_DEV_ENDPOINTS, refused in
               production). Its pages, and every card using it, say SIMULATED.
  * the admin's "Test connection" really goes to https://www.linkedin.com/oauth/v2/authorization. The browser intercepts
    that request (the demo credentials are fake, so nothing is sent to LinkedIn) and the refusal LinkedIn would give an
    unapproved app is then played back to the callback page. That answer is SIMULATED and labelled so.
  * naukri.com pages are intercepted and replaced by a labelled stub.
No real LinkedIn, Indeed or Naukri account is used and no live sign-in is claimed. Output: design-lab/preview/v33/.
"""

from __future__ import annotations

import json
import os
import secrets
import signal
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from v32_demo import ROOT, SimulatedProvider, port, wait  # noqa: E402
from api_helpers import AR_JD, PASSWORD, onboard, register  # noqa: E402
from support import SYNTHETIC_RESUME_LINES, make_pdf  # noqa: E402

OUT = ROOT / "design-lab" / "preview" / "v33"
FRONT = 5197
NAUKRI_URL = "https://www.naukri.com/job-listings-accounts-receivable-analyst-acme-health-bengaluru-3-to-5-years-231125000777"
STUB = ("<!doctype html><title>{t}</title><body style='font:16px system-ui;margin:0'><div style='background:#b42318;color:#fff;padding:10px 16px;"
        "font-weight:700'>{banner}</div><div style='padding:32px;max-width:720px'>{body}</div>")
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)


def backend(tmp: Path, name: str, extra: dict) -> tuple[subprocess.Popen, str, Path]:
    bp, db = port(), tmp / f"{name}.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "STORAGE_DIR": str(tmp / name), "JWT_SECRET": secrets.token_hex(32),
           "CORS_ORIGINS": f"http://localhost:{FRONT}", "SCHEDULER_ENABLED": "false", "LLM_PROVIDER": "rule_based",
           "AUTH_RATE_LIMIT_PER_MINUTE": "1000", "ENVIRONMENT": "development", "DOCS_MODE": "off", "PUBLIC_APP_URL": f"http://localhost:{FRONT}", **extra}
    for k in ("REGISTRATION_INVITE_CODE", "LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "INDEED_CLIENT_ID", "INDEED_CLIENT_SECRET", "OAUTH_DEV_ENDPOINTS"):
        if k not in extra:
            env.pop(k, None)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(bp)], cwd=ROOT, env=env,
                            stdout=open(tmp / f"{name}.log", "w"), stderr=subprocess.STDOUT)
    return proc, f"http://127.0.0.1:{bp}", db


def account(api: str, tmp: Path, email: str, db: Path | None = None, *, admin: bool = False, onboarded: bool = True) -> dict:
    c = httpx.Client(base_url=api, timeout=120)
    if onboarded:
        onboard(c, email, make_pdf(tmp / f"{email}.pdf", SYNTHETIC_RESUME_LINES).read_bytes())
    else:
        register(c, email)
    if admin:
        with sqlite3.connect(db) as con:
            con.execute("update users set role='admin' where email=?", (email,))
    tok = c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()
    return {"api": api, "email": email, "h": {"Authorization": f"Bearer {tok['access_token']}"}}


def fresh_refresh(who: dict) -> str:
    """Refresh tokens rotate, so every browser context signs in on its own."""
    return httpx.post(f"{who['api']}/api/v1/auth/login", json={"email": who["email"], "password": PASSWORD}, timeout=60).json()["refresh_token"]


def main() -> None:
    (OUT / "video").mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="jobpilot-v33-demo-"))
    sim = SimulatedProvider()
    app_url = f"http://localhost:{FRONT}"
    from cryptography.fernet import Fernet

    plain, plain_api, plain_db = backend(tmp, "plain", {"ENCRYPTION_KEY": Fernet.generate_key().decode()})
    nokey, nokey_api, nokey_db = backend(tmp, "nokey", {})  # no ENCRYPTION_KEY: saving connector secrets must be off
    simb, sim_api, _ = backend(tmp, "sim", {
        "LINKEDIN_CLIENT_ID": "sim-linkedin-client", "LINKEDIN_CLIENT_SECRET": "sim-linkedin-secret",
        "INDEED_CLIENT_ID": "sim-indeed-client", "INDEED_CLIENT_SECRET": "sim-indeed-secret", "OAUTH_DEV_ENDPOINTS": json.dumps(sim.endpoints())})
    fe = subprocess.Popen(["npx", "vite", "--port", str(FRONT), "--strictPort"], cwd=ROOT / "frontend", stdout=open(tmp / "vite.log", "w"),
                          stderr=subprocess.STDOUT, start_new_session=True)
    try:
        for u in (f"{plain_api}/api/v1/health", f"{sim_api}/api/v1/health", f"{nokey_api}/api/v1/health", f"{app_url}/"):
            wait(u)
        cand = account(plain_api, tmp, "v33.candidate@example.com")
        admin = account(plain_api, tmp, "v33.admin@example.com", plain_db, admin=True)
        simc = account(sim_api, tmp, "v33.sim@example.com")
        nokey_admin = account(nokey_api, tmp, "v33.nokey.admin@example.com", nokey_db, admin=True)
        drive(app_url, plain_api, cand, admin, sim_api, simc, sim, nokey_api, nokey_admin)
    finally:
        nokey.terminate(); plain.terminate(); simb.terminate(); os.killpg(fe.pid, signal.SIGTERM); sim.server.shutdown()
    failed = [r for r in results if not r[1]]
    (OUT / "demo_results.json").write_text(json.dumps(results, indent=1))
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)


def context(br, api: str, who: dict, *, theme="light", viewport=(1440, 1000), video=False):
    kw = {"record_video_dir": str(OUT / "video"), "record_video_size": {"width": viewport[0], "height": viewport[1]}} if video else {}
    ctx = br.new_context(viewport={"width": viewport[0], "height": viewport[1]}, **kw)
    ctx.add_init_script(f"if (!localStorage.getItem('jobpilot.refreshToken')) {{ localStorage.setItem('jobpilot.apiBaseUrl','{api}');"
                        f"localStorage.setItem('jobpilot.refreshToken','{fresh_refresh(who)}'); }} localStorage.setItem('jobpilot.theme','{theme}');")
    ctx.route("https://www.naukri.com/**", lambda r: r.fulfill(status=200, content_type="text/html", body=STUB.format(
        t="SIMULATED Naukri page", banner="SIMULATED NAUKRI PAGE · intercepted in the test browser · nothing reached naukri.com",
        body="<h1>Accounts Receivable Analyst</h1><p>Acme Health · Bengaluru</p><p>On the real site you sign in yourself if asked, then press Apply.</p>")))
    ctx.route("https://www.linkedin.com/**", lambda r: r.fulfill(status=200, content_type="text/html", body=STUB.format(
        t="INTERCEPTED LinkedIn sign-in", banner="INTERCEPTED · the real LinkedIn sign-in page would load here · the demo's credentials are fake, so nothing was sent",
        body=f"<h1>LinkedIn authorization request</h1><p style='word-break:break-all;font:13px ui-monospace'>{r.request.url}</p>")))
    return ctx


def portals(pg, app_url: str):
    pg.goto(f"{app_url}/#/settings?tab=portals", timeout=120000)
    pg.get_by_test_id("portal-connections").wait_for(timeout=30000)
    pg.wait_for_timeout(900)


def escape(pg):
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(500)


def drive(app_url, plain_api, cand, admin, sim_api, simc, sim, nokey_api, nokey_admin) -> None:
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chromium")
        shot = lambda pg, name, full=False: pg.screenshot(path=str(OUT / f"{name}.png"), full_page=full)  # noqa: E731

        # ---- Candidate on a server with no portal credentials ---------------------------------------------------------
        ctx = context(br, plain_api, cand, video=True)
        pg = ctx.new_page()
        portals(pg, app_url)
        shot(pg, "q01_overview_candidate", True)
        order = pg.locator("[data-testid='portal-connections'] > li").evaluate_all("els => els.map(e => e.dataset.testid)")
        check("overview: three cards in order LinkedIn, Naukri, Indeed", order == ["portal-linkedin", "portal-naukri", "portal-indeed"], str(order))
        check("unconfigured: no Connect button for a candidate", pg.get_by_role("button", name="Connect with LinkedIn").count() == 0)
        check("unconfigured: candidate sees no setup controls", pg.get_by_role("button", name="Set up LinkedIn").count() == 0)
        li = pg.get_by_test_id("portal-linkedin")
        check("unconfigured: one plain reason, no setting names", li.get_by_text("admin needs to add").count() == 1 and "CLIENT_ID" not in li.inner_text())

        li.get_by_role("button", name="Capabilities & limitations").click()
        pg.get_by_test_id("portal-sheet").wait_for()
        pg.wait_for_timeout(700)
        shot(pg, "q02_capabilities_panel")
        sheet = pg.get_by_test_id("portal-sheet").inner_text()
        check("details: grouped Account / Discovery / Applications / Profile improvement",
              all(g in sheet.upper() for g in ("ACCOUNT", "DISCOVERY", "APPLICATIONS", "PROFILE IMPROVEMENT")))
        escape(pg)

        nk = pg.get_by_test_id("portal-naukri")
        with ctx.expect_page() as pop:
            nk.get_by_role("link", name="Open Naukri").click()
        page2 = pop.value
        page2.wait_for_load_state()
        check("Naukri: Open Naukri opens naukri.com in a new tab", page2.url == "https://www.naukri.com/", page2.url)
        page2.close()
        pg.bring_to_front()
        nk.get_by_test_id("naukri-return").wait_for()
        pg.wait_for_timeout(400)
        shot(pg, "q03_naukri_open_and_return_hint")
        check("Naukri: no Connect, and how to come back is explained", nk.get_by_role("button", name="Connect").count() == 0
              and "Copy its link" in nk.get_by_test_id("naukri-return").inner_text())

        nk.get_by_role("button", name="Import Naukri job").click()
        dlg = pg.get_by_test_id("guided-import")
        dlg.get_by_label("Job link").fill(NAUKRI_URL)
        dlg.get_by_role("button", name="Check link").click()
        dlg.get_by_test_id("link-recognised").wait_for(timeout=20000)
        pg.wait_for_timeout(400)
        shot(pg, "q04_import_link_recognised")
        check("import: the link is recognised as a Naukri job", "Naukri job 231125000777 recognised" in dlg.get_by_test_id("link-recognised").inner_text())
        dlg.get_by_role("button", name="Add details").click()
        dlg.get_by_label("Job title (required)").fill("Accounts Receivable Analyst")
        dlg.get_by_label("Company").fill("Acme Health")
        dlg.get_by_label("Location").fill("Bengaluru")
        dlg.get_by_label("Job description").fill(AR_JD)
        dlg.get_by_role("button", name="Review").click()
        pg.wait_for_timeout(300)
        shot(pg, "q05_import_review_before_saving")
        jobs_before = httpx.get(f"{plain_api}/api/v1/jobs", params={"view": "all"}, headers=cand["h"]).json()["total"]
        check("import: nothing saved before confirming", jobs_before == 0, str(jobs_before))
        dlg.get_by_role("button", name="Save & score").click()
        dlg.get_by_test_id("import-done").wait_for(timeout=60000)
        pg.wait_for_timeout(400)
        shot(pg, "q06_import_saved")
        check("import: saved through the existing import service", httpx.get(f"{plain_api}/api/v1/jobs", params={"view": "all"}, headers=cand["h"]).json()["total"] == 1)

        dlg.get_by_role("button", name="Prepare application").click()
        pg.get_by_test_id("ws-resume").wait_for(timeout=30000)
        pg.wait_for_timeout(1000)
        shot(pg, "q07_apply_workspace_resume_choice")
        check("apply: Open on Naukri waits for an explicit resume choice", pg.get_by_test_id("workspace-primary").is_disabled()
              and "Open on Naukri" in pg.get_by_test_id("workspace-primary").inner_text())
        pg.get_by_test_id("ws-resume-recommendation").get_by_role("button", name="Select it").click()
        pg.get_by_role("button", name="Use this resume").click()
        pg.get_by_text("Chosen by you").wait_for(timeout=20000)
        pg.wait_for_timeout(700)
        pg.get_by_test_id("workspace-primary").scroll_into_view_if_needed()
        shot(pg, "q08_resume_chosen_ready_to_open")
        with ctx.expect_page() as pop:
            pg.get_by_test_id("workspace-primary").click()
        naukri = pop.value
        naukri.wait_for_load_state()
        check("apply: the original Naukri listing opens", naukri.url == NAUKRI_URL, naukri.url)
        naukri.close()
        pg.bring_to_front()
        pg.evaluate("window.dispatchEvent(new Event('focus'))")
        pg.get_by_role("button", name="Yes, I submitted it").wait_for(timeout=20000)
        pg.get_by_role("button", name="Yes, I submitted it").click()
        pg.get_by_test_id("ws-done").wait_for(timeout=20000)
        pg.wait_for_timeout(800)
        shot(pg, "q09_outcome_recorded_user_reported")
        check("apply: recorded as user-reported, not verified", "not independently verified" in pg.get_by_test_id("ws-done").inner_text())
        pg.goto(f"{app_url}/#/applied")
        pg.wait_for_timeout(2500)
        shot(pg, "q10_tracked_in_applications")
        check("apply: tracked under Applications", "You told JobPilot" in pg.inner_text("main"))

        # A second Naukri job, added the same way through the API: the applied one has left the feed.
        r = httpx.post(f"{plain_api}/api/v1/jobs/import", headers=cand["h"], timeout=120, json={
            "url": NAUKRI_URL.replace("231125000777", "231125000778").replace("accounts-receivable-analyst", "credit-controller"),
            "title": "Credit Controller", "company": "Acme Health", "location": "Bengaluru", "description": AR_JD})
        check("second Naukri job imported", r.status_code == 201, r.text[:200])
        portals(pg, app_url)
        find = pg.get_by_test_id("find-jobs")
        find.scroll_into_view_if_needed()
        pg.wait_for_timeout(300)
        shot(pg, "q11_find_or_import_jobs")
        check("find jobs: Naukri listing count reflects the import", find.get_by_role("button", name="Naukri · 1").count() == 1)
        find.get_by_role("button", name="Set up the clipper").click()
        pg.get_by_text("Clip to JobPilot").wait_for()
        pg.wait_for_timeout(500)
        shot(pg, "q12_clipper_guidance")
        escape(pg)
        find.get_by_role("button", name="Connect your mailbox").click()
        pg.get_by_text("Job-alert emails").wait_for()
        pg.wait_for_timeout(500)
        shot(pg, "q13_alert_email_setup")
        escape(pg)
        find.get_by_role("button", name="Naukri · 1").click()
        pg.wait_for_url("**/discover**")
        pg.wait_for_timeout(2500)
        shot(pg, "q14_discover_filtered_to_naukri")
        check("browse: Discover opens filtered to Naukri", "Naukri" in pg.inner_text("main") and "Credit Controller" in pg.inner_text("main"))
        ctx.close()

        for name, theme, vp in (("q15_mobile_overview", "light", (390, 844)), ("q16_dark_overview", "dark", (1440, 1000))):
            c2 = context(br, plain_api, cand, theme=theme, viewport=vp)
            p2 = c2.new_page()
            portals(p2, app_url)
            p2.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            if vp[0] == 390:
                w = p2.evaluate("document.documentElement.scrollWidth")
                check("mobile: no horizontal scrolling at 390px", w <= 390, str(w))
            c2.close()

        # ---- Admin on the same server: guided setup --------------------------------------------------------------------
        actx = context(br, plain_api, admin)
        ap = actx.new_page()
        portals(ap, app_url)
        shot(ap, "q17_admin_overview", True)
        check("admin: Set up LinkedIn / Set up Indeed are the main actions", ap.get_by_role("button", name="Set up LinkedIn").count() == 1
              and ap.get_by_role("button", name="Set up Indeed").count() == 1)
        ap.get_by_role("button", name="Set up LinkedIn").click()
        st = ap.get_by_test_id("setup-sheet")
        st.get_by_test_id("callback-url").wait_for(timeout=20000)
        ap.wait_for_timeout(600)
        shot(ap, "q18_linkedin_setup_wizard")
        check("setup: callback URL read from the server's configuration", st.get_by_test_id("callback-url").input_value() == f"{app_url}/oauth-callback.html")
        check("setup: links to LinkedIn Developers and names the OIDC product",
              st.get_by_role("link", name="Open LinkedIn Developers").get_attribute("href") == "https://www.linkedin.com/developers/apps"
              and "Sign In with LinkedIn using OpenID Connect" in st.inner_text())
        check("setup: Test connection is off until credentials exist", st.get_by_role("button", name="Test connection").is_disabled())
        st.get_by_label("Client ID").fill("demo-not-a-real-client-id")
        st.get_by_label("Client Secret").fill("demo-not-a-real-secret")
        check("setup: the secret field is masked", st.get_by_label("Client Secret").get_attribute("type") == "password")
        st.get_by_role("button", name="Save credentials").click()
        st.locator("[data-testid=readiness][data-state=unverified]").wait_for(timeout=20000)
        ap.wait_for_timeout(500)
        shot(ap, "q19_credentials_saved_ready_to_test")
        raw = httpx.get(f"{plain_api}/api/v1/admin/portals", headers=admin["h"]).text
        check("setup: the secret never comes back from the API or into the page", "demo-not-a-real-secret" not in raw
              and "demo-not-a-real-secret" not in ap.content())
        check("setup: candidates can't read the setup", httpx.get(f"{plain_api}/api/v1/admin/portals", headers=cand["h"]).status_code == 403)

        st.get_by_role("button", name="Test connection").click()
        ap.wait_for_url("https://www.linkedin.com/oauth/v2/authorization**", timeout=20000)
        ap.wait_for_timeout(400)
        shot(ap, "q20_test_goes_to_real_linkedin_INTERCEPTED")
        q = parse_qs(urlsplit(ap.url).query)
        check("test: goes to the real LinkedIn authorization URL (not the simulator)", urlsplit(ap.url).hostname == "www.linkedin.com"
              and q["client_id"] == ["demo-not-a-real-client-id"] and q["redirect_uri"] == [f"{app_url}/oauth-callback.html"])
        # SIMULATED answer: what LinkedIn sends back for an app it hasn't approved.
        ap.goto(f"{app_url}/oauth-callback.html?error=unauthorized_client&state={q['state'][0]}")
        ap.locator("[data-testid=readiness][data-state=authorization_required]").wait_for(timeout=30000)
        ap.wait_for_timeout(600)
        shot(ap, "q21_test_result_refused_SIMULATED_ANSWER")
        check("test: the refusal is shown as the result and turns Connect off", "Connect is off for everyone" in ap.get_by_test_id("readiness").inner_text())
        check("test: the backend refuses Connect too", httpx.post(f"{plain_api}/api/v1/portals/linkedin/connect", headers=cand["h"]).status_code == 409)

        cctx = context(br, plain_api, cand)
        cp = cctx.new_page()
        portals(cp, app_url)
        cli = cp.get_by_test_id("portal-linkedin")
        shot(cp, "q22_candidate_sees_provider_authorization_required")
        check("candidate: Provider authorization required, still no Connect", cli.get_by_text("Provider authorization required").count() == 1
              and cli.get_by_role("button", name="Connect with LinkedIn").count() == 0)
        cctx.close()

        escape(ap)
        ap.get_by_role("button", name="Set up Indeed").click()
        ist = ap.get_by_test_id("setup-sheet")
        ist.get_by_test_id("scope-status").wait_for(timeout=20000)
        ap.wait_for_timeout(500)
        shot(ap, "q23_indeed_setup_guidance")
        check("Indeed: partner approval and Partner Console explained",
              "approval isn't automatic" in ist.inner_text() and ist.get_by_role("link", name="Open Indeed Partner Console docs").get_attribute("href")
              == "https://docs.indeed.com/getstarted/partner-console")
        escape(ap)
        ap.get_by_test_id("portal-linkedin").get_by_role("button", name="Review setup").click()
        ap.get_by_test_id("setup-sheet").get_by_role("button", name="Remove").click()
        ap.get_by_role("group", name="Remove credentials").get_by_role("button", name="Remove").click()
        ap.locator("[data-testid=readiness][data-state=missing_configuration]").wait_for(timeout=20000)
        check("setup: removing the credentials turns LinkedIn sign-in off again",
              httpx.get(f"{plain_api}/api/v1/portals", headers=cand["h"]).json()[0]["status"] == "not_configured")
        actx.close()

        # ---- A server without ENCRYPTION_KEY: saving connector secrets is off -------------------------------------------
        nctx = context(br, nokey_api, nokey_admin)
        npg = nctx.new_page()
        portals(npg, app_url)
        npg.get_by_role("button", name="Set up LinkedIn").click()
        nst = npg.get_by_test_id("setup-sheet")
        nst.get_by_test_id("secret-storage-off").wait_for(timeout=20000)
        nst.get_by_label("Client ID").fill("demo-not-a-real-client-id")
        nst.get_by_label("Client Secret").fill("demo-not-a-real-secret")
        npg.wait_for_timeout(400)
        nst.get_by_test_id("secret-storage-off").scroll_into_view_if_needed()
        shot(npg, "q30_no_encryption_key_saving_off")
        check("no ENCRYPTION_KEY: Save is disabled and the reason is shown", nst.get_by_role("button", name="Save credentials").is_disabled()
              and "ENCRYPTION_KEY" in nst.get_by_test_id("secret-storage-off").inner_text())
        r = httpx.put(f"{nokey_api}/api/v1/admin/portals/linkedin/credentials", headers=nokey_admin["h"], json={"client_id": "demo-client", "client_secret": "demo-secret"})
        check("no ENCRYPTION_KEY: the API refuses to store a secret", r.status_code == 409 and "demo-secret" not in r.text, str(r.status_code))
        check("no ENCRYPTION_KEY: the rest of JobPilot works", httpx.get(f"{nokey_api}/api/v1/jobs", headers=nokey_admin["h"]).status_code == 200)
        nctx.close()

        # ---- Candidate on the SIMULATED-provider server: connection flow ------------------------------------------------
        sctx = context(br, sim_api, simc)
        sp = sctx.new_page()
        portals(sp, app_url)
        sli = sp.get_by_test_id("portal-linkedin")
        shot(sp, "q24_ready_to_connect_SIMULATED")
        check("simulated: labelled on the chip and the button", sli.get_by_text("Ready to connect (simulated)").count() == 1
              and sli.get_by_role("button", name="Connect with LinkedIn (simulated)").count() == 1)
        sli.get_by_role("button", name="Connect with LinkedIn (simulated)").click()
        sp.wait_for_url(f"{sim.base}/linkedin/authorize**")
        shot(sp, "q25_consent_page_SIMULATED")
        sp.get_by_role("link", name="Allow").click()
        sli.get_by_test_id("identity-linkedin").wait_for(timeout=30000)
        sp.wait_for_timeout(1000)
        shot(sp, "q26_connected_SIMULATED")
        check("simulated: Connected (simulated) and 'not your LinkedIn account'", sli.get_by_text("Connected (simulated)").count() == 1
              and "not your LinkedIn account" in sli.get_by_test_id("simulated-linkedin").inner_text())
        sli.get_by_role("button", name="Manage connection").click()
        ps = sp.get_by_test_id("portal-sheet")
        ps.get_by_test_id("identity-linkedin").wait_for()
        sp.wait_for_timeout(600)
        shot(sp, "q27_manage_connection_SIMULATED")
        check("simulated: never 'verified by LinkedIn'", "verified by" not in ps.get_by_test_id("identity-linkedin").inner_text())
        ps.get_by_role("button", name="Disconnect").click()
        sp.get_by_role("group", name="Disconnect LinkedIn").get_by_role("button", name="Disconnect").click()
        escape(sp)
        sli.get_by_text("Ready to connect (simulated)").wait_for(timeout=20000)
        check("disconnect: the card updates once the backend confirms", sli.get_by_role("button", name="Connect with LinkedIn (simulated)").count() == 1)
        sctx.close()
        br.close()


if __name__ == "__main__":
    main()
