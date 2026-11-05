# Phase 3 · Stage A: "Fill with JobPilot" extension: architecture and security assessment

Status: **approved and implemented (2026-11-05).** Decisions D1–D6 approved as recommended (D2: confirmation from both the
extension and JobPilot; D3: Greenhouse-hosted form offered only after it is verified live). D7 (stable ngrok domain): free
option documented, needs the owner's ngrok dashboard. Implementation notes: the device credential is kept in the extension's
IndexedDB (not chrome.storage, which content scripts can read); the extension also covers SmartRecruiters/Recruitee
discovery only on the server side (form filling remains Greenhouse, Lever, Ashby). See extension/ docs and
PHASE3_TEST_REPORT.md.
Date: 2026-11-05. Based on reading the code at `635a177` and on read-only inspection of live public application forms
(official Greenhouse question API and headless renders of one Greenhouse, Lever and Ashby form each, never typed into or submitted).

---

## 1. What exists today (verified in code)

| Area | Finding | Reuse? |
|---|---|---|
| Auth | `get_current_user` (`backend/api/deps.py`) accepts only 15-min HS256 access JWTs (`type=access`). Refresh tokens are hashed and rotate. | No: the extension must **not** use the user's login tokens. A separate dependency is added. |
| `extension_tokens` table | Exists since migration 0002, unused: `user_id, name, token_hash (unique), scopes JSON, last_used_at, expires_at, revoked_at`. | **Yes**: covers device tokens **and** pairing codes, with **no migration**. |
| `audit_logs` table | Exists (0002), unused. | Yes: pair, revoke and resume-download events. |
| Profile | `CandidateProfile.confirmed_profile` (`EditableProfile`: name, email, phone, location, headline, summary, skills, experience[], education[], …) and `verified_facts` (CTC, notice, relocation, work authorisation, start date, shifts). | Yes: the single source of truth, read server-side. |
| **Gap** | `EditableProfile` has **no LinkedIn / GitHub / portfolio / website** fields, yet Lever asks for all of them and Ashby often requires LinkedIn. | Add optional fields (JSON column, so **schema-only, no DB migration**). |
| **Gap (data)** | The owner's profile is confirmed (13 fields filled), but **all 7 verified facts are empty**. Screening questions on CTC, notice period and work authorisation will show "needs your input" until they are set. | The extension shows this as a missing-info warning with a link to Settings. |
| Resume | `GET /profile/resume`: owner-scoped, path-traversal checked, `Cache-Control: private, no-store`. | Same logic behind an extension-scoped endpoint. |
| Screening | `ScreeningAnswerer` (`applications/screening_answers.py`) is rule-based. It answers only from verified facts or resume dates, and never answers personal or legal questions. | **Yes**: the extension sends the question labels to answer, and nothing else. |
| Tracking | `applications` table is unique per `(user_id, job_id)`. Flow: `prepare` → `open_listing` (OPENED, never applied) → `confirm(submitted=…)` → `mark_submitted` (sets `submitted_at`, `confirmation_source`, `stage=applied`, `user_job.status=applied`). | **Yes**: the same service functions. No second tracker. |
| Job ↔ board | `job_source_links` plus `ats.base.parse_board_url` turn a Greenhouse, Lever or Ashby URL into (platform, board token, job id). | Yes: backend matches "which of my jobs is this page" without any ID in the URL. |
| CORS | Fixed allowlist. **Verified**: a `chrome-extension://…` preflight is rejected today (400). | Add the extension's fixed origin to `CORS_ORIGINS` (config, not code). |
| Backend URL | ngrok URL is random per restart and republished to `…github.io/Job_portal/config.json` (**verified** `Access-Control-Allow-Origin: *`). | The extension reads the URL from there, so no `*.ngrok-free.app` permission is needed. |

## 2. Architecture

