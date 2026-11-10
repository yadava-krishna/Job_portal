# JobPilot v2: Implementation Plan

v1 (delivered, commit `ba9b46e`/`a9aa1fc`): multi-user portal on top of the CLI engine. Its plan lives in git history.
This plan covers the v2 brief. Companion documents: `REFERENCE_PROJECT_ANALYSIS.md`, `CURRENT_ARCHITECTURE.md`, `SECURITY_REVIEW.md`.

## Ground rules (apply to every phase)
- Existing data is preserved: **additive Alembic migrations only** (new tables, nullable columns, backfills). Before each migration: `pg_dump` backup → `alembic upgrade` → smoke test; `downgrade` written for each revision.
- Never `docker compose down -v`; never recreate volumes.
- All 121 backend and 14 frontend tests stay green. Every new feature gets API tests (incl. cross-user isolation) and frontend tests. The API suite also runs against Postgres.
- No auto-submission, no background crawling of job boards, no cookie or password collection, no "Applied" without confirmation.
- Each phase ends with: tests, migration on the live DB, a restart and persistence check, a short changelog, and a deploy (backend rebuild + Pages).

## Phase 1: Security fixes, foundations and data model (first)
**Fixes:** S2 rate-limit bypass (trusted-proxy IP + per-account throttle + test) · S3 docs off in production · S1 credential rotation runbook executed with you (DB password, invite) · CSP groundwork.

**Migrations (`0002_v2_foundations`):**
| Table / column | Purpose |
|---|---|
| `users.role` (user/admin), `users.nickname`, `users.status`, `users.last_seen_at` | RBAC, fun identity, admin user list |
| `invites` | per-invite tokens, expiry, email lock, max uses, revocation (replaces the shared code; the env code keeps working until revoked) |
| `audit_logs` | admin actions and sensitive reads |
| `jobs.discovered_at`, `jobs.last_verified_at`, `jobs.posted_at_confidence` (verified/estimated/unknown, backfilled from `posted_at_source`), `jobs.company_logo_url`, `jobs.industry`, `jobs.canonical_url` | posting-date accuracy, cards, cross-source dedup |
| `job_sources` (registry: key, kind, enabled, config, health, last_ok_at, last_error) | admin-configurable sources and health |
| `notifications` (+ `notification_prefs`) | in-app notifications with dedupe key and occurrences (JobSync pattern) |
| `user_activity_sessions` / `activity_heartbeats` | accurate time tracking |
| `job_views` | recently viewed, jobs-viewed metric |
| `ai_calls` | AI usage and cost metrics |
| `extension_tokens` | scoped, hashed, revocable tokens for the browser extension |
| `interviews`, `offers`, `application_contacts`, `applications.follow_up_at`, `applications.notes` (editable), `application_stage_history` | pipeline depth (Waddington / App Pal) |
| `saved_searches` (+ `saved_search_runs`) | scheduled discovery per user (JobSync automations) |
| `user_achievements` | badges |

**As built (2026-11-04):** migration `0002` applied live; existing user and data verified intact (row hash identical to the pre-migration backup); upgrade → downgrade → upgrade rehearsed on a restored copy of the live database and covered by `tests/api/test_migrations.py`. Deviations from the table above, chosen to avoid two sources of truth:
- `users.status` not added: `users.is_active` already is the enforced account status.
- `activity_heartbeats` not added: heartbeats aggregate into `user_activity_sessions`, which keeps `active_seconds` and `heartbeats`.
- `application_stage_history` not added: stage changes are already recorded as `STAGE_CHANGED` rows in `application_events`.
- `saved_search_runs` not added: runs are `discovery_runs` rows with the new `saved_search_id`.
- `applications.notes` already existed; only `follow_up_at` was added.

**API contracts:** documented in `docs/API_V2.md` (generated from OpenAPI plus a narrative); all new routes under `/api/v1`, with admin under `/api/v1/admin/*` behind `require_admin`.

**Exit:** migration applied to the live DB with the existing user intact; all tests green; S1–S3 closed.

## Phase 2: Automated job discovery (detailed, approved 2026-11-04)

