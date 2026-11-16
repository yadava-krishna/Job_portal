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

### Phase 2: Resume Studio
- [ ] A shared resume schema, HTML/CSS templates, PDF via headless Chromium (compared against the current ReportLab output first), and DOCX from the same layout spec.
- [ ] Six templates: Classic ATS, Modern Professional, Technical Engineer, Experienced Professional, Fresher/Graduate, Executive.
- [ ] Deterministic pagination rules and warnings. Content is never removed silently.
- [ ] Editor: drag-and-drop ordering, undo/redo, autosave, version history and restore, a page-count indicator, style controls with ATS guard rails.
- [ ] Parser: DOCX, layout-aware PDF (blocks and columns), tables, more heading synonyms, Indian layouts, source text shown for uncertain fields.
- [ ] Rule-based quality checker, with the methodology stated.
- [ ] Job-specific preparation from confirmed facts only, with provenance.
- [ ] Rendering tests: text extraction, page boxes and margins, completeness, long resumes.

### Phase 3: Discovery and matching
- [ ] Freshness, expiry and dead-link checks, a last-verified time, normalised location, work mode and salary, and grouping of duplicates.
- [ ] Permitted new sources, once the owner supplies keys (Adzuna, Jooble, Careerjet).
- [ ] Matching explanations: what matched, what didn't, and what couldn't be evaluated. More synonyms.

### Phase 4: UI/UX
- [ ] Design-system pass. Dashboard actions. Discovery details. A Kanban board for applications. Onboarding. Accessibility.

### Phase 5: Hardening
- [ ] A stable endpoint (needs the owner's approval). CSP. Tunnel routed through nginx. Frontend bound to localhost. Security review. Full regression. Documentation.

## Platform terms (checked 2026-11-16)

| Platform | Finding | JobPilot behaviour |
|---|---|---|
| LinkedIn | Its help page "Prohibited software and extensions" bans browser extensions that automate activity on the site. | Mode C only. Never injected. The user clips or copies by hand. |
| Naukri | Its terms bar automated means. Naukri Gulf's terms name browser extensions explicitly. | Mode C only. |
| Indeed | Its terms bar bots, and automating Indeed Apply is prohibited outside Indeed's own tools. | Mode C only. |
| Greenhouse, Lever, Ashby | Public employer-hosted forms. Candidates commonly use autofill tools. The sites have CAPTCHAs, which JobPilot never touches. | Modes A and B. |
| Workday, iCIMS, SuccessFactors, Taleo, Zoho, Freshteam, Darwinbox, SmartRecruiters | Employer-hosted forms, often behind a candidate account that the user signs into themselves. | Mode A only, with per-site permission. Mode B is not offered until it has been verified on that platform. |
