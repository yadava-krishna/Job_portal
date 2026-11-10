# JobPilot — Master System Architecture Specification

**Document Status:** Complete Master Architecture Specification  
**System Classification:** Integrated IT Career Discovery, Matching, Resume Studio & Application Orchestration Platform  
**Operational Standard:** Pure Python Deterministic Processing, Dual Export (PDF & DOCX), Zero Unapproved Automated Actions

---

## 1. System Vision & Core Question

> **Core Strategic Question:**  
> *How do we turn the existing JobPilot into a reliable, intelligent IT career platform where a candidate discovers a suitable MNC or technology job, understands the skill gaps, generates a truthful job-specific resume and completes the correct application process from one unified experience?*

### The Unified Answer
JobPilot achieves this by integrating five dedicated, deterministic subsystems governed by a unified data model:
1. **Multi-Source Discovery Engine:** Aggregates technology openings from 100+ compliant sources (official ATS APIs, employer sitemaps, JSON-LD feeds, remote aggregators) into a single deduplicated repository.
2. **Deterministic Career Intelligence Engine:** Evaluates candidate-to-job compatibility using mathematical multi-factor scoring (Eligibility, Skills, Experience, Preferences) and highlights actionable skill gaps without hallucination or LLM dependency.
3. **Truthful Resume Studio:** Provides an in-browser WYSIWYG editor that generates tailored resumes in both **pristine machine-readable PDF** and **native Microsoft Word DOCX** formats, re-ordering verified accomplishments without inventing claims.
4. **Unified 4-Route Apply Orchestrator:** Seamlessly guides the candidate through the appropriate application channel (Authorized API, Browser Extension Form Assistant, Recruiter Email, or External Portal Assist) while requiring candidate approval for all final submissions.
5. **IT Industry Government Benefits Module:** Matches individual professionals, startups, MSMEs, and software exporters with verified financial grants, tax exemptions, and STPI export benefits (prioritizing Karnataka and Central Government schemes).

---

## 2. End-to-End Master Architecture Diagram

```
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+
|                                         JOBPILOT MASTER ARCHITECTURE                                        |
+─────────────────────────────────────────────────────────────────────────────────────────────────────────────+

                                     [ EXTERNAL DATA SOURCES & RECIPIENTS ]
   Official ATS APIs      Scrapling Web Crawlers    Syndication Feeds     Government Schemes   Recruiter Inboxes
(Greenhouse/Lever/Ashby) (Career URLs, Sitemaps)   (Remotive, RemoteOK)   (KITS, MeitY, STPI)  (Direct Hiring)
          │                         │                      │                      │                   ▲
          ▼                         ▼                      ▼                      ▼                   │
+─────────────────────────────────────────────────────────────────────────────────────────+           │
| 1. GLOBAL IT JOB DISCOVERY ENGINE                                                       |           │
|  - DNS SSRF Guard & Rate Limiting                                                       |           │
|  - Schema.org JSON-LD & Adaptive HTML Extractors                                         |           │
|  - Deduplication Engine (Company + Title Key) & Expired Job Reaper                       |           │
+───────────────────────────────────────────┬─────────────────────────────────────────────+           │
                                            │ Structured Jobs                                         │
                                            ▼                                                         │
+─────────────────────────────────────────────────────────────────────────────────────────+           │
| 2. DETERMINISTIC CAREER INTELLIGENCE ENGINE                                             |           │
|  - Master Candidate Profile (Single Source of Verified Truth)                           |           │
|  - Requirement Parser (Mandatory vs Preferred Skills, Experience Bounds)                |           │
|  - Multi-Factor Matching Gate: (0.25 Elig + 0.45 Skill + 0.20 Exp + 0.10 Pref)          |           │
|  - Actionable Skill-Gap Diagnostics (Documented Missing vs Clarification Prompts)       |           │
+──────────────────────┬────────────────────────────────────────────┬─────────────────────+           │
                       │ Matched Requirements                       │ Matched Schemes         │
                       ▼                                            ▼                         │
+─────────────────────────────────────────────+  +──────────────────────────────────────+     │
| 3. TRUTHFUL RESUME STUDIO (PDF & DOCX)      |  | 5. IT INDUSTRY GOVERNMENT BENEFITS   |     │
|  - In-Browser WYSIWYG Section Editor        |  |  - Priority 1: Karnataka (KITS/KDEM) |     │
|  - Truthful Bullet Re-ranking Engine        |  |  - Priority 2: Central (MeitY/STPI)  |     │
|  - 3-Tier ATS Compatibility Diagnostic      |  |  - Priority 3: Telangana / TN        |     │
|  - Dual Export: ReportLab PDF & python-docx |  |  - Strict Beneficiary Classification |     │
+──────────────────────┬──────────────────────+  +──────────────────────────────────────+     │
                       │ Tailored Document                                                    │
                       ▼                                                                      │
+─────────────────────────────────────────────────────────────────────────────────────────+   │
| 4. CENTRAL APPLY ORCHESTRATION SERVICE                                                  |   │
|                                                                                         |   │
|   [Route A: Authorized API]       [Route B: Supported ATS Form]                         |   │
|   - Partner API credentials       - Browser Extension Assistant                         |   │
|                                   - User-controlled prefill; zero anti-bot tampering    |   │
|                                                                                         |   │
|   [Route C: Recruiter Email]      [Route D: External Portal Assist]                     |   │
|   - Verified hiring email draft   - Employer portal launch + Companion Answer Panel     |   │
|   - Candidate approval gate ──────┼─────────────────────────────────────────────────────┼───┘
|                                   - Manual submission confirmation & evidence upload    |
+───────────────────────────────────────────┬─────────────────────────────────────────────+
                                            │ State Transitions & Provenance
                                            ▼
+─────────────────────────────────────────────────────────────────────────────────────────+
| 6. APPLICATION TRACKER & AUDIT CORE                                                     |
|  - Application Pipeline (Draft -> Preparing -> Ready -> Submitted -> Interview -> Offer)|
|  - iCalendar RFC 5545 (.ics) Schedule Export & Tri-Bucket Today's Focus Action Agenda   |
|  - Immutable Security Audit Log & Self-Service Account Privacy / Erasure Controls       |
+─────────────────────────────────────────────────────────────────────────────────────────+
```

