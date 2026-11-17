# JobPilot 2.0: Implementation Inventory and Checklist

Started: 2026-11-16. This is the working tracker for the JobPilot 2.0 overhaul. Each item is ticked only after it has been tested.

**Ground rules for this overhaul**
- No AI models, and no AI credentials.
- Existing data is preserved. Migrations only add things, and a verified backup is taken first.
- Nothing is submitted without the user authorising that specific application.
- Third-party terms and protections are respected.

## Baseline (confirmed before any change)

| Suite | Result |
|---|---|
| Backend pytest | 356 passed, 1 failed, 3 skipped. The failure was a real bug, now fixed (see P0-1). |
| Extension e2e (real Chromium) | 30 checks before; 31/31 after Phase 1 |
| Frontend vitest | 44 passed |
| Extension vitest | 14 passed |

## Inventory of major subsystems

**Status key**
- **OK:** working correctly
- **ENH:** needs enhancement
- **REF:** needs refactoring
- **BRK:** broken
- **UNT:** untested
- **BLK:** blocked by an external platform or dependency

| Subsystem | Status | Evidence / root cause |
|---|---|---|
| Auth (invite, JWT, refresh, reset) | OK | Tests and live smoke. The refresh token sits in localStorage, which is P5. |
| Profile and onboarding | OK / ENH | The flow works. The parser is PDF-only and rule-based (Phase 2). |
| Resume parser (`resume/resume_parser.py`, `profile_builder.py`) | ENH | Plain text from PyMuPDF. Headings must be ≥80% capitals and match keywords. No DOCX, no layout or columns, no tables. |
| Resume Studio rendering (`studio_render.py`, ReportLab and python-docx) | ENH / REF | Six basic templates. PDF and DOCX layouts are built separately. No pagination controls. |
| Discovery: ATS boards and feeds | OK / ENH | Fixed in 4d43789. Freshness, expiry and dead-link checks are missing (Phase 3). |
| Discovery: LinkedIn, Naukri, Indeed | BLK | Their terms forbid automated access. Only user clipping is possible. |
| Discovery: Adzuna, Jooble, Careerjet | BLK | Each needs API credentials from the owner. The code exists for Adzuna only. |
| Matching (8 dimensions plus eligibility) | OK / ENH | Explanations are partial. Synonyms are limited. |
| Application tracking | OK / ENH | There's no fine-grained apply state (draft → filling → review → submitted or uncertain). |
| Apply orchestrator | BRK → fixed | It gave made-up default answers ("Yes" to work authorisation, a 30-day notice period, Bengaluru) and its route labels were misleading (P0-2). |
| Chrome extension | ENH / REF | It's safe and tested, but limited:<br>• three platforms only;<br>• a single fill engine file;<br>• labels detected by regex only, with no confidence;<br>• no preview taken from the live form state;<br>• no submit workflow or state machine;<br>• one resume only. |
| Saved answers | ENH | `verified_facts` plus `custom_answers` exist. They have no timestamps or provenance, and no flags for sensitive or context-dependent answers. |
| Scheduler and background jobs | BRK → fixed | Catch-up compared an IST due time with stored UTC run times, so on SQLite some jobs could repeat after a restart (P0-1). |
| Notifications | ENH | In-app notifications work. Email is blocked until SMTP is configured. |
| Admin console | OK / ENH | Extension diagnostics and source freshness are missing. |
| Hosting and tunnel | ENH / BLK | The ngrok URL rotates. A free static ngrok domain needs the owner to claim it (a new credential or config). |
| Security headers / CSP | ENH | There's no CSP. The tunnel skips nginx. The frontend is bound to 0.0.0.0 (P5). |
| Tests | ENH | No Postgres migration tests in CI, no extension e2e in the routine run, no PDF layout tests. |

## Checklist

### Phase 0: audit and stabilisation
- [x] Confirm the baseline for all three suites.
- [x] **P0-1:** the catch-up timezone comparison (`scheduler_service._catch_up_registry_jobs`) now converts the due time to UTC.
- [x] **P0-2:** the orchestrator no longer makes up answers. Unknown facts are `NEEDS_INPUT`, and the route labels are honest.
- [x] Migration and rollback strategy: additive Alembic revisions only. Before each one, take a verified `pg_dump` and rehearse up, down and up on a restored scratch copy (never on port 55432).

