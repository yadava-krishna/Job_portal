# JobPilot: Discovery Diagnostic Report (2026-11-04)

Diagnostics were run against the **live** stack (Docker project `jobpilot`, deployed commit `2463073`, database at Alembic revision `0002`). No data was changed. Personal data is reported as counts or flags only.

## 1. Root cause (exact)

**The live system has no automated job source that can produce jobs, and the one discovery run that happened reported success instead of explaining this.**

1. **No working automated source is configured or deployed.**
   - **Job-alert emails:** no mailbox is connected (`email_integrations`: 0 rows). Also, none of the three platform preferences has `alert_email` as a discovery source (all three are `browser_clipper` and `user_job_url` only).
   - **Adzuna:** `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` are unset in the backend container, and the user has no Adzuna platform preference row.
   - **Greenhouse / Lever / Ashby:** not in the deployed code. The deployed image's `backend/services/` has no ATS clients (`grep greenhouse discovery_service.py` returns 0). That engine exists only in the local working tree (section 6).
   - **LinkedIn / Indeed / Naukri:** by design these are user-driven (clipper, URL or paste, alert emails). There is no automated source for them.

   With no source able to return jobs, `jobs` = 0, `user_jobs` = 0, and the feed is empty for the only user.

2. **Errors are swallowed: a zero-result run is marked "completed".** In deployed `backend/services/discovery_service.py`:
   - **Lines 269–272:** the alert-email branch only records an error `if email_platforms:`. With no platform opted into alert emails, it skips silently.
   - **Lines 294–295:** the Adzuna branch only runs `if adz and adz.enabled:`. With no Adzuna preference row, it skips silently, so even the "Adzuna is not configured" error is never reached.
   - **Line 138:** `finish_run` marks a run `completed` when there are no errors.

   Live evidence: discovery run #3 (manual, sources `["alert_email","adzuna_api"]`) has status **completed**, 0 found, 0 new, `error_details = []`. The UI showed "0 new job(s)" as a success.

3. **The scheduler has never run a discovery.**
   - Health shows the scheduler `running`, but `last_run: null` and `next_run` is 2026-11-05 09:00 IST.
   - The backend was (re)started today after 09:00, and the only scheduled job is the 09:00 daily run.
   - Even when it runs, it calls the same `run_discovery` and would produce the same silent empty result.

## 2. Ruled out (evidence)

| Hypothesis | Finding |
|---|---|
| Background worker not running | Scheduler `running: true`; it simply has nothing that produces jobs (above). |
| Incorrect user-ID filtering | The tables are empty at the source: `jobs` = 0 and `user_jobs` = 0 globally, so no filter could hide rows. |
| Matching threshold too strict | Nothing reached matching. The threshold (70) only decides *shortlisted* versus *new*; neither hides a job from the feed. |
| Wrong date filters | The frontend sent `posted=range` with no dates (it was returned 200). Range with no dates adds only `posted_at IS NOT NULL`, which hides undated jobs. That is a minor UX trap (section 5) but not the cause, since there are 0 jobs. |
| Jobs not persisted | No insert was ever attempted (0 jobs found). |
| Frontend API problem | Requests to `/api/v1/jobs` and `/api/v1/jobs/discover` returned 200 and 202 through the tunnel; CORS preflights were OK. |
| Profile parsing | One candidate profile; confirmed (`confirmed_at` set). |
| Preferences missing | Preferences exist: 2 job titles, 2 locations, min score 70. |
| Network egress | From inside the backend container: Greenhouse 200 (Razorpay board), Lever 200 (Meesho), Ashby 200 (Sarvam). Adzuna returns 400 without credentials (expected). |
| Saved searches misconfigured | The deployed schema has the `saved_searches` table (rev 0002) but no code uses it; 0 rows. |

## 3. Integrations

| Source | Live status | Notes |
|---|---|---|
| Browser clipper / job URL / paste / file import | Working (user-initiated) | Tested in the suite; no jobs imported yet on the live account. |
| Job-alert emails (LinkedIn, Indeed, Naukri alerts) | Not configured | Needs a mailbox app password in Settings, plus the platform's "alert email" source ticked. |
| Adzuna API | **Missing credentials** | `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` unset. You said you will obtain them. |
| Greenhouse / Lever / Ashby (official public board APIs) | **Not deployed** | Reachable from the server. Engine implemented locally (section 6). |
| LinkedIn / Indeed / Naukri automated discovery | Not provided, by policy | Their terms prohibit scraping and automation without permission. Only user-initiated and alert-email paths are supported. Naukri's current terms are still to be re-verified (Phase B task). |
| AI scoring | Rule-based (labelled) | No LLM configured. A failed AI call falls back to rule-based and never removes jobs. |

