# JobPilot: Multi-User Job Application Portal: Implementation Plan

Extends the existing single-candidate automation in this repository into a multi-user web portal.
The existing CLI (`main.py`, `scheduler.py`, SQLite) keeps working unchanged.

## 0. Baseline (recorded before any change)

| Item | Value |
|---|---|
| Test suite | `.venv/bin/python -m pytest` → **89 passed** (2026-11-04) |
| Python | 3.14 venv (code targets 3.12+) |
| Existing SQLite (`~/Job_Applications/database/job_applications.db`) | candidates 1, jobs 0, applications 0, daily_runs 1, platform_status 3 |
| Lint | `ruff check --select F,E9` clean |

## 1. Deployment topology (as requested by the owner)

```
 Browser ──HTTPS──► GitHub Pages (yadava-krishna/Job_portal, gh-pages branch)
    │                 static React build + config.json { apiBaseUrl }
    │
    └──HTTPS──► ngrok edge ──tunnel──► [owner's Ubuntu machine, Docker Compose]
                                          ngrok agent ─► backend (FastAPI :8000)
                                                            │
                                                     postgres:16 (internal only, no host port)
                                          frontend-local (nginx, LAN mode, optional port)
```

* The **backend is the source of truth for availability**: the UI polls `GET /api/v1/health` every 7 s
  (4 s timeout, retry with backoff) and shows the full-screen *JOB PORTAL OFFLINE* page when it fails.
* The ngrok URL on this account is **random per start**. The frontend therefore resolves the backend URL
  at runtime, in this order: `?api=` query parameter → value saved in the browser (Connection settings)
  → `config.json` on GitHub Pages (re-published by `deploy/start.sh` whenever the tunnel URL changes)
  → build-time `VITE_API_BASE_URL`. With a free *static* ngrok domain (`NGROK_DOMAIN`), the URL never changes.
* Cross-site setup (github.io ↔ ngrok): bearer tokens, not cookies (third-party cookies are blocked by
  Safari and increasingly by Chrome). CORS allows only the configured frontend origins. Every request
  sends `ngrok-skip-browser-warning` to bypass ngrok's free-tier interstitial.

## 2. Existing module → backend service map

| Existing module | Portal service | Reuse |
|---|---|---|
| `resume/resume_parser.py` | `backend/services/resume_service.py` | **As is** |
| `resume/profile_builder.py` | `resume_service` | Small refactor: extract `build_profile_from_pdf(path, taxonomy, …)` so it no longer needs global `Settings`; `ProfileBuilder` keeps its API and calls it |
| `core/skills.py` (taxonomy) | resume, matching, discovery | **As is** |
| `intelligence/jd_analyzer.py` | `discovery_service` (JD parsing) | **As is** |
| `intelligence/job_matcher.py` | `matching_service` | **As is**. Fed per-user `MatchingConfig`/`SearchConfig` built from the user's preferences |
| `intelligence/eligibility.py` | `matching_service` | **As is** (per-user `EligibilityConfig`) |
| `intelligence/cover_letter.py` | `application_service` | **As is** |
| `applications/screening_answers.py` | `application_service` | **As is** (per-user verified facts) |
| `applications/submission_verifier.py` | `application_service` | `check_candidate_evidence`, `match_confirmation_email` reused |
| `applications/application_manager.py`, `approval_manager.py` | CLI only | Not used by the portal (SQLite-bound); same state-machine *rules* re-expressed for Postgres |
| `discovery/sources.py` | `discovery_service` | `record_from_mapping`, `parse_text_jobs`, `parse_alert_email`, `EmailAlertSource` reused |
| `discovery/job_extractor.py`, `deduplication.py` | `discovery_service` | **As is** (`JobExtractor.to_posting`, `job_key`, `fingerprint`) |
| `platforms/*` | `platform_service` | **As is** (ID parsing, canonical URLs, search links, capabilities) |
| `reports/excel_generator.py`, `summary_generator.py` | `report_service` | **As is**. A per-user adapter implements the same read methods (`report_rows`, `runs_on`, `errors_on`, `platform_status_on`) over Postgres |
| `core/llm.py` | matching, cover letter | **As is** (provider from env) |
| `database/db.py` (SQLite) | CLI only + one-time import script | Unchanged; `backend/scripts/import_sqlite.py` copies its data into a chosen portal user |
| `main.py`, `scheduler.py`, `runner.py` | CLI | Unchanged |

