#!/bin/sh
# One JobPilot backup, run inside the `backup` container (see docker-compose.yml).
#   /backup/backup.sh [label]      label defaults to "daily"; only "daily-*" folders are ever rotated away.
# Output: /backups/<label>-<UTC timestamp>/
#   jobpilot.dump       pg_dump custom format (restorable with deploy/restore.sh)
#   storage.tar.gz      every user's resumes, exports and reports (the storage volume)
#   counts.txt          row counts per table at backup time (used to verify restores)
#   SHA256SUMS          checksums of the above
# With BACKUP_PASSPHRASE set, the dump and archive are encrypted (AES-256, PBKDF2) as *.enc and the plain files
# are removed. With /offhost mounted to another disk/NAS/cloud-synced folder, a copy is placed there too.
set -eu
LABEL="${1:-daily}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="/backups/${LABEL}-${TS}"
STATUS=/backups/last_backup.json
mkdir -p "$OUT"
fail() { printf '{"status":"failed","at":"%s","label":"%s","error":"%s"}\n' "$TS" "$LABEL" "$1" > "$STATUS"; echo "BACKUP FAILED: $1" >&2; exit 1; }

pg_dump -Fc -f "$OUT/jobpilot.dump" || fail "pg_dump"
pg_restore --list "$OUT/jobpilot.dump" > /dev/null || fail "dump unreadable"
tar -czf "$OUT/storage.tar.gz" -C /data . || fail "storage archive"
psql -At -c "SELECT relname || ' ' || n_live_tup FROM pg_stat_user_tables ORDER BY relname" > "$OUT/counts.txt" 2>/dev/null || true
psql -At -c "SELECT 'users_exact ' || count(*) FROM users; SELECT 'applications_exact ' || count(*) FROM applications; SELECT 'resumes_exact ' || count(*) FROM resumes" >> "$OUT/counts.txt" || fail "counts"

if [ -n "${BACKUP_PASSPHRASE:-}" ]; then
  for f in jobpilot.dump storage.tar.gz; do
    openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_PASSPHRASE -in "$OUT/$f" -out "$OUT/$f.enc" || fail "encrypt $f"
    rm -f "$OUT/$f"
  done
fi
(cd "$OUT" && sha256sum ./* > SHA256SUMS) || fail "checksums"

OFFHOST="no"
[ -d /offhost ] && [ -n "${HOST_UID:-}" ] && chown "${HOST_UID}:${HOST_GID:-$HOST_UID}" /offhost 2>/dev/null || true
if [ -d /offhost ] && [ -w /offhost ] && [ "${BACKUP_OFFHOST:-0}" = "1" ]; then
  cp -r "$OUT" /offhost/ && OFFHOST="yes" || echo "warning: off-host copy failed" >&2
fi

# Rotation: keep BACKUP_KEEP_DAYS of daily backups. Manual/pre-change backups are never deleted automatically.
KEEP="${BACKUP_KEEP_DAYS:-14}"
find /backups -mindepth 1 -maxdepth 1 -type d -name 'daily-*' -mtime "+$KEEP" -exec rm -rf {} + 2>/dev/null || true
[ "$OFFHOST" = "yes" ] && find /offhost -mindepth 1 -maxdepth 1 -type d -name 'daily-*' -mtime "+$KEEP" -exec rm -rf {} + 2>/dev/null || true

SIZE=$(du -sk "$OUT" | cut -f1)
[ -n "${HOST_UID:-}" ] && chown -R "${HOST_UID}:${HOST_GID:-$HOST_UID}" "$OUT" 2>/dev/null || true
printf '{"status":"ok","at":"%s","label":"%s","folder":"%s","size_kb":%s,"encrypted":%s,"offhost":"%s"}\n' \
  "$TS" "$LABEL" "$(basename "$OUT")" "$SIZE" "$([ -n "${BACKUP_PASSPHRASE:-}" ] && echo true || echo false)" "$OFFHOST" > "$STATUS"
[ -n "${HOST_UID:-}" ] && chown "${HOST_UID}:${HOST_GID:-$HOST_UID}" "$STATUS" 2>/dev/null || true
echo "backup ok: $OUT (${SIZE} KB, encrypted=$([ -n "${BACKUP_PASSPHRASE:-}" ] && echo yes || echo no), offhost=$OFFHOST)"
