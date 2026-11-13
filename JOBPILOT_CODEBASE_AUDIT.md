# JobPilot Codebase Audit

Date: 2026-11-11 · Scope: the whole repository (425 tracked files) · Method: read-only. I traced the code, queried the live database and API, and ran the existing test suites. No code was changed.

**Evidence labels**
- **[V]**: verified today by a test run, a live API call or a database query.
- **[C]**: traced in the code but not run.
- **[A]**: an assumption or inference.

---

## Executive summary

JobPilot is a multi-user job-search assistant. It finds jobs from official sources only, scores them against a candidate profile, and helps the candidate prepare an application. The candidate always submits on the employer's site themselves.

**Live today:** a FastAPI + Postgres backend and a React frontend, running in Docker on the owner's machine. The frontend is also on GitHub Pages and reaches the backend through an ngrok tunnel. A Chrome extension fills (never submits) Greenhouse, Lever and Ashby forms.

**Test status:**
- Backend: 348 passed, 3 skipped. **[V]**
- Frontend: 44 passed. **[V]**
- Extension unit tests: 14 passed. **[V]**
- Live end-to-end check: 27/27 passed, both locally and through the public tunnel. **[V]**

**Six main concerns**
1. **Leftover single-user CLI.** An older SQLite-based CLI still sits in the same repo. The portal reuses its libraries.
2. **AI is not active.** The configured provider is `rule_based` and no API key is set. Every "AI" feature is deterministic in practice, and the `ai_calls` log has never been written. **[V]**
3. **A fabrication risk in the apply orchestrator.** When the candidate's work authorization is unknown, it answers "Yes" to "Are you authorized to work in India?" (`backend/services/apply_orchestrator.py:157`). It also labels Greenhouse/Lever/Ashby as "Direct Submission API", although it submits nothing. No UI calls it, but the API endpoint is reachable.
4. **Discovery fails partway on every run.** 9 of 18 recorded runs are `partial`. One Ashby board (Bjak) fails each run with "response too large", and the Lever board for Brillio times out. **[V]**
5. **Built but unused.** About 20 API endpoints and 4 tables are built but used by no UI, or never written at all.
6. **Exposure and stability.**
   - The tunnel goes straight to the backend, bypassing nginx.
   - The frontend port is bound to `0.0.0.0`, so it is open to the local network.
   - There is no CSP.
   - The tunnel URL changes on every restart. It was stale this morning. **[V]**

---

## 1. Product overview and architecture

```
GitHub Pages (static React build, reads config.json for the API URL)
        │ HTTPS, bearer token
        ▼
ngrok tunnel ──► backend:8000 (FastAPI, uvicorn, APScheduler in-process)
                     │                     ▲
localhost:3080 ─► nginx (frontend) ─/api/──┘
                     │
                     ▼
               postgres:16 (internal network only) ◄── backup container (pg_dump)
Chrome extension (MV3) ──► same API, device token
```

| Layer | Evidence |
|---|---|
| Compose services: postgres, backend, frontend (nginx), backup, ngrok (profile `tunnel`), cloudflared (profile `quicktunnel`) | `docker-compose.yml`; `docker compose ps` all healthy **[V]** |
| Backend app factory, 17 routers, 217 API operations | `backend/main.py`; live `/api/v1/openapi.json` **[V]** |
| Migrations run on container start, now at Alembic 0008 | `backend/Dockerfile` CMD; `alembic_version`=0008 **[V]** |
| Backend reuses the legacy packages `core/`, `intelligence/`, `resume/`, `discovery/`, `applications/`, `reports/`, `platforms/`, which are copied into the image | `backend/Dockerfile`; imports counted with grep **[V]** |
| Legacy single-user CLI on SQLite (`main.py`, `runner.py`, `scheduler.py`, `database/db.py`, `systemd/job-automation.service`) | `main.py --help` runs **[V]**; systemd unit not installed **[V]** |

## 2. Frontend (React 19, Vite, TanStack Query, Tailwind 4, HashRouter)

- **Routes (22)** are defined in `frontend/src/App.tsx`:
  - `/login`, `/register`, `/forgot-password`, `/reset-password`, `/onboarding`
  - `/dashboard`, `/discover`, `/saved`, `/applied`, `/searches`, `/reports`, `/settings`
  - `/career`, `/studio`, `/studio/:id`, `/interview-prep`, `/mentor`, `/mentoring`, `/international`
  - `/admin`, `/clip`, plus a catch-all `*`
