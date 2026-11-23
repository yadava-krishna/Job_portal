"""SmartRecruiters end to end, in Chromium with the real extension, against a SIMULATED SmartRecruiters page.

    python extension/e2e/run_sr_e2e.py [--project-python .venv/bin/python] [--out DIR] [--headed]

* SIMULATED: the live SmartRecruiters OneClick form sits behind a bot check for automated browsers (JobPilot does not
  bypass it), so the synthetic copy (tests/fixtures/synthetic/smartrecruiters.html) is served at the real
  jobs.smartrecruiters.com address by request interception. Nothing reaches SmartRecruiters; any POST/PUT is aborted
  and fails the test.
* A throwaway local JobPilot backend (SQLite in a temp dir, fabricated data) as in run_e2e.py.
* The extension is loaded from a temporary copy whose manifest also lists jobs.smartrecruiters.com in
  host_permissions: the stand-in for the user clicking "Allow Smart Apply on jobs.smartrecruiters.com" (Chrome's
  permission prompt can't be clicked by automation). Everything else is the shipped extension.
Checks detection (listing page → no form; form page → form), explicit resume choice and verified attachment,
autofill, the site's required-field validation, and the confirmation after the user's own Submit click.
Writes screenshots and a video to --out.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from run_e2e import EXT, FIXTURES, ROOT, Popup, check, extension_id, free_port, panel_click, panel_text, results, start_backend, tab_id_of  # noqa: E402

JOB = "https://jobs.smartrecruiters.com/FintechExample/744000000000001-data-analyst-payments-risk"
FORM = "https://jobs.smartrecruiters.com/oneclick-ui/company/FintechExample/publication/00000000-0000-4000-8000-000000000001"
LISTING = f"""<!doctype html><html><head><title>Data Analyst, Payments Risk</title></head><body><main>
<h1>Data Analyst, Payments Risk</h1><p>Fintech Example Co · Bengaluru · (SIMULATED SmartRecruiters listing)</p>
<a href="{FORM}" class="apply">I'm interested</a></main></body></html>"""

DEEP = """(sel) => { for (const h of document.querySelectorAll('*')) { const e = h.shadowRoot?.querySelector(sel); if (e) return e; } return null; }"""


def value(page, sel: str) -> str:
    return page.evaluate(f"(s) => ({DEEP})(s)?.value ?? null", sel)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-python", default=str(ROOT / ".venv" / "bin" / "python"))
    ap.add_argument("--out", default=str(ROOT / "design-lab" / "preview" / "v31"))
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    ext_id = extension_id()
    tmp = Path(tempfile.mkdtemp(prefix="jobpilot-sr-e2e-"))
    ext = tmp / "extension"
    shutil.copytree(EXT, ext, ignore=shutil.ignore_patterns("node_modules", "dist", "tests", "e2e"))
    man = json.loads((ext / "manifest.json").read_text())
    man["host_permissions"].append("https://jobs.smartrecruiters.com/*")  # = the user allowed this site
    (ext / "manifest.json").write_text(json.dumps(man, indent=2))

    port = free_port()
    api = f"http://127.0.0.1:{port}"
    backend = start_backend(args.project_python, tmp, port, ext_id)
    try:
        subprocess.run([args.project_python, str(EXT / "e2e" / "seed.py"), api, str(tmp / "seed.json")], cwd=ROOT, check=True,
                       env={"PATH": "/usr/bin:/bin", "DATABASE_URL": f"sqlite:///{tmp / 'e2e.db'}", "STORAGE_DIR": str(tmp / "storage"),
                            "JWT_SECRET": "unused-" + "x" * 40, "HOME": str(tmp)})
        seed = json.loads((tmp / "seed.json").read_text())
        c = httpx.Client(base_url=f"{api}/api/v1", timeout=30)
        H = {"Authorization": f"Bearer {c.post('/auth/login', json={'email': seed['email'], 'password': seed['password']}).json()['access_token']}"}
        run(ext, ext_id, api, c, H, seed, out, args.headed)
    finally:
        backend.terminate()
        backend.wait(10)
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed  (SIMULATED SmartRecruiters page)")
    (out / "sr_e2e_results.json").write_text(json.dumps(results, indent=1))
    sys.exit(1 if failed else 0)