---

## 3. Subsystem Breakdown & Integration Contracts

### 3.1 Discovery Engine to Intelligence Engine Contract
- Jobs are normalized into the `jobs` table with standardized titles, parsed skill arrays (`required_skills`, `preferred_skills`), experience ranges (`experience_min`, `experience_max`), and canonical URLs.
- Provenance links (`job_source_links`) record the initial discovery connector and timestamp.

### 3.2 Intelligence Engine to Resume Studio Contract
- When the candidate clicks **"Tailor Resume"**, the Intelligence Engine supplies:
  - The target job's mandatory keywords.
  - The candidate's verified accomplishments that utilize those keywords.
  - The suggested professional summary emphasizing verified experience.
- The Resume Studio compiles the document and runs an **Anti-Fabrication Diff Check** ensuring no unverified claims exist.

### 3.3 Resume Studio to Apply Orchestrator Contract
- The Resume Studio produces an immutable `tailored_resume_id` (PDF and DOCX binaries stored in `/data/users/{id}/resumes/`) and an approved `cover_letter_id`.
- The Apply Orchestrator attaches this tailored resume to the application session across all routes.

### 3.4 Government Benefits Integration
- Operates as a parallel intelligence track. When viewing company or candidate profiles, relevant schemes (e.g. ELEVATE Karnataka ₹50L, Startup India Seed Fund, STPI export exemptions, FutureSkills Prime subsidies) are displayed with direct official application links and eligibility rationales.

---

## 4. Architectural Invariants (Non-Negotiable Rules)

1. **Zero Mandatory LLM Infrastructure:** The core platform operates 100% deterministically in pure Python using compiled string matching (`rapidfuzz`), HTML parsers (`selectolax`), and standard mathematical weights.
2. **No Automated Submissions:** Applications are never submitted without direct human candidate action. Browser extensions assist with data entry but never click submit buttons or bypass CAPTCHAs.
3. **No Anti-Bot Bypass:** JobPilot does not attempt to defeat Cloudflare, bypass honeypots, or steal sessions. Only public APIs, open feeds, and permitted career pages are crawled.
4. **Strict Separation of Government Benefits:** Company subsidies (e.g. ₹50 Lakh startup grants) are never misrepresented as personal claims for individual employees.
5. **Zero Data Loss on Deployment:** Existing user accounts (`the owner account`), applications, and jobs in PostgreSQL 16 are preserved intact across all future migrations.