- **Pages:** 15 page files in `frontend/src/pages/` (3,736 lines). Feature modules are in `features/career`, `features/growth` and `features/studio`; shared components are in `components/app/`.
- **API client:** `lib/api.ts`.
  - The access token is held in memory only. The refresh token is kept in `localStorage`, an XSS exposure (see §7).
  - The base URL comes from `lib/config.ts`, which reads `./config.json` at runtime.
- **Frontend-to-backend wiring:** the frontend makes 153 API calls, and every one maps to an existing backend route (script cross-check against OpenAPI). **[V]**
- **UI/UX:** dense card and list layouts, skill chips, a score ring, and badges for sponsorship, seniority and "Not eligible" (`components/app/JobCard.tsx`). There is an offline screen when the API can't be reached (`OfflineScreen.tsx`). I didn't do a visual or browser walkthrough in this audit. **[A]**
- **Static checks:** `tsc` is clean. **[V]** `oxlint` gives 2 warnings (`contexts/ConnectionContext.tsx:35,198`). **[V]**

## 3. Backend APIs, services and business logic

| Router (tag) | Ops | Key service(s) |
|---|---|---|
| auth | 8 | `auth_service.py`, `security.py` |
| profile, preferences, platforms, integrations | 27 | `resume_service.py`, `profile_master_service.py`, `preference_service.py` |
| jobs | 16 | `discovery_service.py`, `matching_service.py`, `scoring_v2.py` |
| applications | 13 | `application_service.py`, `apply_orchestrator.py` |
| tracker (interviews, offers, contacts, export/delete) | 16 | `tracker_service.py` |
| companies, saved-searches, notifications, discovery | 25 | `company_service.py`, `saved_search_service.py`, `notification_service.py`, `connectors/`, `ats/` |
| extension | 13 | `extension_service.py` |
| reports, dashboard | 8 | `report_service.py`, `dashboard_service.py` |
| career (skills, evidence, gaps, learning) | 26 | `career_service.py`, `skill_gap_service.py`, `learning_service.py` |
| resume studio, resumes | 17 | `studio_service.py`, `studio_render.py`, `pdf_generator.py`, `docx_generator.py`, `resume_tailor_service.py` |
| growth (interview prep, mentor, international, funnel) | 33 | `interview_service.py`, `mentor_service.py`, `international_service.py` |
| admin, health | 15 | `admin_service.py`, `jobs_registry.py` |

**Business logic (code traced)**
- **Matching:**
  - The v1 `intelligence/job_matcher.py` score feeds `scoring_v2.py`, which uses 8 weighted dimensions summing to 100 (asserted at line 37). Eligibility is kept separate. `matching_service.py:104,123`
  - Skills with project-level evidence or stronger count towards matching. **[V]** (tests)
- **Discovery:**
  - Uses the official Greenhouse, Lever, Ashby, SmartRecruiters and Recruitee board APIs (`services/ats/`).
  - Also uses public feed connectors (`services/connectors/`: RemoteOK, Remotive, Arbeitnow, Himalayas, RSS, JSON-LD, sitemap, NCS, government, academic).
  - `scrapling_client.py` fetches pages with a robots.txt check, an SSRF block and rate limits. **[C]**
  - Live jobs by platform: Greenhouse 34, Ashby 13, Lever 13, SmartRecruiters 4, LinkedIn 1 (user import). **[V]**
- **Scheduler:** 15 registered jobs in `jobs_registry.py:285-300` (discovery, matching, gaps, notifications, reports, visa checks, rollups, cleanup). Live `job_runs` rows show matching, gaps, normalisation and notifications `ok`, and `alert_email_ingestion` `blocked`. **[V]**
- **Applications:** opening a job is not the same as applying. A submission needs explicit user confirmation, and the resume version is locked once confirmed. **[V]** (smoke steps "opened is not applied", "confirm submitted", "resume version locked")

## 4. Database

