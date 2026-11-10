# JobPilot — Codebase Audit & System Verification Report

**Document Status:** Complete Audit & Verification  
**Date:** November 2026  
**Audited Repository:** `yadava-krishna/Job_portal`  
**Working Directory:** `/home/yadava/job_automation`  
**Current Git Branch:** `main` (commit `e65e752`)  
**Current Database Revision:** `0004_multi_source_discovery` (PostgreSQL 16)

---

## 1. Executive Summary of Audit

An exhaustive technical audit of the local codebase, git commit history, database schemas, test suites, and Docker deployment was conducted to establish verified facts for the JobPilot strategic expansion.

JobPilot currently exists as a hybrid system comprising:
1. **The Legacy Single-User Core (Phases 0–1):** Located in the repository root (`main.py`, `runner.py`, `scheduler.py`, `core/`, `discovery/`, `database/`, `resume/`, `intelligence/`). Designed around SQLite (`jobpilot.db`), local YAML configs (`config/settings.yaml`), and daily cron runs.
2. **The Modern Multi-Tenant Web Platform (Phases 1–4):** Located in `backend/`, `frontend/`, `extension/`, and `deploy/`. Built on FastAPI, PostgreSQL 16, SQLAlchemy 2.0, Alembic, React 19, Vite, TanStack Query, Tailwind CSS 4, and a Manifest V3 browser extension.
3. **The Scrapling Multi-Source Extension (Session Additions):** 12 discovery connectors, dual-fetcher engine (`Fetcher` + `StealthyFetcher` with DNS SSRF defense), token-bucket rate limiting, Phase 4 tracking (interviews, offers, contacts, .ics calendar, today view), Phase 5 Admin console, Phase 6 theme switcher, and Phase 7/8 deployment automation.

---

## 2. Verified Feature Matrix

Every capability in the codebase has been audited and classified into one of seven verification states:
- **Verified & Active:** Tested, functional in running containers, wired end-to-end.
- **Implemented but Unverified:** Code exists but lacks comprehensive test coverage or live integration proof.
- **Partially Implemented:** Core logic exists but lacks critical user-facing connections, schemas, or models.
- **Planned Only:** Described in documentation but absent from the codebase.
- **Missing:** Required for the target product vision but not yet designed or implemented.
- **Broken / Flaky:** Code exists but fails under specific runtime conditions or tests.
- **Blocked / Restricted:** External platform restrictions prohibit automated implementation.

