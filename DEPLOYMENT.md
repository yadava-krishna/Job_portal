# Deploying, recovering and rolling back JobPilot

Applies from Phase 3 (2026-11-05). Never run `docker compose down -v` or delete the `jobpilot_pgdata` /
`jobpilot_storage` volumes: they hold all users, resumes and history.

## 1. Before every deployment

```bash
cd ~/job_automation
TS=$(date +%Y%m%d-%H%M%S); B=backups/$TS-pre-<change>; mkdir -m 700 -p "$B"
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$B/jobpilot.dump"
# storage volume (files are owned by the container user, so read them as that user and redirect on the host)
docker run --rm --user 10001 -v jobpilot_storage:/data:ro alpine tar -czf - -C /data . > "$B/storage.tar.gz"
(cd "$B" && sha256sum jobpilot.dump storage.tar.gz > SHA256SUMS) && chmod 600 "$B"/* && echo "$B" > .deploy/last_backup
```
Always use the explicit `$B`. Never reuse "the latest folder" as a fallback (see the incident in PHASE3_TEST_REPORT.md §6).
Restore-check the dump into a scratch Postgres (not port 55432 while FurCare's Postgres runs) and compare row counts.
If the release adds migrations, run `alembic upgrade head` on that restored copy first.

## 2. Deploy

```bash
./deploy/start.sh            # rebuilds backend + web UI images, applies migrations, restarts, republishes the tunnel URL
./deploy/deploy_frontend.sh  # tests, builds and publishes the React app to GitHub Pages
```
`.env` must contain the extension origin in `CORS_ORIGINS` (see `.env.example`).

Then verify `/api/v1/health` through the tunnel, the web app login, and (optionally) `extension/e2e/prod_check.py`.
That script creates a temporary account. Delete it afterwards: users rows, `/data/users/<id>`, and its audit entries.

## 3. Automatic recovery

- Containers use `restart: unless-stopped`, and Docker starts at boot, so after a crash or reboot everything comes
  back by itself in order: Postgres, then backend, then web UI and tunnel. Each waits for the previous one to be
  healthy. `./deploy/stop.sh` is a deliberate stop and stays stopped.
- Runs interrupted by a restart are marked failed at start-up. A missed 09:00 daily discovery is run once as
  "catch_up" shortly after start-up, and never if it already ran that day.
- **The tunnel address changes on every restart** with a free random ngrok URL. Two options:
  1. **Recommended, free:** ngrok gives every free account one static domain. Copy it from
     https://dashboard.ngrok.com/domains into `.env` as `NGROK_DOMAIN=…ngrok-free.app` and run `./deploy/start.sh`.
     The URL then never changes. No purchase is needed.
  2. **Until then:** let cron republish the address. Run these yourself; the assistant's attempt to edit your
     crontab was blocked:
     ```bash
     (crontab -l 2>/dev/null; \
      echo "@reboot $HOME/job_automation/deploy/url_watch.sh --boot"; \
      echo "*/10 * * * * $HOME/job_automation/deploy/url_watch.sh") | crontab -
     ```
     `url_watch.sh` never starts or stops containers. It only republishes `config.json` when the tunnel URL changed
     and the backend answers through it. Its log is `.deploy/url_watch.log`.

## 4. Reboot test (to do once)

After a reboot, without running anything:
```bash
docker ps --format '{{.Names}} {{.Status}}'          # four jobpilot-* containers, "Up … (healthy)"
curl -s "$(cat .deploy/last_published_url)/api/v1/health" -H 'ngrok-skip-browser-warning: 1'
curl -s https://yadava-krishna.github.io/Job_portal/config.json   # matches the tunnel (after the cron job ran, or NGROK_DOMAIN)
```

## 5. Rollback

Phase 3 has **no database migration**, so code rollback is safe with the current data:
```bash
git checkout 635a177 -- .           # last Phase 2 commit (or: git revert <phase-3 commits>)
./deploy/start.sh && ./deploy/deploy_frontend.sh
```
- Data written by Phase 3 is harmless to Phase 2 code: extension credentials sit in `extension_tokens`; profile links,
  answer bank and notification preferences sit in JSON fields that older code ignores. Disconnect browsers first if
  you roll back, so no credential outlives the feature.
- Remove the extension origin from `CORS_ORIGINS` if the extension is withdrawn.
- **Data restore** (only if data was damaged):
  ```bash
  ./deploy/stop.sh
  docker compose up -d postgres
  docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < backups/<folder>/jobpilot.dump
  docker run --rm -v jobpilot_storage:/data -v "$PWD/backups/<folder>":/b alpine sh -c 'tar -xzf /b/storage.tar.gz -C /data'
  ./deploy/start.sh
  ```

## 6. Extension releases

`cd extension && npm test && npm run package`, then share `dist/fill-with-jobpilot-<version>.zip` (unpacked install).
Keep `.deploy/extension-key.pem` private and backed up. It fixes the extension ID and therefore the allowed CORS
origin. For a Chrome Web Store listing (needs the owner's approval and developer account), remove `"key"` from
`manifest.json`, upload the zip, then add the store-assigned ID to `CORS_ORIGINS`.

---

## 7. Automated Backups & Safe Restore (Added in Session 2026-11-06)

Phase 8 automated backup and recovery with dedicated shell scripts:

### Running an automated backup:
```bash
./deploy/backup.sh
```
- Performs a live `pg_dump -Fc` from the Postgres container.
- Creates a timestamped tarball of `/data` from the `jobpilot_storage` volume.
- Generates `SHA256SUMS` verification hash.
- Prunes backups older than 7 days (`RETENTION_DAYS=7`).
- Recommended daily cron entry:
  ```bash
  0 2 * * * $HOME/job_automation/deploy/backup.sh >> $HOME/job_automation/backups/backup.log 2>&1
  ```

### Restoring from backup:
```bash
# Dry run verification:
./deploy/restore.sh --dry-run backups/20261106-120000

# Full restoration:
./deploy/restore.sh backups/20261106-120000
```
- Validates SHA256 checksums before touching any live services.
- Halts backend gracefully, applies `pg_restore --clean --if-exists`, unpacks storage volume, and restarts services.

---

## 8. Scrapling Runtime Dependencies (Added in Session 2026-11-06)
- Backend dependency `scrapling[fetchers]==0.5.1` is installed in `.venv` and Docker backend image.
- Includes `patchright` (Patchright stealth browser driver) and `curl_cffi` for TLS-fingerprinted HTTP/2 requests.
- No Redis/RabbitMQ brokers required: concurrency is bounded in-process via `asyncio.Semaphore(4)`.