- **Scale:** 74 tables and 103 foreign keys in Postgres. **[V]** There are 73 ORM models: 43 in `backend/models/__init__.py` (844 lines) and 30 in `backend/models/career.py`.
- **Migrations:** `backend/migrations/versions/0001…0008`. 0007 (career graph) is the largest, at 623 lines.
- **Core relationships (traced through the foreign keys):**
  - `users` 1-N `resumes`, `candidate_profiles`, `user_jobs`, `applications`, `saved_searches`, `extension_tokens`, `refresh_tokens`.
  - `jobs` 1-N `user_jobs` (per-user score and status) and `job_source_links` (cross-source dedupe).
  - `applications` 1-N `application_events`, `interviews`, `offers`, `application_contacts`, `stage_transitions`.
  - Career graph: `candidate_skills` 1-N `skill_evidence`; `gaps`, `match_history`, `learning_sessions`.
  - Studio: `resume_versions` 1-N `resume_sections` → `resume_blocks` → `resume_bullets`; `resume_exports`; `resume_feedback`.
  - Mentoring: `mentor_assignments` 1-N `mentor_notes`, `mentor_sessions`, `mentor_actions`.
- **Live data:**
  - Users 3, jobs 65, user_jobs 61, companies 206, applications 4.
  - Seeded tables: countries 10, visa routes 9, learning resources 150, templates 6. **[V]**
- **Never written (0 rows, no writer code):**
  - `task_queue` and `it_government_schemes` have no code that creates `TaskQueueItem` or `ITGovernmentScheme`. **[V]**
  - `ai_calls`: the model exists, but nothing ever creates one. **[V]**
  - `candidate_profiles_v2` has 0 rows, because its API has no UI. **[V]**

## 5. AI/LLM and automation

- **Provider layer:** `core/llm.py` supports three providers: `anthropic`, `openai_compatible` (for example a local Ollama container) and `rule_based`. It falls back to rule-based when the provider is unusable. **[C]**
- **Live configuration:** the provider is `rule_based`, set by `PORTAL_LLM_PROVIDER` → `LLM_PROVIDER` in `docker-compose.yml:64`. No `ANTHROPIC_API_KEY` is set. **[V]**
  - Consequence: JD analysis, matching, tailoring, interview prep and the mentor plan are all deterministic and template-based.
- **Where the LLM would be called:** only `matching_service.get_llm` calls `build_llm`. **[V]** Tailoring, interview prep and the mentor plan never call an LLM. **[C]**
- **No AI audit trail:** prompt versioning, cost tracking and `AICall` logging don't exist (`ai_calls` = 0). **[V]**
- **Automation:** APScheduler runs inside the backend process (`scheduler_service.py`), with a catch-up run after downtime. **[C]** The scheduler is running, and its next daily run is 2026-11-12 09:00 IST (from `/health`). **[V]**
- **No browser automation anywhere:** a grep for playwright and selenium in `backend` and `extension/src` returns nothing. **[V]**

## 6. Chrome extension (`extension/`)

- **Manifest:** MV3 1.0.0. Permissions are `storage`, `activeTab` and `scripting`. Host permissions cover only the Greenhouse, Lever and Ashby job-board domains. **[V]**
- **Code:**
  - `src/content/core.js` fills fields. It never calls `submit` or `requestSubmit`, and only clicks radio and checkbox inputs and list options (lines 9-10, 169-177). **[C]**
  - Site adapters are in `src/content/adapters/{greenhouse,lever,ashby}.js`. The token store is `src/lib/vault.js`, which deliberately avoids `chrome.storage.local`. The popup lets you pair the device.
- **Backend side:** `/extension/*` covers pairing codes, device tokens (rotate and disconnect), field matching, the autofill profile, the resume, and starting and confirming applications.
- **Tests:** 14 unit tests pass (`extension/tests/unit/fill.test.js`). **[V]** The e2e scripts (`extension/e2e/run_e2e.py`, `prod_check.py`) were **not run today**. The live `extension_tokens` table has 0 rows, so no device is paired. **[V]**
- **Not published to the Chrome Web Store.** It installs unpacked, and the fixed ID depends on `.deploy/extension-key.pem`. **[C]**

## 7. Authentication, security and deployment

