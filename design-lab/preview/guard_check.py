"""End-to-end check of the Settings unsaved-changes guard against the sample-data harness."""
import asyncio, json, sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse
sys.path.insert(0, str(Path(__file__).parent)); import shoot  # noqa: E402
from playwright.async_api import async_playwright

async def main():
    puts = []
    async with async_playwright() as p:
        b = await p.chromium.launch(); ctx = await b.new_context(viewport={"width": 1440, "height": 900})
        await ctx.add_init_script(f"localStorage.setItem('jobpilot.refreshToken','preview-refresh');localStorage.setItem('jobpilot.apiBaseUrl','{shoot.API}');")
        async def route(r):
            u = r.request.url; path = "/" + u.split("://", 1)[1].split("/", 1)[1].split("?", 1)[0]
            if r.request.method in ("PUT", "POST", "PATCH"): puts.append((r.request.method, path))
            body = shoot.answer(path, r.request.method, parse_qs(urlparse(u).query))
            if r.request.method == "PUT" and path.endswith("/preferences"): body = shoot.FIXTURES.get("/api/v1/preferences", {})
            await r.fulfill(status=200, content_type="application/json", body=json.dumps(body if body is not None else []), headers={"access-control-allow-origin": "*"})
        await ctx.route(f"{shoot.API}/**", route)
        pg = await ctx.new_page()
        await pg.goto(f"{shoot.APP}/#/settings?tab=preferences"); await pg.wait_for_timeout(2500)
        dialog = pg.locator('[data-testid="unsaved-dialog"]')
        field = pg.locator("main input[type=number], main input:not([type])").first
        # 1. untouched: switching is immediate
        await pg.get_by_role("button", name="Platforms").first.click(); await pg.wait_for_timeout(500)
        print("1 clean switch → platforms:", "tab=platforms" in pg.url, "| dialog:", await dialog.count())
        await pg.get_by_role("button", name="Job preferences").first.click(); await pg.wait_for_timeout(800)
        # 2. edit, then switch category → dialog; Keep editing stays
        await field.click(); await field.press("End"); await field.type("7"); await pg.wait_for_timeout(300)
        print("2 'Unsaved changes' badge:", await pg.get_by_text("Unsaved changes").count() > 0)
        await pg.get_by_role("button", name="Platforms").first.click(); await pg.wait_for_timeout(500)
        print("  dialog on category switch:", await dialog.count() == 1)
        await pg.get_by_role("button", name="Keep editing").click(); await pg.wait_for_timeout(400)
        info = await field.evaluate("e => [e.id, e.type, e.placeholder, e.value]")
        print("  keep editing → still on preferences:", "tab=preferences" in pg.url, "| field:", info, "| still dirty:", await pg.get_by_text("Unsaved changes").count() > 0)
        # 3. Discard → switches, edits gone
        await pg.get_by_role("button", name="Platforms").first.click(); await pg.wait_for_timeout(400)
        await pg.get_by_role("button", name="Discard").click(); await pg.wait_for_timeout(700)
        print("3 discard → platforms:", "tab=platforms" in pg.url)
        await pg.get_by_role("button", name="Job preferences").first.click(); await pg.wait_for_timeout(800)
        print("  no dialog after discard:", await dialog.count() == 0, "| badge gone:", await pg.get_by_text("Unsaved changes").count() == 0)
        # 4. edit, click a sidebar link → dialog; Save changes → PUT then navigates
        await field.click(); await field.press("End"); await field.type("3"); await pg.wait_for_timeout(300)
        await pg.locator('aside a[href="#/dashboard"]').first.click(); await pg.wait_for_timeout(500)
        print("4 dialog on sidebar link:", await dialog.count() == 1, "| still on settings:", "/settings" in pg.url)
        before = len(puts)
        await pg.get_by_role("button", name="Save changes").click(); await pg.wait_for_timeout(1500)
        print("  save → request sent:", puts[before:] , "| navigated home:", pg.url.endswith("#/dashboard"))
        # 5. refresh with edits → browser prompt
        await pg.goto(f"{shoot.APP}/#/settings?tab=preferences"); await pg.wait_for_timeout(2200)
        field = pg.locator("main input[type=number], main input:not([type])").first
        await field.click(); await field.press("End"); await field.type("9"); await pg.wait_for_timeout(300)
        seen = []
        pg.on("dialog", lambda d: (seen.append(d.type), asyncio.ensure_future(d.dismiss())))
        try:
            await pg.reload(timeout=3000)
        except Exception:
            pass
        await pg.wait_for_timeout(500)
        print("5 refresh with edits → browser prompt:", seen)
        await b.close()

asyncio.run(main())
