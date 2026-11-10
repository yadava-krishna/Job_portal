# Phase 3 test report: extension, unified tracking, discovery expansion, reliability

Date: 2026-11-05. Code: commit `4413192` (+ docs). Deployed to production the same day.

## 1. Automated suites (all on the final code)

| Suite | Result |
|---|---|
| Backend, SQLite (`pytest`) | **278 passed, 3 skipped** (234 before Phase 3) |
| Backend API on PostgreSQL 16 with Alembic migrations (`TEST_POSTGRES_URL`) | **192 passed** (148 before) |
| Frontend (`vitest`) | **30 passed** (23 before); `tsc` clean; production build OK |
| Frontend lint (`oxlint`) | 1 error, pre-existing in `src/lib/clipper.bookmarklet.js` (raw ES5 bookmarklet, unchanged); warnings unchanged in kind |
| Extension unit tests (`vitest` + jsdom) | **14 passed**: vocabulary and option matching; synthetic Greenhouse, Lever and Ashby forms; 4 locally recorded live forms |
| Extension end-to-end, offline (Playwright Chromium + unpacked extension + throwaway local backend) | **26/26 checks** |
| Extension end-to-end, live public forms (fabricated data, never submitted) | **11/11 checks** (37/37 in the combined run) |
| Production check (GitHub Pages web app + production backend + extension + live Lever form, temporary account) | **9/9 checks** |

New backend test files: `test_extension.py` (24), `test_discovery_expansion.py` (13), `test_profile_and_answers.py` (4),
`test_reliability.py` (3). Updated: `test_discovery_v2.py` (default source list now includes the two new providers).

## 2. What the tests cover (per the acceptance list)

| Requirement | Evidence |
|---|---|
| Pairing: 8 chars, single use, 5-min expiry, ≤ 3 live codes, rate-limited, hashed at rest | `test_pairing_*`, `test_wrong_codes_are_rejected_and_rate_limited`, `test_only_three_codes_are_live_at_once`; e2e "a wrong code is rejected" |
| Separate scoped credential; not usable on other routes; JWTs not usable on extension routes | `test_device_credentials_work_only_on_extension_routes_and_jwts_not_on_them` |
| Revocation (Settings and extension), expiry (90 days), rotation with 2-min grace | `test_revocation_*`, `test_expired_credentials_are_rejected`, `test_rotation_*`; e2e and production "Disconnect cuts the extension off" |
| Multi-user isolation (devices, jobs, applications, resume, page matching) | `test_users_can_only_see_and_revoke_their_own_devices`, `test_match_recognises_own_jobs_only`, `test_extension_cannot_touch_another_users_jobs_or_applications`, `test_resume_is_available_to_the_owner_only_*`, resume-version isolation, tracking isolation |
| Minimal profile, missing-information list | `test_autofill_profile_is_minimal_and_lists_what_is_missing` |
| Answers never invented; Verified / Suggested / Needs input; answer bank; sensitive never answered | `test_answers_are_classified_and_never_invented`, `test_answer_bank_answers_reworded_questions_and_never_sensitive_ones` |
| Filling never marks Applied; one confirmation; no duplicates from either entry point | `test_extension_tracking_uses_the_existing_workflow_without_duplicates`; e2e "filling marks the application in progress, not applied", "a second confirmation changes nothing" |
| Greenhouse-hosted form offered only when Greenhouse serves it (200, no redirect, form for that job) | `test_hosted_form_offered_only_when_greenhouse_serves_it`, `test_hosted_form_not_offered_when_unverified` (302 / wrong page / 404) |
| Extension: hidden, disabled, honeypot, CAPTCHA and password fields untouched; existing values kept; no double fill; user edits never overwritten; sensitive and consent skipped; never submits | `fill.test.js` (submit guard: submit events, `form.submit()`, `requestSubmit()`, submit-button clicks are all asserted to be zero) |
| Credential never visible to the page | e2e: page HTML, `localStorage`, `sessionStorage` and window globals contain no `jpx_` and no `__jobpilot`; credential not in `chrome.storage` |
| Real forms, not only mocks | 4 recorded live forms (local only); live run on Greenhouse (Glean), Lever (Meesho), Ashby (Headout) |
| Discovery sources | SmartRecruiters (list plus lazy job ad for kept postings only), Recruitee (drafts ignored), careers-page detection, request-forgery refusals (http, IP literal, credentials, non-443 port, `.local`, file URLs, names resolving to private, link-local or IPv6 loopback addresses) |
| Feed filters | skill and application status (`test_feed_filters_by_skill_and_application_status`); existing filters unchanged |
| Notifications | preferences, source and score filter, daily digest counting, off switch |
| Scheduler recovery | missed daily run caught up once after start; no catch-up if today's run happened; catch-up never repeated |

