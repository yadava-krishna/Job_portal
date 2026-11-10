# JobPilot — Seamless Apply Orchestration Architecture

**Document Status:** Complete Architecture & Design Specification  
**Design Principles:** Unified Apply Experience, 4-Route Dynamic Dispatching, Strict Candidate Consent  
**Compliance Standard:** Purely User-Controlled Assistance. No anti-bot bypass, no honeypot tampering, no automated submission.

---

## 1. System Vision & Central Apply Orchestrator

Applying for a technology role is often fragmented across proprietary employer portals, various ATS platforms, direct recruiter emails, and job boards. JobPilot solves this through a **Central Application Orchestration Service**.

When a candidate clicks **"Apply"** on any job card in JobPilot:
1. The orchestrator inspects the job's origin, URL structure, and source metadata.
2. It classifies the opening into one of **Four Supported Application Routes**.
3. It provisions the job-specific tailored resume and approved screening answers.
4. It guides the candidate through the submission process, ensuring the candidate maintains complete control and oversight at every step.

```
                              [ CANDIDATE CLICKS APPLY ]
                                          │
                                          ▼
                      +─────────────────────────────────────────+
                      |     Central Apply Orchestrator Engine   |
                      |  - Analyzes Source & Application URL    |
                      |  - Resolves Tailored Resume & Answers   |
                      |  - Selects Optimal Application Route    |
                      +───────────────────┬─────────────────────+
                                          │
         ┌──────────────────┬─────────────┴──────────────┬──────────────────┐
         ▼                  ▼                            ▼                  ▼
   [ ROUTE A ]        [ ROUTE B ]                  [ ROUTE C ]        [ ROUTE D ]
Authorized API     Supported ATS Form           Recruiter Email     External Portal
Employer Partner   Browser Extension            Direct Ingestion    Assisted Manual
Credentials API    Assisted Autofill            & Draft Approval    Redirect & Copy
```

---

## 2. The Four Application Routes

### Route A: Authorized Employer API
- **Applicability:** Organizations where JobPilot or the candidate holds authorized, documented API credentials (e.g. custom corporate integrations, direct partner ATS APIs).
- **Protocol:** Direct REST/JSON payload submission adhering to the employer's official OpenAPI specification.
- **Verification:** Instant HTTP response verification with official application confirmation reference ID.
- **Strict Limitation:** JobPilot never assumes a public job-listing endpoint permits application submission. Route A is activated only when mutual API keys are explicitly configured.

---

### Route B: Supported ATS Form (Browser Extension)
- **Applicability:** Official job boards hosted on supported ATS platforms:
  - Greenhouse (`boards.greenhouse.io/*`, `job-boards.greenhouse.io/*`)
  - Lever (`jobs.lever.co/*`)
  - Ashby (`jobs.ashbyhq.com/*`)
  - *Future Extensible Adapters:* SmartRecruiters, Workable, BambooHR.
- **Mechanism:** The **Fill with JobPilot** Manifest V3 browser extension assists the candidate directly within their active browser tab.
- **Workflow & Safety Rules:**
  1. *Loads Selected Resume:* Fetches the candidate's approved tailored resume PDF from the local JobPilot instance.
  2. *Maps Verified Profile Fields:* Fills standard fields (`First Name`, `Last Name`, `Email`, `Phone`, `LinkedIn URL`, `GitHub URL`, `Current Company`).
  3. *Maps Verified Answers:* Injects pre-approved screening answers from the candidate's Answer Bank (e.g., notice period, work authorization).
  4. *Preserves Existing Data:* If a field already contains data typed by the user or pre-filled by the ATS, the extension **never** overwrites it unless the user explicitly toggles "Overwrite".
  5. *Zero Honeypot Tampering:* The extension adheres strictly to standard DOM inputs. It does not attempt to detect, bypass, or manipulate hidden anti-bot honeypot inputs.
  6. *Never Automates Submission:* The extension **never clicks the submit button**. The candidate must personally review every filled field, complete any CAPTCHA/OTP verification, and execute the final submission manually.

---

### Route C: Verified Recruiter / Hiring Email
- **Applicability:** Job postings that explicitly publish a designated recruitment contact email address (e.g. `careers@company.com`, `tech-hiring@startup.io`) within the official job description.
- **Safety & Verification Rules:**
  1. *Source Extraction Verification:* Extracts only email addresses explicitly published in the verified job description text or official careers page.
  2. *Domain Association Check:* Verifies that the email domain matches the employer's official domain. Generic email services (@gmail.com, @yahoo.com) are flagged with an unverified warning.
  3. *No Email Guessing:* JobPilot **never guesses or extrapolates email formats** (e.g. `first.last@company.com`).
  4. *No Automated Mass Mailing:* The candidate is presented with a complete pre-drafted email containing:
     - Clear subject line (e.g., *"Application for Senior Backend Engineer — [Candidate Name]"*).
     - Professional cover letter customized for the role.
     - Attached approved tailored resume PDF.
  5. *Mandatory Explicit Approval:* The candidate must review the recipient, message, and attachments, and click **"Send Application Email"** (or export to their local email client).