| Subsystem / Capability | Location in Codebase | Status | Technical Details & Verification Notes |
| :--- | :--- | :--- | :--- |
| **User Authentication** | `backend/api/routes/auth.py`, `backend/services/auth_service.py` | **Verified & Active** | Argon2id password hashing, JWT access (15m) and refresh (14d) tokens, token family replay detection, brute-force throttling. Tested via 304 unit/integration tests and live API curls. |
| **Role-Based Access Control** | `backend/api/deps.py` (`require_admin`) | **Verified & Active** | `role` column on `users` table ('user' \| 'admin'). Enforced via backend dependency. Verified live: admin access granted to `the owner account`, 403 Forbidden enforced for `candidate@jobpilot.io`. |
| **Database Migrations** | `backend/migrations/versions/` | **Verified & Active** | Alembic migrations `0001` through `0004_multi_source_discovery` applied and verified on live PostgreSQL 16 container (`alembic -c backend/alembic.ini current` -> `0004 (head)`). |
| **Curated ATS Connectors** | `backend/services/ats/` | **Verified & Active** | HTTPX clients for Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee. 176 curated Indian technology employer tokens verified in `backend/data/ats_companies/curated_india.json`. |
| **Scrapling 0.5.1 Framework** | `backend/services/scrapling_client.py` | **Verified & Active** | Bounded dual-fetcher (`Fetcher` + `StealthyFetcher`). SSRF protection with DNS resolution and private CIDR blocking. 25MB response caps. Mock transport overrides in test suite. |
| **Multi-Source Connectors (12)** | `backend/services/connectors/` | **Verified & Active** | 12 modular connectors registered in `registry.py`: `jsonld`, `rss_feed`, `sitemap`, `html_career`, `career_url`, `remotive`, `himalayas`, `remoteok`, `arbeitnow`, `ncs_gov`, `government_portal`, `academic_research`. |
| **Restricted Portals (LinkedIn, Indeed, Naukri)** | `platforms/linkedin.py`, `indeed.py`, `naukri.py` | **Verified & Active (Assisted Only)** | No unauthorized scraping. Assisted discovery via candidate's own email alerts (IMAP), manual URL importing, canonical job ID normalization, and filtered search link generation. |
| **Browser Extension (Fill with JobPilot)** | `extension/` (Manifest V3) | **Verified & Active** | Pre-fills candidate information into Ashby, Greenhouse, and Lever forms. Pure JavaScript, zero runtime dependencies. Content scripts preserve user edits and guard honeypot fields. |
| **Application Pipeline & Tracking** | `backend/services/tracker_service.py`, `backend/api/routes/tracker.py` | **Verified & Active** | Sub-entities for Interviews, Offers, Recruiter Contacts, and Application Events. RFC 5545 iCalendar `.ics` export verified. |
| **Today's Action Agenda** | `backend/services/tracker_service.py:today_view` | **Verified & Active** | Tri-bucket prioritization (`your_move`, `coming_up`, `waiting_on_them`). Active in `TodayView.tsx` on frontend dashboard. |
| **Admin Management Console** | `backend/services/admin_service.py`, `frontend/src/pages/AdminPage.tsx` | **Verified & Active** | Platform metrics, user activation toggle, role elevation, custom invite generator, immutable security audit logging. |
| **Privacy & Self-Service Data Controls** | `backend/services/tracker_service.py:export/delete_account` | **Verified & Active** | Complete JSON data export (17 tables/entities). Password-gated account deletion with cascading file and relational cleanup. |
| **Theme System** | `frontend/src/components/ui/ThemeToggle.tsx` | **Verified & Active** | Dark/Light mode toggle with `localStorage` persistence and `classList` synchronization. |
| **Master Candidate Profile** | `backend/models/__init__.py:CandidateProfile` | **Partially Implemented** | Currently stores unstructured JSON blob (`verified_facts`). Lacks a typed, relational schema for verified work history, skills, proficiencies, education, and credentials. |
| **Resume Builder & Studio** | `backend/services/resume_service.py` | **Partially Implemented** | Supports PDF upload, SHA256 deduplication, and PyMuPDF text/metadata parsing. Lacks interactive visual resume builder, ATS template engine, and DOCX generation. |
| **Truthful Resume Tailoring** | `None` | **Missing** | No automated, truthful resume tailoring engine exists. Currently resumes are static uploads. |
| **ATS Compatibility Testing** | `intelligence/` | **Partially Implemented** | Basic keyword and eligibility matching exists. Lacks 3-tier ATS compatibility diagnostic (text extraction, structural integrity, and parser view). |
| **Apply Route Orchestrator** | `backend/services/application_service.py` | **Partially Implemented** | Records applications and stages (`PREPARED`, `OPENED`, etc.). Lacks central router to classify openings into Route A (API), Route B (Extension), Route C (Email), or Route D (External). |
| **Recruiter Email Dispatcher** | `backend/services/email_service.py` | **Partially Implemented** | SMTP transport with SSL/STARTTLS configured. Lacks recruiter email address extraction, validation, and consent-gated drafting UI. |
| **IT Industry Government Benefits** | `None` | **Missing / Planned Only** | Zero implementation. No database tables, APIs, or UI exist for government schemes, STPI benefits, or startup subsidies. |
| **AI Agents Architecture** | `core/llm.py` | **Partially Implemented** | Basic Anthropic and OpenAI-compatible client abstraction. Lacks central orchestrator, multi-agent role separation, and deterministic execution boundaries. |
| **Dependency Management (`uv`)** | `backend/requirements.txt` | **Partially Implemented** | Uses standard `requirements.txt` with pip in Docker. `pyproject.toml` and `uv.lock` not yet adopted. |

---

## 3. Detailed Audit of Architectural Layers

### 3.1 Legacy CLI vs. Modern Portal Duplication
The codebase contains dual implementations of several business domains:
- **Database Access:**
  - *Legacy:* `database/db.py` uses raw SQLite connections with custom SQL queries and `sqlite3.Row` dict mappings.
  - *Modern:* `backend/db.py` and `backend/models/__init__.py` use SQLAlchemy 2.0 ORM over PostgreSQL 16 with session factories.
- **Settings & Config:**
  - *Legacy:* `core/settings.py` loads `config/settings.yaml` into Pydantic v2 `Settings` models for CLI execution.
  - *Modern:* `backend/config.py` loads environment variables (`.env`) into `BackendSettings` via `pydantic-settings`.
- **Normalization:**
  - *Legacy:* `discovery/job_extractor.py` and `discovery/sources.py` map raw data to `core.models.RawJobRecord`.
  - *Modern:* `backend/services/normalization.py` maps raw payloads to `NormalizedJob` and SQLAlchemy `Job` models.
