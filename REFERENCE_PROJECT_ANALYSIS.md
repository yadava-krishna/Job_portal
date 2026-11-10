# Reference Project Analysis

Phase 0 deliverable. All five projects were cloned and read at source level on 2026-11-04 (not just their READMEs).
Licence status decides what we may reuse: **ideas are always fine; code only where the licence allows, with attribution.**

| Project | Stack | Licence | Code reuse allowed? |
|---|---|---|---|
| [Gsync/jobsync](https://github.com/Gsync/jobsync) | Next.js 15, Prisma, Postgres, Vercel AI SDK, shadcn/Radix, Nivo charts, MCP server | **MIT** | Yes, with copyright notice |
| [sanT-0/JobTrack](https://github.com/sanT-0/JobTrack) | React 19 + Vite, FastAPI, SQLAlchemy 2, MySQL | **No licence file** → all rights reserved | **No** (ideas only) |
| [AnkurNapa/jobgrab](https://github.com/AnkurNapa/jobgrab) | Chrome MV3 extension, vanilla JS, `chrome.storage.local` | **No licence file** → all rights reserved | **No** (ideas only) |
| [Doebele/application-pal](https://github.com/Doebele/application-pal) (site: doebele.github.io/application-pal-website) | React + Vite + Tailwind, Node/TS backend, Drizzle ORM, Postgres, multi-provider AI | **MIT** | Yes, with copyright notice |
| [waddington/job-application-tracker](https://github.com/waddington/job-application-tracker) | FastAPI, SQLAlchemy 2.1, Alembic, SQLite + JSONL, React + i18n | **Apache-2.0** (+ NOTICE) | Yes, keeping LICENSE/NOTICE and marking changes |

**Policy for JobPilot:** we implement equivalent functionality in our own architecture (FastAPI + SQLAlchemy + React/TS). The only candidate for *direct* reuse is **data**: JobSync's MIT-licensed ATS company directories (Greenhouse 2,421 / Lever 1,160 / Ashby 1,860 board tokens). If used, they go in `backend/data/ats_companies/` with JobSync's MIT notice. No code from JobTrack or JobGrab is copied.

---

## 1. JobSync (Gsync/jobsync): strongest overall reference

**Architecture.** Next.js app router with server actions (`src/actions/*.actions.ts`), Prisma over Postgres (SQLite legacy), a scheduler (`src/lib/scheduler`) driving "automations", per-source scrapers under `src/lib/scraper/{greenhouse,lever,ashby}`, AI through the Vercel AI SDK with provider adapters (Ollama, OpenAI, DeepSeek, Google…), API keys encrypted at rest with `ENCRYPTION_KEY`, an MCP server with per-user revocable tokens, OpenTelemetry option, backup/restore zip.

**Strongest features**
- **Automated discovery through public ATS job-board APIs**: Greenhouse (`boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`), Lever (`api.lever.co/v0/postings/{token}`, EU variant), Ashby (`api.ashbyhq.com/posting-api/job-board/{token}`). These are documented, unauthenticated endpoints that companies publish for embedding their careers pages. They return full descriptions and real publish timestamps. *Verified: all three answered HTTP 200 from our host today for Indian employers (Razorpay, CRED, Navi).*
- Company **watchlist** with a built-in searchable directory of board tokens.
- `Automation` model: per-user saved search (board, keywords, location, resume, `matchThreshold`, `scheduleHour`, `nextRunAt`, status) + `AutomationRun` history.
- **Notification** model with `kind`, dedupe key (`boardToken`), `occurrences` counter, `readAt`/`dismissedAt`.
- **AiCall** usage log (feature, provider, model, tokens, duration): direct fit for our admin "AI usage" metric.
- Activity time tracking with breaks (`Activity` with `breakMinutes`, `breakStartedAt`), daily goals.
- Interviews, contacts, company pages, question bank, job timeline (stages with interviewers and prep questions).
- Resume import with AI → review cards per section (same principle as our parse → review step).

**UI/UX ideas.** Docked AI assistant panel that keeps the page visible; "Discovered jobs → accept/dismiss" inbox; calendar heatmap of activity (Nivo calendar); confirmation card before AI-extracted data is saved.

**Limitations.** Single-tenant mindset (no admin dashboard); AI features need a tool-calling model; Next.js server actions don't map to our FastAPI split; no Indian job boards.

**Adopt in JobPilot**
1. **ATS board discovery** (Greenhouse, Lever, Ashby) as a first-class source with a company watchlist and an India-relevant default directory. *Biggest single improvement to automated discovery.*
2. Saved searches ("automations") per user with schedule, threshold and run history (extends our `discovery_runs`).
3. Notifications table design (dedupe key + occurrences + read/dismiss).
4. AI call usage log for admin metrics and cost control.
5. Per-user revocable tokens (their MCP tokens) → our **browser-extension tokens**.

**Do not adopt.** Next.js/Prisma stack; MCP server (out of scope now; possible later); docked chat assistant (high AI cost, low value vs our explainable scoring).

---

## 2. JobTrack (sanT-0/JobTrack): clean FastAPI reference (no licence)

**Architecture.** FastAPI with **repository → service → API** layers (`app/repositories`, `app/services`, `app/api`), pydantic-settings, python-jose JWT + bcrypt, SQLAlchemy 2 typed models, MySQL in prod / SQLite StaticPool in tests, Axios with JWT + 401 interceptors, 36 pytest tests including cross-user isolation.

**Strongest features.** Simple, readable lifecycle enum (`Applied, Shortlisted, Interview, Offer, Rejected, Withdrawn`); `interview_date` with an "upcoming interviews" widget; isolation tests that assert 404 for another user's record (same approach JobPilot already uses).

**Limitations.** Basic CRUD only (no discovery, matching or AI); committed `jobtrack.db` and default `JWT_SECRET_KEY="change-this-in-production"` (anti-patterns); client-side filtering; no refresh tokens; no licence.

**Adopt (ideas only).** Upcoming-interviews widget; a thin repository layer *only* where queries are reused (admin analytics), since our service layer already scopes by user. **Do not adopt:** its auth (ours is stronger: Argon2id, rotating refresh tokens, reuse detection); its MySQL setup.

---

## 3. JobGrab (AnkurNapa/jobgrab): browser capture reference (no licence)

**Architecture.** Chrome **Manifest V3** extension. Per-site content scripts (`content/scraper-{linkedin,indeed,naukri,wellfound,glassdoor}.js`) share a toolkit (`scraper-lib.js`) and expose a 4-hook contract (`source`, `currentId`, `onJobPage`, `scrape`). One site-agnostic `inject.js` renders a draggable floating "Save job" button and quick-add panel in a **Shadow DOM** (immune to host CSS), with a `MutationObserver` to follow SPA navigation (LinkedIn split view, Indeed panel). Stateless service worker; `lib/insights.js` computes "needs attention" (overdue follow-ups, applications gone quiet after 10 days, deadlines within 7 days); `lib/dedupe.js` dedupes per platform by job ID. Data stays in `chrome.storage.local`.

**Strongest features.** JSON-LD `JobPosting` first, selectors as fallback (same strategy as our bookmarklet); **5 boards** incl. Wellfound and Glassdoor; captures apply URL, deadline, LinkedIn poster contact; SPA-aware "already saved" state; Kanban with Bookmarked → Applying → Applied → Interviewing → Negotiating → Accepted / Rejected / Ghosted; skills word cloud and health row (response, interview and ghost rates).

**Limitations.** Local-only (no multi-device, no server matching); broad host permissions; Chrome only; no licence; also injects into claude.ai to autofill prompts (not relevant).

**Adopt (re-implemented, no code copied).** Upgrade our bookmarklet to a **JobPilot MV3 extension**:
- per-site extractor modules with the same 4-hook *pattern* (our own code), JSON-LD first;
- floating button in Shadow DOM + SPA observer, so no need to click a bookmark on each page;
- capture **apply URL, deadline, posting date, job ID**; add **Wellfound and Glassdoor** extractors (plus Foundit);
- send to our API with a **scoped extension token** (not the user's login token), then show the score inline;
- "Needs attention" rules (follow-up due, gone quiet, deadline soon) → our notifications and Today view.

**Do not adopt.** Local-only storage; claude.ai injection; overly broad permissions (we request host permissions only for supported boards, optional per site).

---

## 4. Application Pal (Doebele/application-pal): AI coaching and workflow reference (MIT)

**Architecture.** React + Vite + Tailwind frontend, TypeScript backend, **Drizzle ORM** migrations (`backend/drizzle/0000…0013`), Postgres, shared zod schemas (`shared/src/schema.ts`), Docker release compose, Google Drive OAuth integration, 6 AI providers incl. local (LM Studio/Ollama), WebAuthn.

**Data model highlights.** `applications.stage` enum (import_validating → preparing_cv → preparing_letter → application_sent → pending → interview_1 → interview_2 → rejected/accepted); `application_activities` (note, email, call, interview, deadline, stage_change, document); `application_contacts`; `application_tasks` (**stage-specific checklists**); `user_documents`; **`invites` table (token, optional email lock, used flag, expiry, created_by)**; `password_reset_tokens`; `webauthn_credentials`; knowledge base (`kb_companies`, `kb_roles`, `kb_insights`).

**Strongest features.** Stage-aware AI "tiles" (ATS keywords cloud, CV highlights, company research, interview prep with STAR examples, salary negotiation script); guided cover-letter workspace (prepare → draft → result, version history, reusable personal guidance); calendar of interviews, deadlines and follow-ups with iCal export; configurable table view (resize, reorder, pin columns); application drawer with tabs.

**Limitations.** Single user per install in practice; AI estimates of ratings or salaries risk hallucination; Google Drive dependency for documents; Swiss/German-specific features (RAV export, Kununu).

**Adopt.**
1. **Proper invites table** (per-invite tokens, expiry, optional email lock, single/multi-use, created_by): replaces our single shared invite code.
2. **Password reset tokens** (needs email delivery: see Notifications plan).
3. **Stage-specific checklists** and **activity timeline** per application.
4. **ATS keywords** panel (must-have / nice-to-have from the JD vs profile). We already compute required/preferred skills, so this is mostly UI.
5. Interview prep generator (LLM, optional) and **calendar + iCal export** for interviews and follow-ups.
6. Cover-letter versions with the user's reusable guidance (extends our verified cover letter).

**Do not adopt.** AI-estimated Glassdoor/Kununu ratings and salary medians (we don't present unverifiable AI guesses as data); Google Drive integration (later, optional); WebAuthn (later).

---

## 5. Waddington Job Application Tracker: pipeline/CRM reference (Apache-2.0)

**Architecture.** FastAPI + SQLAlchemy 2.1 + Alembic (same stack as ours), SQLite plus plain-text JSONL/Markdown export, git-snapshot backups, React + i18next frontend, OpenAPI, CLI (`jat`). Rich **domain layer** (`src/jat/domain/`: workflow, insights, conversations, duplicates, offers, interviews, rejections, replies, scorecard, document_performance, stats).

**Strongest features.**
- **Configurable workflow** (`domain/workflow.py`): active, closed and success stages; any active stage → closed; `ghosted` can be reopened; every change timestamped.
- **"Today" home page**: *Your move* (replies, follow-ups due, to-dos, roles to decide), *Coming up* (interviews, calls), *Waiting on them* (stalled applications with per-recruiter typical response time).
- **Recruiter/agency CRM**: people, calls, roles pitched, recruiter scorecard.
- **Interview rounds**, **offers side-by-side**, rejections with reasons.
- **Insights**: Sankey diagram of the whole search (source → stages → outcome), conversion and time per stage, direct vs recruiter.
- **Timeline** of everything (list or lanes per role); full-text search; duplicate detection; document performance (which CV version gets responses).

**Limitations.** Deliberately no AI, no discovery, single user, localhost only, SQLite.

**Adopt.**
1. **Workflow state machine for the post-application pipeline** (configurable stages, Ghosted re-openable, timestamped transitions). Our `applications.stage` becomes a proper workflow with history.
2. **Today view** (your move / coming up / waiting on them) as the new dashboard top section.
3. **Interviews** (rounds, date, type, outcome) and **Offers** (amount, deadline, compare) entities.
4. **Follow-up reminders and stalled detection** (gone quiet after N days per stage).
5. **Sankey funnel** and time-in-stage analytics.
6. Lightweight **contacts** (recruiter or hiring manager per application).
7. **Plain-data export** (JSON plus Excel) for user data portability.

**Do not adopt.** SQLite and file-folder storage; git snapshots (our Postgres backup is `pg_dump`); full recruiter CRM (keep it light).

---

## 6. Platform realities (discovery and application), checked per platform

| Platform | Public job-seeker search API | Permitted third-party apply | JobPilot approach |
|---|---|---|---|
| LinkedIn | No (Job Posting / Apply Connect are ATS-partner only) | No; automation by bots is prohibited in the User Agreement | Extension capture on user click; job-alert emails; assisted apply (open listing, answer panel, confirm) |
| Indeed | No (Publisher API closed; Indeed Apply / Job Sync for employers) | No | Same as LinkedIn |
| Naukri | No public API | No | Same; the user enables Naukri's own in-app tools themselves |
| Foundit (Monster India) | No public API known | No | Extension capture (new extractor); alert emails |
| Glassdoor | Public API discontinued (partner-only) | No | Extension capture (new extractor) |
| Wellfound | No public API | No | Extension capture (new extractor) |
| **Greenhouse / Lever / Ashby** (employer ATS boards) | **Yes**: public, unauthenticated board APIs (verified 200 today) | Application forms live on the employer's own ATS page; **user-triggered autofill by the user's own extension is technically possible**, and the user reviews and submits | **Automated discovery** via a company watchlist; **assisted autofill** on these forms (Phase 3, user clicks Fill, never auto-submit) |
| Adzuna | **Yes**, official API (free keys); India supported | No (redirects to source) | Already implemented; needs keys |
| Jooble, Careerjet | Partner/publisher APIs exist (keys on request) | No | Optional sources, to verify terms before enabling |

**Conclusion on "maximum legitimate automation":**
- Fully automated **discovery**: Adzuna + Greenhouse/Lever/Ashby boards + the user's alert emails (all real and permitted).
- **Capture** from LinkedIn, Indeed, Naukri, Foundit, Glassdoor and Wellfound: extension on the user's click, in their own logged-in browser. No cookies leave it.
- **Application**: on employer ATS forms (Greenhouse/Lever/Ashby, later Workday), a user-clicked "Fill with JobPilot" that fills fields from the reviewed profile. On LinkedIn/Indeed/Naukri, a side panel with copy-ready answers (no auto-filling or clicking on those sites).
- **Never**: auto-submit, background crawling, cookie export, CAPTCHA/OTP bypass, marking "Applied" without confirmation.

---

## 7. Session Evaluation & Implementation: Scrapling Framework (2026-11-06)

Following evaluation of the [Scrapling](https://github.com/D4Vinci/Scrapling) framework and its official documentation:
- **Adopted**: Scrapling 0.5.1 (`scrapling[fetchers]==0.5.1`) with `Fetcher` (curl_cffi HTTP/2 TLS browser impersonation) and `StealthyFetcher` (Patchright headless isolation).
- **Selector Engine**: Utilized `scrapling.parser.Adaptor` with CSS and XPath selectors for resilient extraction of semi-structured listings and Schema.org JSON-LD microdata.
- **Safety Hardening**: Enforced pre-flight DNS SSRF vetting, token-bucket per-domain rate limiting, and cached robots.txt compliance parsing.
- **Implemented Connectors**: Delivered 12 multi-source connectors (Remotive, Himalayas, RemoteOK, Arbeitnow, NCS India, Indian Government agencies, Academic institutions, Schema.org, RSS/Atom, XML Sitemaps, HTML Adaptor, and Career URL detector).
- **Phases 4–8 Fulfilled**: Completed Today View, Interview/Offer tracking, Recruiter contacts, Data export, Account deletion, Admin console, Dark theme toggle, Maritime nicknames, Achievements, SMTP email, and DevOps backup automation.

