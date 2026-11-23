"""V3.2 local walkthrough: Portal Connections (LinkedIn OIDC, Indeed OAuth, Naukri hand-off) and the native apply flow.

    .venv/bin/python design-lab/preview/v32_demo.py

Everything here is local and SIMULATED:
  * two throwaway backends on SQLite in a temp dir (never the production database or containers): one with no portal
    credentials (what a server looks like before the owner sets them), one with fake LinkedIn/Indeed credentials;
  * a SIMULATED sign-in server on 127.0.0.1 standing in for LinkedIn and Indeed (OAUTH_DEV_ENDPOINTS, refused in
    production). Its pages say so. It signs real RS256 ID tokens, checks PKCE and the redirect URI, and can revoke;
  * Naukri pages are intercepted in the browser and replaced by a labelled stub: nothing reaches naukri.com.
No real LinkedIn or Indeed account is connected. Screenshots and a video go to design-lab/preview/v32/.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "tests" / "api"), str(Path(__file__).parent)]
from api_helpers import PASSWORD, import_job, onboard  # noqa: E402
from support import SYNTHETIC_RESUME_LINES, make_pdf  # noqa: E402
from v31_demo import port, wait  # noqa: E402

OUT = ROOT / "design-lab" / "preview" / "v32"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
FRONT = 5199
NAUKRI_URL = "https://www.naukri.com/job-listings-accounts-receivable-analyst-acme-health-bengaluru-3-to-5-years-231125000001"
ACCOUNTS = {"linkedin": {"sub": "sim-li-7Qx2", "name": "Test Candidate", "given_name": "Test", "family_name": "Candidate",
                         "email": "test.candidate@example.com", "email_verified": True},
            "indeed": {"sub": "sim-in-55c1", "email": "test.candidate@example.com", "email_verified": True}}


class SimulatedProvider:
    """LinkedIn- and Indeed-shaped OAuth servers on one local port. SIMULATED: for local demos only."""

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.codes: dict[str, dict] = {}
        self.tokens: dict[str, dict] = {}
        self.refresh: dict[str, dict] = {}
        self.port = port()
        self.base = f"http://127.0.0.1:{self.port}"
        sim = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def _send(self, code: int, body: str | dict, ctype: str = "application/json", headers: dict | None = None) -> None:
                data = (json.dumps(body) if isinstance(body, dict) else body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                u = urlsplit(self.path)
                prov, _, what = u.path.strip("/").partition("/")
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                if what == "authorize":
                    return self._send(200, sim.consent_page(prov, q), "text/html; charset=utf-8")
                if what == "decide":
                    return self._send(302, "", headers={"Location": sim.decide(prov, q)})
                if what == "jwks":
                    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(sim.key.public_key()))
                    return self._send(200, {"keys": [{**jwk, "kid": "sim-1", "use": "sig", "alg": "RS256"}]})
                if what == "userinfo":
                    acct = sim.tokens.get(self.headers.get("Authorization", "").removeprefix("Bearer "))
                    return self._send(200, acct) if acct else self._send(401, {"error": "invalid_token"})
                if what == "revoke-all":  # the member removed JobPilot on the provider
                    sim.tokens.clear()
                    sim.refresh.clear()
                    return self._send(200, {"revoked": True})
                return self._send(404, {"error": "not_found"})

            def do_POST(self):
                prov = urlsplit(self.path).path.strip("/").partition("/")[0]
                form = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()).items()}
                if form.get("client_id") != f"sim-{prov}-client" or form.get("client_secret") != f"sim-{prov}-secret":
                    return self._send(401, {"error": "invalid_client"})
                if form.get("grant_type") == "refresh_token":
                    acct = sim.refresh.pop(form.get("refresh_token", ""), None)
                    return self._send(200, sim.issue(prov, acct, None)) if acct else self._send(400, {"error": "invalid_grant"})
                entry = sim.codes.pop(form.get("code", ""), None)
                if not entry or entry["q"]["redirect_uri"] != form.get("redirect_uri"):
                    return self._send(400, {"error": "invalid_grant"})
                ch = entry["q"].get("code_challenge")
                if ch and base64.urlsafe_b64encode(hashlib.sha256(form.get("code_verifier", "").encode()).digest()).rstrip(b"=").decode() != ch:
                    return self._send(400, {"error": "invalid_grant"})
                return self._send(200, sim.issue(prov, ACCOUNTS[prov], entry["q"]))

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def endpoints(self) -> dict:
        return {p: {"authorize": f"{self.base}/{p}/authorize", "token": f"{self.base}/{p}/token", "userinfo": f"{self.base}/{p}/userinfo",
                    "jwks": f"{self.base}/{p}/jwks", "issuer": f"{self.base}/{p}"} for p in ("linkedin", "indeed")}

    def consent_page(self, prov: str, q: dict) -> str:
        name = {"linkedin": "LinkedIn", "indeed": "Indeed"}[prov]
        acct = ACCOUNTS[prov]
        allow = f"/{prov}/decide?" + urlencode({**q, "decision": "allow"})
        deny = f"/{prov}/decide?" + urlencode({**q, "decision": "deny"})
        scopes = "".join(f"<li><code>{html.escape(s)}</code></li>" for s in q.get("scope", "").split())
        return f"""<!doctype html><html><head><meta charset="utf-8"><title>SIMULATED {name} sign-in</title>