| Control | Status |
|---|---|
| Passwords hashed with argon2 | `backend/security.py:15-30` **[C]**, tests pass **[V]** |
| Access tokens are HS256 JWTs with required claims; refresh tokens are random and stored hashed | `security.py:58-67`, `auth_service.py:93-107` **[C]** |
| Sign-up needs an invite: a global code from `.env`, or a hashed admin invite with expiry and use count | `auth_service.py:61-68` **[C]**, smoke register **[V]** |
| Password reset uses a signed, time-limited JWT | `auth_service.py:140-156` **[C]** |
| Rate limiter is a sliding window in memory: per-process, lost on restart | `security.py` `RateLimiter` **[C]** |
| CORS allowlist, no cookies; headers `nosniff`, `DENY`, `no-referrer`, `no-store` on the API | `backend/main.py:52-88`, `frontend/nginx.conf:9-11` **[C]** |
| **No Content-Security-Policy** | neither nginx nor FastAPI sets one **[C]** |
| API docs served to local callers only (`DOCS_MODE`) | `main.py` `docs_allowed` **[C]** |
| IMAP passwords Fernet-encrypted. **The key is derived from `jwt_secret` when no separate key is set**, so leaking one secret exposes both | `backend/config.py:23`, `security.py` `CredentialCipher` **[C]** |
| Refresh token in `localStorage` (XSS-readable) | `frontend/src/lib/api.ts:4,27` **[C]** |
| Postgres has no host port; backend bound to `127.0.0.1` | `docker-compose.yml:30,83` **[C]** |
| **Frontend bound to `0.0.0.0:3080`**, open to the LAN | `docker-compose.yml:97` **[C]** |
| **ngrok forwards to `backend:8000`, not nginx**, so the public path skips the nginx headers and proxy | `docker-compose.yml` ngrok `command` **[C]** |
| Containers run with `restart: unless-stopped`, CPU/memory limits, and a non-root backend (uid 10001) | `docker-compose.yml`, `backend/Dockerfile` **[C]** |
| Tunnel URL rotates on restart; `deploy/url_watch.sh` republishes it, but its cron line isn't installed | the stale `config.json` found today **[V]** |
| No hard-coded secrets found by a grep of tracked files; `config/candidate_profile.json` holds only nulls | **[V]** |
| No logged-in scraping: LinkedIn, Indeed and Naukri are "assisted" (search links, alert emails, user import only) | `platforms/linkedin.py:1-11` **[C]** |

## 8. Tests and actual status (run today)

| Suite | Result |
|---|---|
| Backend pytest (`tests/`, 286 test functions, parametrised to 351 cases) | **348 passed, 3 skipped** in 72 s **[V]** |
| Skipped | `tests/api/test_migrations.py:82,114,146`, which need `TEST_POSTGRES_URL`. **Migrations aren't tested on Postgres in CI** |
| Backend test database | SQLite with `create_all` (`tests/api/conftest.py:38`). Postgres-only code, such as full-text search at `routes/jobs.py:140`, is checked only by the live smoke |
| Frontend vitest (8 files in `frontend/src/test/`) | **44 passed** **[V]** |
| Frontend typecheck / lint | clean / 2 warnings **[V]** |
| Extension vitest | **14 passed** **[V]** |
| Live smoke, 27 steps from register to account delete (scratchpad `smoke.py`, not committed) | **27/27** on localhost:3080 and through the tunnel **[V]** |
| Not run / don't exist | browser e2e of the UI, extension e2e, visual regression, load tests, reboot or restore drills |

## 9. Feature status

**Implemented and verified [V]** (by tests and the live smoke)
- **Onboarding and profile:**
  - invite sign-up, login, refresh and password reset;
  - resume upload and parse, then confirming the profile;
  - preferences, platforms, onboarding;
  - a manual profile without a resume.
- **Jobs:**
  - job import and 8-dimension scoring;
  - filters (country, seniority, sponsorship, eligibility) and Postgres full-text search;
  - saved searches and watchlists.
- **Career:** the snapshot and next step, gaps, skill evidence with re-scoring and history, and learning (gated on consent).
- **Resume Studio:** 6 templates, PDF preview and DOCX export, feedback.
- **Growth:** interview prep, the mentor plan, international/visa routes, the funnel.
- **Applications:**
  - the open → confirm flow with the resume version locked;
  - interviews and offers with .ics export;
  - account export and delete.
- **Admin:** users, invites, metrics, the jobs registry.
- **Extension:** form-fill logic, unit tests only.

**Partially implemented**
- **Discovery** works but fails partway on every run (§10).
- **Email notifications:** the code exists, but no SMTP is configured, so delivery is blocked. **[V]**
- **Alert-email ingestion:** the job is `blocked` because no mailbox is connected. **[V]**
- **Master profile v2** (`/profile/master`, `/profile/experiences`): API only, with no UI and 0 rows.
- **Resume tailoring** (`/resumes/tailor*`): API only; the Studio replaced it in the UI.
- **Apply orchestrator** (`/applications/jobs/{id}/orchestrate`, `/email-draft`): API only, and its route labels are misleading.
- **AI gateway:** the abstraction exists but isn't active, and there's no logging or versioning.
- **Reports:** a daily Excel report exists; weekly and monthly don't.