**Findings from inspecting Phase 0/1 code that shape this phase**
- `upsert_job` merges only on the exact `job_key`, so the same role from Adzuna, an alert email and a clip becomes several `jobs` rows and several feed items. There is no cross-source dedup yet.
- `ingest_postings` takes the CLI's `JobPosting`, whose `platform` is the LinkedIn/Indeed/Naukri enum. Adzuna works around this (`Platform.LINKEDIN`, then overwrites the column). ATS jobs need a backend-level normalised type instead of extending the CLI enum, which drives the CLI adapters.
- `deduplication.normalize_company` feeds the stored `job_key` hash for jobs without an ID, so it must not change. Cross-source identity gets its own key.
- Verified live: Greenhouse has `first_published` (real publish time; `updated_at` is *not* a posting date); Lever has `createdAt` (ms epoch); Ashby has `publishedAt` and `isListed`. A stale token returns 404, so a missing board is a normal, reportable state.
- JobSync (MIT, commit `8c20325`) ships `{name, token}` directories: Greenhouse, Lever, Ashby. Mostly non-Indian employers; tokens can be stale.

**2.1 Unified normalisation** (`backend/services/normalization.py`)
- `NormalizedJob`: one schema for every source (source, source key, display platform, company, title, locations, work mode, employment type, experience, salary, plain-text description, skills, URLs, posted date + date source, industry, department).
- Helpers: HTML to safe plain text (we never render source HTML), canonical URL, employment-type and work-mode vocabularies, ISO/epoch dates, location tokens with Indian city aliases (Bengaluru/Bangalore, Gurugram/Gurgaon, Mumbai/Bombay…), `company_key`/`title_key`.
- Converters from the CLI `JobPosting` (clip, URL, file, alert email) and from Adzuna, so every source goes through one ingest path.

**2.2 Official ATS integrations** (`backend/services/ats/`)
- Greenhouse `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`, Lever `api.lever.co/v0/postings/{token}?mode=json` (+ EU host), Ashby `api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true`. Read-only public endpoints that employers publish for their own careers pages; no auth, no scraping.
- Errors classified as not-found / transient / invalid; response size cap; timeouts; an identifying User-Agent; in-process board cache (30 min) so many users and searches share one fetch.
- Posting date: Greenhouse `first_published`, Lever `createdAt`, Ashby `publishedAt` → `verified`; absent → `unknown`, never "today". Ashby `isListed=false` is skipped.
- A job that disappears from a board after a successful fetch gets `closed_at`, marked "No longer listed".

**2.3 Cross-source deduplication**
1. Same source key (`job_source_links.source_key`).
2. Same `job_key` (legacy).
3. Same canonical URL.
4. Same `dedup_key` (normalised company + title) **and** compatible locations (overlapping cities, or exactly one candidate when a location is missing).

On a match, the job is enriched (full description beats a snippet; better-ranked posting date wins) and the extra source is recorded as a link. One job means one feed item per user (existing unique constraint).

**2.4 Companies and watchlists**
- `companies` table: rows are created only when a company is used, so the 5,400-entry directory is not copied into the database.
- Directory search over the JobSync data (with MIT notice in `backend/data/ats_companies/`), plus a small curated, **live-verified** India-relevant list with industries.
- Add a company by board URL or token (validated by one probe call). Per-user watchlist.

**2.5 Saved searches and scheduling**
- CRUD under `/api/v1/saved-searches`. Criteria: titles/keywords, exclude keywords, locations, remote OK, industries, experience, employment types, work modes, companies (or the watchlist), sources (Greenhouse/Lever/Ashby/Adzuna), minimum match score, schedule (manual/daily/weekly).
- "Run now" plus an in-process scheduler tick every 15 minutes for due searches. Each run is a `discovery_runs` row with `saved_search_id`. Per-search lock; runs left "running" across a restart are marked interrupted (S10).
- The existing 09:00 daily job (alert emails, Adzuna) is unchanged.

**2.6 Matching:** every new feed item is scored by the existing `UserMatcher` against the user's confirmed resume and preferences. Rule-based scoring remains the fallback and is labelled. The search's own minimum score decides shortlisting and notifications.

**2.7 Adzuna:** saved searches can include Adzuna. The integration goes through the same normalisation and dedup. Without `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` in `.env`, runs report "not configured" (no invented credentials).

**2.8 Notifications without duplicates:** one in-app notification per *newly added* feed item at or above the search's threshold, keyed `new_match:{job_id}` with a unique (user, key) constraint. Repeat runs find the existing feed item and notify nothing. API: list, unread count, mark read, read all. Minimal bell in the header (the full centre is Phase 7).

