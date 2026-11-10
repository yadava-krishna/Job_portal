#!/bin/sh
# Runs backup.sh once a day at BACKUP_TIME (local time, TZ), plus once at start-up when the last good backup is
# older than 26 hours (e.g. the machine was off at the scheduled time).
set -u
TIME="${BACKUP_TIME:-02:30}"
last_ok_age() {  # seconds since the newest daily backup folder, or a large number
  newest=$(ls -1d /backups/daily-* 2>/dev/null | sort | tail -1)
  [ -z "$newest" ] && { echo 999999; return; }
  echo $(( $(date +%s) - $(stat -c %Y "$newest") ))
}
if [ "${1:-}" = "once" ]; then exec /backup/backup.sh "${2:-manual}"; fi
sleep 20
[ "$(last_ok_age)" -gt 93600 ] && /backup/backup.sh daily || true
while true; do
  now=$(date +%s); target=$(date -d "$(date +%Y-%m-%d) $TIME" +%s 2>/dev/null || date -D "%Y-%m-%d %H:%M" -d "$(date +%Y-%m-%d) $TIME" +%s)
  [ "$target" -le "$now" ] && target=$((target + 86400))
  sleep $((target - now))
  /backup/backup.sh daily || true
done