## 4. Missing configuration

- `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` (in `.env`; never committed).
- A mailbox app password, if you want alert-email ingestion.
- Company watchlists or saved searches. These can only be created once the ATS engine is deployed.

## 5. Recommended fixes (ordered)

1. **Deploy the ATS discovery engine** (Greenhouse, Lever, Ashby; company registry; saved searches; scheduler tick every 15 minutes). This is the only automated source that works without credentials or third-party permission. Also seed each user with a starter saved search from their preferences, so the feed fills without manual setup.
2. **Never report an empty run as success.**
   - Every requested source that is unconfigured or has no companies must add an explanatory entry: "Adzuna not configured", "No companies configured", "No alert-email source enabled".
   - A run with 0 jobs found must carry a reason and be shown as "nothing found because …", not as success.
3. **Source health panel:** last attempt, last success, counts and errors for each source, from the `job_sources` registry.
4. **Feed empty states that explain why:** discovery never ran, no sources configured, credentials missing, filters too narrow.
5. Fix the date-range trap: `posted=range` with no dates should behave like "any".
6. Add Adzuna once you provide the credentials, and connect alert emails if wanted.

## 6. State of the local (undeployed) work

Already built in the working tree and **not yet deployed**:
- Official Greenhouse, Lever and Ashby clients, with error classification, size cap and a shared cache.
- The unified `NormalizedJob` schema.
- Cross-source dedup (source key, then job key, then canonical URL, then company + title with compatible locations) with `job_source_links`.
- Company registry: a 30-employer curated India list verified live today, plus the JobSync MIT directory with attribution.
- Saved searches with a scheduler tick, closed-job detection, notifications without duplicates, and new feed filters.
- Additive migration `0003_discovery`.
- Tests: 219 backend passed on SQLite (3 Postgres-only skipped) and 133 API tests on PostgreSQL, including mocked official feeds.

Frontend: card and filter changes are done; the Searches/Companies page is written; route, nav, notification bell and frontend tests are not done yet.

Gaps against your Phase 2 brief that are **not yet implemented**:
- The fix in 5.2 (swallowed errors in the legacy `run_discovery` path).
- A per-source health panel (5.3) and explained empty states (5.4).
- Automatic starter search per user.
- Pagination: the three board APIs return whole boards, so this is not needed there, but Adzuna paging is.
- Retry with backoff, and per-provider rate limiting.
- A "Run discovery now" action across all sources, with staged progress.
- Country and careers-URL fields on companies.
- The two-user end-to-end test and frontend loading/error-state tests.
- The required documents: `DISCOVERY_SOURCE_STATUS.md`, `DISCOVERY_TEST_REPORT.md`, plus updates to the README and architecture docs.

## 7. Resolution (implemented 2026-11-04)

| Recommended fix | Done |
|---|---|
| 5.1 Deploy the ATS engine; starter search per user | Greenhouse, Lever and Ashby engine; every onboarded user gets "Jobs matching my profile" (titles and locations follow preferences; 30 curated, live-verified employer boards; related titles). It is created at onboarding, on first visit or by the 15-minute scheduler tick, and runs immediately, then daily. Discover also starts a run automatically on the first visit. |
| 5.2 Never report empty runs as success | Every requested source records an outcome in `discovery_runs.source_results` (`ok`, `empty`, `partial`, `failed`, `not_configured`, `disabled`) plus a plain-language `summary`. A run where nothing could run is `failed`. A run that reached its sources but matched nothing is `completed` with "no listings matched" (distinct from failure). The legacy alert-email/Adzuna path no longer skips silently. |
| 5.3 Source health panel | `GET /api/v1/discovery/sources` plus Searches & sources → Source health: configured, connection, last attempt and success, jobs in feed, board counts, latest outcome, what's missing. |
| 5.4 Explained empty states | Discover shows why the feed is empty (never ran, running, failed with reasons, ran with no matches, filters too narrow), with "Run discovery now". |
| 5.5 Date-range trap | "Date range" with no dates filters nothing. Date filters report how many unknown-date jobs they hid and can include them, labelled. |
| 5.6 Adzuna | Integrated in saved searches and the legacy path; reported as "not configured" until `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` are set. |

Verification: see `DISCOVERY_TEST_REPORT.md`.