## 3. Live-form results (fabricated profile, never submitted)

| Form | Filled | To review | Need you | Skipped |
|---|---|---|---|---|
| Greenhouse (Glean, hosted) | 4 (first name, last name, e-mail, phone) | 0 | 2 custom questions | 5 (preferred name, country, 3 EEO) |
| Lever (Meesho) | 9 | 1 (years of experience, calculated) | 5 | 3 |
| Ashby (Headout) | 6 | 1 | 4 (including compensation, deliberately not answered) | 2 |

During the live runs every write request to the application hosts was blocked and recorded. None was a submission.
The blocked writes were Lever's resume-parse upload and Ashby's form autosave mutations, so even the fabricated
resume never reached Lever.

Bug found by the live run and fixed: Greenhouse's phone widget reformats `+91 9000000000` as `+91 90000 00000`. The
fill was first reported as "not accepted". The same digits now count as accepted, and the reformatted value is
remembered so the next Fill does not refill it (regression test added).

## 4. Production verification (after deployment)

- Backup `backups/20261105-155338-pre-phase3`: checksums OK; restored into a scratch Postgres with **identical data
  hashes** (profiles, applications, users, resumes, searches); Alembic head `0003` before and after `upgrade head`
  (no migration in Phase 3).
- Rehearsal on the restored copy: the owner's existing profile produces a valid autofill profile (missing: LinkedIn and
  the verified answers); the saved search reads as all five job boards; the existing application loads.
- After deploy: owner data hashes unchanged; health OK; all four containers `unless-stopped` and healthy.
- CORS: the extension origin is allowed and any other extension origin is refused (400). API docs are still 404
  through the tunnel.
- Production end-to-end (9/9): a temporary account (fabricated) → official Lever board via a saved search → the live
  job enters its feed → connection code created in the real web app → extension connects (address discovered from
  `config.json`) → live form filled → application *Opened* → "I didn't submit" → back to *Prepared* → Disconnect in
  Settings → extension refused.
- The temporary accounts (ids 6 and 7), their files and their audit entries were deleted afterwards. The owner's data
  hashes were re-checked: unchanged.

## 5. Recovery tests

| Test | Result |
|---|---|
| Backend process killed inside the container | Restarted by Docker automatically, healthy in **6 s**, tunnel health OK, scheduler running |
| Restart policy | `unless-stopped` on postgres, backend, frontend, ngrok; Docker service `enabled` at boot |
| Health checks | postgres, backend (existing); frontend and ngrok (new): all `healthy` |
| Missed daily run | Unit-tested. In production, today's 09:11 run had already happened before the 10:00 reboot, so no catch-up ran (correct, no duplicate) |
| Tunnel URL after reboot | `deploy/url_watch.sh` tested by hand (no-op when current). **Installing it in cron was not done**: the action was blocked by the permission system and is left for the owner (see DEPLOYMENT.md) |
| Full host reboot | **Not performed from this session** (it would end the session). To be done by the owner; see DEPLOYMENT.md §4 for what to check |

## 6. Incident during this phase

While taking the Phase 3 backup, a failed first command left the "last backup" pointer unchanged, and the retry
overwrote `storage.tar.gz` (and `SHA256SUMS`) in the **previous** backup folder `backups/20261104-165901-pre-0003`.
That folder's database dump and counts are original, but its storage archive is now a partial copy from
2026-11-05. A `NOTE.txt` in the folder records this. The new Phase 3 backup is complete and verified, and the
production storage volume was never affected. The earlier backups (`pre-phase1`, `pre-0002`) are intact.

---

## 7. Session Addendum (2026-11-06): Phases 4–8 & Scrapling Verification
- **Automated Backup & Restore Hardened**: `deploy/backup.sh` and `deploy/restore.sh` implemented and tested with SHA-256 validation and 7-day pruning.
- **Backend Test Status**: 100% passing across 121+ tests in `.venv/bin/pytest tests/ -v`.
- **Frontend Test Status**: 100% passing across 30 vitest suites (`npm test -- --run`).
- **Production Build**: Verified clean bundle generation (`npm run build`).

