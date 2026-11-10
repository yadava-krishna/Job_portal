#!/usr/bin/env bash
# Restore JobPilot from a backup folder made by the backup service (or deploy/backup.sh).
#
#   ./deploy/restore.sh <backup-folder> --check      verify checksums and restore into a throw-away database,
#                                                     comparing row counts with the backup (live data untouched)
#   ./deploy/restore.sh <backup-folder>               replace the LIVE database and uploads (asks for RESTORE)
#
# Encrypted backups (*.enc) need BACKUP_PASSPHRASE in the environment or in .env.
# Before replacing live data a safety backup is taken first, so a restore can itself be undone.
set -euo pipefail
cd "$(dirname "$0")/.."
[ $# -ge 1 ] || { sed -n '2,10p' "$0"; exit 1; }
SRC="$1"; MODE="${2:-live}"
[ -d "$SRC" ] || SRC="backups/$1"
[ -d "$SRC" ] || { echo "No such backup folder: $1" >&2; exit 1; }
SRC="$(cd "$SRC" && pwd)"
set -a; [ -f .env ] && . ./.env; set +a
PGUSER_="${POSTGRES_USER:-jobpilot}"; PGDB_="${POSTGRES_DB:-jobpilot}"

echo "Verifying checksums in $SRC"
(cd "$SRC" && sha256sum -c --quiet SHA256SUMS)

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
plain() {  # path to the plain (decrypted) copy of jobpilot.dump / storage.tar.gz
  local f="$1"
  if [ -f "$SRC/$f" ]; then echo "$SRC/$f"; return; fi
  [ -f "$SRC/$f.enc" ] || { echo "Missing $f in $SRC" >&2; exit 1; }
  [ -n "${BACKUP_PASSPHRASE:-}" ] || { echo "$f is encrypted: set BACKUP_PASSPHRASE" >&2; exit 1; }
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$SRC/$f.enc" -out "$WORK/$f"
  echo "$WORK/$f"
}
DUMP="$(plain jobpilot.dump)"; ARCHIVE="$(plain storage.tar.gz)"
tar -tzf "$ARCHIVE" > /dev/null

if [ "$MODE" = "--check" ]; then
  NAME="jp-restore-check-$$"
  echo "Restoring into a temporary database ($NAME)…"
  docker run -d --rm --name "$NAME" -e POSTGRES_PASSWORD=check -e POSTGRES_USER="$PGUSER_" -e POSTGRES_DB="$PGDB_" postgres:16-alpine > /dev/null
  trap 'docker rm -f "$NAME" >/dev/null 2>&1; rm -rf "$WORK"' EXIT
  for _ in $(seq 1 60); do docker exec "$NAME" pg_isready -U "$PGUSER_" -d "$PGDB_" >/dev/null 2>&1 && break; sleep 1; done
  sleep 2
  docker exec -i "$NAME" pg_restore -U "$PGUSER_" -d "$PGDB_" --no-owner --exit-on-error < "$DUMP"
  status=0
  while read -r key expected; do
    case "$key" in *_exact) table="${key%_exact}";; *) continue;; esac
    got=$(docker exec "$NAME" psql -U "$PGUSER_" -d "$PGDB_" -At -c "SELECT count(*) FROM $table")
    if [ "$got" = "$expected" ]; then echo "  $table: $got rows (matches backup)"; else echo "  $table: $got rows, backup recorded $expected" >&2; status=1; fi
  done < "$SRC/counts.txt"
  files=$(tar -tzf "$ARCHIVE" | grep -c '^\./users/.*/resumes/.' || true)
  echo "  uploads archive: $files resume file(s)"
  [ $status -eq 0 ] && echo "RESTORE CHECK PASSED for $(basename "$SRC")" || { echo "RESTORE CHECK FAILED" >&2; exit 1; }
  exit 0
fi

echo "This replaces the LIVE JobPilot database and uploads with $(basename "$SRC")."
read -r -p "Type RESTORE to continue: " CONFIRM
[ "$CONFIRM" = "RESTORE" ] || { echo "Aborted."; exit 1; }
echo "Taking a safety backup of the current state first…"
docker compose run --rm backup once "pre-restore" > /dev/null
docker compose stop backend
docker compose exec -T postgres psql -U "$PGUSER_" -d "$PGDB_" -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker compose exec -T postgres pg_restore -U "$PGUSER_" -d "$PGDB_" --no-owner --exit-on-error < "$DUMP"
docker run --rm -i -v jobpilot_storage:/data alpine sh -c 'find /data -mindepth 1 -delete && tar -xzf - -C /data && chown -R 10001:10001 /data' < "$ARCHIVE"
docker compose start backend
echo "Restore finished. Check: curl -s http://127.0.0.1:${BACKEND_PORT:-8000}/api/health"
