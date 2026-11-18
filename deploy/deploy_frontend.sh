#!/usr/bin/env bash
# Build the React app and publish it to GitHub Pages (gh-pages branch).
# The backend address is not baked in: the app reads config.json, kept up to date by start.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
( cd frontend && npm ci --no-audit --no-fund && npm test && npm run build )
. ./deploy/_pages_checkout.sh
keep=""
[ -f "$PAGES_DIR/config.json" ] && keep=$(cat "$PAGES_DIR/config.json")
# Keep earlier builds' hashed files under assets/ (a tab still running the previous version loads its page code from
# there); drop ones older than 14 days. Everything else is replaced.
find "$PAGES_DIR" -mindepth 1 -maxdepth 1 ! -name .git ! -name assets -exec rm -rf {} +
mkdir -p "$PAGES_DIR/assets"
find "$PAGES_DIR/assets" -type f -mtime +14 -delete
cp -r frontend/dist/. "$PAGES_DIR/"
touch "$PAGES_DIR/.nojekyll"
if [ -n "$keep" ]; then printf '%s\n' "$keep" > "$PAGES_DIR/config.json"
elif [ -f .deploy/last_published_url ]; then printf '{\n  "apiBaseUrl": "%s"\n}\n' "$(cat .deploy/last_published_url)" > "$PAGES_DIR/config.json"; fi
pages_commit_push "Deploy frontend $(git rev-parse --short HEAD 2>/dev/null || date +%F)"
echo "Frontend published: ${PAGES_URL:-GitHub Pages}"