<style>body{{font:15px system-ui,sans-serif;background:#eef0f3;margin:0}}.sim{{background:#b42318;color:#fff;padding:10px 16px;font-weight:700;letter-spacing:.02em}}
.card{{max-width:440px;margin:48px auto;background:#fff;border-radius:12px;padding:28px;box-shadow:0 2px 10px #0002}}
h1{{font-size:20px;margin:0 0 6px}}.who{{background:#f4f5f7;border-radius:8px;padding:10px 12px;margin:14px 0}}
a.btn{{display:inline-block;padding:9px 18px;border-radius:20px;text-decoration:none;font-weight:600;margin-right:8px}}
.allow{{background:#1f4fd1;color:#fff}}.deny{{border:1px solid #888;color:#333}}code{{font-size:13px}}</style></head><body>
<div class="sim">SIMULATED {name.upper()} SIGN-IN · local test server on 127.0.0.1 · this is not {name}</div>
<div class="card"><h1>JobPilot wants to sign you in with {name}</h1>
<p>Signed in as:</p><div class="who"><strong>{html.escape(acct.get('name') or acct['email'])}</strong><br>{html.escape(acct['email'])}</div>
<p>JobPilot is asking for:</p><ul>{scopes}</ul>
<a class="btn allow" href="{html.escape(allow)}">Allow</a><a class="btn deny" href="{html.escape(deny)}">Cancel</a></div></body></html>"""

    def decide(self, prov: str, q: dict) -> str:
        back = {"state": q["state"]}
        if q.get("decision") == "allow":
            code = secrets.token_urlsafe(16)
            self.codes[code] = {"q": q}
            back["code"] = code
        else:
            back.update(error="user_cancelled_authorize" if prov == "linkedin" else "access_denied", error_description="The user cancelled")
        if prov == "indeed":
            back["iss"] = f"{self.base}/indeed"  # RFC 9207, as Indeed sends it
        return f"{q['redirect_uri']}?{urlencode(back)}"

    def issue(self, prov: str, acct: dict, q: dict | None) -> dict:
        tok = secrets.token_urlsafe(24)
        self.tokens[tok] = acct
        if prov == "indeed":
            rt = secrets.token_urlsafe(24)
            self.refresh[rt] = acct
            return {"access_token": tok, "refresh_token": rt, "expires_in": 3600, "token_type": "Bearer", "scope": "email offline_access"}
        now = int(time.time())
        claims = {"iss": f"{self.base}/linkedin", "aud": "sim-linkedin-client", "sub": acct["sub"], "iat": now, "exp": now + 3600,
                  **{k: v for k, v in acct.items() if k != "sub"}}
        if q and q.get("nonce"):
            claims["nonce"] = q["nonce"]
        return {"access_token": tok, "expires_in": 5184000, "scope": "openid,profile,email",
                "id_token": jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "sim-1"})}


def backend(tmp: Path, name: str, extra: dict) -> tuple[subprocess.Popen, str]:
    bp = port()
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp / (name + '.db')}", "STORAGE_DIR": str(tmp / name), "JWT_SECRET": secrets.token_hex(32),
           "CORS_ORIGINS": f"http://localhost:{FRONT}", "SCHEDULER_ENABLED": "false", "LLM_PROVIDER": "rule_based",
           "AUTH_RATE_LIMIT_PER_MINUTE": "1000", "ENVIRONMENT": "test", "DOCS_MODE": "off", **extra}
    for k in ("REGISTRATION_INVITE_CODE", "LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "INDEED_CLIENT_ID", "INDEED_CLIENT_SECRET", "PUBLIC_APP_URL"):
        if k not in extra:
            env.pop(k, None)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(bp)], cwd=ROOT, env=env,
                            stdout=open(tmp / f"{name}.log", "w"), stderr=subprocess.STDOUT)
    return proc, f"http://127.0.0.1:{bp}"


def seed(api: str, tmp: Path, email: str, *, job: bool) -> dict:
    c = httpx.Client(base_url=api, timeout=120)
    h = onboard(c, email, make_pdf(tmp / f"{email}.pdf", SYNTHETIC_RESUME_LINES).read_bytes())
    refresh = c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["refresh_token"]
    if job:
        import_job(c, h, url=NAUKRI_URL, title="Accounts Receivable Analyst", company="Acme Health")
    return {"refresh": refresh}


def main() -> None:
    (OUT / "video").mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="jobpilot-v32-demo-"))
    sim = SimulatedProvider()
    app_url = f"http://localhost:{FRONT}"
    plain, plain_api = backend(tmp, "plain", {})
    full, full_api = backend(tmp, "full", {
        "PUBLIC_APP_URL": app_url, "LINKEDIN_CLIENT_ID": "sim-linkedin-client", "LINKEDIN_CLIENT_SECRET": "sim-linkedin-secret",
        "INDEED_CLIENT_ID": "sim-indeed-client", "INDEED_CLIENT_SECRET": "sim-indeed-secret", "OAUTH_DEV_ENDPOINTS": json.dumps(sim.endpoints())})
    fe = subprocess.Popen(["npx", "vite", "--port", str(FRONT), "--strictPort"], cwd=ROOT / "frontend", stdout=open(tmp / "vite.log", "w"), stderr=subprocess.STDOUT, start_new_session=True)
    try:
        for u in (f"{plain_api}/api/v1/health", f"{full_api}/api/v1/health", f"{app_url}/"):
            wait(u)
        a = seed(plain_api, tmp, "v32.plain@example.com", job=False)
        b = seed(full_api, tmp, "v32.demo@example.com", job=True)
        drive(app_url, plain_api, a, full_api, b, sim)
    finally:
        plain.terminate(); full.terminate(); os.killpg(fe.pid, signal.SIGTERM); sim.server.shutdown()
    failed = [r for r in results if not r[1]]
    (OUT / "demo_results.json").write_text(json.dumps(results, indent=1))
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed (SIMULATED providers)")
    print("screenshots and video in", OUT.relative_to(ROOT))
    sys.exit(1 if failed else 0)


def drive(app_url: str, plain_api: str, a: dict, api: str, b: dict, sim: SimulatedProvider) -> None:
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chromium")

        # 1. A server without portal credentials: honest "not set up", no Connect button, Naukri as a hand-off.
        ctx0 = br.new_context(viewport={"width": 1440, "height": 1000})
        ctx0.add_init_script(f"localStorage.setItem('jobpilot.apiBaseUrl','{plain_api}');localStorage.setItem('jobpilot.refreshToken','{a['refresh']}');"
                             "localStorage.setItem('jobpilot.theme','light');")
        pg0 = ctx0.new_page()
        pg0.goto(f"{app_url}/#/settings?tab=portals")
        pg0.get_by_test_id("portal-connections").wait_for(timeout=30000)
        pg0.wait_for_timeout(800)
        pg0.screenshot(path=str(OUT / "p1_not_configured_three_cards.png"), full_page=True)
        check("not configured: three portal cards", pg0.locator("[data-testid^='portal-']").count() >= 3)
        check("not configured: no Connect button anywhere", pg0.get_by_role("button", name="Connect with LinkedIn").count() == 0
              and pg0.get_by_role("button", name="Connect with Indeed").count() == 0)
        check("not configured: says what the owner must set", "LINKEDIN_CLIENT_ID" in pg0.get_by_test_id("portal-linkedin").inner_text())
        ctx0.close()

        # 2. With (simulated) LinkedIn and Indeed sign-in configured.
        ctx = br.new_context(viewport={"width": 1440, "height": 1000}, record_video_dir=str(OUT / "video"), record_video_size={"width": 1440, "height": 1000})
        ctx.add_init_script(f"if (!localStorage.getItem('jobpilot.refreshToken')) {{ localStorage.setItem('jobpilot.apiBaseUrl','{api}');"
                            f"localStorage.setItem('jobpilot.refreshToken','{b['refresh']}'); }} localStorage.setItem('jobpilot.theme','light');")
        ctx.route("https://www.naukri.com/**", lambda route: route.fulfill(status=200, content_type="text/html", body=(
            "<!doctype html><title>SIMULATED Naukri job page</title><body style='font:16px system-ui;margin:0'>"
            "<div style='background:#b42318;color:#fff;padding:10px 16px;font-weight:700'>SIMULATED NAUKRI PAGE · intercepted in the test browser · nothing reached naukri.com</div>"
            "<div style='padding:32px'><h1>Accounts Receivable Analyst</h1><p>Acme Health · Bengaluru · 3-5 years</p>"
            "<p>On the real site you'd be signed in already if you were before, then press Apply and upload your resume.</p></div>")))
        real_hosts: list[str] = []
        ctx.on("request", lambda r: real_hosts.append(r.url) if any(h in r.url for h in ("linkedin.com", "indeed.com", "naukri.com")) else None)
        pg = ctx.new_page()
        shot = lambda name, full=False: pg.screenshot(path=str(OUT / f"{name}.png"), full_page=full)  # noqa: E731
        cards = f"{app_url}/#/settings?tab=portals"
        pg.goto(cards)
        pg.get_by_test_id("portal-connections").wait_for(timeout=30000)
        pg.wait_for_timeout(800)
        shot("p2_configured_not_linked", True)

        pg.get_by_role("button", name="Connect with LinkedIn").click()
        pg.wait_for_url(f"{sim.base}/linkedin/authorize**")
        shot("p3_linkedin_consent_SIMULATED")
        pg.get_by_role("link", name="Allow").click()
        pg.get_by_test_id("identity-linkedin").wait_for(timeout=30000)
        pg.wait_for_timeout(1200)
        shot("p4_linkedin_linked", True)
        check("LinkedIn: linked after consent, identity shown", "Test Candidate" in pg.get_by_test_id("identity-linkedin").inner_text())

        pg.get_by_role("button", name="Connect with Indeed").click()
        pg.wait_for_url(f"{sim.base}/indeed/authorize**")
        pg.get_by_role("link", name="Allow").click()
        pg.get_by_test_id("identity-indeed").wait_for(timeout=30000)
        pg.wait_for_timeout(1200)
        shot("p5_both_linked_permissions", True)
        ind = pg.get_by_test_id("identity-indeed").inner_text()
        check("Indeed: linked (PKCE + iss), granted permissions shown", "email" in ind and "offline_access" in ind, ind)
        check("linked accounts still show no job API or submission", pg.get_by_test_id("portal-indeed").locator("[data-cap='job_retrieval']").inner_text().count("not available") == 1)

        li = pg.get_by_test_id("portal-linkedin")
        li.get_by_role("button", name="Disconnect").click()
        pg.wait_for_timeout(400)
        shot("p6_disconnect_confirm")
        pg.get_by_role("group", name="Disconnect LinkedIn").get_by_role("button", name="Disconnect").click()
        li.get_by_text("Not linked").wait_for(timeout=15000)
        pg.wait_for_timeout(600)
        shot("p7_linkedin_disconnected")
        check("disconnect: LinkedIn back to Not linked", li.get_by_text("Not linked").count() == 1)
        li.get_by_role("button", name="Connect with LinkedIn").click()
        pg.wait_for_url(f"{sim.base}/linkedin/authorize**")
        pg.get_by_role("link", name="Allow").click()
        pg.get_by_test_id("identity-linkedin").wait_for(timeout=30000)

        httpx.get(f"{sim.base}/linkedin/revoke-all")  # the member removes JobPilot on the (simulated) provider
        li.get_by_role("button", name="Check connection").click()
        li.get_by_text("Reconnect needed").wait_for(timeout=15000)
        pg.wait_for_timeout(800)
        li.scroll_into_view_if_needed()
        shot("p8_reconnect_needed")
        check("revoked on the provider: Check connection shows Reconnect needed", li.get_by_role("button", name="Reconnect LinkedIn").count() == 1)
        li.get_by_role("button", name="Reconnect LinkedIn").click()
        pg.wait_for_url(f"{sim.base}/linkedin/authorize**")
        pg.get_by_role("link", name="Cancel").click()
        pg.get_by_role("alert").wait_for(timeout=15000)
        pg.wait_for_timeout(600)
        shot("p9_cancelled_nothing_linked")
        check("cancel on the provider: nothing linked, said plainly", "Nothing was linked" in pg.get_by_role("alert").inner_text())
        li.get_by_role("button", name="Reconnect LinkedIn").click()
        pg.wait_for_url(f"{sim.base}/linkedin/authorize**")
        pg.get_by_role("link", name="Allow").click()
        li.get_by_text("Linked", exact=True).wait_for(timeout=30000)
        check("reconnect: linked again", True)

        # 3. Naukri: Discover → Apply → choose resume → open on Naukri (native hand-off) → I applied → tracked.
        pg.goto(f"{app_url}/#/discover")
        pg.wait_for_timeout(2500)
        pg.get_by_role("button", name="Apply", exact=True).or_(pg.get_by_role("button", name="Continue", exact=True)).first.click()
        pg.get_by_test_id("ws-resume").wait_for(timeout=30000)
        pg.wait_for_timeout(1000)
        shot("p10_naukri_apply_resume_required")
        check("Naukri: Open on Naukri waits for an explicit resume choice", pg.get_by_test_id("workspace-primary").is_disabled()
              and "Open on Naukri" in pg.get_by_test_id("workspace-primary").inner_text())
        pg.get_by_test_id("ws-resume-recommendation").get_by_role("button", name="Select it").click()
        pg.get_by_role("button", name="Use this resume").click()
        pg.get_by_text("Chosen by you").wait_for(timeout=20000)
        pg.wait_for_timeout(800)
        pg.get_by_test_id("workspace-primary").scroll_into_view_if_needed()
        shot("p11_naukri_ready_open_on_naukri")
        check("Naukri: enabled once the resume is chosen", pg.get_by_test_id("workspace-primary").is_enabled())
        with ctx.expect_page() as pop:
            pg.get_by_test_id("workspace-primary").click()
        naukri = pop.value
        naukri.wait_for_load_state()
        naukri.wait_for_timeout(600)
        naukri.screenshot(path=str(OUT / "p12_naukri_page_SIMULATED.png"))
        check("Naukri: the original listing opens in this browser", naukri.url == NAUKRI_URL, naukri.url)
        naukri.close()
        pg.bring_to_front()
        pg.evaluate("window.dispatchEvent(new Event('focus'))")
        pg.get_by_role("button", name="Yes, I submitted it").wait_for(timeout=20000)
        pg.wait_for_timeout(800)
        shot("p13_back_did_you_submit")
        check("opening the page is not applying: asks for the outcome", pg.get_by_text("Did you submit the application on Naukri?").count() == 1)
        pg.get_by_role("button", name="Yes, I submitted it").click()
        pg.get_by_test_id("ws-done").wait_for(timeout=20000)
        pg.wait_for_timeout(1000)
        shot("p14_recorded_user_reported")
        check("I applied is recorded as user-reported, not verified", "not independently verified" in pg.get_by_test_id("ws-done").inner_text())
        pg.goto(f"{app_url}/#/applied")
        pg.wait_for_timeout(2500)
        shot("p15_tracked_in_applications")
        check("tracked under Applications", "You told JobPilot" in pg.inner_text("main"))
        check("no request reached LinkedIn, Indeed or Naukri (Naukri page intercepted)", all("naukri.com" in u for u in real_hosts), str(real_hosts[:3]))
        ctx.close()
        br.close()


if __name__ == "__main__":
    main()
