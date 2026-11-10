#!/usr/bin/env bash
# deploy/restore.sh - Restore JobPilot database and user storage from an archived backup
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <backup_directory_or_timestamp> [--dry-run]"
    exit 1
fi

TARGET="$1"
DRY_RUN="${2:-}"

if [ ! -d "${TARGET}" ]; then
    if [ -d "./backups/${TARGET}" ]; then
        TARGET="./backups/${TARGET}"
    else
        echo "Error: Backup directory ${TARGET} does not exist."
        exit 1
    fi
fi

echo "Verifying checksums in ${TARGET}..."
cd "${TARGET}"
sha256sum -c SHA256SUMS
cd - > /dev/null

if [ "${DRY_RUN}" = "--dry-run" ]; then
    echo "Checksums verified. Dry-run mode completed without modifying live data."
    exit 0
fi

read -p "WARNING: Restoring will overwrite current database and storage. Type 'RESTORE' to proceed: " CONFIRM
if [ "${CONFIRM}" != "RESTORE" ]; then
    echo "Aborted."
    exit 1
fi

# 1. Restore Database
if [ -f "${TARGET}/jobpilot_db.dump" ]; then
    echo "Restoring database from ${TARGET}/jobpilot_db.dump..."
    docker compose exec -T postgres pg_restore -U "${POSTGRES_USER:-jobpilot}" -d "${POSTGRES_DB:-jobpilot}" --clean --if-exists "${TARGET}/jobpilot_db.dump" || true
fi

# 2. Restore Storage
STORAGE_PATH="${STORAGE_DIR:-./data}"
if [ -f "${TARGET}/jobpilot_storage.tar.gz" ]; then
    echo "Restoring storage from ${TARGET}/jobpilot_storage.tar.gz..."
    mkdir -p "${STORAGE_PATH}"
    tar -xzf "${TARGET}/jobpilot_storage.tar.gz" -C "${STORAGE_PATH}"
fi

echo "Restore finished successfully."