### Phase 1: Smart Apply (extension 2.0). Done locally on 2026-11-16, not yet deployed
- [x] Modular content scripts:
  - `dom.js`: DOM helpers.
  - `fieldmap.js`: the classifier.
  - `scan.js`: reads the form.
  - `fill.js`: fills it.
  - `resume.js`: attaches the resume.
  - `review.js`: builds the review.
  - `submit.js`: submits and watches for confirmation.
  - `core.js`: entry points.
  - `panel.js`: the review panel.
  - Adapters: greenhouse, lever, ashby, workday, generic.
- [x] Multi-signal classifier with confidence:
  - signals: label, `autocomplete`, name/id, placeholder, type;
  - fill threshold 0.75;
  - conflicts are refused;
  - "Not sure" fields are filled only when the user clicks.
- [x] New field keys: address, city, state, postal code, country, phone country code and national number, graduation
  year. Values derived from the profile are marked "please review".
- [x] Resume choice: uploaded PDFs, or Studio versions as PDF or DOCX (`GET /extension/resumes`,
  `GET /extension/resume?kind=&id=&format=`). The attachment is read back from the input; if it fails, the user gets
  an honest manual hand-off.
- [x] Live-state preview:
  - sections: job, personal, professional, documents, questions;
  - the source of each answer;
  - validation (missing, invalid, upload errors, warnings);
  - a fingerprint; any change makes the review stale.
- [x] **Mode A:** the user submits on the page, and the extension watches for the confirmation.
- [x] **Mode B:** a trusted click, a reviewed fingerprint and confirmed ticks allow one click on the site's own submit.
  Greenhouse, Lever and Ashby only.
- [x] **Mode C:** LinkedIn, Naukri and Indeed are blocked in code; the popup offers copy-ready details, resume
  download, and recording the application.
- [x] Apply state machine:
  - migration 0010 (additive: `apply_state`, `apply_state_at`, `apply_mode`, `apply_session`);
  - `POST /extension/applications/{id}/state`;
  - `GET /extension/applications/{id}` for recovery;
  - duplicate prevention (409 once submitted);
  - "submitted" requires a confirmation signal;
  - an uncertain outcome becomes CONFIRMATION_PENDING until the user answers.
- [x] Confirmation detection: in the page (success URL or text, adapter-specific), and after navigation (the service
  worker re-checks).
- [x] Multi-step: Workday step detection, step-change notice, button dropdowns. Mode A only.
- [x] Optional per-site permission for other employer sites (`optional_host_permissions`, one site at a time, from a
  popup click).
- [x] Saved answers:
  - server-set `created_at` and `updated_at`;
  - `_updated` timestamp per fact;
  - `applies_to: one_job` answers are returned as SUGGESTED, with a reason;
  - committing answers must be ticked before Mode B.
- [x] UI:
  - a side-docked review panel (collapse, move left or right, Review and "What JobPilot did" tabs, status chips,
    accessible tabs and labels);
  - the popup shows resume choice, step, recovery prompt, permission view and hand-off view.
- [x] Web app: Smart Apply state on the Applications page and in the detail view; saved answers get a "use for"
  choice and a "Saved <date>" label; extension wording updated.
- [x] Tests:
  - backend 364 passed, 3 skipped, plus the 3 Postgres migration tests passed on a disposable DB;
  - extension unit 27, up from 14;
  - real-Chromium e2e 31/31, including one authorised submission, confirmation, a stale review and duplicate
    prevention;
  - frontend 44.
- [x] Migration 0010: rehearsed up, down and up on a restored copy of the live database (4 users, 6 applications,
  371 jobs intact). Backup `backups/pre-0010-20261116T060619Z` is checksum-verified.
- **Limits:**
  - Workday and the generic sites are tested on synthetic forms only, not on live tenants.
  - The LinkedIn hand-off can't be driven by the e2e (no activeTab in a test-opened popup); it is covered by unit
    tests.
- [ ] **Deploy** (backend rebuild, which applies migration 0010; frontend; reloading the extension): awaiting the
  owner's go-ahead.

