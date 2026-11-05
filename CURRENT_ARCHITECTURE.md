# JobPilot: Current Architecture (as built, inspected 2026-11-04)

Facts below come from the code and the running system, not from earlier summaries. **Corrections to the brief:** there is **no admin functionality** yet (no roles, no admin routes or UI), no notifications, no session/time tracking, no interviews/offers entities, and only LinkedIn, Indeed, Naukri and Adzuna sources.

## 1. Deployment

```
GitHub Pages (gh-pages: static React build + config.json{apiBaseUrl})
        │ HTTPS (bearer tokens, CORS allowlist)
        ▼
ngrok (random free URL, republished by deploy/start.sh) ─► backend container (FastAPI, :8000 bound to 127.0.0.1)
                                                           ├─► postgres:16 (internal Docker network only, volume jobpilot_pgdata)
LAN: frontend container (nginx :3080, /api proxy) ─────────┘   storage volume jobpilot_storage (/data/users/<id>/…)
```

| Item | State |
|---|---|
| Compose project | `jobpilot`: postgres (healthy), backend (healthy), frontend (healthy), ngrok (profile `tunnel`) |
| Restart policy | `on-failure:5`; CPU/memory caps on every service |
| Volumes | `jobpilot_pgdata`, `jobpilot_storage`: **must never be removed** (`down -v` is forbidden) |
| Scripts | `deploy/start.sh`, `stop.sh`, `init_env.sh`, `publish_backend_url.sh`, `deploy_frontend.sh` |
| Live data | 1 registered user (not yet onboarded), 0 jobs, 0 applications; Alembic revision `0001` |
| Repo | public `yadava-krishna/Job_portal`, default branch `main`, Pages from `gh-pages`; `docs/` (user guide PDF) untracked |

## 2. Code inventory

| Area | Files | Notes |
|---|---|---|
| Python (CLI engine + backend) | 87 files, ~11.3k LOC | |
| Frontend (TS/TSX) | 54 files, ~5.9k LOC | React 19, Vite 8, TS 7, Tailwind v4, shadcn (Base UI), TanStack Query, HashRouter |
| Tests | **121 backend** (89 CLI incl. 1 local-only real-resume test + 32 API), **14 frontend** (vitest) | API suite also runs on Postgres + Alembic via `TEST_POSTGRES_URL` |

### Original single-candidate engine (unchanged, reused)
`resume/` (PyMuPDF parser, `ResumeProfileExtractor`, experience union) · `intelligence/` (`jd_analyzer`, `job_matcher` 5-component weighted score with LLM or rule-based, `eligibility`, `cover_letter` with fact verification) · `discovery/` (sources: inbox, IMAP alerts; extractor; dedup keys and fingerprints) · `platforms/` (LinkedIn/Indeed/Naukri adapters: ID parsing, canonical URLs, search links) · `applications/` (CLI state machine, screening answers, submission verifier) · `reports/` (OpenPyXL generator, pandas summary) · `core/` (settings, LLM providers, taxonomy, redacting logs) · `main.py`, `runner.py`, `scheduler.py` (CLI, SQLite).

### Backend (`backend/`)
| Layer | Contents |
|---|---|
| `config.py`, `db.py`, `security.py` | env settings; SQLAlchemy engine; Argon2id, JWT (15 min), rotating refresh tokens (14 d, hashed, family reuse detection), Fernet credential cipher, in-memory rate limiter |
| `models/` | `users, refresh_tokens, resumes, candidate_profiles, job_preferences, platform_preferences, email_integrations, jobs (global), user_jobs (per user), applications, application_events, discovery_runs, reports, run_errors` |
| `services/` | auth, resume (upload validation, parse, confirm, matcher profile), preference (prefs, platforms, email, onboarding), matching (per-user `UserMatcher`), discovery (import, file import, IMAP, Adzuna, ingest/dedup, posted labels, search links), application (prepare/open/confirm/pending/fail/withdraw/stage), report (adapter over the existing Excel generator), dashboard (summary, activity, analytics), scheduler (daily 09:00 discovery and report per onboarded user), adzuna client |
| `api/routes/` | **53 endpoints**: auth 6, health 2, profile/preferences/platforms/integrations 13, jobs 15, applications 9, reports and dashboard 8 |
| `migrations/` | Alembic `0001_initial_portal_schema` |
| `scripts/import_sqlite.py` | idempotent CLI history → portal user |

### Frontend (`frontend/src/`)
Routes: `/login`, `/register`, `/onboarding`, `/dashboard`, `/discover`, `/saved`, `/applied`, `/reports`, `/settings`, `/clip`. Contexts: `ConnectionContext` (health polling 7 s online / 5 s offline, 4 s timeout, 2 s failure confirmation, published-URL refresh), `AuthContext` (memory access token, localStorage refresh token, session restore on reconnect). Components: JobCard, JobDetailSheet, ApplyDialog (prepare → open → confirm), ImportDialog, OfflineScreen, forms (resume, profile, preferences, platforms, clipper), raw-JS bookmarklet (`lib/clipper.bookmarklet.js`). Pages are lazy-loaded (initial JS ~327 kB).

## 3. Feature status vs the new brief

