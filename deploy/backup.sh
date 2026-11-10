#!/usr/bin/env bash
# Take a backup now (same code as the scheduled daily backup). Optional label, e.g. ./deploy/backup.sh pre-upgrade
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose run --rm backup once "${1:-manual}"
