#!/usr/bin/env bash
# deploy/backup.sh - Automated PostgreSQL and storage volume backup for JobPilot
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
TARGET_DIR="${BACKUP_DIR}/${TIMESTAMP}"
mkdir -p "${TARGET_DIR}"

echo "Starting JobPilot backup to ${TARGET_DIR}..."

# 1. PostgreSQL Database Dump (Custom format with compression)
if docker compose ps postgres | grep -q "Up"; then
    echo "Dumping PostgreSQL database..."
    docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-jobpilot}" -Fc "${POSTGRES_DB:-jobpilot}" > "${TARGET_DIR}/jobpilot_db.dump"
else
    echo "Warning: postgres container not running; skipping live DB dump."
fi

# 2. Storage Directory / Resumes
STORAGE_PATH="${STORAGE_DIR:-./data}"
if [ -d "${STORAGE_PATH}" ]; then
    echo "Archiving storage directory..."
    tar -czf "${TARGET_DIR}/jobpilot_storage.tar.gz" -C "${STORAGE_PATH}" .
fi

# 3. Compute Checksums
cd "${TARGET_DIR}"
sha256sum * > SHA256SUMS
cd - > /dev/null

echo "Backup completed successfully at ${TARGET_DIR}:"
ls -lh "${TARGET_DIR}"

# 4. Prune old backups (keep last 7 days)
find "${BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf {} +
echo "Pruned backups older than 7 days."