---

### Route D: External Application Assistance
- **Applicability:** Enterprise career portals requiring authentication, complex legacy ATS platforms (Workday, Taleo, iCIMS), or unintegrated job boards.
- **Assisted Workflow:**
  1. *Opens Employer Portal:* Opens the official application URL in a dedicated browser tab.
  2. *Provides Floating Sidecar / Companion Panel:* Displays the candidate's tailored resume and a **"Copy-Ready Answer Panel"** containing:
     - One-click copy for Employment History, Project Descriptions, and Education details.
     - Pre-formatted responses to common application questionnaire prompts.
  3. *Checklist Tracking:* Displays missing items required for the candidate to manually input.
  4. *Return-to-Portal Confirmation Flow:* Upon completion, the candidate returns to JobPilot and enters their application reference number or confirmation receipt.

---

## 3. Application State Machine & Provenance Tracking

JobPilot maintains a strict audit trail of every application attempt. An application is **never marked as Submitted merely because a tab was opened**.

```
+-----------------------------------------------------------------------------------+
|                            APPLICATION STATE MACHINE                              |
|                                                                                   |
|     +-------------+                                                               |
|     |    DRAFT    |  (Job shortlisted, resume tailoring in progress)              |
|     +------+------+                                                               |
|            |                                                                      |
|            v                                                                      |
|     +-------------+                                                               |
|     |  PREPARING  |  (Tailored resume & answer bank locked for this job)          |
|     +------+------+                                                               |
|            |                                                                      |
|            v                                                                      |
|     +------------------+                                                          |
|     | READY_FOR_REVIEW |  (Candidate approved resume & route selected)             |
|     +---+----------+---+                                                          |
|         |          |                                                              |
|         | Route B/D| Route C                                                      |
|         v          v                                                              |
|   +------------+ +------------+                                                   |
|   |   OPENED   | | EMAIL_SENT |                                                   |
|   | EXTERNALLY | +-----+------+                                                   |
|   +-----+------+       |                                                          |
|         |              v                                                          |
|         v        +-----------+                                                    |
|   +------------+ | SUBMITTED |                                                    |
|   |  PENDING   | +-----+-----+                                                    |
|   |CONFIRMATION|       |                                                          |
|   +-----+------+       v                                                          |
|         |        +-------------------------------------------------------------+  |
|         +───────►| POST-SUBMISSION STAGES:                                     |  |
|                  | Applied -> Screening -> Interviewing -> Offer -> Rejected   |  |
|                  +-------------------------------------------------------------+  |
|                                                                                   |
|  * Exception States: FAILED (Technical error) | WITHDRAWN (Candidate cancelled)   |
+-----------------------------------------------------------------------------------+
```

### 3.1 Data Model Specification (`applications` table enhancements)

```sql
-- Comprehensive application provenance
ALTER TABLE applications ADD COLUMN application_route VARCHAR(20) DEFAULT 'ROUTE_D'; -- ROUTE_A, ROUTE_B, ROUTE_C, ROUTE_D
ALTER TABLE applications ADD COLUMN tailored_resume_id INTEGER REFERENCES resumes(id);
ALTER TABLE applications ADD COLUMN cover_letter_id INTEGER;
ALTER TABLE applications ADD COLUMN route_metadata JSONB DEFAULT '{}'::jsonb;
-- route_metadata records:
-- Route A: { "api_endpoint": "...", "transaction_id": "..." }
-- Route B: { "extension_version": "1.0.0", "ats_platform": "greenhouse", "fields_filled": 14 }
-- Route C: { "recipient_email": "careers@corp.com", "smtp_message_id": "...", "sent_at": "..." }
-- Route D: { "external_url": "https://wd5.myworkdayjobs.com/...", "opened_at": "..." }

ALTER TABLE applications ADD COLUMN candidate_confirmation_evidence TEXT;
ALTER TABLE applications ADD COLUMN confirmation_timestamp TIMESTAMPTZ;
```

---

## 4. Candidate Feedback & Audit Logging

Every interaction with an external employer site or email server is immutably recorded in the platform security audit log:
- **Event:** `APPLICATION_ROUTE_TRIGGERED` (Timestamp, User ID, Job ID, Route selected).
- **Event:** `EXTENSION_FIELDS_FILLED` (Timestamp, Fields populated, Sensitive fields skipped).
- **Event:** `APPLICATION_EMAIL_DISPATCHED` (Timestamp, Recruiter address, Subject, Attachment hash).
- **Event:** `APPLICATION_CONFIRMED_BY_USER` (Timestamp, Reference ID, Candidate confirmation text).

The candidate always knows precisely what JobPilot has assisted with and what final action remains in their hands.
