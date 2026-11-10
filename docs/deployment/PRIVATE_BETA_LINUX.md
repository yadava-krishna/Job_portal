# JobPilot private beta on one Linux machine

For 2–4 trusted users. One Linux host, Docker Compose, no domain, no AWS, no inbound ports.
(The PRD's later "20 beta candidates" launch gate is a separate milestone; see `docs/requirements`.)

## Host

| | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 22.04/24.04 LTS (any recent Linux with Docker) | same |
| CPU / RAM | 2 cores / 4 GB | 4 cores / 8 GB |
| Disk | 30 GB free SSD | 50 GB free SSD |
| Network | stable broadband | same; wired preferred |

The host must stay on and awake: disable suspend (`sudo systemctl mask sleep.target suspend.target hibernate.target`),
keep it on mains power, and expect the app to be offline while the machine or its network is down. A Quick Tunnel
has no uptime guarantee.

## Network picture

```
 browser ──HTTPS──▶ public tunnel (ngrok today, or Cloudflare Quick Tunnel) ──▶ host loopback only
                                                                                  │
            ┌──────────────────────── docker network "edge" ─────────────────────┤
            │ frontend (nginx :80, serves the app and proxies /api → backend)    │
            │ backend  (FastAPI :8000, bound to 127.0.0.1 on the host)           │
            └──────────── docker network "internal" (no internet route) ─────────┤
              postgres (no host port)   backup (daily dumps → ./backups)
```

Only the tunnel reaches the app. Postgres has no host port; the backend is bound to 127.0.0.1; there is no Redis,
no exposed Docker daemon and no admin port. JobPilot's own login (and invite-only registration) applies even
behind the tunnel: an obscure URL is not access control.

## Install

```bash
git clone <repo> ~/job_automation && cd ~/job_automation
./deploy/init_env.sh          # creates .env with random secrets (chmod 600); never commit it
./deploy/start.sh             # builds images, runs migrations, starts everything, publishes the tunnel URL
```

Optional settings in `.env`: `NGROK_AUTHTOKEN`/`NGROK_DOMAIN` (tunnel), `SMTP_*` and `PUBLIC_APP_URL` (e-mail reminders and
password reset), `BACKUP_PASSPHRASE` (encrypt backups), `BACKUP_OFFHOST=1` + `BACKUP_OFFHOST_DIR` (copy backups to
another disk or a synced folder), `ANTHROPIC_API_KEY` + `PORTAL_LLM_PROVIDER` (AI-assisted scoring; rule-based otherwise).

### Tunnel options

* **ngrok (current)** — `docker compose --profile tunnel up -d`. Free URLs change on restart; `deploy/url_watch.sh`
  republishes the address for the GitHub Pages front end (install its cron line once, see `DEPLOYMENT.md`).
  A reserved `NGROK_DOMAIN` keeps one stable URL.
* **Cloudflare Quick Tunnel (hosting plan §16)** — `docker compose --profile quicktunnel up -d`, then read the
  `https://…trycloudflare.com` address from `docker compose logs cloudflared`. It points at nginx, so the app and
  `/api` share one address. Limits: the URL changes on every restart, no uptime guarantee, a cap on concurrent
  requests, and no server-sent events. JobPilot only uses ordinary requests and polling, so nothing depends on SSE.
  For a closed beta you can add Cloudflare's e-mail allow-list for Quick Tunnels in front, as well as JobPilot's login.

After a tunnel URL change: open the new URL, log in, and re-pair the browser extension if you use it (pairing is
tied to the JobPilot account, not the URL, but the extension needs the new address).

## Health and diagnostics

```bash
curl -s http://127.0.0.1:8000/api/health      # app, database, scheduler (no secrets)
docker compose ps                               # every service should be "healthy"/"Up"
docker compose logs --tail 100 backend          # structured logs; tokens and resume text are redacted
```
The admin page (**Admin → System**) shows disk use (warnings at 70/80/90%) and the last backup.
**Admin → Background jobs** shows every scheduled job, its last result and errors, and can re-run one.

## Backups and restore

* The `backup` service makes a daily backup at `BACKUP_TIME` (default 02:30) of the database **and** the uploads
  volume, with row counts and checksums, keeps `BACKUP_KEEP_DAYS` (default 14) of daily backups and never deletes
  manual ones. It also catches up at start-up if the machine was off.
* Take one now: `./deploy/backup.sh before-upgrade`.
* Prove a backup restores (live data untouched): `./deploy/restore.sh backups/<folder> --check`.
* Restore for real (asks for `RESTORE`, takes a safety backup first): `./deploy/restore.sh backups/<folder>`.
* Off-host copy: mount another disk or a cloud-synced folder and set `BACKUP_OFFHOST=1`, `BACKUP_OFFHOST_DIR=/path`;
  with `BACKUP_PASSPHRASE` set, the off-host copy is encrypted (AES-256). Keep the passphrase somewhere else.

**Recovery objectives (beta):** RPO ≈ 24 h (last daily backup; take a manual one before risky changes), RTO ≈ 1 h
on a prepared machine.

### Moving to a second machine
1. Install Docker and clone the repo on the new machine; copy `.env` securely (or recreate it and keep the old
   `POSTGRES_PASSWORD`/`JWT_SECRET`/`ENCRYPTION_KEY` — the encryption key is needed for stored mailbox passwords).
2. Copy the latest backup folder to `backups/` and run `./deploy/start.sh`, then `./deploy/restore.sh backups/<folder>`.
3. Start the tunnel and log in with an existing account; check resumes download and jobs/applications are present.

## Updating and rolling back

```bash
./deploy/backup.sh pre-update                   # 1. backup
git pull                                        # 2. new code
docker tag jobpilot-backend:latest jobpilot-backend:previous   # 3. keep the last good image
docker compose build backend && docker compose up -d backend backup   # 4. migrations run on start
curl -s http://127.0.0.1:8000/api/health        # 5. verify, then log in and check a job and a resume
```
Rollback: `docker tag jobpilot-backend:previous jobpilot-backend:latest && docker compose up -d backend`, and if a
migration must be undone, restore the pre-update backup with `deploy/restore.sh`. Migrations are additive.

## Reboots

All services use `restart: unless-stopped`, and Docker starts at boot, so the stack returns after a reboot. Test it
once: reboot, then check `docker compose ps` and `/api/health`.

## Development vs beta

Development uses `.venv` + SQLite (`uvicorn backend.main:app --reload`, `npm run dev`) and test fixtures; the beta
uses the Compose stack with Postgres, real secrets in `.env`, `DOCS_MODE=local` (API docs only from the host) and
the backup service.
