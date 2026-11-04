#!/usr/bin/env bash
# Start the JobPilot portal: Postgres + backend + local UI (+ ngrok tunnel), then publish the
# tunnel URL for the GitHub Pages frontend if it changed. Data persists across restarts.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo "Docker is required."; exit 1; }
./deploy/init_env.sh >/dev/null
set -a; . ./.env; set +a
BACKEND_PORT=${BACKEND_PORT:-8000}; FRONTEND_PORT=${FRONTEND_PORT:-3000}; INSPECT=${NGROK_INSPECT_PORT:-4041}

profiles=()
[ -n "${NGROK_AUTHTOKEN:-}" ] && profiles=(--profile tunnel)
echo "Building and starting containers…"
docker compose "${profiles[@]}" up -d --build

echo -n "Waiting for the backend"
for i in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/v1/health/ready" >/dev/null 2>&1; then echo " ready."; break; fi
  echo -n "."; sleep 2
  [ "$i" = 90 ] && { echo; echo "Backend did not become ready. See: docker compose logs backend"; exit 1; }
done

public=""
if [ ${#profiles[@]} -gt 0 ]; then
  echo -n "Waiting for the ngrok tunnel"
  for i in $(seq 1 30); do
    public=$(curl -fsS "http://127.0.0.1:${INSPECT}/api/tunnels" 2>/dev/null | python3 -c "import sys,json; t=[x['public_url'] for x in json.load(sys.stdin).get('tunnels',[]) if x['public_url'].startswith('https://')]; print(t[0] if t else '')" 2>/dev/null || true)
    [ -n "$public" ] && { echo " $public"; break; }
    echo -n "."; sleep 2
  done
  if [ -n "$public" ]; then
    if curl -fsS -H "ngrok-skip-browser-warning: true" "$public/api/v1/health" | grep -q jobpilot-backend; then
      echo "Backend reachable through the tunnel."
      ./deploy/publish_backend_url.sh "$public" || echo "WARNING: could not publish the backend URL to GitHub Pages (see above)."
    else
      echo "WARNING: tunnel is up but the backend did not answer through it."
    fi
  else
    echo " no tunnel URL (see: docker compose logs ngrok)"
  fi
fi

lan=$(hostname -I 2>/dev/null | awk '{print $1}')
cat <<MSG

JobPilot is running.
  Local UI (this machine) : http://localhost:${FRONTEND_PORT}
  LAN UI (same network)   : http://${lan:-<this-machine-ip>}:${FRONTEND_PORT}
  API docs (this machine) : http://127.0.0.1:${BACKEND_PORT}/api/v1/docs
${public:+  Public backend (ngrok)  : ${public}
  Public UI (GitHub Pages): ${PAGES_URL:-https://<user>.github.io/<repo>/}
}  Registration invite code: ${REGISTRATION_INVITE_CODE:-<none: registration is open>}
Stop with ./deploy/stop.sh (data is kept).
MSG