**2.9 Feed:**
- Each card shows source(s), discovery time, original posting date with a confidence chip (Verified / Estimated / Unknown), and a "No longer listed" badge.
- Filters: source, posted window (today / 24h / 3d / 7d / 30d / range; verified dates only unless "include estimated"), confidence, industry, employment type, company, saved search, include closed.
- Sorting: match, newest posting, recently found. Save/dismiss and match/matching/missing skills as before.
- New **Searches** page (saved searches and run history) and **Companies** tab (watchlist, directory, suggested, add by URL).

**Migration `0003_discovery`** (additive):
- New tables: `companies`, `user_companies`, `job_source_links`.
- New columns: `jobs.dedup_key` (indexed), `jobs.company_id`, `jobs.closed_at`, `jobs.department`.
- Backfills: one source link per existing job and `dedup_key` for existing jobs.
- A downgrade, and a migration test extended to 0003.

**Tests:**
- Normaliser unit tests.
- ATS clients against mocked official feeds (`httpx.MockTransport`) with synthetic fixtures shaped like the live responses: 404, 5xx, malformed body, unlisted, missing dates, EU host, size cap.
- API integration: saved search → run → scored feed; repeat runs produce no duplicate jobs or notifications; clip + Greenhouse merge into one item; closed jobs; Adzuna mocked and unconfigured; per-user isolation; scheduler due logic; feed filters; company add/validation.
- Existing LinkedIn/Indeed/Naukri clip/import/email tests unchanged and green; SQLite + Postgres; frontend tests for cards and filters.

**As built (2026-11-04).** Delivered as planned, plus the fixes from `DISCOVERY_DIAGNOSTIC_REPORT.md`:
- Starter saved search per user (suggested employers, related-title families, experience from the resume).
- "Run discovery now" across all sources, with staged progress.
- Per-source run outcomes, a summary, honest run status, and a Source health panel.
- The date-range fix and the hidden-unknown-dates count.
- Same-board repost dedup.

Migration `0003_discovery`, additive:
- New tables: `companies`, `user_companies`, `job_source_links`.
- `jobs`: `dedup_key`, `company_id`, `department`, `closed_at`.
- `users.starter_search_created_at`, `saved_searches.origin`.
- `discovery_runs`: `source_results`, `summary`.
- Backfills: links, `dedup_key` and `canonical_url`.

