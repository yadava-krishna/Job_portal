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

## Phase 2: Discovery, dedup, matching, feed
1. **ATS board discovery** (Greenhouse, Lever, Ashby): source adapters, company watchlist per user, default India-relevant directory (JobSync MIT data with notice), saved searches with schedule and threshold, run history. Background worker: an in-process queue with persisted job state and recovery on startup (no new infrastructure); Redis/RQ only if needed later.
2. **Adzuna** keys (yours), plus an optional Jooble/Careerjet after terms check.
3. **Posting-date model:** `verified` (API timestamp / listing page / user) · `estimated` (alert-email date, "x days ago" text) · `unknown`; filters Today, 24h, 3d, 7d, 30d, custom; "Today" only for verified.
4. **Cross-source dedup:** canonical URL + (normalised company, title, location) fingerprint merges the same job from Adzuna, an ATS and a clip into one listing with multiple `job_sources` links.
5. **Matching v2:** add components *title relevance, industry relevance, salary fit, employment-type fit*; weights configurable per user (defaults keep today's behaviour); a 1–2 sentence **AI suitability summary** when an LLM is configured, labelled "rule-based" otherwise; LLM-aware re-scoring in the background (fixes the overwrite debt).
6. **Resume parsing v2:** industry, tools and technologies extraction from the taxonomy; DOCX support; optional LLM-assisted extraction where every item must be found in the resume text (anti-fabrication check).
7. **Feed v2:** company logos (favicon service via domain, cached), industry and employment-type filters, salary filter, infinite scroll, recently viewed, share (copy link / Web Share API), AI summary line.
**Exit:** discovery runs on a schedule for test users, dedup across sources verified, all filters tested.

## Phase 3: Browser extension and application assistance
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
| ngrok static domain | stable backend URL | any time |
| SMTP credentials (optional) | email notifications and password reset | Phase 7 |
| Chrome Web Store developer account (optional) | publish the extension instead of unpacked install | Phase 3+ |

## Effort and order
Phase 1 is a prerequisite for everything else. Phases 2 and 3 deliver the biggest user value. 4 → 5 → 6 → 7 → 8 follow. Each phase is shipped and verified on the live deployment before the next starts.