def run(ext: Path, ext_id: str, api: str, c, H, seed, out: Path, headed: bool) -> None:
    posts: list[str] = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(ext.parent / "profile"), channel="chromium", headless=not headed, viewport={"width": 1280, "height": 860},
            record_video_dir=str(out / "video"), record_video_size={"width": 1280, "height": 860},
            args=[f"--disable-extensions-except={ext}", f"--load-extension={ext}"])
        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=15000)

        def serve(route, request):
            if request.method != "GET":
                posts.append(f"{request.method} {request.url}")
                return route.abort()
            body = (FIXTURES / "smartrecruiters.html").read_text() if "/oneclick-ui/" in request.url else LISTING
            route.fulfill(status=200, content_type="text/html", body=body)
        ctx.route("https://jobs.smartrecruiters.com/**", serve)

        setup = ctx.new_page()
        setup.goto(f"chrome-extension://{ext_id}/src/popup/popup.html")
        setup.evaluate("(u) => new Promise(r => chrome.runtime.sendMessage({action: 'setApiBase', args: {url: u}}, r))", api)
        setup.reload()
        setup.locator("input.code").fill(c.post("/extension/pairing-codes", headers=H).json()["code"])
        setup.get_by_role("button", name="Connect").click()
        setup.wait_for_function("() => !document.querySelector('input.code')", timeout=20000)
        setup.close()

        # 1. The listing (no form yet): an accurate message, not a false "form" and not a false "nothing here".
        page = ctx.new_page()
        page.goto(JOB)
        tab = tab_id_of(ctx, sw, "https://jobs.smartrecruiters.com/")
        pop = Popup(ctx, ext_id, tab)
        pop.wait_text("SmartRecruiters page")
        check("listing page: says no form yet and to click I'm interested", "I'm interested" in pop.text(), pop.text()[:200])
        pop.page.screenshot(path=str(out / "sr_1_listing_popup.png"))

        # 2. The user clicks I'm interested; the OneClick form (web components) loads; Check again finds it.
        page.get_by_text("I'm interested").click()
        page.wait_for_url("**/oneclick-ui/**")
        page.wait_for_timeout(500)
        pop.click("Check again")
        pop.wait_text("Fill with JobPilot")
        check("form page: the SmartRecruiters form is detected", "Data Analyst, Payments Risk" in pop.text(), pop.text()[:300])
        check("no resume is preselected: the user must choose", pop.page.locator("select[aria-label='Resume to attach']").input_value() == "")
        check("Attach is disabled until a resume is chosen", pop.page.get_by_role("button", name="Attach", exact=True).is_disabled())
        pop.page.screenshot(path=str(out / "sr_2_form_detected_popup.png"))

        # 3. Explicit choice, then attach: verified by reading the file input back.
        sel = pop.page.locator("select[aria-label='Resume to attach']")
        first = sel.locator("option:not([disabled])").first.get_attribute("value")
        sel.select_option(first)
        pop.click("Attach")
        pop.wait_text("Attached and checked on the form")
        files = page.evaluate(f"() => {{ const i = ({DEEP})('#resume-input'); return [...(i?.files || [])].map(f => [f.name, f.size]); }}")
        check("resume attached to the drop zone and read back", len(files) == 1 and files[0][1] > 1000, str(files))
        pop.page.screenshot(path=str(out / "sr_3_resume_attached_popup.png"))

        # 4. Fill.
        pop.click("Fill with JobPilot")
        pop.wait_text("filled", timeout=60000)
        check("first name filled", bool(value(page, "#first-name-input")))
        check("e-mail and its confirmation filled with the same address", "@" in (value(page, "#email-input") or "") and value(page, "#email-input") == value(page, "#confirm-email-input"),
              f"{value(page, '#email-input')} / {value(page, '#confirm-email-input')}")
        check("phone filled", bool(value(page, "#phone-number")))
        check("gender never answered", value(page, "#q3") == "")
        check("privacy consent never ticked", page.evaluate(f"() => ({DEEP})('#privacy').checked") is False)
        page.wait_for_timeout(800)
        page.screenshot(path=str(out / "sr_4_filled_with_panel.png"))
        panel_click(page, "Review")
        page.wait_for_timeout(500)
        check("review panel reports the form's empty Experience section", "Experience is empty on the form" in panel_text(page))
        page.screenshot(path=str(out / "sr_4b_review_panel.png"))

        # 5. The user submits too early: the site's own validation stops it; nothing is sent.
        page.locator("spl-button.submit button").click()
        page.wait_for_timeout(600)
        errs = page.evaluate("() => [...document.querySelectorAll('*')].map(e => e.shadowRoot).filter(Boolean).flatMap(r => [...r.querySelectorAll('.error-message')]).length")
        check("required fields still empty: the form shows its errors", errs >= 1, str(errs))
        page.screenshot(path=str(out / "sr_5_validation.png"))

        # 6. The user answers the rest and submits: SmartRecruiters' (simulated) thank-you page is the confirmation.
        page.evaluate(f"""() => {{ const d = {DEEP};
            const set = (s, v) => {{ const e = d(s); e.value = v; e.dispatchEvent(new Event('input', {{bubbles: true, composed: true}})); }};
            set('#q1', 'No'); if (!d('#q2').value) set('#q2', '30 days'); if (!d('#phone-number').value) set('#phone-number', '9845012345');
            if (!d('#last-name-input').value) set('#last-name-input', 'Candidate'); }}""")
        page.locator("#privacy").check()
        page.locator("spl-button.submit button").click()
        page.get_by_text("Thank you for applying!").wait_for(timeout=5000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(out / "sr_6_confirmed.png"))
        check("confirmation shown after the user's own submit click", "Thank you for applying" in page.inner_text("main"))
        check("nothing was sent to SmartRecruiters", posts == [], str(posts))
        ctx.close()


if __name__ == "__main__":
    main()
