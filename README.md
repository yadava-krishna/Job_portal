# JobPilot: multi-user job application portal

A self-hosted web portal on top of the job-automation engine in this repository. Each user uploads their resume, reviews the parsed profile, sets preferences and job portals, then discovers jobs with **per-user, explainable match scores**. They apply **on the original platform** and track every application.

* **Frontend:** React + TypeScript + Vite + Tailwind + shadcn/ui, hosted on **GitHub Pages**
* **Backend:** FastAPI + SQLAlchemy + Alembic + **PostgreSQL**, running on the owner's Ubuntu machine in **Docker**, exposed over **HTTPS through ngrok**
* **Engine:** the existing modules (resume parser, JD analyser, matcher, eligibility, screening answers, Excel reports), reused unchanged

```
Browser ──► GitHub Pages (static app + config.json)            ┌─ postgres (internal network only)
   └────► https://<tunnel>.ngrok-free.app ──► ngrok agent ──► backend ─┤
                                     LAN users ──► :FRONTEND_PORT nginx ┘   (same-origin /api proxy)
```

## What it does (and deliberately does not do)

| | |
|---|---|
| Accounts | Register (optional invite code), login, rotating refresh tokens, Argon2id passwords, per-user data isolation on every query |
| Onboarding | Resume PDF upload → parsed with the existing parser → **editable** profile → preferences (multiple domains and roles) → platform selection → confirm |
| Automated discovery | **Official employer job boards** (Greenhouse, Lever, Ashby public job-board APIs): every user gets a starter saved search built from their preferences over a curated, live-verified list of employers hiring in India, run daily and on demand ("Run discovery now"). Users can add any company by its careers-page link, browse a 5,400-board directory (JobSync data, MIT), and create their own saved searches. Jobs are normalised to one schema, deduplicated across sources, scored against the user's resume, and marked "No longer listed" when they leave the board |
| Other sources | **Browser clipper** (one click on a LinkedIn/Indeed/Naukri page you are viewing, in your own logged-in browser) · paste URL + description · JSON/CSV/TXT import · your own **job-alert emails** (IMAP, read-only, encrypted app password) · optional **Adzuna official API** (needs `ADZUNA_APP_ID`/`ADZUNA_APP_KEY`) · pre-filtered search links |
| Honest outcomes | Every discovery run records each source's result (found / reached-no-match / partly failed / failed / not configured / turned off) and a plain-language summary. A run where nothing could run is **failed**, never "completed". The **Source health** panel shows configuration, connection, last attempt/success, jobs found and what's missing |
| Matching | Existing engine per user: skills 35, experience 25, responsibilities 20, education 10, location/preferences 10 (weights editable). Excellent ≥85, Good 70–84, Moderate 55–69, Low <55 |
| Dates | Every card shows the posting date with a confidence chip (Verified / Estimated / Unknown) and when JobPilot found it. Date filters (today, 24 h, 3/7/30 days, range) only count dates we can vouch for; jobs with unknown dates are counted ("N hidden… show them") rather than silently dropped or shown as recent |
| Apply | Prepare (checklist, screening answers with `NEEDS_CANDIDATE_INPUT` where unknown, resume, optional cover letter) → open the original listing → you submit there → come back and confirm. **Opening is never counted as applying** |
| Tracking | Saved, Applications (list, **pipeline board**: Applied → Screening → Interview → Offer/Rejected, event history), dashboard analytics, per-user Excel reports (daily and full history) |
| Availability | The UI polls `/api/v1/health` every 5–10 s. When the backend (or its database) is down it shows **JOB PORTAL OFFLINE**, disables everything, and reconnects automatically |
| Not done | No scraping, crawling or browser automation of LinkedIn, Indeed, Naukri or any job site (their terms prohibit it), no use of anyone's session cookies, no automated submission, no CAPTCHA/OTP bypass |

