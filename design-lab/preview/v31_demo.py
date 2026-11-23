"""V3.1 local walkthrough: the real web app (Vite dev server) against a throwaway local backend with fabricated data.

    .venv/bin/python design-lab/preview/v31_demo.py

Starts the backend on SQLite in a temp dir (never the production database or containers), seeds one fabricated user
("Test Candidate"), a job, a Resume Studio version with the reported problems (a character that prints as a box, an
emoji, a weak bullet, a missing start date), and an application. Then drives Chromium through Resume Studio
(Check, Suggestions, accept a fix, re-check, preview) and the Apply window's resume choice, saving screenshots and a
video to design-lab/preview/v31/.
"""

from __future__ import annotations

import copy
import re
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "tests" / "api")]
from api_helpers import import_job, onboard  # noqa: E402
from support import SYNTHETIC_RESUME_LINES, make_pdf  # noqa: E402

OUT = ROOT / "design-lab" / "preview" / "v31"
FRONT = 5199


def port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait(url: str, n: int = 80) -> None:
    for _ in range(n):
        try:
            if httpx.get(url, timeout=1).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise SystemExit(f"{url} did not start")


def seed(api: str, tmp: Path) -> dict:
    c = httpx.Client(base_url=api, timeout=120)
    h = onboard(c, "v31.demo@example.com", make_pdf(tmp / "cv.pdf", SYNTHETIC_RESUME_LINES).read_bytes())
    tokens = c.post("/api/v1/auth/login", json={"email": "v31.demo@example.com", "password": "Test-Passw0rd!"})
    if tokens.status_code != 200:
        from api_helpers import PASSWORD
        tokens = c.post("/api/v1/auth/login", json={"email": "v31.demo@example.com", "password": PASSWORD})
    refresh = tokens.json()["refresh_token"]
    uj = import_job(c, h, title="Accounts Receivable Analyst", company="Acme Health")["user_job_ids"][0]
    v = c.post("/api/v1/studio/versions", headers=h, json={"name": "AR Analyst · Acme", "template_key": "ats_simple"}).json()
    secs = copy.deepcopy(v["sections"])
    exp = next(s for s in secs if s["type"] == "experience")
    b0 = exp["blocks"][0]
    # The reported problems, as they reach Studio from a Word resume's Symbol-font bullets and a misread import.
    b0["bullets"][0]["text"] = b0["bullets"][0]["text"].replace(" ", " � ", 1)
    b0["bullets"].append({"text": "Responsible for daily cash posting and unapplied cash follow-ups 🚀", "source": "user", "approved": True, "evidence_refs": []})
    if len(exp["blocks"]) > 1:
        exp["blocks"][1]["content"]["start"] = None
    v = c.put(f"/api/v1/studio/versions/{v['id']}", headers=h, json={"revision": v["revision"], "sections": secs}).json()
    app = c.post("/api/v1/applications/prepare", headers=h, json={"user_job_id": uj}).json()
    return {"refresh": refresh, "version": v["id"], "user_job": uj, "app": app.get("id") or app.get("application", {}).get("id")}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="jobpilot-v31-demo-"))
    bp = port()
    api = f"http://127.0.0.1:{bp}"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp / 'demo.db'}", "STORAGE_DIR": str(tmp / "storage"), "JWT_SECRET": secrets.token_hex(32),
           "CORS_ORIGINS": f"http://localhost:{FRONT}", "SCHEDULER_ENABLED": "false", "LLM_PROVIDER": "rule_based",
           "AUTH_RATE_LIMIT_PER_MINUTE": "1000", "ENVIRONMENT": "test", "DOCS_MODE": "off"}
    env.pop("REGISTRATION_INVITE_CODE", None)
    # The production image's fonts only, so the PDFs look exactly as they do for users.
    fc = Path(__file__).parent / "v31_fonts.conf"
    fc.write_text("<?xml version='1.0'?><!DOCTYPE fontconfig SYSTEM 'fonts.dtd'><fontconfig>"
                  + "".join(f"<dir>{d}</dir>" for d in ("/usr/share/fonts/truetype/liberation", "/usr/share/fonts/truetype/lato",
                                                         "/usr/share/fonts/opentype/urw-base35", "/usr/share/fonts/truetype/dejavu"))
                  + f"<cachedir>{tmp / 'fc'}</cachedir></fontconfig>")
    env["FONTCONFIG_FILE"] = str(fc)
    be = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(bp)], cwd=ROOT, env=env,
                          stdout=open(tmp / "backend.log", "w"), stderr=subprocess.STDOUT)
    fe = subprocess.Popen(["npx", "vite", "--port", str(FRONT), "--strictPort"], cwd=ROOT / "frontend", stdout=open(tmp / "vite.log", "w"), stderr=subprocess.STDOUT)
    try:
        wait(f"{api}/api/v1/health")
        wait(f"http://localhost:{FRONT}/")
        d = seed(api, tmp)
        drive(api, d)
    finally:
        be.terminate(); fe.terminate()
        fc.unlink(missing_ok=True)
    print("screenshots and video in", OUT.relative_to(ROOT))


