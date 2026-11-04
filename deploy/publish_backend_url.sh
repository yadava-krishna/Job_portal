#!/usr/bin/env bash
# Publish the current backend URL as config.json on the GitHub Pages branch (only if it changed).
set -euo pipefail
cd "$(dirname "$0")/.."
url="${1:?usage: publish_backend_url.sh https://<tunnel-host>}"
set -a; [ -f .env ] && . ./.env; set +a
mkdir -p .deploy
if [ -f .deploy/last_published_url ] && [ "$(cat .deploy/last_published_url)" = "$url" ]; then
  echo "Backend URL unchanged ($url); nothing to publish."; exit 0
fi
. ./deploy/_pages_checkout.sh
printf '{\n  "apiBaseUrl": "%s"\n}\n' "$url" > "$PAGES_DIR/config.json"
pages_commit_push "Point frontend at backend $url"
echo "$url" > .deploy/last_published_url
echo "Published backend URL to ${PAGES_URL:-GitHub Pages} (the Pages CDN may take a few minutes to refresh)."