Ideas adapted (not copied) from [alexmc2/jobs-tracker](https://github.com/alexmc2/jobs-tracker): pipeline board with event log, quick manual import, fit-assessment panel, keyboard shortcuts on the job list (`j`/`k`/`o`/`s`/`a`/`d`), funnel and per-source analytics, onboarding gate, and the Adzuna source. See `IMPLEMENTATION_PLAN.md`.

## Run it (owner's Ubuntu machine)

```bash
cd ~/job_automation
./deploy/start.sh      # first run creates .env with random secrets and an invite code, builds and starts everything
./deploy/stop.sh       # stops everything; data is kept
```

`start.sh` waits for the backend, opens the ngrok tunnel, checks the backend through it, and **publishes the tunnel URL** to `config.json` on GitHub Pages when it changes. Plain Compose also works:

```bash
docker compose --profile tunnel up -d --build   # with the tunnel
docker compose up -d --build                    # LAN only
docker compose ps
docker compose logs -f            # or: docker compose logs -f backend
docker compose restart backend
docker compose down               # NEVER `down -v`: that deletes the database volume
```

Data lives in Docker volumes `jobpilot_pgdata` (PostgreSQL) and `jobpilot_storage` (resumes, Excel reports and logs under `/data/users/<id>/`). Both survive restarts, rebuilds and `down`. Back up with `docker compose exec postgres pg_dump -U jobpilot jobpilot > backup.sql`.

Restart policy is `on-failure`: crashed containers restart, but nothing auto-starts at boot. Run `start.sh` when you want the portal online. Containers have CPU and memory caps.

### Hosting modes

* **Remote (default): GitHub Pages + ngrok.** Users open `PAGES_URL`. The app reads the backend address from `config.json`. Everything is HTTPS end to end. On ngrok's free plan the URL changes whenever the tunnel restarts. To keep it fixed, claim your free static domain at <https://dashboard.ngrok.com/domains> and set `NGROK_DOMAIN` in `.env`. Users can also set an address under *Backend address* on the offline screen or *Settings → Account & connection*, or open the site with `?api=https://…`.
* **LAN.** On the same network, users open `http://<this-machine-ip>:FRONTEND_PORT`. nginx serves the app and proxies `/api` to the backend, so no CORS or tunnel is needed. Remote users should not use plain-HTTP LAN mode; use the HTTPS tunnel or a VPN.

PostgreSQL never has a host port. The backend binds to `127.0.0.1` only and is reachable from outside **only** through the tunnel.

### Configuration (`.env`, created by `deploy/init_env.sh`, mode 600, never committed)

| Variable | Purpose |
|---|---|
| `POSTGRES_PASSWORD`, `JWT_SECRET`, `ENCRYPTION_KEY` | Generated secrets (changing `JWT_SECRET` signs everyone out; `ENCRYPTION_KEY` protects stored IMAP passwords) |
| `REGISTRATION_INVITE_CODE` | Required to register. Share it only with the people you invite (empty means open registration) |
| `CORS_ORIGINS` | Browser origins allowed to call the API (GitHub Pages and the local UI) |
| `NGROK_AUTHTOKEN`, `NGROK_DOMAIN` | Tunnel (token copied from `~/.config/ngrok/ngrok.yml`) |
| `PORTAL_LLM_PROVIDER` + `ANTHROPIC_API_KEY` | `rule_based` (default) or `anthropic` for AI scoring |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Optional official job API (free keys at developer.adzuna.com) |
| `SCHEDULER_RUN_TIME` | Daily background discovery (alert emails and Adzuna) plus a daily report for every onboarded user |
| `FRONTEND_PORT`, `BACKEND_PORT` | Local ports (the UI picks a free port if 3000 is taken) |
| `PAGES_REPO`, `PAGES_SSH_KEY`, `PAGES_URL` | GitHub Pages deployment |

### Deploy or update the frontend

```bash
./deploy/deploy_frontend.sh     # npm ci, tests, build, push to the gh-pages branch (keeps config.json)
```

### The browser clipper

*Settings → Platforms* (also shown during onboarding) has a **"Clip to JobPilot"** button to drag onto the bookmarks bar. On a LinkedIn, Indeed or Naukri job page, click the bookmark. It reads that page only (schema.org data first, then page elements, then any text you selected) and opens JobPilot with the job prefilled for review. It runs only when clicked. Captured data travels in the URL fragment, which is never sent to a server, and cookies and passwords never leave the browser. If a site changes its layout, select the description text before clicking.

## API

OpenAPI docs: `http://127.0.0.1:8000/api/v1/docs` (or `<tunnel>/api/v1/docs`). Main groups: `auth`, `health`, `profile` / `preferences` / `platforms` / `integrations`, `jobs` (discover, import, list with filters, detail, analysis, save, dismiss, description), `applications` (prepare, open, confirm, pending, fail, withdraw, stage, tracking, apply-options), `reports`, `dashboard`, `companies` / `saved-searches` / `notifications` (incl. preferences) / `discovery/sources`, and `extension` (pairing-codes, devices, pair, rotate, disconnect, status, match, autofill-profile, answers, resume, applications/start, applications/{id}/confirm). Profile also has `profile/resumes` (versions, default, rename, file, delete).

**Fill with JobPilot** browser extension: see [extension/README.md](extension/README.md). Discovery sources and their limits: [SOURCE_CAPABILITY_MATRIX.md](SOURCE_CAPABILITY_MATRIX.md). Deploy, recovery and rollback: [DEPLOYMENT.md](DEPLOYMENT.md).

## Security summary

Argon2id hashing and a password policy · 15-minute JWT access tokens · rotating refresh tokens stored hashed, with reuse detection that revokes the session family · auth rate limiting · optional invite-only registration · strict CORS allowlist · every user-data query scoped by the token's user ID (other users' records return 404) · uploads checked for size, `%PDF` magic, a PyMuPDF open, encryption and page count, and stored under server-generated names in `storage/users/<id>/resumes/` · file downloads served only via database ownership and a path check · IMAP passwords encrypted with Fernet · no secrets in logs · security headers · Postgres on an internal-only network.

