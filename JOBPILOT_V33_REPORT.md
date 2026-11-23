# JobPilot V3.3: Portal Connections and guided discovery UX

Local only. Nothing was committed, pushed or deployed. No production database, container or `.env` value was touched.
The production backend on port 8000 and the `jobpilot-*` containers were not touched. Every run used throwaway SQLite
backends; the PostgreSQL check used a throwaway `postgres:16` container on port 55491, removed afterwards. Setup and
security details: `docs/PORTAL_CONNECTIONS.md`. Screenshots: `design-lab/preview/v33/`.

## What changed for users

**Overview.** Three full-width cards in order: LinkedIn, Naukri, Indeed. Each card has:
- a brand-coloured mark and a one-line summary;
- the real status;
- one primary action, at most two more, and footer links (Manage connection, Profile checklist, Capabilities &
  limitations, and Setup for admins).

The nine-line capability list is gone from the cards. It now lives in a **Capabilities & limitations** side panel,
grouped as Account / Discovery / Applications / Profile improvement. The setup reason is stated once per portal; the
"Official sign-in" row just says "Not set up on this JobPilot server yet."

**Statuses**
| Status | When |
|---|---|
| Not configured | No credentials on the server |
| Ready to connect | Sign-in is set up and nothing is linked |
| Connecting | On the way to the portal |
| Connected | Linked |
| Connected with limited permissions | Linked, but some requested scopes weren't granted |
| Reconnect required | Access expired or was revoked |
| Provider authorization required | The portal refused JobPilot's app in the admin's last real test |
| Opens in browser | Naukri |
| Temporarily unavailable | A check got a 502; the link is kept |
| Connection failed | Shows the cause and **Try again** |

Any simulated server or identity adds "(simulated)" to the label, the Connect button and the success toast. A
simulated identity never shows "verified by LinkedIn".

**Role-aware setup**
- **Admins** get **Set up LinkedIn / Set up Indeed**: a five-step side panel.
  1. The developer console link, plus the LinkedIn Company Page or Indeed partner-review requirement.
  2. The product and scopes, with an approval status.
  3. The callback URL from the server's own configuration, read-only, with Copy. Without `PUBLIC_APP_URL` it says what
     to set instead of inventing localhost.
  4. Client ID and a masked, write-only Client Secret.
  5. **Test connection**: the real sign-in. The result shows at the top of the panel.
- **Candidates** never see setup controls; the backend also returns 403 to them.
- **Not configured** shows candidates one plain reason and only the actions that work: Import, Open, Prepare.

**LinkedIn / Indeed (candidate)**
- **Connect** goes to the portal's own page.
- On success the card shows the provider's name and e-mail.
- **Manage connection** has the account details: granted permissions, missing scopes, dates, Check, Reconnect, and
  Disconnect with confirmation. The card updates only after the backend confirms.
- The profile photo is still not loaded; the panel says so.
- No profile sync, job API, Easy Apply or Indeed Apply is offered.

**Naukri**
- **Open Naukri** opens naukri.com in a new tab, so the JobPilot tab and session stay put.
- A note then explains how to come back and import the job's link.
- **Import Naukri job**, **Prepare application**, **Profile checklist** and **Capabilities** are also there.
- No Connect button or OAuth state ever appears.

**Guided import** (one implementation: `ImportDialog.tsx` → `GuidedImportDialog`, same `/jobs/import` service):
1. Paste the link.
2. Basic URL check in the browser.
3. **Check link** (new read-only `POST /jobs/import/preview`): recognises the portal and job ID, or finds the job
   already in your feed.
4. Add details from the listing.
5. Review. Nothing is saved before this step is confirmed.
6. **Save & score**, with progress.
7. **Prepare application** opens the Apply Workspace.

An unrecognised link can be entered by hand with a chosen portal; the unknown URL isn't saved.

**Find or import jobs** (under the cards)
- Browse your listings by portal, with per-portal feed counts. Each opens Discover filtered with the new `?platform=`.
- Import a link.
- The existing clipper card, in a side panel.
- The existing alert-mailbox setup, in a side panel, showing whether it's connected.
- A one-line "then" path: Prepare application → resume → answers → open the posting → report the outcome.

## Engineering

