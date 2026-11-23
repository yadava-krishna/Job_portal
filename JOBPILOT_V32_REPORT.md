# JobPilot V3.2: LinkedIn, Indeed and Naukri account integration and application hand-off

Local only. Nothing was committed, pushed or deployed. No production database, container or `.env` value was touched.
Every run used throwaway SQLite backends in temp directories; the PostgreSQL check used a throwaway container on port
55491, removed afterwards. Setup and security details: `docs/PORTAL_CONNECTIONS.md`. Screenshots and video:
`design-lab/preview/v32/`.

## Baseline (before editing)
Backend: 573 passed, 3 skipped. Extension: 78/78. Frontend: 91/91. One earlier frontend run had 2 load-related
timeouts, which passed on rerun; this is the known flake.

## Audit: existing vs added
| Area | Existed | V3.2 |
|---|---|---|
| Users and auth | JWT + refresh tokens, `AuditLog` | Reused unchanged. A portal account is never a way to sign in to JobPilot |
| External identity | None | `ExternalIdentity` and `OAuthState` tables (migration 0017) |
| Secrets at rest | `CredentialCipher` (Fernet, IMAP passwords) | Reused for portal tokens and the PKCE verifier |
| Portal Connections | Static capability list + LinkedIn/Naukri checklists | Per-user capability model; connect, complete, check and disconnect; checklists kept |
| Destinations | LinkedIn/Indeed/Naukri → `restricted` → native hand-off | Reused. A resume choice is now required before the portal page opens |
| Tracking | `/handoff` = page opened, `/confirm` = user-reported | Reused, and tested for Naukri end to end |
| Job ingestion | `ingest_normalized` (single path) | `provider_jobs` mapper, gated on approved access (none is approved) |

## Implemented, per provider
- **LinkedIn (Sign In with LinkedIn using OpenID Connect).** Authorization-code flow with scopes `openid profile email`,
  state and nonce. The ID token is verified against LinkedIn's JWKS: RS256 only, issuer, audience, expiry, nonce. The
  userinfo `sub` must match. The account is linked by stable subject.
  - The card shows the name, the e-mail and whether LinkedIn verified it, the granted permissions, the link date, the
    last check and the access expiry.
  - Check, disconnect, reconnect, and reconnect-needed (60-day token, no refresh) all work.
  - Job search, saved jobs, recommendations, the full profile and Easy Apply stay disabled, each with a stated reason.
  - PKCE is off by default because LinkedIn doesn't advertise it for web apps (`LINKEDIN_PKCE` turns it on).
  - A nonce that is present is always checked. LinkedIn's discovery document lists no nonce claim, so requiring one is
    opt-in (`LINKEDIN_REQUIRE_NONCE`).
- **Indeed (3-legged OAuth).** Scopes `email offline_access` only; `employer_access` and any other scope are refused.
  Uses PKCE S256 and the RFC 9207 `iss` check on the callback. The ID token is verified if Indeed sends one, then
  userinfo is called.
  - Refresh works with rotation; a refused refresh means reconnect needed.
  - Unlinking works. Neither provider has a revocation endpoint, so the user is told where to remove JobPilot on the
    portal itself.
  - Indeed's live discovery document lists `job_seeker.jobs.search` and `job_seeker.profile.read`, but no documentation
    or API for them exists, so JobPilot neither requests nor calls them. Job retrieval and submission are reported as
    unavailable.
- **Naukri (native hand-off).** The card says "Opens on Naukri"; no sign-in exists, so no connect state is ever shown.
  - **Open Naukri** and **Import job link** work.
  - In the Apply Workspace, a Naukri job resolves to its original listing. **Open on Naukri** is disabled until a resume
    is explicitly chosen, then opens in the same browser, so an existing Naukri session is reused.
  - Opening the page is recorded as "page opened". **Yes, I submitted it** records `user_reported`, shown as "not
    independently verified".
- **Shared.**
  - Each card shows every capability separately: official sign-in, account linked, profile access, jobs into JobPilot,
    job listings via API, opening jobs on the portal, applying via API, automatic filling, profile checklist.
  - Buttons appear only when they work. Without credentials the card says "Sign-in not set up" and names the missing
    settings.

