"""Local preview of the Apply Workspace with fabricated data. Nothing here touches the Docker stack or its database.

    .venv/bin/python extension/e2e/preview.py [--api-port 8011] [--web-port 5181]

Starts the same throwaway backend as run_journey.py (SQLite in a temp dir, scheduler off, outbound internet blocked),
seeds the journey user and jobs A-F (seed_journey.py), and serves the built web app (frontend/dist) with config.json
pointing at that backend. The sign-in details are written to <temp dir>/seed.json (a fabricated test account).
Ctrl+C stops both and deletes the temp dir.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_journey import DIST, EXT, ROOT, start_backend  # noqa: E402


class WebApp(http.server.SimpleHTTPRequestHandler):
    api = ""

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path.endswith("/config.json"):
            body = json.dumps({"apiBaseUrl": self.api}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if not (DIST / path.lstrip("/")).is_file():
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, *a) -> None:
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-python", default=str(ROOT / ".venv" / "bin" / "python"))
    ap.add_argument("--api-port", type=int, default=8011)
    ap.add_argument("--web-port", type=int, default=5181)
    args = ap.parse_args()
    if not (DIST / "index.html").is_file():
        raise SystemExit("Build the web app first: cd frontend && npx vite build")
    if args.api_port in (8000, 55432) or args.web_port == 3080:
        raise SystemExit("Those ports belong to the Docker stack: pick others.")
    tmp = Path(tempfile.mkdtemp(prefix="jobpilot-preview-"))
    web = f"http://127.0.0.1:{args.web_port}"
    api = f"http://127.0.0.1:{args.api_port}"
    # start_backend allows the extension origin and the journey's web origin; add this preview's origin too.
    import run_journey
    run_journey.APP = web
    proc = start_backend(args.project_python, tmp, args.api_port, "preview")
    try:
        subprocess.run([args.project_python, str(EXT / "e2e" / "seed_journey.py"), api, str(tmp / "seed.json")], cwd=ROOT, check=True,
                       env={**os.environ, "DATABASE_URL": f"sqlite:///{tmp / 'journey.db'}", "STORAGE_DIR": str(tmp / "storage")})
        WebApp.api = api
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", args.web_port), functools.partial(WebApp, directory=str(DIST)))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"web app:  {web}/#/discover", flush=True)
        print(f"backend:  {api}  (log: {tmp / 'backend.log'})", flush=True)
        print(f"sign-in:  see {tmp / 'seed.json'} (fabricated test account)", flush=True)
        print("Ctrl+C to stop.", flush=True)
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        proc.wait(timeout=20)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