### Phase 2: Resume Studio. Done locally on 2026-11-16, not yet deployed

**Root causes found on real renders of the old ReportLab output**
- Modern Professional: a 152 pt hole under the sidebar on page 1, and the layout changed after page 1.
- Long resumes: a last page holding 2–3 lines.
- Dates on their own lines, tiny bullets, and uneven spacing.
- Duplicated achievement bullets (lifted out of experience bullets by the parser).

**Work done**
- [x] **New renderer** (`backend/services/studio_render.py`):
  - HTML/CSS through WeasyPrint 66, compared side by side with the old output before replacing it;
  - deterministic pagination rules: headings never end a page, an entry's title and dates stay with its first
    bullet, short entries are never split, bullets are never split, long entries may continue on the next page;
  - right-aligned dates;
  - clickable mailto/tel/web links;
  - embedded, subset fonts;
  - PDF metadata;
  - "page X of Y" from page 2.

  Pages now fill to 86–99% (the old ones stopped well short), and keep-with-next no longer chains across sections.
- [x] **DOCX from the same render model and layout spec.** Same fonts, sizes, margins, spacing and accent; dates
  right-aligned with a tab stop; keep-with-next; hyperlinks; core properties. Word-for-word parity with the PDF is
  tested for all templates.
- [x] **Seven templates:**
  - Classic ATS, Modern Professional (labels in the margin), Technical Engineer, Experienced Professional,
    Fresher/Graduate, Executive (new) and International;
  - the keys are unchanged, so existing versions keep working, and catalogue rows are updated in place.
- [x] **Settings with guard rails:** font from each template's list, size 9–12 (9.5 or more on ATS templates), line
  height, margins, section spacing, heading style (no margin labels on ATS templates), accent colour (contrast 4.5 or
  more on white), date format, page size.
- [x] **Layout report** (`GET /studio/versions/{id}/layout`): pages, fill of each page, warnings, and fit suggestions
  that apply only when the user clicks them. Content is never removed.
- [x] **Editor:**
  - undo/redo (buttons and keyboard, typing grouped into single steps);
  - drag-and-drop for sections and entries, with the arrow buttons kept for keyboard users;
  - Design controls for every setting;
  - a layout bar on the preview.

  Autosave, save status, version history and restore, copies, and template switching already existed.
- [x] **Parser** (no AI):
  - Word `.docx` (page headers, tables as separate items, layout tables, bullets);
  - layout-aware PDF: two-column pages are read column by column, with guards against title/date rows and
    margin-label layouts;
  - Title-Case and Indian headings ("Career Objective", "Personal Details", "Declaration" is kept out of skills);
  - "June, 2021" dates;
  - one skill per line;
  - contact details (name, e-mail, phone, location) from pieces separated by "|";
  - the "Title / dates / Company" layout.
- [x] **DOCX upload:** magic-byte check, macros refused, zip-bomb limit, original kept, served with the right type.
  The extension can attach `.docx` uploads.
- [x] **Quality checker:**
  - issues labelled by kind (format, accuracy, writing, job);
  - duplicates, date order, missing dates, odd characters, layout warnings;
  - reads the exported PDF back with the parser;
  - states how the score is calculated (no "ATS score").
- [x] **Job tailoring:** reorder skills, reorder projects, reorder bullets, and add skills from the profile only,
  matching skill synonyms through the taxonomy. Every suggestion is "supported" and applied only when the user
  accepts it.
- [x] **Tests:**
  - backend 432 passed (55 new rendering tests, 11 parsing tests including a round trip through all 7 templates, and
    checker and tailoring tests);
  - frontend 46 (undo/redo, layout bar);
  - extension 27, plus real-Chrome e2e 31/31.
- [x] **Visual review:** Studio Content, Design and Check tabs with a local backend and a throwaway database.
- [x] **Docker:** the backend image builds with Pango and the fonts (`fonts-liberation`, `fonts-lato`,
  `fonts-urw-base35`, `fonts-dejavu-core`) and renders correctly inside the container.
- **Limits:**
  - No OCR: scanned PDFs are still refused, with a clear message.
  - Uncertain parser fields are corrected on the profile review screen; the source text isn't shown next to each
    field yet.
  - The editor's preview is the real PDF, refreshed about 1 second after each save, not keystroke-live.