## Tests

```bash
.venv/bin/python -m pytest                       # CLI and API tests (SQLite)
TEST_POSTGRES_URL=postgresql+psycopg://… .venv/bin/python -m pytest tests/api   # API tests on PostgreSQL + Alembic
cd frontend && npm test && npm run build          # cards, run outcomes, source health, offline logic, clipper, build
```

Discovery documentation: `DISCOVERY_DIAGNOSTIC_REPORT.md` (why the feed was empty), `DISCOVERY_SOURCE_STATUS.md` (sources, companies, configuration), `DISCOVERY_TEST_REPORT.md` (tests and live verification).

Moving the CLI's SQLite history into a portal account:

```bash
docker compose exec backend python -m backend.scripts.import_sqlite --sqlite /path/in/container.db --email you@example.com --dry-run
```

---

## Part 2: Command-line automation (single candidate)

A local Python application that runs every morning (09:00 IST by default). It:

1. parses the candidate's PDF resume into a structured profile (experience is calculated from employment dates, and overlapping periods are counted once),
2. collects jobs for **LinkedIn, Indeed and Naukri** from permitted sources,
3. deduplicates them in SQLite (platform plus job ID, or a normalised company/title/URL hash),
4. scores each job 0–100 against the resume with an explainable, weighted model (LLM or rule-based),
5. applies hard eligibility rules separately from the score,
6. prepares application packages (resume, screening answers, optional cover letter) and asks for approval,
7. records submissions **only with confirmation evidence**,
8. writes a new Excel workbook every day and keeps logs.

## Platform access: what is automated and what is not

None of the three platforms offers job seekers an API for searching or applying, and all three prohibit scraping and bots. This project therefore **does not scrape, automate a browser, use private APIs, or submit applications on these platforms**. That is a deliberate constraint, not a missing feature.

| Step | How it works | Human needed? |
|---|---|---|
| Discover jobs | (a) the candidate's own job-alert emails from LinkedIn, Indeed and Naukri, read read-only over IMAP; (b) jobs you import (JSON/CSV/TXT files or `add-job`); (c) pre-filtered search links you open and review | Set up alerts and the mailbox once. Paste job descriptions for jobs you want fully scored |
| Job descriptions | Taken only from what you import. Alert emails contain title, company and location, not the full description | Use `add-jd` to attach a description |
| Scoring, eligibility, dedup, reports | Fully automatic | No |
| Submission | **Assisted**: the package is prepared and the job page opens; you submit on the platform (Easy Apply, Indeed Apply, Naukri Apply) | Yes |
| Confirmation | Automatic when a platform confirmation email ("Your application was sent to …") matches; otherwise you run `mark-submitted` with a reference ID or the confirmation text | Sometimes |
| Naukri's own assistant / auto-apply features | Configured by the candidate inside their Naukri account. This tool cannot see or control them | Yes |

