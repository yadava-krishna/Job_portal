"""Run JobPilot locally to try Portal Connections by hand. Keeps running until Ctrl+C.

    .venv/bin/python design-lab/preview/v32_local.py               # real LinkedIn/Indeed where keys are set, else "not set up"
    .venv/bin/python design-lab/preview/v32_local.py --simulated   # a local SIMULATED sign-in server for portals without keys

  web app   http://localhost:5199   (Vite, this checkout)
  backend   http://127.0.0.1:8799   (SQLite in DATA_DIR, never the production database or containers)

Real sign-in: put the portal's keys in .env.portals.local at the repo root (git-ignored, not read by docker compose):
    LINKEDIN_CLIENT_ID=...
    LINKEDIN_CLIENT_SECRET=...
and register http://localhost:5199/oauth-callback.html as an authorized redirect URL in that portal's developer app.
LinkedIn's own sign-in page then uses the LinkedIn session already in your browser, or asks you to sign in on
linkedin.com. JobPilot never sees that password.
A candidate and an admin test account and a Naukri job are created on first start; the logins are written to DATA_DIR/LOGIN.txt.
"""

from __future__ import annotations

import json
import os
import secrets
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from v32_demo import ROOT, NAUKRI_URL, SimulatedProvider, wait  # noqa: E402
from api_helpers import PASSWORD, import_job, onboard  # noqa: E402
from support import SYNTHETIC_RESUME_LINES, make_pdf  # noqa: E402

FRONT, API_PORT = 5199, 8799
DATA = Path(os.environ.get("DATA_DIR") or ROOT / "design-lab" / "preview" / ".v32_local")
EMAIL = "local.tester@example.com"        # a candidate
ADMIN_EMAIL = "local.admin@example.com"   # an admin: sees "Set up LinkedIn / Indeed" in Portal Connections


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    secret_file = DATA / "jwt_secret"
    if not secret_file.exists():
        secret_file.write_text(secrets.token_hex(32))
    app_url, api = f"http://localhost:{FRONT}", f"http://127.0.0.1:{API_PORT}"

    keys = {}
    key_file = ROOT / ".env.portals.local"
    if key_file.exists():
        for line in key_file.read_text().splitlines():
            k, sep, v = line.strip().partition("=")
            if sep and k.strip().startswith(("LINKEDIN_", "INDEED_")) and v.strip():
                keys[k.strip()] = v.strip().strip('"').strip("'")
    os.environ.update(keys)
    real = {p for p in ("linkedin", "indeed") if os.environ.get(f"{p.upper()}_CLIENT_ID") and os.environ.get(f"{p.upper()}_CLIENT_SECRET")}
    sim = SimulatedProvider()
    dev = {p: e for p, e in sim.endpoints().items() if p not in real} if "--simulated" in sys.argv else {}
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{DATA / 'local.db'}", "STORAGE_DIR": str(DATA / "storage"),
           "JWT_SECRET": secret_file.read_text().strip(), "CORS_ORIGINS": app_url, "SCHEDULER_ENABLED": "false",
           "LLM_PROVIDER": "rule_based", "ENVIRONMENT": "development", "DOCS_MODE": "off", "PUBLIC_APP_URL": app_url,
           "OAUTH_DEV_ENDPOINTS": json.dumps(dev)}
    env.pop("REGISTRATION_INVITE_CODE", None)
    for p in dev:  # simulated portals get the simulated server's own client credentials
        env[f"{p.upper()}_CLIENT_ID"], env[f"{p.upper()}_CLIENT_SECRET"] = f"sim-{p}-client", f"sim-{p}-secret"
    env.pop("LINKEDIN_REDIRECT_URI", None) if "linkedin" not in real else None
    env.pop("INDEED_REDIRECT_URI", None) if "indeed" not in real else None

    be = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(API_PORT)], cwd=ROOT, env=env,
                          stdout=open(DATA / "backend.log", "a"), stderr=subprocess.STDOUT)
    fe = subprocess.Popen(["npx", "vite", "--port", str(FRONT), "--strictPort"], cwd=ROOT / "frontend",
                          env={**os.environ, "VITE_API_BASE_URL": api}, stdout=open(DATA / "vite.log", "a"), stderr=subprocess.STDOUT, start_new_session=True)

    def stop(*_):
        be.terminate(); os.killpg(fe.pid, signal.SIGTERM); sim.server.shutdown()
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    wait(f"{api}/api/v1/health")
    wait(f"{app_url}/")
    c = httpx.Client(base_url=api, timeout=120)
    if c.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code != 200:
        h = onboard(c, EMAIL, make_pdf(DATA / "cv.pdf", SYNTHETIC_RESUME_LINES).read_bytes())
        import_job(c, h, url=NAUKRI_URL, title="Accounts Receivable Analyst", company="Acme Health")
    if c.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD}).status_code != 200:
        onboard(c, ADMIN_EMAIL, make_pdf(DATA / "cv.pdf", SYNTHETIC_RESUME_LINES).read_bytes())
        with sqlite3.connect(DATA / "local.db") as con:
            con.execute("update users set role='admin' where email=?", (ADMIN_EMAIL,))
    (DATA / "LOGIN.txt").write_text(f"Open: {app_url}/?api={api}#/login\n\nCandidate  {EMAIL}\nAdmin      {ADMIN_EMAIL}\nPassword (both): {PASSWORD}\n"
                                    "(local throwaway test accounts on the local backend only)\n")
    mode = {p: ("REAL" if p in real else "SIMULATED" if p in dev else "NOT_SET_UP") for p in ("linkedin", "indeed")}
    print(f"READY {app_url}/?api={api}#/login  linkedin={mode['linkedin']} indeed={mode['indeed']}  login: {DATA / 'LOGIN.txt'}", flush=True)
    while be.poll() is None and fe.poll() is None:
        time.sleep(2)
    stop()


if __name__ == "__main__":
    main()