```
 JobPilot web app (Pages)                Backend (FastAPI, ngrok HTTPS)
  Settings → "Connect extension"  ──JWT──▶ POST /extension/pairing-codes  → 8-char code, 5 min, one use
  Settings → devices / Disconnect ──JWT──▶ GET/DELETE /extension/tokens
  Apply dialog (unchanged flow)   ──JWT──▶ /applications/{id}/open, /confirm

 Extension (MV3, separate folder extension/)
  popup.html/js ── user enters code, sees status, presses "Fill with JobPilot", "I submitted it"
  service_worker.js ── ONLY place the extension token lives; ONLY component that talks to the backend
        │  fetch(apiBase + /extension/…)  Authorization: Bearer jpx_…  (CORS: extension origin)
        │  chrome.scripting.executeScript on the active tab only, after the click (activeTab-style)
  content/ (isolated world; no token, no network)
     core.js      field discovery, visibility/disabled checks, label resolution, safe setters, overlay
     greenhouse.js / lever.js / ashby.js  per-platform adapters (selectors + rules)
     review panel (Shadow DOM): filled / skipped-with-reason / needs-input / resume button
```

**Flow**
1. User opens the job from JobPilot (existing dialog marks it OPENED).
2. User clicks the toolbar icon. The popup asks the service worker to detect the platform from the tab URL (allowlist).
3. "Fill with JobPilot": the worker calls `POST /extension/match {url}` and gets the user's job or application for that page (or "not in JobPilot"). It then calls `GET /extension/autofill-profile` and gets a minimal field set plus a `missing[]` list.
4. The worker injects the adapter. The adapter scans visible, enabled fields and maps each one with a confidence score. Only high-confidence fields are filled, and **non-empty fields are kept** unless the user ticks "overwrite" for that field in the review panel.
5. Custom questions: the adapter sends the **question labels only** → `POST /extension/answers` → `ScreeningAnswerer`. Answers are filled only when status is ANSWERED **and** the field type and options match. Anything else is listed under "needs your input".
6. Resume: a button labelled "Attach my JobPilot resume" (an explicit click) makes the worker fetch the PDF. The content script builds an in-memory `File` and sets it on the platform's resume `<input type=file>` with `DataTransfer`. Nothing is persisted. If the input is missing, rejects the file, or uses a picker the browser does not allow scripts to drive, the panel shows "Download resume" and asks the user to attach it by hand.
7. User reviews and edits, solves any CAPTCHA, and **clicks Submit themselves**. The extension never touches submit buttons and never registers listeners on them.
8. Confirmation: "I submitted this application" (popup, or the existing JobPilot dialog) calls the same `confirm(submitted=true)`, so **SUBMITTED is set only on that explicit click** and gets `submitted_at` and `confirmation_source="extension_user_confirmed"`. The unique (user, job) constraint and `mark_submitted` idempotency prevent duplicates. A thank-you page is never treated as confirmation; at most the popup *suggests* confirming.

## 3. Authentication and pairing (chosen design)

| Step | Detail |
|---|---|
| Pairing code | Created in JobPilot Settings by the logged-in user (JWT). 8 characters, Crockford base32 (~40 bits), **5-minute expiry, single use**. Stored in `extension_tokens` as `sha256(code)`, `scopes=["pair"]`. A pair-scoped row is never accepted as a bearer token. At most 3 live codes per user. |
| Exchange | Popup → worker → `POST /extension/pair {code, device_name}`, unauthenticated and rate-limited (existing `auth_rate_limit`, plus 5 failures per 10 min per IP). The code row is revoked atomically. A new row is created: `jpx_` + 32 random bytes, hashed, `scopes=["autofill:read","applications:track"]`, `expires_at = now + 90 days`, `name=device_name`. The token is returned **once**. |
| Storage | Token in `chrome.storage.local`, read only by the service worker. Content scripts never receive it, and nothing is ever put on the page, in URLs or in DOM attributes. Profile responses are held in worker memory for the fill and discarded. |
| Every request | New `ExtensionPrincipal` dependency: hash lookup, then not revoked, not expired, user active, scope present. It updates `last_used_at` (throttled to 1 per 5 min). Data is user-scoped through the existing `scoped()` and `get_owned()` helpers. Extension tokens are **only** accepted on `/extension/*`. Existing routes stay JWT-only and unchanged. |
| Revocation | Settings → "Connected browsers" lists name, created, last used and expiry, with **Disconnect** (`revoked_at`). Popup "Disconnect" calls `POST /extension/disconnect` (self-revoke) and clears storage. Revocation takes effect on the next request (no caching). Password change and logout-all will also revoke extension tokens. |
| Why not a JWT exchange | An opaque token with a DB lookup is instantly revocable and simple. The extra short-lived-JWT hop gives no benefit at this scale. |
| Never | No JobPilot password in the extension. No cookies, `chrome.cookies`, history, passwords or session-storage access. No `externally_connectable`, so web pages cannot message the extension. |