| Brief area | Status today |
|---|---|
| Register / login / invite | ✅ single shared invite code (env) · ❌ invite management, roles, password reset |
| Resume upload, parse, edit | ✅ PDF only, rule-based parser · ❌ industry/tools extraction, DOCX, LLM-assisted parse |
| Preferences, platforms | ✅ · ❌ Foundit/Glassdoor/Wellfound, industry relevance in score |
| Discovery | ✅ clipper (bookmarklet), paste/file import, IMAP alerts, Adzuna (no keys set) · ❌ ATS boards, saved searches, browser extension |
| Posting-date accuracy | ⚠️ `posted_at` + `posted_at_source` (platform_api/platform_page/user_provided/alert_email); filters today/24h/range · ❌ 3/7/30-day presets, `last_verified_at`, explicit confidence field |
| Dedup | ✅ platform+ID or normalised hash; cross-platform fingerprint blocks duplicate applications · ⚠️ no cross-source *listing* merge (same job on Adzuna and LinkedIn shows twice) |
| Matching | ✅ explainable 5 components, rule-based fallback labelled, LLM path (Anthropic/OpenAI-compatible) · ❌ salary/title/industry/employment-type components, AI summary text on cards |
| Apply workflow | ✅ prepare → open original → confirm; never auto-applied · ❌ autofill assistance, follow-up dates, notes UI per application |
| Tracking | ✅ list, pipeline board (applied/screening/interview/offer/rejected/withdrawn), events · ❌ interviews, offers, reminders, Today view |
| Dashboard | ✅ totals, 30-day chart, funnel, platform table, activity, backend status · ❌ time tracking, sessions, score distribution, weekly activity |
| Admin | ❌ none |
| Excel | ✅ daily + full history per user · ❌ weekly/monthly, admin aggregate |
| Notifications | ❌ none |
| Theme / fun UI | ❌ neutral shadcn theme only, no dark-mode toggle, no motion |
| Offline UX | ✅ full-screen offline, auto-reconnect, session restore; distinguishes backend vs DB down · ⚠️ third-party source failures shown only as discovery-run errors (correctly not "offline") |

## 4. Known technical debt
- Rescoring after profile/preference edits runs rule-based only (would overwrite LLM scores when an LLM is enabled).
- `BackgroundTasks` (in-process) for discovery; no job queue, so a backend restart loses an in-flight run (it stays `running` until the 10-minute guard).
- Rate limiter and scheduler are in-process (fine for one worker; blocks horizontal scaling).
- Adzuna jobs are stored with `platform="Adzuna"` but `job_to_posting` maps unknown platforms to LinkedIn internally (cosmetic only, but confusing).
- `docs/` (user guide PDF) not committed; it contains screenshots of a test account only.


## 5. Automated discovery (Phase 2, as built 2026-11-04)

```
scheduler (09:00 daily: run_all per user; every 15 min: starter creation + due saved searches)
   │                         "Run discovery now" (POST /jobs/discover) ─┐
   ▼                                                                   ▼
saved_search_service.run_all / execute ── criteria (search ∪ preferences, related-title families)
   ├─ company boards: company_service.refresh_board → ats.board_cache → ats.{greenhouse,lever,ashby}.fetch   (official public APIs)
   │       └─ closed-job detection, company health, source_registry (job_sources)
   ├─ Adzuna (when ADZUNA_APP_ID/KEY set)        ├─ alert emails (user mailbox)        (clipper/links/imports: user-initiated)
   ▼
normalization.NormalizedJob (one schema, plain-text descriptions, location/date/vocabulary normalisation)
   ▼
discovery_service.ingest_normalized → upsert_normalized (dedup: source key → job key → canonical URL → company+title+location;
   │                                    same-board reposts) + job_source_links → add_to_feed (per-user user_jobs)
   ▼
matching_service.UserMatcher (rule-based, labelled; LLM when configured) → notifications (deduplicated) → run.source_results + summary
```

- **Shared versus private:** `jobs` and `job_source_links` are public listings, shared. `user_jobs`, `saved_searches`, `user_companies`, `discovery_runs` and `notifications` are per user and always scoped by `user_id`.
- **Frontend:**
  - Discover: latest-run card, explained empty states, source and date filters, unknown-date notice.
  - Searches & sources: saved searches, companies (watchlist, suggested, directory, add by URL) and Source health.
  - A notification bell.
- **Not automated, by design:** LinkedIn, Indeed and Naukri. They are reached only through the clipper, links, paste, file import and alert emails.


## 6. Phase 3 additions (as built 2026-11-05)

- **Extension** (`extension/`): MV3 with no build step.
  - The service worker holds the device credential in IndexedDB and is the only part that calls the API.
  - Content scripts (fieldmap, core, panel, Greenhouse/Lever/Ashby adapters) are injected only after a click, only
    into allow-listed frames.
  - Tests: vitest (jsdom), and Playwright end-to-end runs (offline, `--live`, and `prod_check.py`).
- **Backend:**
  - `api/routes/extension.py` plus `services/extension_service.py`: pairing, devices, rotation, revocation, audit,
    autofill profile, page matching via `job_source_links.source_key`, and the verified Greenhouse-hosted form.
  - `services/answer_service.py`: Verified, Suggested or Needs-input classification over `ScreeningAnswerer`, which
    now also uses the answer bank in `verified_facts.custom_answers`.
  - `services/ats/smartrecruiters.py` and `ats/recruitee.py`, plus `services/careers_page.py` (request-forgery-safe
    board detection).
  - Resume versions in `resume_service`; tracking notes and follow-up; Assessment and Archived stages; notification
    preferences in `notification_prefs.kinds`; scheduler catch-up for a missed daily run.
- **Database:** no new migration (head still `0003`). Uses the existing `extension_tokens`, `audit_logs` and
  `notification_prefs` tables, and JSON columns.
- **Deployment:** `restart: unless-stopped`, health checks on all four services, and `deploy/url_watch.sh`
  (republishes the tunnel URL; cron entry to be added by the owner). See DEPLOYMENT.md.
