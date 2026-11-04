# JobPilot: Discovery Test Report (2026-11-04)

## 1. Automated test suites (final run before deployment, commit `cda6dfd`)

| Suite | Result |
|---|---|
| Backend: CLI and API on SQLite (`pytest`) | **234 passed**, 3 skipped (the PostgreSQL-only migration tests) |
| API suite on PostgreSQL 16 + Alembic (`TEST_POSTGRES_URL=… pytest tests/api`) | **148 passed** (includes migrations 0002/0003 upgrade → downgrade → upgrade with seeded data, and schema = models) |
| Frontend (`vitest`) | **23 passed** (14 existing + 9 new) |
| Type check (`tsc -b`) and production build (`vite build`) | Clean |
| Lint (`ruff F,E9`; `oxlint`) | Backend clean. Frontend: no findings in new or changed files. Remaining warnings and the one error (`clipper.bookmarklet.js`, a deliberate raw ES5 file) are pre-existing |

New tests in this phase:
- `tests/api/test_ats_and_normalization.py` (46):
  - Greenhouse, Lever and Ashby parsing against mocked feeds that copy the live response shapes.
  - Greenhouse `updated_at` is never treated as a posting date.
  - Ashby unlisted postings skipped; Lever EU host.
  - HTTP 404/429/5xx/403 classification; timeouts; invalid JSON; size cap.
  - Bad tokens rejected before any request; board-cache sharing and caching of 404s; board-URL parsing (accepted and rejected).
  - HTML to text, canonical URLs, dedup keys, Indian city aliases, remote-India detection, vocabularies, and timezone-correct posting dates.
- `tests/api/test_discovery_v2.py` (40):
  - Saved search → scored feed; repeat runs add no duplicate jobs or notifications; the same title in two cities stays two jobs; same-board reposts merge.
  - A clipped LinkedIn job merges with its Greenhouse twin; Adzuna merges with a board listing.
  - Closed and re-listed jobs; unknown dates never counted as recent.
  - Feed and criteria filters; related titles versus strict titles.
  - Per-source outcomes and summaries; zero-match runs are "empty", not "failed"; all boards failing → failed; partial provider failure.
  - Nothing configured → failed with every reason listed; Adzuna missing credentials.
  - Starter search created once, includes Adzuna only when configured, and is not recreated after deletion.
  - "Run discovery now" with suggested boards and no manual setup.
  - Source-health panel before and after a run, and per user.
  - Date range without dates hides nothing; the hidden-unknown-dates count and the option to include them.
  - Two users with independent matches from shared boards; full cross-user isolation (searches, runs, watchlists, notifications, feed items: 404).
  - Scheduler due logic; interrupted runs; no concurrent duplicate runs; company add-by-URL validation; directory, suggested list and attribution.
- `frontend/src/test/discovery.test.tsx` (9):
  - Posting-date display never shows an unknown date as recent; cards show confidence, every source, discovery time and closed status; Apply only opens the dialog.
  - Run summary lists each source with its own status and reason, and a failed run is never shown as completed.
  - Empty-feed explanations: never ran, running, failed, no matches, filtered.
  - Source-health panel shows missing credentials, timing and counts.
- The existing LinkedIn, Indeed and Naukri clipper, URL, file-import and alert-email tests run unchanged through the new unified ingest path and pass.

Defects found by the tests and fixed before release:
- Source-health bookkeeping inserted a duplicate `job_sources` row within one session, and the error handler then crashed on a failed session. Fixed: de-duplicated, it can no longer break a run, and handlers capture the run id up front.
- Same-board reposts showed as two identical cards. The first fix was too broad: it merged a LinkedIn import with a Naukri import and so bypassed the existing duplicate-application guard. That was caught by the existing test and restricted to the same employer board.

## 2. Real discovery, before deployment (live public APIs, local stack, production frontend build)

Two users registered and onboarded through the API, then pressed **Run discovery now**. Nothing else was configured: no companies and no searches.

| | User A (finance: "Accounts Receivable Associate", "FP&A"; Bengaluru, remote-India) | User B (data: "Data Analyst", "Business Analyst"; Bengaluru, Hyderabad) |
|---|---|---|
| Starter search | Created automatically | Created automatically |
| Boards read | 30 of 30 (Greenhouse 18, Lever 8, Ashby 4) | 30 of 30 (shared cache: the run took 1 s) |
| Listings checked | 4,635 | 4,635 |
| Matched → in feed | 12 (Greenhouse 7, Lever 5) | 8 matched → **7** in feed (1 Headout repost merged) |
| Posting dates | 12 verified | 7 verified |
| Full descriptions | 12 | 7 |
| Top matches | Stripe "Corporate Accounting Analyst" 53, Databricks "Senior Payroll Accountant" 49, Stripe "AR Analyst" 39 | Okta "Senior Data Analyst" 72, Okta "Staff Data Analyst" 69, Headout "Lead Data Analyst" 67 |
| Run status | completed. Adzuna and email reported "not configured" | completed. Same warnings |