## 4. Extension permissions (minimum)

```json
"permissions": ["storage", "activeTab", "scripting"],
"host_permissions": [
  "https://job-boards.greenhouse.io/*", "https://boards.greenhouse.io/*",
  "https://jobs.lever.co/*", "https://jobs.eu.lever.co/*",
  "https://jobs.ashbyhq.com/*"
]
```
- **No `<all_urls>`, no `cookies`, no `tabs`, no `webRequest`, no `history`.** The backend is reached through CORS (extension origin allowlisted), so there is no ngrok wildcard. The Pages `config.json` is public with ACAO `*`.
- The host permissions are needed so the adapter can run inside **Greenhouse/Ashby iframes embedded on employer sites** (`all_frames`). `activeTab` alone does not grant iframes on other origins.
- A fixed `key` in the manifest pins the extension ID, and so the `chrome-extension://<id>` CORS origin, for unpacked installs.
- No analytics. No AI. No third-party calls. Employer page content goes nowhere except the question **labels** sent to our own backend for rule-based answers.

## 5. Platform differences (from live forms, 2026-11-05)

| | Greenhouse (new job-boards UI) | Lever | Ashby |
|---|---|---|---|
| Form URL | `job-boards.greenhouse.io/<board>/jobs/<id>` and `/embed/job_app?for=<board>&token=<id>`; often embedded as an iframe on employer sites | `jobs.lever.co/<co>/<uuid>/apply` | `jobs.ashbyhq.com/<co>/<uuid>/application` (React SPA, also embeddable) |
| Identity fields | `#first_name`, `#last_name`, `#preferred_name`, `#email` (autocomplete attrs present) | `name="name"` (full name), `email`, `phone`, `location`, `org` (current company) | `#_systemfield_name` (full), `#_systemfield_email`, `phone_number` (often required) |
| Phone | intl-tel-input with country flag picker | plain text | plain text |
| Dropdowns | **react-select comboboxes** (`[role=combobox]`; no native `<select>`): country, location (async typeahead), school/degree (async) | native `<select>`, radios, checkboxes | radios with `<uuid>_question_<id>` names, Yes/No **buttons**, comboboxes |
| Links | custom `question_<id>` text | `urls[LinkedIn]`, `urls[GitHub]`, `urls[Portfolio]`, `urls[Other]` | custom questions labelled "LinkedIn Profile", "portfolio" |
| Custom questions | `question_<id>`; labels via `<label for>` | `cards[<uuid>][fieldN]`; real label in the enclosing `.application-question .application-label` (the input's own label is "Type your response") | `question_<id>`; `<label for>` |
| Resume | `#resume` file input (accepts pdf/doc/docx/txt/rtf), plus Dropbox and "Enter manually" | `#resume-upload-input`; **Lever parses it and may overwrite name/email**, so upload first, then fill | `#_systemfield_resume` (required). A **separate "autofill from resume" drop zone** must not be used |
| EEO / demographics | gender, Hispanic, veteran, disability comboboxes | diversity cards | gender and similar radios |
| Anti-bot | reCAPTCHA Enterprise (invisible) | hCaptcha on submit | reCAPTCHA Enterprise |
| Submit | "Submit application" | `#btn-submit` "SUBMIT APPLICATION" | "Submit Application" |

**Policy for all adapters**
- Never fill EEO, demographic, disability, veteran, race or gender questions, consent or legal checkboxes, password, OTP, CAPTCHA or hidden fields.
- Comboboxes are filled only when an option matches the normalised target exactly. Otherwise skip with the reason "no exact option".
- React inputs are set through the native value setter followed by `input` and `change` events.
- A `MutationObserver` re-scans steps that appear later. Each field is filled at most once per click, and a field the user edits afterwards is never refilled.

**Employer custom sites are unsupported, and the extension says so.** Example verified today: Stripe's Greenhouse jobs redirect to `stripe.com/careers/apply/…`, which uses Stripe's own form. Databricks and Okta are similar. 6 of the 9 Greenhouse jobs in the DB have such URLs. Option (decision D3): JobPilot offers "Open the Greenhouse-hosted form" (`/embed/job_app?for=<board>&token=<id>`, a Greenhouse page that returns 200 today), which the extension supports.

## 6. Backend changes (additive; no existing route changed)

New router `backend/api/routes/extension.py` under `/api/v1/extension`, plus `services/extension_service.py`:

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /pairing-codes` | user JWT | create code |
| `GET /tokens`, `DELETE /tokens/{id}` | user JWT | list and disconnect devices |
| `POST /pair` | none, rate-limited | code → device token |
| `POST /disconnect` | ext token | self-revoke |
| `GET /status` | ext token | user's display name, profile completeness and missing list, for the popup |
| `POST /match {url}` | ext `applications:track` | the user's job, user_job and application for this page (platform, board, id parsed server-side); never other users' data |
| `GET /autofill-profile` | ext `autofill:read` | **minimal** fields only: first, last and full name, email, phone, location, current company and title, latest education, links, verified facts, `missing[]`. No summary, skills, bullets, scores, other jobs or resume text |
| `POST /answers {questions[≤50]}` | ext `autofill:read` | ScreeningAnswerer results |
| `GET /resume` | ext `autofill:read` | active resume bytes, `no-store`, audited, rate-limited (10/hour). No URL that works without the token |
| `POST /applications/{id}/opened`, `/confirm` | ext `applications:track` | call the **existing** `open_listing` and `confirm` service functions |

Other changes:
- `EditableProfile` + profile editor: optional `linkedin_url`, `github_url`, `portfolio_url`, `website_url`, validated `https://`.
- `CORS_ORIGINS` + one origin.
- Revoke extension tokens on password change.
- `.env.example` documents the extension ID.

**Database: no migration needed** (reuses `extension_tokens` and `audit_logs`; the profile links live in the existing JSON column). If review prefers a dedicated pairing table, it would be one additive migration (0004), preceded by the usual verified backup and rehearsal.

Frontend:
- Settings → "Browser extension" card (code, devices, disconnect).
- Profile editor link fields.
- Apply dialog hint, plus the Greenhouse-hosted-form option (D3).

## 7. Proposed file structure

```
extension/
  manifest.json            MV3, minimal permissions, fixed key
  src/service_worker.js    token storage, backend client, injection, message validation (sender.tab + allowlisted URL)
  src/api.js               config.json → apiBase (https only), fetch wrapper, error mapping
  src/popup.html|css|js    pair / status / Fill / resume / "I submitted it" / disconnect
  src/content/core.js      scan, visibility, labels, setters, confidence, review panel (Shadow DOM)
  src/content/adapters/greenhouse.js | lever.js | ashby.js
  src/content/fieldmap.js  semantic keys ↔ label patterns (shared)
  tests/                   vitest + jsdom unit tests; fixtures recorded from live forms
  e2e/                     Playwright (real Chrome, --load-extension) against live forms: fill only, never submit
  README.md  INSTALLATION.md  SECURITY.md  PLATFORM_SUPPORT.md
backend/api/routes/extension.py, backend/services/extension_service.py, backend/schemas/extension.py
tests/api/test_extension.py
frontend: SettingsPage card, ProfileEditor links, ApplyDialog hint
```
Plain JavaScript with no bundler and no third-party runtime dependencies, so every line shipped is reviewable. The existing repository layout is unchanged.

## 8. Stages and tests

| Stage | Content | Tests |
|---|---|---|
| **B** Backend | extension router and service, profile links, CORS config, Settings card | pytest (SQLite and Postgres): pairing expiry, single use, brute-force limit, scope enforcement, revoked or expired token → 401, cross-user isolation (user B's token can never see A's jobs, resume or apps), ext token rejected on existing routes, JWT rejected on token-only routes, minimal-fields assertion, resume no-store and audit, confirm idempotent and no duplicate rows, OPENED ≠ applied |
| **C** Extension core + adapters | manifest, worker, popup, core, three adapters | vitest on **recorded real DOM**: detection, hidden/disabled skipped, preserve existing values, no double fill, radios/selects/checkboxes/textarea, combobox exact-match-only, EEO and consent never filled, submit never clicked (a spy on every submit button and form `submit`) |
| **D** Real browser | Playwright with Chrome and the unpacked extension against **live** Greenhouse, Lever and Ashby forms, using a temporary test JobPilot account with fictional data on the production backend (deleted afterwards, as in Phase 2) | Fields filled correctly, resume attached through DataTransfer (or the fallback shown), **no network request to the form's submit endpoint**, page never navigates. Then a manual check by you on a real job. |
| **E** Docs + deploy | the four docs, backup, deploy backend and frontend, unpacked install guide | full suites, live verification, report |

## 9. Security implications and residual risks

- **Token theft**: anyone who can read the extension's local storage on your machine has a 90-day token. It is limited to the autofill fields, the resume and application tracking, and can be revoked in Settings. That is lower than the existing refresh token in `localStorage` (S6).
- **Employer page**: profile values enter the page's DOM when you click Fill, which is the point. A hostile page could read them before you submit. The extension only runs on the 3 allowlisted ATS hosts, only on click, and only with the minimal field set.
- **Resume**: bytes pass worker → content script → the file input. They are never stored, never sent anywhere else, and never available through a URL.
- **Messages**: the worker accepts messages only from its own content scripts in tabs whose URL is on the allowlist. Message shapes are validated, and pages cannot reach the worker.
- **No auto-submit, CAPTCHA, OTP or anti-bot interaction**: enforced by adapter policy and tested.
- **Pairing code**: about 40 bits, with a 5-minute expiry, single use and rate limits, so online guessing is impractical.

## 10. Limitations (known before building)

- Employer custom application sites (Stripe, Databricks, Okta, …) are not fillable; see D3.
- Async typeahead comboboxes (Greenhouse location, school, degree) may need you to pick manually when no exact option is offered.
- Programmatic file attach works on all three hosted forms in Chrome today. Where it fails, a manual upload is required, using the download button.
- Screening answers are limited to what `ScreeningAnswerer` can answer from your verified facts, and yours are currently empty.
- Chrome and Edge (Chromium) only. Unpacked install; no Web Store listing without your approval.
- The backend URL changes on each ngrok restart. The extension follows `config.json` automatically, but a static ngrok domain would remove the dependency.

## 11. Decisions needing your approval

- **D1 Pairing and token**: the design in §3 (8-char code, 5 min, single use → opaque 90-day scoped token, reusing `extension_tokens`, no migration). Alternative: a dedicated pairing table (one additive migration).
- **D2 Where "I submitted it" may be clicked**: (a) **extension popup and JobPilot dialog, both explicit and using the same endpoint** (recommended), or (b) JobPilot dialog only, as your brief literally says.
- **D3 Employer custom sites**: (a) **show "Open Greenhouse-hosted form" for Greenhouse jobs whose URL redirects to an employer site** (recommended), or (b) keep opening the employer page and say "unsupported".
- **D4 Profile links**: add LinkedIn, GitHub, portfolio and website fields to the profile (no DB migration).
- **D5 Live-form testing (Stage D)**: fill live public forms with **fictional** data from a temporary account, never submit, then delete the account. Note that some employers' analytics may observe typed values even without a submit.
- **D6 Token lifetime**: 90 days (recommended), or 30.
- **D7 Static ngrok domain**: optional; if you create one, set `NGROK_DOMAIN` in `.env`.