## 3. New database (PostgreSQL, SQLAlchemy 2 + Alembic)

| Table | Key columns | Constraints / indexes |
|---|---|---|
| `users` | email, password_hash (Argon2id), full_name, is_active, created_at, last_login_at | unique(email) |
| `refresh_tokens` | user_id, token_hash (SHA-256), expires_at, revoked_at, replaced_by | unique(token_hash); rotation + reuse detection |
| `resumes` | user_id, original_filename, stored_path, sha256, size_bytes, page_count, is_active | index(user_id) |
| `candidate_profiles` | user_id, active_resume_id, parsed_profile JSON, confirmed_profile JSON, experience_months, verified_facts JSON, confirmed_at | unique(user_id) |
| `job_preferences` | domains, industries, job_titles, title_keywords, locations, work_modes, salary_min/max, currency, experience_min/max, employment_types, notice_period, preferred/excluded_companies, min_match_score, weights, application_settings | unique(user_id) |
| `platform_preferences` | user_id, platform, enabled, discovery_sources | unique(user_id, platform) |
| `email_integrations` | user_id, imap_host/port/username, **encrypted** password (Fernet), folder, enabled, last_checked_at | unique(user_id) |
| `jobs` (global public listing) | job_key, platform, external_job_id, fingerprint, company, title, location, work_mode, employment_type, salary/experience fields, description, skills/education JSON, job_url, posted_at, posted_at_source, source | unique(job_key); index(fingerprint), index(posted_at) |
| `user_jobs` (private per user) | user_id, job_id, discovery_run_id, source, match_score, match_category, match JSON, matching/missing skills, eligibility, status (new/shortlisted/saved/dismissed/applied), saved_at, dismissed_at | unique(user_id, job_id); index(user_id, status), index(user_id, match_score) |
| `applications` | user_id, job_id, user_job_id, status, stage, resume_id, resume_used, cover_letter, screening_answers, checklist, reference_id, confirmation_*, opened_at, submitted_at | unique(user_id, job_id), so duplicate applications are impossible |
| `application_events` | application_id, user_id, event_type, from/to status, details | index(application_id) |
| `discovery_runs` | user_id, trigger, status, started/completed, jobs_found/new/matched/duplicates, error_details, filters | index(user_id, started_at) |
| `reports` | user_id, kind (daily/history), report_date, file_path, size | index(user_id, created_at) |

**Isolation rule:** every query for user data goes through `scoped(select(Model), user)`, which adds
`Model.user_id == current_user.id`. Routes never accept a `user_id` from the client. Cross-user access
returns 404 (not 403), so existence isn't leaked. Tests cover each resource with two users.

**Posting dates:** `posted_at_source` ∈ {`platform_api` (verified), `user_provided`, `alert_email`
(approximate: on or before the alert), null}. "Today" filters use only verified dates
(`platform_api`, `user_provided`). Anything else is labelled *Unknown* or *≤ alert date*.

## 4. Discovery sources (permitted only)

| Source | Platforms | Posting date |
|---|---|---|
| Paste URL + description (Quick Import) | LinkedIn / Indeed / Naukri | user-provided |
| Upload JSON / CSV / TXT | all three | user-provided |
| User's own job-alert emails (IMAP, read-only, password encrypted at rest) | all three | approximate |
| Adzuna official API (optional, server keys `ADZUNA_APP_ID/KEY`) | "Other: official API" (aggregator) | verified |
| Pre-filtered search links (manual search) | all three | n/a |

No scraping, browser automation, private APIs or auto-submission. Job pages are never fetched;
"is this still open?" is a checklist item for the user.

