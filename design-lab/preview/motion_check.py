"""Proves the transitions happen: samples element geometry/opacity frame by frame, records a video, and repeats with
prefers-reduced-motion to confirm motion is skipped. Uses the sample-data harness (dev server on 127.0.0.1:5199).

    python design-lab/preview/motion_check.py            # sidebar + JD modal (+ settings if --settings)
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))
import shoot  # noqa: E402

VIDEOS = Path(__file__).parent / "videos"
SAMPLE_MS = [0, 40, 80, 120, 160, 200, 260, 340]

SAMPLE_JS = """async ([sel, prop, times]) => {
  const out = [];
  const t0 = performance.now();
  for (const t of times) {
    while (performance.now() - t0 < t) await new Promise(r => requestAnimationFrame(r));
    const all = document.querySelectorAll(sel); const el = all[all.length - 1];
    if (!el) { out.push([t, null]); continue; }
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    out.push([t, prop === 'width' ? Math.round(r.width) : prop === 'opacity' ? Number(cs.opacity).toFixed(2) : cs.transform]);
  }
  return out;
}"""


async def route_ctx(ctx):
    async def route(r):
        path = "/" + r.request.url.split("://", 1)[1].split("/", 1)[1].split("?", 1)[0]
        body = shoot.answer(path, r.request.method)
        await r.fulfill(status=200, content_type="application/json", body=json.dumps(body if body is not None else []),
                        headers={"access-control-allow-origin": "*"})
    await ctx.route(f"{shoot.API}/**", route)
    await ctx.add_init_script("localStorage.setItem('jobpilot.refreshToken','preview-refresh');"
                              f"localStorage.setItem('jobpilot.apiBaseUrl','{shoot.API}');"
                              "localStorage.setItem('jobpilot.theme','light');localStorage.removeItem('jobpilot.sidebar');")


async def run(reduced: bool, record: bool, settings: bool) -> None:
    async with async_playwright() as p:
        b = await p.chromium.launch()
        kw = {"viewport": {"width": 1440, "height": 900}, "reduced_motion": "reduce" if reduced else "no-preference"}
        if record:
            VIDEOS.mkdir(parents=True, exist_ok=True)
            kw["record_video_dir"] = str(VIDEOS)
            kw["record_video_size"] = {"width": 1440, "height": 900}
        ctx = await b.new_context(**kw)
        await route_ctx(ctx)
        pg = await ctx.new_page()
        label = "reduced motion" if reduced else "normal motion"
        await pg.goto(f"{shoot.APP}/#/discover")
        await pg.wait_for_timeout(2200)

        # 1. sidebar collapse, then expand
        click = pg.locator('[data-testid="sidebar-toggle"]').click()
        samples = await asyncio.gather(pg.evaluate(SAMPLE_JS, ["aside[aria-label=Sidebar]", "width", SAMPLE_MS]), click)
        print(f"[{label}] sidebar collapse width(ms→px):", samples[0])
        await pg.wait_for_timeout(700)
        click = pg.locator('[data-testid="sidebar-toggle"]').click()
        samples = await asyncio.gather(pg.evaluate(SAMPLE_JS, ["aside[aria-label=Sidebar]", "width", SAMPLE_MS]), click)
        print(f"[{label}] sidebar expand width(ms→px):", samples[0])
        await pg.wait_for_timeout(700)

        # 2. Full JD modal open (opacity + transform), then Escape
        click = pg.get_by_role("button", name="View full JD").first.click()
        samples = await asyncio.gather(pg.evaluate(SAMPLE_JS, ['[data-testid="jd-modal"]', "opacity", SAMPLE_MS + [500, 700, 1000]]), click)
        print(f"[{label}] JD modal opacity(ms→value):", samples[0])
        await pg.wait_for_timeout(900)
        if record:
            await pg.locator('[data-testid="jd-modal"] nav[aria-label="Sections"] button').nth(1).click()
            await pg.wait_for_timeout(900)
        focused_before = await pg.evaluate("document.activeElement && document.activeElement.textContent")
        await pg.keyboard.press("Escape")
        await pg.wait_for_timeout(500)
        gone = await pg.locator('[data-testid="jd-modal"]').count()
        focus_after = await pg.evaluate("document.activeElement && document.activeElement.textContent")
        print(f"[{label}] JD modal closed by Escape: {gone == 0}; focus returned to: {focus_after!r} (was in modal: {focused_before!r})")

        # 3. page transition
        click = pg.locator("aside nav a[href=\"#/dashboard\"]").first.click()
        samples = await asyncio.gather(pg.evaluate(SAMPLE_JS, ["main .jp-rise", "transform", [0, 60, 120, 200, 320, 500, 800]]), click)
        print(f"[{label}] page enter transform:", samples[0])
        await pg.wait_for_timeout(900)

        if settings:
            await pg.goto(f"{shoot.APP}/#/settings?tab=profile")
            await pg.wait_for_timeout(1500)
            for name in ["Job preferences", "Browser extension", "Notifications"]:
                btn = pg.get_by_role("button", name=name).or_(pg.get_by_role("link", name=name)).first
                if await btn.count():
                    await btn.click()
                    await pg.wait_for_timeout(700)
            print(f"[{label}] settings category switching exercised")
        await ctx.close()
        await b.close()


if __name__ == "__main__":
    rec = "--record" in sys.argv
    st = "--settings" in sys.argv
    asyncio.run(run(False, rec, st))
    if "--no-reduced" not in sys.argv:
        asyncio.run(run(True, False, False))