**New files**
- `backend/services/portal_setup_service.py`: admin overview, save/clear credentials, start and record tests.
- `backend/migrations/versions/0018_portal_provider_setup.py`: the additive `portal_provider_configs` table, plus
  `oauth_states.purpose` (default `link`).
- `frontend/src/components/settings/portals/`: `types.ts`, `hooks.ts`, `PortalLogo.tsx`, `ProviderCard.tsx`,
  `PortalSheet.tsx`, `SetupSheet.tsx`, `PrepareSheet.tsx`, `FindJobs.tsx`.
- `tests/api/test_v33_portal_setup.py` (11 tests), `design-lab/preview/v33_demo.py`, this report.

**Changed files**
- `backend/models/__init__.py`: the `PortalProviderConfig` model and `OAuthState.purpose`.
- `backend/services/identity_providers.py`
  - `credentials()`: environment settings win, otherwise admin-saved credentials, decrypted on the backend only.
  - `get(settings, key, db)` and `Provider.source`.
  - The simulator never applies to admin-saved credentials.
  - `invalid_client` / `unauthorized_client` from the token endpoint becomes the `client` error kind.
- `backend/services/connection_service.py`
  - `start(..., purpose)`.
  - `complete()` handles admin tests (admin only; links nothing, keeps no token) and records their verdict.
  - Clear messages for an app the portal refused.
- `backend/services/portal_service.py`
  - The status model with spec labels, `summary`, a single `reason` and `limited`.
  - The `listings` capability with feed counts, shorter capability text, and `prepare`/`browse`/`setup` actions
    (`setup` for admins only).
- `backend/api/routes/admin.py`: `GET /admin/portals`, `PUT|DELETE /admin/portals/{p}/credentials`,
  `POST /admin/portals/{p}/test`. All require `CurrentAdmin`.
- `backend/api/routes/portals.py`: `oauth/complete` returns `setup_test` for admin tests.
- `backend/api/routes/jobs.py`, `backend/services/discovery_service.py`: `POST /jobs/import/preview`.
- `frontend/src/components/settings/PortalConnections.tsx`: the page, the OAuth return per portal and purpose, and
  wiring for the sheets, import and Apply Workspace.
- `frontend/src/components/app/ImportDialog.tsx`: `GuidedImportDialog`. The existing Add job dialog is unchanged.
- `frontend/src/pages/DiscoverPage.tsx`: the `?platform=` filter.
- `frontend/src/components/settings/config.ts`: the section description.
- Tests and docs:
  - `frontend/src/test/portals.test.tsx` (rewritten, 25 tests);
  - `tests/api/test_v32_portal_accounts.py` (labels and actions updated);
  - `docs/PORTAL_CONNECTIONS.md`, `USER_GUIDE.md` (Portal Connections section);
  - `design-lab/preview/v32_local.py` (now also creates an admin test account).

**Reused, not duplicated**
- The OAuth flow, state binding, PKCE, ID-token checks and token encryption from V3.2 (`connection_service`,
  `identity_providers`, `CredentialCipher`).
- The `/jobs/import` ingest path, `record_from_mapping` parsing, the Apply Workspace (`ApplyDialog`), `ClipperCard`,
  `EmailSection`, the Discover platform filter and `require_admin`.

## Results
| Suite | V3.2 | Now |
|---|---|---|
| Backend (excluding the two daemon e2e files) | 599 passed, 3 skipped | 611 passed, 3 skipped, 0 failed |
| PostgreSQL 16: migrations to 0018 + V3.2/V3.3/portal API tests | 29 passed | 43 passed |
| Frontend unit | 97/97 | 115/115; `tsc -b` clean; oxlint: no findings in new or changed files |
| Extension unit | 78/78 | 78/78 (unchanged) |
| V3.3 browser walkthrough (`v33_demo.py`) | n/a | 34/34 checks |

**Not rerun:** the Greenhouse/Lever/Ashby and SmartRecruiters browser e2e. The extension and the apply backend weren't
changed.

`design-lab/preview/v32_demo.py` still asserts the old V3.2 card text, so it would now fail. `v33_demo.py` replaces it.