- [ ] **Deploy:** this needs a backend image rebuild (new system packages) and frontend publish. Awaiting the owner.

### Phase 3: Discovery and matching. Deployed on 2026-11-16 (migration 0011)
- [x] Normalised facts, filled on every ingest and back-filled once by the `job_normalisation` job (each row is version-stamped):
  - locations, countries and remote scope: `core/locations.py`;
  - salaries in any currency: `core/salary.py`;
  - migration 0011 (additive): `location_normalized`, `remote_scope`, `salary_*`, `expires_at`, `link_status`, `link_checked_at`, `normalized_version`.
  - The raw text the source wrote is kept and shown on hover.
  - The country used to be dropped on ingest (a bug); it is now stored.
- [x] Salaries are never converted between currencies. With no period stated, only 5-figure and larger amounts are read as yearly, and they're labelled "assumed".
- [x] Freshness (`backend/services/freshness.py`):
  - states: open / unconfirmed / unchecked / expired / closed, each saying how and when it was confirmed;
  - "expired" no longer sets `closed_at`;
  - old jobs still listed on the board stay open;
  - the source's own closing date is respected;
  - the feed hides closed and expired jobs by default.
- [x] Dead-link check (`job_link_check`, daily 04:30):
  - only for jobs no board re-confirms;
  - never LinkedIn, Naukri, Indeed or Glassdoor;
  - goes through the shared client (robots.txt, SSRF guard, rate limits);
  - 60 pages a day at most, each job once every 3 days;
  - only a 404/410 or a clear "job closed" title or visible text closes a job.
- [x] Duplicate grouping: the feed shows one card per company and title. Filters apply first, then grouping; the other cities and re-posts are listed on the card. `group_similar=false` lists them all.
- [x] Connector fixes:
  - Himalayas: dates (Unix seconds), closing date, currency and period, application link, seniority, and the countries a job is open to. Every job used to read "Worldwide Remote".
  - A source can now correct its own earlier location or salary.
- [x] Matching:
  - remote roles not open to the candidate's country score 10 on location (they used to score 100), and remote roles that don't say get 85;
  - the salary dimension uses the normalised pay;
  - `breakdown` lists what matched, partly matched, didn't match, and couldn't be checked;
  - the score version is `v2.2026-11.2`;
  - 35 new skills and many synonyms, including upper-case acronyms (O2C, P2P, R2R, DSO, ERP).