- **Recommendation:** Do not remove the CLI immediately as it serves as a standalone testing utility, but all future expansions (Phases 9–16) must strictly build on the `backend/` and `frontend/` architecture.

### 3.2 Test Suite Audit
- **Backend Test Suite (`pytest`):**
  - Total tests: 307 collected.
  - Result: **304 passed, 3 skipped (100% green)** in 25.4 seconds.
  - Coverage includes: Authentication, RBAC, database migrations, ATS clients, Scrapling client, SSRF defense, 12 connectors, tracker service, achievements, security audit logs.
  - Deprecation warnings: `datetime.utcnow()` in connector base classes (scheduled for replacement with `datetime.now(timezone.utc)`).
- **Frontend Test Suite (`vitest`):**
  - Total tests: **30 passed in 5 test files (100% green)**.
  - Production build (`tsc -b && vite build`): Succeeded in 733ms without errors.
- **Browser Extension Test Suite:**
  - Located in `extension/tests/unit/fill.test.js`.
  - Lever and Greenhouse synthetic form tests pass. Note: `accepts a phone number the page reformats` has an explicit 60-second timer to simulate page reformatting.

### 3.3 Security & Threat Audit
- **SSRF Defense:** `backend/services/scrapling_client.py` implements pre-fetch DNS resolution and verifies that resolved IP addresses do not fall within RFC 1918 private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`), link-local (`169.254.0.0/16`), or multicast ranges.
- **Honeypot & Form Safety in Extension:**
  - `extension/src/content/core.js` and `extension/tests/unit/fill.test.js` inspect form fields.
  - *Audit Finding:* The extension currently avoids hidden inputs and elements styled with `display: none` or zero opacity. However, automated form interaction must never attempt anti-bot bypass. All application submissions must remain manual and candidate-approved.
- **File Upload Security:** `backend/services/resume_service.py` enforces:
  - File size limit $\le 5$ MB.
  - Header validation (`%PDF-` magic bytes).
  - PyMuPDF inspection for corruption and password protection.
  - Page count bound (1 to 15 pages).
  - Server-generated UUID file naming to prevent directory traversal.
- **Credential Protection:** IMAP email passwords and OAuth secrets are encrypted at rest using AES-128-CBC via Fernet (`backend/security.py:CredentialCipher`).

---

## 4. Top 10 Architectural Gaps Identified

1. **Unstructured Candidate Profile:** `CandidateProfile.verified_facts` is an untyped JSON blob, preventing deterministic skill-gap calculations, relational querying, and verified credential proofs.
2. **Absence of Visual Resume Builder:** Candidates can only upload static PDFs. There is no in-browser WYSIWYG editor or ATS-optimized template engine.
3. **Missing DOCX Generation:** Enterprise ATS systems frequently prefer or parse DOCX more reliably than complex PDFs. JobPilot currently only handles PDF.
4. **Lack of Truthful Tailoring Engine:** There is no mechanism to compare a master profile against a target job description and re-order verified bullets without human manual editing.
5. **Absence of Standardized Apply Route Orchestrator:** Applying to a job is currently handled ad-hoc across tabs rather than routing dynamically through Route A (API), Route B (Extension), Route C (Email), or Route D (External).
6. **No Recruiter Email Ingestion & Drafting:** While SMTP sending is implemented, there is no system to extract, verify, and draft candidate-approved emails to hiring managers.
7. **Complete Absence of Government IT Benefits:** No capability exists to guide Indian IT professionals, startups, or software exporters to central and state benefits (MeitY, STPI, KITS, Startup India).
8. **Dependency on Pipelined `pip` Rather Than `uv`:** Docker builds take several minutes downloading packages without shared caching or reproducible lockfile guarantees.
9. **In-Process Semaphore Concurrency Limitations:** Scrapling runs via `asyncio.Semaphore(4)` inside the web backend process. Long-running crawls can tie up backend CPU/memory.
10. **Heuristic Keyword Matching Only:** Existing job matching uses basic regex and token overlap without deterministic multi-factor scoring (eligibility gate, verified skill match, experience match, preference match).

---

## 5. Audit Conclusion

The JobPilot foundation is structurally sound, secure, and stable. The PostgreSQL schema, FastAPI backend, React frontend, and Scrapling crawler framework are functioning reliably with zero regressions. The strategic expansion can proceed on top of this verified foundation without rewriting existing integrations or resetting user data.
