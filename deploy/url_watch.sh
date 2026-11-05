#!/usr/bin/env bash
# Keep the GitHub Pages frontend pointed at the backend after restarts (run by cron: at boot and every 10 minutes).
#
# Docker restarts the containers by itself (restart: unless-stopped). With a free random ngrok address, the tunnel
# URL changes on every restart; this script republishes config.json when it changed and the backend answers through
# it. It never starts or stops containers, so a deliberate ./deploy/stop.sh stays stopped. With NGROK_DOMAIN set in
# .env the address never changes and this does nothing.
set -uo pipefail
cd "$(dirname "$0")/.."
LOG=.deploy/url_watch.log
mkdir -p .deploy
log() { echo "$(date -Is) $*" >> "$LOG"; tail -n 500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; }
exec 9>.deploy/url_watch.lock
flock -n 9 || exit 0
set -a; [ -f .env ] && . ./.env; set +a
INSPECT=${NGROK_INSPECT_PORT:-4041}
for i in $(seq 1 30); do  # at boot, give Docker time to bring the tunnel up
  public=$(curl -fsS "http://127.0.0.1:${INSPECT}/api/tunnels" 2>/dev/null | python3 -c "import sys,json; t=[x['public_url'] for x in json.load(sys.stdin).get('tunnels',[]) if x['public_url'].startswith('https://')]; print(t[0] if t else '')" 2>/dev/null || true)
  [ -n "$public" ] && break
  [ "${1:-}" = "--boot" ] || exit 0  # not at boot: tunnel down (stopped on purpose?) → nothing to do
  sleep 10
done
[ -z "${public:-}" ] && { log "no tunnel after boot wait"; exit 0; }
[ -f .deploy/last_published_url ] && [ "$(cat .deploy/last_published_url)" = "$public" ] && exit 0
if curl -fsS -m 15 -H "ngrok-skip-browser-warning: true" "$public/api/v1/health" | grep -q jobpilot-backend; then
  if ./deploy/publish_backend_url.sh "$public" >> "$LOG" 2>&1; then log "published $public"; else log "publish FAILED for $public"; fi
else
  log "tunnel $public up but backend not answering yet"
fi