## 5. Ideas adopted from alexmc2/jobs-tracker (JobOps)

Concepts only; no code is copied (that project is AGPLv3 + Commons Clause). Its LinkedIn/Indeed scraping
is deliberately **not** adopted.

1. Post-application **pipeline board**: Applied → Screening → Interview → Offer / Rejected / Withdrawn, with an event log.
2. **Manual import sheet**: paste URL + JD in one step (our primary discovery path).
3. **Fit assessment** panel with a score indicator and component breakdown.
4. **Keyboard shortcuts** on the discovery list (j/k move, o open JD, s save, d dismiss, a apply).
5. **Analytics**: applications per day, funnel conversion, results by platform.
6. **Onboarding gate**: the app routes to onboarding until resume, profile, preferences and platforms are confirmed.
7. **Adzuna** official API as an extra legitimate source.
8. **Search helpers**: per-platform pre-filtered search links plus a "company careers page" web search link.

## 6. API (FastAPI, `/api/v1`, OpenAPI at `/api/docs`)

auth: register, login, refresh, logout, me · health: health, health/ready · profile: get/put, resume upload/download, parse-resume, verified facts ·
preferences get/put · platforms list / put preferences · integrations email get/put/test ·
jobs: discover, import (single/file), list (filters), get, analysis, save/unsave, dismiss/restore, search-links ·
applications: prepare, open, confirm, fail, withdraw, stage, list, get · reports: list, daily, history, download ·
dashboard: summary, activity, analytics.

## 7. Frontend (React 19 + TS + Vite + Tailwind v4 + shadcn/ui + React Router + TanStack Query)

Pages: Login, Register, Onboarding (resume → review profile → preferences → platforms → confirm), Dashboard,
Discover (workspace with filters, job cards, JD side sheet, Apply dialog), Saved, Applied (table + board), Reports, Settings,
Offline screen, Connection settings. Uses a HashRouter (GitHub Pages has no SPA rewrites).

## 8. Security

Argon2id hashing, password policy, 15-min JWT access tokens, rotating refresh tokens (hashed, revocable,
reuse detection), auth rate limiting, optional registration invite code (the backend is internet-reachable),
CORS allowlist, upload validation (MIME + magic bytes + size + PyMuPDF open + sanitised name, stored under
`storage/users/{id}/resumes/<uuid>.pdf`), path-traversal-safe file serving through DB ownership,
Fernet-encrypted IMAP passwords, secrets in `.env`, redacted logs, Postgres with no host port.

## 9. Phases and verification

| Phase | Deliverable | Verified by |
|---|---|---|
| 1 | This plan + baseline | 89 tests |
| 2 | Postgres schema (SQLAlchemy + Alembic), auth | auth/isolation tests |
| 3 | Resume parser + matching integration | resume/matching API tests |
| 4 | Onboarding: profile, preferences, platforms | API tests |
| 5 | Discovery (import, email, Adzuna), dedup, filters | discovery tests |
| 6–7 | React app: dashboard, discovery workspace, JD sheet, apply flow, saved/applied/board | `npm run build`, vitest |
| 8 | Per-user Excel reports | report tests |
| 9 | Health + offline/reconnect UI | backend health tests + frontend hook tests + live stop/start |
| 10 | Docker (postgres, backend, ngrok, local nginx), start/stop scripts, Pages deploy | `docker compose up`, live curl through ngrok |
| 11 | Full integration, persistence across restarts | restart test, end-to-end through the public URLs |

## 10. Known constraints (stated up front)

* No platform offers job-seeker search/apply APIs; discovery depends on user imports, the user's alert emails, and Adzuna.
* Adzuna returns description *snippets*; full descriptions must be pasted by the user for high-confidence scoring.
* GitHub Pages on a **private** repository requires a paid GitHub plan; on a free plan the repo must be public.
* With a random ngrok URL, a change of address takes effect when `deploy/start.sh` republishes `config.json` (and the Pages CDN refreshes, up to ~10 min); a static ngrok domain avoids this.