`PERMITTED_AUTO_APPLY` mode exists and is wired end to end (state machine, verification, and stopping on security challenges), but it only submits through an adapter that declares an authorised mechanism (`capabilities.automated_apply = True` with a real `submit_application`). **No adapter does today**, so in this mode jobs fall back to assisted submission and the report says so. CAPTCHA, OTP and login challenges are never bypassed.

---

## 1. Install (Ubuntu)

```bash
cd ~/job_automation
python3 -m venv .venv            # Python 3.12+ (if venv is missing: sudo apt install python3-venv)
.venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env
.venv/bin/python -m pytest       # optional: run the test suite
```

## 2. Configure the resume path

In `config/settings.yaml`:

```yaml
candidate:
  resume_path: "/absolute/path/to/resume.pdf"
```

Or set `RESUME_PATH="/absolute/path/to/resume.pdf"` in `.env`, which overrides the YAML. Then check the parse:

```bash
.venv/bin/python main.py profile            # add --refresh to force a rebuild
```

The profile is cached at `~/Job_Applications/cache/candidate_profile.json` and rebuilt automatically when the PDF changes (SHA-256). If a field is parsed wrongly, correct it in `config/candidate_profile.json` → `profile_overrides`, using only facts that are on the resume.

**Verified answers.** Fill in `config/candidate_profile.json` → `verified_facts` (current/expected CTC, notice period, relocation, work authorization, start date, shifts) only with values the candidate has confirmed. Any field left `null` produces `NEEDS_CANDIDATE_INPUT` and is never guessed.

## 3. Configure job preferences

Everything lives in `config/settings.yaml` and is validated at startup (typos and invalid values fail with a clear message):

| Setting | Section |
|---|---|
| Job titles, locations, posted-within hours, experience range, minimum salary, employment types, work modes | `search` |
| Match threshold, component weights, category boundaries | `matching` |
| Hard rules: max experience gap, allowed modes/types/cities, excluded companies and title words, qualifications the candidate lacks, max job age | `eligibility` |
| Mode, max applications per day, reprocessing, cross-platform duplicate blocking, cover letters | `applications` |
| Enable or disable LinkedIn / Indeed / Naukri | `platforms` |
| Import inbox, email alerts (IMAP host/folder/lookback) | `sources` |
| LLM provider/model/effort, concurrency, fallback | `llm` |
| Daily time, catch-up after downtime, retries | `scheduler` |

Application modes: `DISCOVERY_ONLY` (score and report only), `ASSISTED` (prepare, then you submit), `APPROVAL_REQUIRED` (**default**: prepare, you approve, then you submit), `PERMITTED_AUTO_APPLY` (see above).

## 4. Credentials (kept in `.env` only)

* **`ANTHROPIC_API_KEY`** for AI matching (default model `claude-opus-5`, effort `medium`; requests use Anthropic's server-side refusal fallback). Without a key, the transparent rule-based scorer is used and each job shows which method scored it. To use a local model instead, set `llm.provider: openai_compatible` and `llm.base_url` (for example a local Ollama container's `/v1` endpoint).
* **`IMAP_USERNAME` / `IMAP_PASSWORD`** to read job alerts and confirmation emails. For Gmail, use an *App Password*. The mailbox is opened read-only and messages are fetched with `BODY.PEEK`, so nothing is marked as read.

Secrets, cookies, email addresses and phone numbers are redacted from logs.

**Recommended alert setup.** Create daily job alerts on LinkedIn, Indeed and Naukri for the configured titles and locations, sent to the mailbox above, then set `sources.email_alerts.enabled: true`.

## 5. Run manually

```bash
.venv/bin/python main.py run                         # full daily workflow now
.venv/bin/python main.py run --mode DISCOVERY_ONLY   # one-off mode override
```

Add jobs you found yourself:

```bash
.venv/bin/python main.py add-job --url "https://www.linkedin.com/jobs/view/4123456789/" \
    --title "Financial Analyst" --company "Acme" --location Bengaluru --jd-file jd.txt \
    --question "What is your notice period?"
# or drop files into ~/Job_Applications/inbox/  (see examples/sample_jobs.json, examples/sample_job.txt)
.venv/bin/python main.py add-jd 42 --file jd.txt     # attach a description to discovered job #42; it is re-scored next run
.venv/bin/python main.py search-links [--platform Naukri] [--open]
```

## 6. Approve and submit

```bash
.venv/bin/python main.py approvals                   # what is waiting for you
.venv/bin/python main.py show 7                      # package: checklist, screening answers, cover letter, history
.venv/bin/python main.py approve 7                   # opens the job page; submit it on the platform
.venv/bin/python main.py mark-submitted 7 --reference "APP-123" --confirmation "Your application was sent to Acme"
.venv/bin/python main.py reject 7 --reason "not interested"
.venv/bin/python main.py mark-failed 7 --reason "job closed"
```

Opening a job page is never counted as applying. `mark-submitted` refuses to record a submission without a reference ID or genuine confirmation text. Each job can have only one application, enforced by a database constraint, and a job with the same company and title on another platform is skipped while an application is active.

Application packages are written to `~/Job_Applications/applications/<date>/` (`.txt` to read, `.json` for tools).

## 7. Daily scheduler

```bash
.venv/bin/python main.py schedule        # foreground; Ctrl+C stops it gracefully
```

* Runs at `scheduler.run_time` (Asia/Kolkata), one run at a time (file lock plus `max_instances=1`).
* **Missed runs:** at startup, if today's run time has passed and no scheduled run completed today, it runs immediately (`run_missed_on_startup`). If the laptop sleeps through the run time, APScheduler runs it late within `misfire_grace_hours`.
* **Retries:** transient failures (network, IMAP, LLM 429/5xx) are retried with backoff, and a failed run is retried `retry_attempts` times.
* **Recovery:** a run left `running` by a crashed process is marked `interrupted`. Unscored jobs are picked up on the next run, inbox files are only archived after a successful run, and an application interrupted mid-submission becomes `NEEDS_VERIFICATION` (never re-submitted blindly).
* **Run it in the background** with the provided systemd user unit (not installed automatically): see the comments in `systemd/job-automation.service`.

`main.py status` shows recent runs and counts.

## 8. Excel reports

```
~/Job_Applications/
  2026/November/2026-11-04_Applications.xlsx      (a second run that day -> _run2.xlsx; files are never overwritten)
  database/job_applications.db
  logs/2026-11-04.log
  inbox/  (processed/, failed/)
  applications/<date>/   cache/   config/   reports/
```

Sheets:

1. **Application Details**: the 35 required columns. Every job discovered or updated that day appears, and *Application Status* separates DISCOVERED, BELOW_THRESHOLD, NOT_ELIGIBLE, NEEDS_DESCRIPTION, SHORTLISTED, AWAITING_APPROVAL, PENDING_MANUAL_SUBMISSION, SUBMITTED, FAILED and so on. *Match Explanation* shows each component's score, weight and evidence.
2. **Daily Summary**: the totals, broken down by platform, plus platform access status.
3. **Job Analysis**: score, skills, experience fit, eligibility and recommendation for each job.
4. **Errors and Logs**: every recorded error with its recovery status.
5. **Search Links**: pre-filtered searches to review manually.

The workbook has frozen headers, filters, wrapped descriptions, date formats, colour-coded match percentages and clickable job URLs. Text cells are sanitised so job text can never become an Excel formula. Regenerate a fresh copy at any time with `main.py report [--date YYYY-MM-DD]`.

## 9. How the score works

| Component | Weight | Source |
|---|---|---|
| Core skills | 35 | LLM (or rule-based taxonomy match). Required skills count far more than preferred ones |
| Relevant experience | 25 | 50% deterministic years-vs-required range + 50% domain relevance |
| Responsibilities | 20 | LLM (or overlap between JD duties and resume bullets) |
| Education | 10 | LLM (or degree rules; only *mandatory* qualifications count heavily) |
| Location / work mode | 10 | Deterministic from your preferences |