**Missing**
- CSP.
- Retry, backoff and circuit breaking for job-board fetches.
- Separate dev and beta Compose profiles.
- A health-check or diagnostics script.
- Browser e2e and visual-regression tests.
- Score calibration from real outcomes.
- Off-host backup.
- A durable, shared rate limiter.

**Broken or defective**
1. **The Bjak Ashby board fails on every discovery run** ("Job board response is too large"), and the Brillio Lever board timed out. Recent runs found 0 new jobs (runs 24-26). **[V]**
2. **`apply_orchestrator.py:157` defaults unknown work authorization to "Yes"**, and line 68 defaults it to "India (Citizen)". This breaks the project's own "never guessed" rule (`config/candidate_profile.json` `_comment`). **[C]**
3. **Wrong route labels in the orchestrator.** Route A says "Direct Public ATS Submission API" but submits nothing. Route B says the browser extension covers Workday, SmartRecruiters and others, but the extension supports only 3 ATS sites (`apply_orchestrator.py:127-146`). **[C]**
4. **The public site broke on its own after a restart** because the tunnel URL changed and nothing republished it. **[V]**

## 10. Technical debt, duplication and risks

**Duplication**
- **Two applications in one repo:** the legacy CLI on SQLite (`main.py`, `database/`, `runner.py`, `scheduler.py`, `systemd/`) and the portal on Postgres. They share the libraries but keep separate data.
- **Two profile models:** `candidate_profiles` (what matching reads) and `candidate_profiles_v2` (unused).
- **Two resume-tailoring paths:** `resume_tailor_service`/`tailored_resumes` and Resume Studio.
- **Two scorers:** the v1 `JobMatcher` with the v2 overlay on top, which exposes both `components` and the 8 dimensions.
- **Three source layers:**
  - `discovery/sources.py` (legacy),
  - `backend/services/ats/*`,
  - `backend/services/connectors/*`,
  - plus `source_registry.py`, `source_policies.py` and `source_health.py`.
- **Code with no caller:**
  - About 20 API endpoints have no frontend or extension caller (for example `/profile/master`, `/resumes/tailor`, `/applications/{id}/email-draft`, `/discovery/detect-ats`, `/matches/recompute`, `/resources`, `/jobs/{id}/intelligence`).
  - 3 tables have no writer, and 1 more has no rows (§4).
- **28 Markdown documents at the repo root**, many of them older design and status files. They risk going out of date relative to the code. **[A]**
- **Oversized modules:** `backend/models/__init__.py` (844 lines) and `discovery_service.py` (696).

**Prioritised gaps and risks**

| # | Priority | Gap / risk | Evidence | Fix direction |
|---|---|---|---|---|
| 1 | P0 | Fabricated screening answer defaults in the orchestrator | `apply_orchestrator.py:68,157` | return "needs input" when unknown |
| 2 | P0 | Public path skips nginx; frontend open to the LAN; no CSP | `docker-compose.yml:97`, ngrok `command` | tunnel → nginx, bind to 127.0.0.1, add CSP |
| 3 | P0 | Discovery fails partway on every run; no retry, backoff or size handling | `discovery_runs` 9/18 partial | handle large responses, retry and back off, isolate failing boards |
| 4 | P0 | Tunnel URL rotation breaks the public site | stale `config.json` today | static ngrok domain or the url_watch cron |
| 5 | P0 | Migrations never tested on Postgres; unit tests on SQLite only | 3 skipped tests | run the tests against a disposable Postgres |
| 6 | P1 | AI features are labelled as AI but are rule-based; no `AICall` audit | `ai_calls`=0, provider `rule_based` | label results honestly; log calls when enabled |
| 7 | P1 | IMAP encryption key derived from the JWT secret | `config.py:23` | require a separate key |
| 8 | P1 | Refresh token in `localStorage` | `lib/api.ts:27` | CSP first, then consider an httpOnly cookie |
| 9 | P1 | Rate limiter in memory only | `security.py` | fine for one worker; document or persist it |
| 10 | P1 | Duplicate profile, tailoring, scoring and source layers, plus about 20 endpoints with no UI | §10 | pick one of each; remove or flag the rest |
| 11 | P2 | Legacy CLI and SQLite still in the repo and the image | `backend/Dockerfile` COPY lines | move shared libraries under `backend/` and retire the CLI |
| 12 | P2 | No browser e2e, visual regression, extension e2e, or reboot and restore drills | §8 | add Playwright-style UI e2e; schedule the drills |