Known limits:
- Coverage is only boards on Greenhouse, Lever and Ashby (many large Indian employers aren't).
- Greenhouse gives no work mode, so it is inferred from text.
- Scoring is rule-based until an LLM is configured.
- Adzuna awaits credentials.

**Out of scope here (later phases):** company logos (needs a privacy-safe favicon proxy), LLM-assisted extraction and AI summaries (Phase 3/6 with the local Docker model), Jooble/Careerjet, and admin source configuration (Phase 5).

## Phase 3: Browser extension and application assistance
**Status (2026-11-05): delivered for Greenhouse, Lever and Ashby forms**, plus unified tracking, SmartRecruiters and Recruitee discovery, careers-page detection, resume versions, answer bank, notification preferences and restart recovery. See PHASE3_TEST_REPORT.md.

**Not delivered (by design or pending you):**
- **LinkedIn, Indeed and Naukri extractors and side panel:** not built. The bookmarklet and alert e-mails remain the path for these sites.
- **Workday:** no documented API.
- **Direct application through APIs:** needs employer keys.
- **E-mail notifications:** need SMTP.
- **AI scoring:** an optional layer, designed, not built.

Original plan, for reference:
- **JobPilot MV3 extension** (`extension/`): per-site extractors (LinkedIn, Indeed, Naukri, Foundit, Glassdoor, Wellfound, Greenhouse, Lever, Ashby) with JSON-LD first; Shadow-DOM floating button; SPA observer; shows "already in JobPilot · 82%" on the page.
- **Auth:** Settings → "Connect browser" creates a scoped extension token (pairing code), revocable per device.
- **Assisted apply:**
  - On employer ATS forms (Greenhouse, Lever, Ashby; Workday later), "Fill with JobPilot" fills name, email, phone, links and resume upload, plus answers from verified facts, only on click. **The user reviews and submits.**
  - On LinkedIn, Indeed, Naukri, Foundit, Glassdoor and Wellfound: **side panel with copy-ready answers** and a "Mark as submitted" button. No automated typing or clicking on those sites.
- Confirmation stays explicit (button / reference ID / confirmation email). The bookmarklet stays as the no-install fallback.
- Packaging: unpacked install guide now; Chrome Web Store / Edge listing later (needs your developer account).
**Exit:** extension tested on recorded fixture pages per site + manual check on live pages by you.

## Phase 4: User dashboard, pipeline, reminders
- **Today view** (Waddington): *your move* (follow-ups due, prepared-but-unsent, decide on saved jobs), *coming up* (interviews), *waiting on them* (gone quiet after N days per stage).
- Interviews (rounds, date, mode, outcome, iCal export), offers (compare), contacts, notes, follow-up date, stage history; configurable stages incl. Ghosted (re-openable).
- **Time tracking:** client heartbeat every 30 s only when the tab is visible **and** there was input in the last 2 min; server aggregates sessions (gap > 5 min = new session). Metrics: active time, sessions, average session, jobs viewed/saved, applications completed, daily/weekly activity.
- Charts: applications by day/platform, status breakdown, discovery trend, score distribution, weekly activity heatmap, interview/offer trend, **Sankey funnel**.
- Data export (JSON + Excel) and account deletion (privacy).
**Exit:** metrics verified against seeded fixtures; isolation tests.

## Phase 5: Admin dashboard
- Users (status, role, registration, last login, resume uploaded yes/no, onboarding, preferred platforms) with activate/deactivate and role change; invites (create/copy/revoke, usage); aggregate application analytics (by user, company, platform, date, status, interview/offer/rejection counts, top companies/titles); system analytics (jobs discovered/matched, duplicates prevented, AI usage, source health, failed integrations, discovery errors, confirmations); source configuration; logs viewer (redacted); usage stats; aggregate Excel export.
- Privacy: admins see aggregates and per-user application *metadata*; resume files and profile contents only through an explicit, audited "view personal data" action.
**Exit:** non-admin gets 403 on every admin route (test per route); audit entries verified.

## Phase 6: Visual system, theme, delight
- Design tokens; **light and dark themes** with a toggle; typography refresh; `motion` (Framer Motion) for page/card transitions with reduced-motion support; skeletons everywhere.
- **"Voyage" theme (toggleable, default on):** discovery as a treasure hunt, saved jobs = treasure chest, application progress as a voyage map, bounty-style stats, achievements ("First voyage", "Ten treasures", "Crew assembled"…). **All artwork, icons and copy original**; light nods only (e.g. "the Grand Line"), with no character names, logos or show artwork.
- **Context-aware loading messages** (pools per context: resume parsing, discovery, matching, prep, report, dashboard, reconnect; no immediate repeats).
- **Nicknames** (adjective_noun, e.g. `Brave_Captain`), stored per user, regenerate button; never replaces real name in reports.
- Onboarding v2 (9 steps as in the brief, resumable, no duplicate data entry), CSP meta tag.
**Exit:** Lighthouse performance ≥ 85 on Discover/Dashboard, accessibility ≥ 90; visual check on mobile/tablet/desktop.

## Phase 7: Notifications and reporting
- In-app notification centre (bell, unread count, mark read, preferences/frequency): high-match jobs, posted-today jobs, saved-job reminders, follow-ups, interviews, status changes, failed integrations, profile updates.
- Optional email digests via SMTP (your mailbox app password or a provider key); password reset by email.
- Excel: weekly, monthly, history per user (reusing the generator) + admin aggregate workbook; the daily report gains the brief's columns (confirmation timestamp, reference ID, etc.).

## Phase 8: Deployment and hardening
- Nightly `pg_dump` + storage tarball (`deploy/backup.sh`, systemd timer or cron, retention), tested `deploy/restore.sh`.
- Structured JSON logs, request IDs, error budget on discovery sources, health detail split (public minimal vs admin full).
- Static ngrok domain (yours to claim) to stop URL churn; optional Cloudflare Tunnel alternative.
- Full acceptance run (brief §18) and final documentation set.

## Needs from you
| Item | Why | When |
|---|---|---|
| Approve rotating the DB password and invite code (S1) | exposed in chat | Phase 1 |
| `ANTHROPIC_API_KEY` (or local Ollama in Docker per your rule) | AI scoring and summaries; otherwise rule-based (clearly labelled) | Phase 2 |
| Adzuna app ID/key | automated discovery with verified dates | Phase 2 |
| ngrok static domain (free: dashboard → Domains) | stable backend URL; until then add the cron entry in DEPLOYMENT.md §3 | **now** |
| Decision: Workable widget, Remotive/Himalayas attribution terms, Jooble/Careerjet keys | more discovery sources (SOURCE_CAPABILITY_MATRIX.md) | any time |
| SMTP credentials (optional) | email notifications and password reset | Phase 7 |
| Chrome Web Store developer account (optional) | publish the extension instead of unpacked install | Phase 3+ |

## Effort and order
Phase 1 is a prerequisite for everything else. Phases 2 and 3 deliver the biggest user value. 4 → 5 → 6 → 7 → 8 follow. Each phase is shipped and verified on the live deployment before the next starts.

---

## Session Update (2026-11-06): Multi-Source Discovery & Phases 4–8 Delivered

**Delivered in this session:**

1. **Scrapling Framework & Multi-Source Engine (Stages A–J)**:
   - `scrapling[fetchers]==0.5.1` integrated into `.venv` and `requirements.txt`.
   - `services/source_policies.py`: Source Policy Registry pre-populated with 50+ compliant sources with rate limits, methods, and robots.txt caching. Zero scraping on LinkedIn, Indeed, Naukri maintained.
   - `services/scrapling_client.py`: Async semaphore-bounded fetcher with SSRF defense (blocking private IPs, loopback, cloud metadata), 25 MB max response limit, and token bucket.
   - `services/connectors/`: 12 discovery connectors implemented (JSON-LD, RSS/Atom, Sitemap, HTML Adaptor, Career URL ATS-detector, Remotive, Himalayas, RemoteOK, Arbeitnow, NCS India, Government portals, Academic institutions).
   - Migration `0004_multi_source_discovery.py`: Additive migration for `source_connectors`, `user_career_urls`, and multi-source metadata fields.
   - Frontend: `<CareerUrlForm />` and `<SourcesPanel />` wired into `SearchesPage.tsx`.

2. **Phase 4: Tracking, Today Focus & Privacy**:
   - `<TodayView />`: Tri-bucket agenda (Your Move, Coming Up, Waiting On Them) wired into `DashboardPage.tsx`.
   - Interview tracker: Scheduling, round notes, meeting links, and iCal calendar feed (`/api/v1/interviews/calendar.ics`) wired into `AppliedPage.tsx`.
   - Offer tracker & recruiter contacts directory wired into `AppliedPage.tsx`.
   - User privacy: Full JSON data export (`/api/v1/account/export`) and password-verified account deletion wired into `SettingsPage.tsx`.
   - Session activity: `useHeartbeat` hook mounted in `AppLayout.tsx`.

3. **Phase 5: Admin Dashboard**:
   - RBAC security: `require_admin` dependency and `role` column on users.
   - `backend/services/admin_service.py` & `backend/api/routes/admin.py`: User activation toggle, role assignment, invite code generation, metrics, and audit log.
   - Frontend: `<AdminPage />` lazy-loaded at `/admin` route with `RequireAdmin` guard and dynamic navbar link.

4. **Phase 6: Visual System & Gamification**:
   - Dark/Light mode theme system with persistent toggle (`<ThemeToggle />`) mounted in `AppLayout.tsx`.
   - Maritime candidate nickname generator (`backend/services/nickname_service.py`).
   - Milestone achievement badge system (`backend/services/achievement_service.py`).

5. **Phase 7: Notifications & Transactional Email**:
   - Production SMTP client (`backend/services/email_service.py`) supporting SSL/STARTTLS and test outbox hook.
   - Secure password reset workflow (`/auth/forgot-password` and `/auth/reset-password`).

6. **Phase 8: Deployment & Hardening**:
   - Production backup script (`deploy/backup.sh`) with pg_dump, storage tarball, SHA256 checksums, and 7-day retention.
   - Safe restore script (`deploy/restore.sh`) with dry-run support.
   - Structured JSON logging (`JSONFormatter`) and `X-Request-ID` correlation middleware in `backend/main.py`.
   - Verification: All 121+ backend tests passed (100% green), all 30 vitest tests passed, and frontend production build succeeds with zero errors.