- **Isolation:** no shared feed items; B reading A's feed items gives 404 ×5; B reading A's run gives 404.
- **Real account, on a restored copy of the live database:** run against live boards → **13 jobs** (Greenhouse 7, Lever 6), all scored. Top: Stripe "AR Analyst" 64, Glean "Accountant" 61, Glean "Product Finance Analyst" 59.

### Browser (headless Chrome driving the production build)

| Check | Result |
|---|---|
| A sees 12 cards, B sees 7; neither sees the other's | Pass |
| Status card shows the run summary with per-source reasons | Pass |
| Every card shows a verified posting date chip, discovery time, source and match score | Pass |
| Job detail shows posting date (verified), "Found by JobPilot", "still listed", "Seen on" with the original link | Pass |
| Apply → "Open original listing" opens the stored URL in a **new tab** (e.g. `https://www.okta.com/company/careers/opportunity/8323989?gh_jid=8323989`); status becomes **OPENED**, `submitted_at` stays empty | Pass (third-party pages were blocked from loading during the test) |
| "Date range" with no dates still shows all 12 | Pass |
| Source health tab shows connection, last attempt and success, jobs in feed, board counts, and the missing Adzuna credentials and mailbox | Pass |
| Mobile 390 px: no horizontal overflow | Pass |
| JavaScript page errors | None |

## 3. Deployment verification (live)

| Check | Result |
|---|---|
| Backup | `backups/<timestamp>-pre-0003/`: `pg_dump` + storage tarball, SHA-256 verified, restored into PostgreSQL 16 with identical counts and hashes |
| Migration rehearsal on the restored copy | 0002 → 0003 → 0002 → 0003. User, preferences, profile and resume data unchanged; downgrade identical to the backup |
| Live migration | `Running upgrade 0002 -> 0003` at container start; Alembic at `0003`; 32 tables |
| Existing user | Row, preferences and profile hashes identical to the backup; 1 resume file present; volumes `jobpilot_pgdata` and `jobpilot_storage` untouched |
| Health | `status ok`, database connected, scheduler running |
| Public frontend | GitHub Pages serves the new build (`assets/index-BD2YdPPN.js`, same as the local build); `config.json` preserved; tunnel health 200 |
| Live public end-to-end (temporary account through Pages → ngrok, then deleted with its uploaded file) | First visit to Discover started discovery by itself; **12 real jobs** visible after 73 s (Greenhouse 7, Lever 5); run `completed` with Adzuna and email "not configured"; source health correct; no page errors |
| **Existing user, live** | Starter search "Jobs matching my profile" was created automatically. Run #5 (11:37 UTC, started by the automatic first-visit discovery): `completed`; 30 boards / 4,633 listings checked → **13 jobs in the feed** (Greenhouse 7, Lever 6), all scored, all with verified posting dates. Top matches: Stripe "AR Analyst" 64.1, Glean "Accountant" 60.5, Glean "Product Finance Analyst" 59.3, Meesho "Deputy Manager - Business Finance" 57.7, Databricks "Senior Payroll Accountant" 55.1. Next scheduled run: 2026-11-05. 0 notifications, because no score reached the user's 70% threshold (rule-based scoring). |
| Backend logs after deploy | No errors or tracebacks |

## 4. Remaining limitations

- **Coverage:** only employers that publish a Greenhouse, Lever or Ashby board. The curated list has 30. Many large Indian employers aren't on these ATSs and are not covered. More can be added by URL or from the directory.
- **Scores:** rule-based until an LLM provider is configured. Related-title matches score modestly (top 64 for the existing user), so none were shortlisted or notified at the default 70% threshold.
- **Greenhouse work mode:** Greenhouse publishes no work-mode field, so it is inferred from the description and can be wrong (e.g. "Remote" from a remote-friendly sentence).
- **Adzuna:** disabled until `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` are set. Its paging (one page of up to 50 per query) is unchanged.
- **Retries:** transient board failures are retried on the next scheduled run rather than with in-run backoff. The cache and the 6-hour not-found cache keep request volume low.
- **Notifications:** in-app only (the bell). No email digests yet (Phase 7).
- **LinkedIn, Indeed, Naukri:** not automated, by policy. They're available through the clipper, links, paste, file import and alert emails.
