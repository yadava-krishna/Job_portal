#!/usr/bin/env bash
# Stop all JobPilot containers. Volumes (database, resumes, reports) are kept.
# Never run `docker compose down -v`: it deletes the database volume.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
docker compose --profile tunnel down
for port in "${BACKEND_PORT:-8000}" "${FRONTEND_PORT:-3000}" "${NGROK_INSPECT_PORT:-4041}"; do
  if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN && docker ps --format '{{.Ports}}' | grep -q ":$port->"; then
    echo "WARNING: port $port is still held by a container"; fi
done
echo "Stopped. Data volumes kept: $(docker volume ls -q --filter name=jobpilot_ | tr '\n' ' ')"
echo "The portal now shows 'JOB PORTAL OFFLINE' to users until ./deploy/start.sh is run again."
