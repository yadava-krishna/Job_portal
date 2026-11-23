"""Screenshots for USER_GUIDE.md, taken from the LIVE site (GitHub Pages) with sample data.

The live frontend is loaded as-is, but every API call is answered from the preview fixtures (shoot.py and
fixtures_*.py): the demo user "Asha Rao" and made-up jobs. No real user's data appears, nothing is sent to the
real backend, and calls to any ngrok host are blocked.

    python design-lab/preview/guide_shots.py            # all shots
    python design-lab/preview/guide_shots.py dashboard  # only shots whose name contains "dashboard"
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent))
import shoot  # noqa: E402  (fixtures + answer())
import fixtures_guide  # noqa: E402

from playwright.async_api import async_playwright  # noqa: E402

LIVE = "https://yadava-krishna.github.io/Job_portal/"
API = "http://127.0.0.1:59999"  # answered locally; the live site's CSP only allows localhost and ngrok
PDF = Path(__file__).parent / "sample_resume.pdf"
OUT = Path(__file__).resolve().parents[2] / "docs" / "guide"

# name, hash route, actions, options. Actions: ("click", selector) | ("scroll", px) | ("wait", ms) | ("text", text)
SHOTS: list[tuple[str, str, list, dict]] = [
    ("01-login", "login", [], {"auth": False}),
    ("02-register", "register", [], {"auth": False}),
    ("03-forgot-password", "forgot-password", [], {"auth": False}),
    ("04-onboarding", "onboarding", [], {"onboarding": False}),
    ("10-dashboard", "dashboard", [], {}),
    ("11-dashboard-lower", "dashboard", [("scroll", 900)], {}),
    ("12-dashboard-dark", "dashboard", [], {"theme": "dark"}),
    ("13-dashboard-phone", "dashboard", [], {"phone": True}),
    ("20-discover", "discover", [], {}),
    ("21-discover-job", "discover", [("text", "Data Analyst, Payments Risk")], {}),
    ("21b-apply-workspace", "discover", [("role", "button", "Apply")], {}),
    ("22-discover-filters", "discover", [("role", "button", "Filters")], {}),
    ("23-discover-phone", "discover", [], {"phone": True}),
    ("25-saved", "saved", [], {}),
    ("30-searches", "searches?tab=searches", [], {}),
    ("31-searches-companies", "searches?tab=companies", [], {}),
    ("32-searches-sources", "searches?tab=sources", [], {}),
    ("40-applied-list", "applied", [], {}),
    ("41-applied-board", "applied", [("role", "tab", "Board")], {}),
    ("42-applied-pending", "applied", [("role", "tab", "Pending")], {}),
    ("43-applied-detail", "applied?app=25", [], {}),
    ("45-reports", "reports", [], {}),
    ("50-studio", "studio", [], {}),
    ("51-studio-editor", "studio/3", [("wait", 5000)], {}),
    ("52-studio-design", "studio/3", [("role", "tab", "Design")], {}),
    ("53-studio-check", "studio/3", [("role", "tab", "Check")], {}),
    ("54-studio-suggestions", "studio/3", [("role", "tab", "Suggestions")], {}),
    ("60-career-gaps", "career?tab=gaps", [], {}),
    ("61-career-skills", "career?tab=skills", [], {}),
    ("62-career-learning", "career?tab=learning", [], {}),
    ("63-interview-prep", "interview-prep", [], {}),
    ("64-interview-prep-job", "interview-prep?job=100", [], {}),
    ("65-interview-practice", "interview-prep?practice=7", [], {}),
    ("66-mentor", "mentor", [], {}),
    ("66b-mentor-mentors", "mentor", [("scroll", 2200)], {}),
    ("67-mentoring", "mentoring", [], {}),
    ("68-international", "international", [], {}),
    ("90-offline", "dashboard", [("wait", 3000)], {"offline": True}),
    ("70-settings-profile", "settings?tab=profile", [], {}),
    ("71-settings-career-goals", "settings?tab=career-goals", [], {}),
    ("72-settings-preferences", "settings?tab=preferences", [], {}),
    ("73-settings-platforms", "settings?tab=platforms", [], {}),
    ("74-settings-portals", "settings?tab=portals", [], {}),
    ("74b-settings-portals-linkedin", "settings?tab=portals", [("role", "button", "Optimize profile")], {}),
    ("75-settings-extension", "settings?tab=extension", [], {}),
    ("76-settings-answers", "settings?tab=answers", [], {}),
    ("76b-settings-answers-remembered", "settings?tab=answers", [("scroll", 1500)], {}),
    ("77-settings-email", "settings?tab=email", [], {}),
    ("78-settings-notifications", "settings?tab=notifications", [], {}),
    ("79-settings-privacy", "settings?tab=privacy", [], {}),
    ("80-settings-account", "settings?tab=account", [], {}),
]

ONBOARDING_TODO = {"resume_uploaded": False, "profile_confirmed": False, "preferences_saved": False,
                   "platforms_selected": False, "completed": False}
USER_NEW = dict(shoot.USER, onboarding_completed_at=None)


async def run(only: str | None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    missing: set[str] = set()
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chromium")  # full Chromium: renders the PDF preview
        for name, route, actions, opt in SHOTS:
            if only and only not in name:
                continue
            phone = opt.get("phone", False)
            vp = {"width": 390, "height": 844} if phone else {"width": 1440, "height": 900}
            theme = opt.get("theme", "light")
            ctx = await browser.new_context(viewport=vp, device_scale_factor=2 if phone else 1,
                                            color_scheme="dark" if theme == "dark" else "light")
            init = f"localStorage.setItem('jobpilot.theme','{theme}');localStorage.setItem('jobpilot.apiBaseUrl','{API}');"
            if opt.get("auth", True):
                init += "localStorage.setItem('jobpilot.refreshToken','preview-refresh');"
            await ctx.add_init_script(init)
            onboarding_done = opt.get("onboarding", True)

            async def api(r, onboarding_done=onboarding_done, opt_offline=opt.get("offline", False)):
                url = r.request.url
                path = "/" + url.split("://", 1)[1].split("/", 1)[1].split("?", 1)[0]
                if r.request.method == "OPTIONS":
                    return await r.fulfill(status=204, headers={"access-control-allow-origin": "*",
                                                                "access-control-allow-headers": "*",
                                                                "access-control-allow-methods": "*"})
                if path.endswith("/preview.pdf"):
                    return await r.fulfill(status=200, content_type="application/pdf", body=PDF.read_bytes(),
                                           headers={"access-control-allow-origin": "*"})
                if opt_offline:
                    return await r.abort()
                if path == "/api/v1/applications/prepare" and r.request.method == "POST":
                    return await r.fulfill(status=200, content_type="application/json", body=json.dumps(fixtures_guide.APPLY_APP),
                                           headers={"access-control-allow-origin": "*"})
                if not onboarding_done and path == "/api/v1/onboarding":
                    body = ONBOARDING_TODO
                elif not onboarding_done and path == "/api/v1/auth/me":
                    body = USER_NEW
                elif path == "/api/v1/auth/refresh" and r.request.method == "POST" and not onboarding_done:
                    body = {"access_token": "preview-access", "refresh_token": "preview-refresh", "token_type": "bearer",
                            "expires_in": 3600, "user": USER_NEW}
                else:
                    body = shoot.answer(path, r.request.method, parse_qs(urlparse(url).query))
                if body is None:
                    missing.add(path)
                    body = []
                await r.fulfill(status=200, content_type="application/json", body=json.dumps(body),
                                headers={"access-control-allow-origin": "*"})

            await ctx.route(f"{API}/**", api)
            await ctx.route("**/*ngrok*/**", lambda r: r.abort())  # never reach the real backend
            page = await ctx.new_page()
            await page.goto(f"{LIVE}#/{route}")
            await page.wait_for_timeout(3200)
            for a in actions:
                try:
                    if a[0] == "click":
                        await page.locator(a[1]).first.click(timeout=4000)
                    elif a[0] == "text":
                        await page.get_by_text(a[1]).first.click(timeout=4000)
                    elif a[0] == "role":
                        await page.get_by_role(a[1], name=a[2]).first.click(timeout=4000)
                    elif a[0] == "scroll":
                        await page.mouse.wheel(0, a[1])
                    elif a[0] == "wait":
                        await page.wait_for_timeout(a[1])
                except Exception as e:  # keep going; the shot shows what happened
                    print(f"  {name}: action {a} failed: {type(e).__name__}")
                await page.wait_for_timeout(1400)
            # The Account page prints the backend address: show the real format instead of the local stand-in.
            await page.evaluate("""(api) => { const w = document.createTreeWalker(document.body, NodeFilter.SHOWTEXT);
                for (let n; (n = w.nextNode());) if (n.nodeValue.includes(api)) n.nodeValue = n.nodeValue.replace(api, 'https://your-portal.ngrok-free.dev'); }""".replace("SHOWTEXT", "SHOW_TEXT"), API)
            out = OUT / f"{name}.png"
            await page.screenshot(path=str(out))
            print(out.relative_to(OUT.parents[1]))
            await ctx.close()
        await browser.close()
    if missing:
        print("unmocked:", sorted(missing))


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else None))
