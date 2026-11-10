# JobPilot — Resume Studio & ATS Optimization Design

**Document Status:** Complete Architecture & Design Specification  
**Core Principles:** Truthful Representation, Dual Export (PDF & DOCX), 3-Tier ATS Compatibility Testing  
**Strict Anti-Fabrication Guarantee:** Zero invented employers, dates, credentials, or unproven technical skills.

---

## 1. System Overview & Open-Source Evaluation

The JobPilot Resume Studio enables technology professionals to create, manage, and tailor ATS-compatible resumes directly within the platform. Rather than treating each resume as an isolated document, Resume Studio connects directly to the **Master Candidate Profile** as the single source of verified truth.

### 1.1 Open-Source Repository Review & Architecture Lessons

| Repository | License | Stars | Architecture | Key Lessons & Applicability for JobPilot |
| :--- | :--- | :--- | :--- | :--- |
| **Reactive Resume** (`AmruthPillai/Reactive-Resume`) | MIT | 24,000+ | NestJS, React, Tailwind, PostgreSQL, MinIO | Excellent JSON Schema for resume sections and modular templates. *Decision:* Adopt its section data structure and JSON Resume alignment; do not import its monolithic NestJS backend. |
| **ResumeFold** (`delta-dog/resumefold`) | MIT | 1,200+ | React, Vite, Tailwind CSS, Client-side PDF | High-speed client-side DOM-to-canvas rendering. Demonstrates that client-side rendering avoids heavy backend PDF engines. |
| **OpenResume** (`xitanggg/open-resume`) | MIT | 6,500+ | Next.js, React-PDF, Tailwind | Clean single-column ATS layouts and direct PDF text extraction diagnostics. Informs JobPilot's single-column ATS template. |

---

## 2. Integrated Resume Editor Architecture

The editor is a React 19 WYSIWYG workspace backed by a strongly typed schema:

```
+-------------------------------------------------------------------------------------------------+
|                                     RESUME STUDIO WORKSPACE                                     |
|                                                                                                 |
|  [ Master Profile Link ]  [ Select Template: Single-Column ATS | Modern Hybrid ]  [ Export v ]  |
|                                                                                                 |
|  +--------------------------------------------+  +-------------------------------------------+  |
|  |           Structured Section Form          |  |         Live ATS Compatibility Canvas     |  |
|  |                                            |  |                                           |  |
|  | 1. Contact & Identity                      |  |   YADAVA KRISHNA                          |  |
|  |    Name, Email, Phone, GitHub, LinkedIn    |  |   Bengaluru, KA | the owner account  |  |
|  |                                            |  |                                           |  |
|  | 2. Professional Summary                     |  |   PROFESSIONAL SUMMARY                    |  |
|  |    Targeted overview (Role-specific)       |  |   Senior Backend Engineer with 5+ years   |  |
|  |                                            |  |   in Python, FastAPI, and PostgreSQL.     |  |
|  | 3. Technical Skills (Categorized)          |  |                                           |  |
|  |    Languages, Frameworks, DBs, Cloud       |  |   TECHNICAL SKILLS                        |  |
|  |                                            |  |   * Languages: Python, SQL, TypeScript    |  |
|  | 4. Work Experience (Verified Bullets)      |  |   * Frameworks: FastAPI, React, Docker    |  |
|  |    [Re-order] [Highlight Relevant]         |  |                                           |  |
|  |                                            |  |   EXPERIENCE                              |  |
|  | 5. Projects & Architecture Evidence        |  |   JobPilot - Lead Architect (2024-Present)|  |
|  | 6. Education & Certifications              |  |   * Engineered 12 discovery connectors... |  |
|  +--------------------------------------------+  +-------------------------------------------+  |
+-------------------------------------------------------------------------------------------------+
```

### 2.1 Supported Document Formats & Templates
1. **ATS Pure (Single-Column Standard):**
   - **Target Parsers:** Workday, Oracle Taleo, Greenhouse, iCIMS, SAP SuccessFactors.
   - **Layout Rules:** Single text column, standard system fonts (Arial, Calibri, Helvetica), standard section headers (`EXPERIENCE`, `EDUCATION`, `SKILLS`), no graphics, no tables, no multi-column floats.
2. **Modern Hybrid (Two-Column Visual):**
   - **Target:** Human recruiter review, networking, and direct email applications.
   - **Layout Rules:** Left sidebar for skills and education, right main panel for experience.
   - **ATS Warning:** Explicit visual banner alerting the candidate: *"Two-column formats may scramble text reading order in legacy enterprise ATS parsers."*

---

## 3. Truthful Job-Specific Resume Tailoring

When a candidate clicks **"Tailor Resume for this Job"**, JobPilot generates a customized, job-specific version based exclusively on verified facts:

```
+-----------------------------------------------------------------------------------+
|                        TRUTHFUL RESUME TAILORING WORKFLOW                         |
|                                                                                   |
|  +--------------------------------+       +------------------------------------+  |
|  |     Master Profile (Truth)     |       |      Target Job Description (JD)   |  |
|  | - Verified Roles & Companies   |       | - Target Title & Seniority         |  |
|  | - Verified Employment Dates    |       | - Required Tech Stack              |  |
|  | - Fact-Checked Accomplishments |       | - Mandatory Qualifications         |  |
|  +----------------+---------------+       +-----------------+------------------+  |
|                   |                                         |                     |
|                   +--------------------+--------------------+                     |
|                                        v                                          |
|  +-----------------------------------------------------------------------------+  |
|  |                         DETERMINISTIC TAILORING RULES                       |  |
|  |                                                                             |  |
|  | 1. Re-Rank Skills: Move verified skills that match JD keywords to the top.  |  |
|  | 2. Re-Order Bullets: Prioritize accomplishments utilizing matching tech.    |  |
|  | 3. Focused Summary: Tailor headline to target role without inventing years.|  |
|  | 4. Project Selection: Promote relevant technical projects matching stack.  |  |
|  +-------------------------------------+---------------------------------------+  |
|                                        |                                          |
|                                        v                                          |
|  +-----------------------------------------------------------------------------+  |
|  |                         AUDIT & ANTI-FABRICATION GATE                       |  |
|  |                                                                             |  |
|  | Diff engine checks proposed tailored resume against master candidate profile.|  |
|  |   [PASS] Every claim, date, employer, and skill exists in Master Profile.   |  |
|  |   [FAIL] If any unverified claim or keyword is injected -> Block generation.|  |
|  +-------------------------------------+---------------------------------------+  |
|                                        |                                          |
|                                        v                                          |
|  +-----------------------------------------------------------------------------+  |
|  |         Tailored Resume Version Saved (Linked to Job ID & Application)       |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

### 3.1 Strict Anti-Fabrication Invariants
1. **Never Invent Employers or Dates:** Employment records are strictly read-only from the verified master profile.
2. **Never Invent Degrees or Certifications:** Only verified educational credentials can be included.
3. **Never Inject Unproven Keywords:** If a job requires `Kubernetes` and the candidate does not have it in their profile, the system **never** inserts `Kubernetes` into the resume. It flags it as a skill gap in the diagnostic view.

---

## 4. Dual Export Engine: High-Fidelity PDF & Clean DOCX

JobPilot includes native support for both major enterprise application formats from day one:

```
                       +----------------------------------+
                       |   Tailored Resume JSON Schema    |
                       +-----------------+----------------+
                                         |
                ┌────────────────────────┴────────────────────────┐
                ▼                                                 ▼
+-------------------------------+                 +-------------------------------+
|       PDF EXPORT ENGINE       |                 |       DOCX EXPORT ENGINE      |
|                               |                 |                               |
| - Standard: ReportLab / Weasy |                 | - Library: `python-docx`      |
| - Machine-readable text stream|                 | - Clean OOXML Paragraphs      |
| - Embedded Type-1/TrueType font|                | - Standard Word Style mapping |
| - Zero rasterization of text  |                 | - No floating text boxes      |
| - Strict left-to-right reading|                 | - Native table-free flow      |
| - Validated via `pdftotext`   |                 | - 100% editable by candidate  |
+-------------------------------+                 +-------------------------------+
```

### 4.1 DOCX Generation Specification (`python-docx`)
- Generates clean OpenXML documents without non-standard macros or drawing canvases.
- Heading 1 $\rightarrow$ Full Name (20pt Bold).
- Heading 2 $\rightarrow$ Section Titles (12pt Bold, uppercase).
- Heading 3 $\rightarrow$ Company & Role with right-tabbed dates.
- Body Text $\rightarrow$ Bullet lists using standard `List Bullet` styles.

---

## 5. 3-Tier ATS Compatibility Diagnostic Engine

JobPilot conducts comprehensive compatibility testing without claiming to simulate proprietary, secret ATS algorithms:

### Tier 1: Document Structure & Readability Diagnostic
- **PDF Text Stream Extraction:** Evaluates whether text can be extracted cleanly using standard PDF parsers (`pdfminer`, `pypdf`, `pymupdf`).
- **Layout Integrity:** Detects multi-column text interleaving, unreadable ligature characters, and header/footer collisions.

### Tier 2: Keyword & Skill Alignment Testing
- **Lexical Overlap:** Measures exact matches between job requirements and resume text.
- **Categorical Breakdown:** Evaluates coverage across Programming Languages, Frameworks, Cloud Platforms, and Databases.

### Tier 3: Simulated ATS Text-Ingestion View
- Renders the exact unstyled, linear text representation as an enterprise ATS text parser receives it.
- Allows candidates to visually verify that their contact info, dates, and bullet points do not get jumbled or lost.

---

## 6. Cover Letter & Verified Application Answer Bank

1. **Deterministic Cover Letter Generator:**
   - Template-based structural composition:
     - *Paragraph 1:* Specific job title, company name, and source opening reference.
     - *Paragraph 2:* Candidate's verified core technical competencies directly relevant to the role.
     - *Paragraph 3:* Key verified engineering achievements and project impacts.
     - *Paragraph 4:* Notice period, current availability, and professional sign-off.
2. **Verified Application Answer Bank:**
   - Stores pre-validated answers to common screening questions:
     - Notice period (e.g. `30 days, negotiable`).
     - Current and expected compensation (e.g. `Current: 12 LPA, Expected: 18 LPA`).
     - Total years of IT experience (calculated mathematically from employment dates).
     - Work authorization status (e.g. `Authorized to work in India; Indian Citizen`).
     - Preferred work arrangement (e.g. `Remote or Hybrid in Bengaluru`).
   - Sensitive questions (e.g. diversity, equity, disability, criminal history) are never auto-filled and require explicit candidate input.