def drive(api: str, d: dict) -> None:
    base = f"http://localhost:{FRONT}/"
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chromium")
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=str(OUT / "video"), record_video_size={"width": 1440, "height": 900})
        ctx.add_init_script(f"localStorage.setItem('jobpilot.apiBaseUrl','{api}');localStorage.setItem('jobpilot.refreshToken','{d['refresh']}');"
                            "localStorage.setItem('jobpilot.theme','light');")
        pg = ctx.new_page()
        shot = lambda name: pg.screenshot(path=str(OUT / f"{name}.png"))  # noqa: E731

        pg.goto(f"{base}#/studio/{d['version']}")
        pg.get_by_role("tab", name="Check").click()
        pg.get_by_label("Check against a job (optional)").select_option(str(d["user_job"]))
        pg.get_by_test_id("score-quality").wait_for(timeout=90000)
        pg.get_by_test_id("score-alignment").wait_for(timeout=90000)
        pg.wait_for_timeout(1500)
        shot("app_1_check_three_scores")
        row = pg.locator("[data-issue^='unreadable_chars']").first
        row.get_by_role("button", name="Details").click()
        pg.wait_for_timeout(400)
        row.scroll_into_view_if_needed()
        shot("app_2_check_issue_details")
        row.get_by_role("button", name="Go to").click()
        pg.wait_for_timeout(1200)
        shot("app_3_go_to_field")

        pg.get_by_role("tab", name="Suggestions").click()
        pg.locator("[data-suggestion]").first.wait_for(timeout=60000)
        pg.wait_for_timeout(800)
        shot("app_4_suggestions_by_category")
        fix = pg.locator("[data-suggestion^='c']").first
        fix.get_by_role("button", name="Accept").click()
        pg.wait_for_timeout(600)
        emoji = pg.locator("[data-suggestion^='w']").first
        if emoji.count():
            emoji.get_by_role("button", name="Accept").click()
        pg.get_by_text("Saved").first.wait_for(timeout=20000)
        pg.wait_for_timeout(2500)
        pg.get_by_role("tab", name="Check").click()
        pg.get_by_test_id("check-revision").wait_for(timeout=90000)
        pg.wait_for_timeout(2500)
        shot("app_5_rechecked_after_accepting")
        pg.wait_for_timeout(1500)
        shot("app_6_revised_preview")

        pg.goto(f"{base}#/discover")
        pg.wait_for_timeout(2500)
        apply_btn = pg.get_by_role("button", name=re.compile(r"^(Apply|Continue)$")).first
        if apply_btn.count():
            apply_btn.click()
            pg.get_by_test_id("ws-resume").wait_for(timeout=30000)
            pg.get_by_test_id("ws-resume").scroll_into_view_if_needed()
            pg.wait_for_timeout(1000)
            shot("app_7_apply_resume_not_chosen")
            pg.get_by_test_id("ws-resume-recommendation").get_by_role("button", name="Select it").click()
            pg.get_by_role("button", name="Use this resume").click()
            pg.get_by_text("Chosen by you").wait_for(timeout=20000)
            pg.wait_for_timeout(800)
            shot("app_8_apply_resume_chosen")
        ctx.close()
        b.close()


if __name__ == "__main__":
    main()