The total is always computed in code from the component scores. Skills an LLM claims as "matching" are dropped unless they appear in the resume. Categories: 85+ Excellent, 70–84 Good, 55–69 Moderate, below 55 Low. Eligibility (`ELIGIBLE` / `NEEDS_REVIEW` / `INELIGIBLE`) is separate, so a missing optional skill never disqualifies a job.

## 10. Adding an authorised integration later

If a platform grants an official API or partner access:

1. Implement the access in that platform's adapter (`platforms/<name>.py`): a new source for discovery, and/or `submit_application(job, package)` returning `{"confirmed": bool, "reference_id": ..., "confirmation_text": ...}`. Raise `SecurityChallengeEncountered` on any CAPTCHA, OTP or unexpected form.
2. Set the adapter's `capabilities.automated_apply = True` only for that authorised mechanism.
3. Set `applications.mode: PERMITTED_AUTO_APPLY`. Jobs with eligibility `NEEDS_REVIEW` still require approval.

## Project layout

```
main.py            CLI                      scheduler.py   APScheduler, catch-up, retries
runner.py          daily workflow, lock, recovery
config/            settings.yaml, candidate_profile.json (verified facts), skills_taxonomy.yaml
core/              settings (pydantic), models, LLM providers, logging/redaction, skill taxonomy
resume/            resume_parser.py (PyMuPDF), profile_builder.py (experience union, cache)
platforms/         base_platform.py + linkedin / indeed / naukri adapters
discovery/         sources (inbox, IMAP alerts), job_extractor, deduplication
intelligence/      jd_analyzer, job_matcher, eligibility, cover_letter
applications/      application_manager (state machine), approval_manager, screening_answers, submission_verifier
database/          db.py, models.py (schema)
reports/           excel_generator.py, summary_generator.py
tests/             pytest suite (unit and end-to-end, no network)
```

* Every job scored `rule_based (LLM unavailable ...)`: set `ANTHROPIC_API_KEY` in `.env`.
* Email source errors appear in the *Errors and Logs* sheet. Check the IMAP host, the app password, and that IMAP is enabled in the mailbox settings.

---

## What was added in this session (2026-11-06)

* **Multi-Source Discovery Engine (Scrapling 0.5.1)**:
  - Integrated `scrapling[fetchers]==0.5.1` with `Fetcher` (curl_cffi) and `StealthyFetcher` (Patchright).
  - Central Source Policy Registry (`source_policies.py`) governing 50+ sources with rate limiting and robots.txt parsing.
  - 12 active connectors: Remotive, Himalayas, RemoteOK, Arbeitnow, NCS India, Indian Government notices (UPSC, SSC, ISRO, DRDO), Academic institutes (IIT Bombay, IIT Delhi, IIT Madras, IISc), Schema.org JSON-LD parser, RSS/Atom feed parser, XML Sitemap crawler, and Career URL ATS auto-detection.
  - Interactive **Career URL Form** and **Sources Panel** in the web UI.
* **Phase 4: Tracking, Today Focus & Privacy**:
  - **Today's Focus widget** (`<TodayView />`) displaying actionable application buckets.
  - **Interview scheduling** with interviewer details, meeting links, and **iCal Calendar download** (`/api/v1/interviews/calendar.ics`).
  - **Offer tracking** with compensation breakdowns (salary, bonus, equity), deadlines, and negotiation statuses.
  - **Recruiter & contact directory** per application.
  - **Full Data Export** (JSON) and **Password-Gated Account Deletion**.
* **Phase 5: Web Admin Console (`/admin`)**:
  - Dedicated admin panel with system metrics, user activation/deactivation, role promotion, invite code management, and audit trail.
* **Phase 6: Visual System & Gamification**:
  - Light/Dark mode switcher (`<ThemeToggle />`).
  - Maritime candidate nickname generator.
  - Milestone achievement badge system.
* **Phase 7: Notifications & Transactional Email**:
  - Production SMTP client supporting SSL/STARTTLS and self-service password reset.
* **Phase 8: DevOps & Hardening**:
  - Automated zero-downtime database and storage backup (`deploy/backup.sh`) with SHA256 checksums and 7-day retention.
  - Safe restoration script (`deploy/restore.sh`).
  - Structured JSON logging (`JSONFormatter`) and `X-Request-ID` correlation middleware.