## Live verified
**None.** No LinkedIn or Indeed developer credentials or partner approval are configured (`.env` has none), so no live
OAuth flow or provider API was exercised. Only the providers' public discovery documents were fetched (2026-11-23) to pin
endpoints, issuers and algorithms.

## Simulated
- `tests/api/test_v32_portal_accounts.py`: providers simulated with `httpx.MockTransport` at the real LinkedIn and
  Indeed URLs, with RSA-signed ID tokens, a JWKS, and checks on client credentials, redirect URI and PKCE.
- `design-lab/preview/v32_demo.py`: the real web app and two local backends (one unconfigured, one configured) against
  a simulated LinkedIn/Indeed sign-in server on 127.0.0.1. Its pages are labelled SIMULATED, and production refuses
  `OAUTH_DEV_ENDPOINTS`. Naukri pages are intercepted and replaced by a labelled stub.

## Blocked (what's needed to go live)
- **LinkedIn:** a LinkedIn Developer app with the *Sign In with LinkedIn using OpenID Connect* product. Set
  `LINKEDIN_CLIENT_ID` and `LINKEDIN_CLIENT_SECRET`, and register `<PUBLIC_APP_URL>/oauth-callback.html` as the
  redirect URL.
  - Then one live sign-in, to confirm the ID token's `iss` value and whether LinkedIn returns the nonce. If it does,
    set `LINKEDIN_REQUIRE_NONCE=true`.
  - Job, profile or apply APIs need LinkedIn partner programmes, which are not available to JobPilot.
- **Indeed:** an approved Partner Console app with 3-legged OAuth (Indeed reviews these). Set `INDEED_CLIENT_ID` and
  `INDEED_CLIENT_SECRET`, and allowlist the same redirect URL.
  - Job retrieval or submission would need an Indeed partnership granting a documented job-seeker API. None is
    published.
- **Naukri:** nothing to configure; no public sign-in or API exists.
- **Deploy:** set `PUBLIC_APP_URL` on the backend, deploy the frontend (it includes `oauth-callback.html`), and run
  migration 0017.

## Engineering
**New files**
- `backend/services/identity_providers.py`: pinned endpoints, config validation, PKCE, HTTP client, ID-token
  verification.
- `backend/services/connection_service.py`: start, complete, check/refresh, disconnect, status.
- `backend/services/provider_jobs.py`: gated mapper into the existing ingest path.
- `backend/migrations/versions/0017_external_identities.py`.
- `frontend/public/oauth-callback.html` and `oauth-callback.js`.
- `tests/api/test_v32_portal_accounts.py` (26 tests).
- `design-lab/preview/v32_demo.py`, `docs/PORTAL_CONNECTIONS.md`, this report.

**Changed files**
- `backend/models/__init__.py`: `ExternalIdentity`, `OAuthState`.
- `backend/config.py`: provider settings. Also `PUBLIC_APP_URL` is now actually read; docker-compose passed it but
  settings ignored it, so password-reset links were relative.
- `backend/services/portal_service.py`: the capability model.
- `backend/api/routes/portals.py`: connect, complete, check, disconnect.
- `backend/services/tracker_service.py`: data export lists linked accounts, without tokens.
- `core/logging_setup.py`: redaction of OAuth tokens, codes, states, secrets and JWTs.
- `frontend/src/components/settings/PortalConnections.tsx`: cards, the sign-in return, actions.
- `frontend/src/components/settings/config.ts`: section description.
- `frontend/src/components/app/ApplyDialog.tsx`: the portal resume gate and session note.
- `frontend/src/features/apply/ResumeChooser.tsx`: upload-it-yourself note on portals.
- Tests and docs: `frontend/src/test/portals.test.tsx`, `apply_workspace.test.tsx`, `tests/api/test_portals.py`,
  `.env.example`, `docker-compose.yml` (environment pass-through only), `USER_GUIDE.md` (Portal Connections text).

**Migration 0017** is additive and creates two tables. It was tested on PostgreSQL 16 with `test_migrations.py`
(upgrade, downgrade, re-upgrade, schema matches models). The V3.2 and portal tests also ran against PostgreSQL: 29
passed.

