#!/usr/bin/env bash
# Creates .env with random secrets (first run only). Never overwrites an existing .env.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .env ] && grep -q '^JWT_SECRET=' .env; then echo ".env already exists; leaving it unchanged."; exit 0; fi
[ -f .env ] || cp .env.example .env
rand() { python3 -c "import secrets;print(secrets.token_urlsafe($1))"; }
fernet() { python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"; }
set_var() { # set_var NAME VALUE (replace or append)
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi
}
set_var POSTGRES_PASSWORD "$(rand 24)"
set_var JWT_SECRET "$(rand 48)"
set_var ENCRYPTION_KEY "$(fernet)"
set_var REGISTRATION_INVITE_CODE "jobpilot-$(rand 6)"
token=$(sed -n 's/^ *authtoken: *//p' ~/.config/ngrok/ngrok.yml 2>/dev/null | head -1 || true)
[ -n "$token" ] && set_var NGROK_AUTHTOKEN "$token"
# Default UI port 3000 is often taken (e.g. by a dev server); pick the first free one.
for port in 3000 3080 3081 3090; do
  if ! ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then set_var FRONTEND_PORT "$port"; break; fi
done
chmod 600 .env
echo "Created .env with fresh secrets (chmod 600). Invite code: $(sed -n 's/^REGISTRATION_INVITE_CODE=//p' .env)"