- [ ] New sources (Adzuna is built; Jooble and Careerjet aren't). All three need API keys from the owner. Not started.

### Phase 4: UI/UX. Done locally on 2026-11-17, not yet deployed
- [x] Dashboard action centre (`GET /dashboard/overview`, `backend/services/overview_service.py`, `features/dashboard/`). Every line is built from real rows and links straight to its job or application:
  - new matching jobs: the last 7 days, at or above the user's own minimum score, not opened yet;
  - needs your attention;
  - coming up;
  - saved jobs (with a warning when a saved job is no longer open);
  - recently submitted;
  - resume status;
  - discovery health.
- [x] Fixed: the old Today panel showed a company line the API never sent (always blank). It is replaced by the action centre.
- [x] Deep links: `#/applied?app=<id>` opens that application, and `#/discover?job=<id>` opens that job. Both also react to a new link while the page is open.
- [x] Applications Kanban (`features/applications/PipelineBoard.tsx`):
  - drag and drop between stages, plus a "Move to stage" menu on each card for keyboard and screen-reader users;
  - each card shows days since applying, a follow-up-due flag and the match score;
  - columns fill wide screens.
- [x] Application history in plain words: "Moved to Interview" instead of "stage changed", and "You confirmed it in JobPilot" instead of `source=user_confirmed`. The dashboard's recent activity uses the same labels.
- [x] Onboarding:
  - an accessible stepper (`aria-current`, labelled steps, "Step N of 5" heading);
  - focus moves to the new step;
  - a "What happens next" box covers discover, then resume, then apply with review.
- [x] Accessibility:
  - a skip link;
  - `main` landmark and labelled navigation;
  - the mobile menu is a modal dialog and closes with Escape;
  - focus outlines on navigation and links;
  - a label on the contact delete button;
  - shared `LoadingState` (announced to screen readers) and `ErrorState` (with retry) in `common.tsx`, used in place of 12 bare spinners.
- [x] Fixed: Discover stopped following a run after 5 minutes, but full runs take about 7.5. It now follows a run for up to 15 minutes.
- [x] Tests: `tests/api/test_dashboard_overview.py` (2) and `frontend/src/test/phase4.test.tsx` (5).
- [x] Visual review (Playwright, throwaway SQLite stack): light and dark at 1366 px, and light at 390 px. No console errors.
- [ ] Not done:
  - a full design-token pass over every older page (Mentor, International, Interview prep);
  - an automated axe accessibility check in CI (no axe package is installed; adding one needs approval of a new dependency).

### Phase 5: Hardening. In progress (2026-11-17, local, not deployed)
- [x] In-app notifications: the `notification_sweep` job runs hourly at :15 (`backend/services/notification_sweep.py`).
  - What it alerts on:
    - follow-up due;
    - interview within 24 hours;
    - an application left unfinished for more than 3 days, or one Smart Apply couldn't confirm;
    - a saved or in-progress job that is no longer listed;
    - a failed discovery run.
  - Each alert has a stable dedupe key, and there are look-back limits.
  - When one sweep would send a user more than 3 closed-listing alerts, they get one summary instead.
  - `notification_dispatch` reuses the same functions, so no reminder is sent twice.
  - Per-kind off switches are honoured. There is no Settings toggle for them yet.
- [x] Runs where no source was set up are not "failed" (`discovery_service.nothing_configured`). Example: the daily connected-sources run when there's no alert mailbox and no Adzuna key.
  - They are not alerted, and the dashboard says "not set up".
  - This prevents a false alert every day for every user.
- [x] Admin console Health tab (`GET /admin/ops-health`, `ops_health_service.py`, `features/growth/OpsHealth.tsx`) shows:
  - what needs attention;
  - disk for data and backups;
  - database size, largest tables and connections;
  - backup age, size and count (a warning after 26 h);
  - failed jobs and runs over the last 7 days;
  - per-source health and freshness;
  - activity counts;
  - extension tokens.

  Each check degrades to "not available" instead of failing. Error text is redacted.
- [x] Regression on 2026-11-17: backend 499 passed, 3 skipped; frontend 57 passed; typecheck clean.
- [ ] Not done:
  - **Stable endpoint:** needs the owner's free ngrok static domain in `NGROK_DOMAIN`, or the `url_watch` cron.
  - **CSP** for Pages and nginx.
  - **Tunnel through nginx.**
  - **Frontend bound to localhost:** decide whether LAN or phone access is needed first.
  - **Security review pass.**
  - **Notification preference toggles in Settings.**
  - **Extension version reporting.**
  - **Postgres-only ops-health queries:** verify on the live database at deploy.

### Discovery engine (JPSE)
- [ ] Plan of record: `JOBPILOT_JPSE_BLUEPRINT.md` (owner-reviewed 2026-11-17). Its Phase 0 (instrumentation and baseline) and Phase 1 (background crawling, so that Discover never waits on the network) come first. Not started.

## Platform terms (checked 2026-11-16)

| Platform | Finding | JobPilot behaviour |
|---|---|---|
| LinkedIn | Its help page "Prohibited software and extensions" bans browser extensions that automate activity on the site. | Mode C only. Never injected. The user clips or copies by hand. |
| Naukri | Its terms bar automated means. Naukri Gulf's terms name browser extensions explicitly. | Mode C only. |
| Indeed | Its terms bar bots, and automating Indeed Apply is prohibited outside Indeed's own tools. | Mode C only. |
| Greenhouse, Lever, Ashby | Public employer-hosted forms. Candidates commonly use autofill tools. The sites have CAPTCHAs, which JobPilot never touches. | Modes A and B. |
| Workday, iCIMS, SuccessFactors, Taleo, Zoho, Freshteam, Darwinbox, SmartRecruiters | Employer-hosted forms, often behind a candidate account that the user signs into themselves. | Mode A only, with per-site permission. Mode B is not offered until it has been verified on that platform. |