**Security checks covered by tests**
- Rejected states:
  - unknown, reused, expired;
  - another user's state (and it is burned).
- Rejected ID tokens:
  - wrong nonce, foreign signature, wrong audience, wrong issuer;
  - expired;
  - HS256 algorithm confusion;
  - missing ID token.
- Indeed callbacks with a foreign `iss`.
- Duplicate identity across users (409), and cross-user isolation (check/disconnect another user's account → 404 or
  nothing).
- Tokens absent from every API response, the audit log, logs and the export, and encrypted at rest.
- Cascade on account deletion.
- `employer_access`, extra scopes, non-HTTPS or fragment redirect URIs, and dev endpoints in production are all refused.

**Independent review.** A separate code review of the OAuth code found no vulnerabilities and five correctness issues,
all fixed with tests:
- A 5xx from Indeed's token endpoint no longer forces a reconnect; it answers 502 and keeps the link.
- A rotated refresh token's expiry is now recorded.
- A check locks the identity row (`FOR UPDATE`). On SQLite it re-reads the row instead, so a double-click can't spend a
  rotated refresh token twice and drop a healthy link.
- The state is claimed atomically (`UPDATE … WHERE used_at IS NULL`).
- A long provider `error_description` no longer fails validation.

Forced JWKS refetches are also throttled to one per 30 s.

**Regression results (after all changes)**
| Suite | Baseline | Now |
|---|---|---|
| Backend (excluding the two daemon e2e files) | 573 passed, 3 skipped | 599 passed, 3 skipped, 0 failed |
| Extension unit | 78/78 | 78/78 (extension unchanged; still 2.4.0) |
| Frontend unit | 91/91 | 97/97; `tsc -b` clean; oxlint: no findings in touched files |
| Greenhouse/Lever/Ashby browser e2e | 39/39 | 39/39 |
| SmartRecruiters browser e2e (SIMULATED) | 14/14 | 14/14 |
| V3.2 browser walkthrough (SIMULATED providers) | n/a | 17/17 |
| PostgreSQL 16: migrations + V3.2 + portal tests | n/a | 29 passed |

## Demonstration
`.venv/bin/python design-lab/preview/v32_demo.py` starts the Vite app on `http://localhost:5199`, two throwaway backends
and the simulated provider. It prints PASS/FAIL per step and writes `v32/demo_results.json`.

Screenshots in `design-lab/preview/v32/`:
- `p1_not_configured_three_cards`
- `p2_configured_not_linked`
- `p3_linkedin_consent_SIMULATED`
- `p4_linkedin_linked`
- `p5_both_linked_permissions`
- `p6_disconnect_confirm`
- `p7_linkedin_disconnected`
- `p8_reconnect_needed`
- `p9_cancelled_nothing_linked`
- `p10_naukri_apply_resume_required`
- `p11_naukri_ready_open_on_naukri`
- `p12_naukri_page_SIMULATED`
- `p13_back_did_you_submit`
- `p14_recorded_user_reported`
- `p15_tracked_in_applications`

Video: `v32/video/portal_connections_and_naukri_handoff_SIMULATED.webm`.

## Known limitations (carried and new)
- SmartRecruiters is still not verified against a real application form (bot check). That is unchanged from V3.1.
- LinkedIn and Indeed linking are unverified live (see Blocked). The identity is shown only; nothing in JobPilot uses it
  yet beyond display and status.
- The profile photo URL is stored but not loaded, to avoid a third-party image request and a CSP change. The card says
  what was shared.
- Provider monograms stand in for logos. Official brand assets weren't added.
- `USER_GUIDE.md` text is updated. Its Portal Connections screenshots (`docs/guide/74*`) come from the live site and will
  need a reshoot after deploy.

## Git status
Nothing committed, pushed or deployed. Pre-existing untracked items are untouched: `.vscode/`,
`JOBPILOT_STATUS_AND_OPEN_QUESTIONS.md`, `design-lab/preview/all-pages-light.png`, `design-lab/preview/shots/`,
`design-lab/preview/videos/`, `engine/bench/recall_results.json`. The V3.1 work and the user-guide changes from before
are also still uncommitted, awaiting your approval.