## Screenshots (`design-lab/preview/v33/`)
**Candidate**
- `q01_overview_candidate`
- `q02_capabilities_panel`
- `q03_naukri_open_and_return_hint`

**Guided import and application**
- `q04_import_link_recognised`
- `q05_import_review_before_saving`
- `q06_import_saved`
- `q07_apply_workspace_resume_choice`
- `q08_resume_chosen_ready_to_open`
- `q09_outcome_recorded_user_reported`
- `q10_tracked_in_applications`

**Find or import jobs**
- `q11_find_or_import_jobs`
- `q12_clipper_guidance`
- `q13_alert_email_setup`
- `q14_discover_filtered_to_naukri`

**Layout**
- `q15_mobile_overview` (390 px, no horizontal scroll)
- `q16_dark_overview`

**Admin**
- `q17_admin_overview`
- `q18_linkedin_setup_wizard`
- `q19_credentials_saved_ready_to_test`
- `q20_test_goes_to_real_linkedin_INTERCEPTED`
- `q21_test_result_refused_SIMULATED_ANSWER`
- `q22_candidate_sees_provider_authorization_required`
- `q23_indeed_setup_guidance`

**Connection flow (simulated providers)**
- `q24_ready_to_connect_SIMULATED`
- `q25_consent_page_SIMULATED`
- `q26_connected_SIMULATED`
- `q27_manage_connection_SIMULATED`

Video: `v33/video/`.

## Security findings
- **Client secret**
  - Write-only and encrypted with `CredentialCipher`. Never in any response, the page, the audit log or logs
    (`client_secret` is already redacted by `core/logging_setup.py`). Tests check all of these.
  - `CredentialCipher` uses `ENCRYPTION_KEY`, or a key derived from `JWT_SECRET`, the same as portal tokens and
    mailbox passwords. **Set `ENCRYPTION_KEY` in production**; rotating `JWT_SECRET` without it makes saved secrets
    unreadable, and they must then be re-entered.
- **Admin-only access**
  - Setup routes use `CurrentAdmin`; candidates get 403.
  - An admin's test state is bound to that admin: a candidate posting it gets 403 and nothing is linked.
  - Completing a test requires the admin role.
- **No simulator stand-ins**
  - Admin-saved credentials always use the real portal endpoints.
  - A server on `OAUTH_DEV_ENDPOINTS` can't run Test connection; its results are marked simulated and never count as
    verified.
- **Environment wins**
  - Environment settings take precedence over credentials saved in the app.
  - They're shown read-only, so the app can't override a deployment's configuration.
- **Import preview**
  - Only parses the link. Nothing is fetched from the portal and nothing is saved.
- **Unchanged from V3.2**
  - State hashing and single use, user binding, `iss`, PKCE, ID-token checks and token encryption.
  - No passwords, OTPs or cookies, no scraping, no automation on the portals.
- **Gap to decide on:** the candidate connect endpoint doesn't itself refuse when the last admin test was "refused".
  The UI hides the button; a direct API call would just get the portal's own refusal.

## Real-provider verification
- **Not verified live.** No LinkedIn or Indeed developer credentials exist.
- In the demo, the admin test really targeted `https://www.linkedin.com/oauth/v2/authorization` with the right
  `client_id` and `redirect_uri`. The browser intercepted it because the credentials were fake, and the refusal that
  came back was **simulated**.
- The connect flow screenshots use the labelled local simulator.
- To verify for real: create the LinkedIn app, then either
  - save its keys in Settings → Portal Connections → Set up LinkedIn as an admin, or
  - set `LINKEDIN_CLIENT_ID` / `LINKEDIN_CLIENT_SECRET`,

  register the callback, and press **Test connection**.

## Known limitations
- Provider marks are simple brand-coloured monograms, not official logo assets.
- The profile photo isn't loaded (no third-party image fetch, no CSP change).
- Indeed partner approval can only be observed through a real test; there's no Indeed API to query it.
- **Prepare application** lists up to 25 of the portal's jobs (most recent first).
- The user-guide screenshots `docs/guide/74*` show the old page and need a reshoot after deploy.

## Git status
Nothing committed, pushed or deployed. The V3.1, user-guide and V3.2 work remain uncommitted, as before, awaiting
approval. Pre-existing untracked items are untouched.
