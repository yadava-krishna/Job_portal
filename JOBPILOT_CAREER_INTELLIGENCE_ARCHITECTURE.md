# JobPilot — Career Intelligence Architecture (Deterministic & Explainable)

**Document Status:** Technical Architecture & Design Specification  
**Design Paradigm:** Pure Python Deterministic Processing, Rule-Based Evaluation & Structured Matching  
**Zero-LLM Mandate:** No local models, Docker inference containers (Ollama/Llama/Qwen), or mandatory cloud LLM dependencies.

---

## 1. System Vision & Guiding Principles

The JobPilot Career Intelligence Engine evaluates the true technical compatibility between an IT professional and a job opening. Unlike opaque generative AI systems that hallucinate qualifications or produce fluctuating scores, JobPilot is engineered on **deterministic, auditable, and rule-based computer science algorithms**:
1. **Explainable Scoring:** Every score is broken down into clear mathematical weights (Eligibility, Skills, Experience, Preferences).
2. **Strict Verification Gates:** A candidate cannot be marked eligible if a hard requirement (e.g. mandatory B.Tech/M.Tech degree, 5+ years experience, or work authorization) is missing from their verified profile.
3. **No Phantom Claims:** The system never invents skills, projects, or accomplishments. Missing skills are categorized as either *Absent from Profile* or *Clarification Required*.
4. **Lightweight & High-Throughput:** Runs in standard Python processes using compiled C/Rust extensions (`rapidfuzz`, `selectolax`, `pydantic`), consuming minimal CPU and zero GPU resources.

---

## 2. Master Candidate Profile Architecture

The Master Candidate Profile serves as the **single source of verified truth** for the candidate. While a candidate can upload multiple historical PDF resumes, the master profile aggregates and structures all verified facts.

```
+-----------------------------------------------------------------------------------------+
|                                MASTER CANDIDATE PROFILE                                 |
|                                                                                         |
|  +---------------------------+  +---------------------------+  +---------------------+  |
|  |     Personal & Contact    |  |    Employment History     |  |   Education & Certs |  |
|  | - Full Name, Email, Phone |  | - Normalized Company      |  | - Degree, Field     |  |
|  | - Location, Work Mode     |  | - Standardized Title      |  | - Institution, Year |  |
|  | - Work Authorization      |  | - Start/End Dates (UTC)   |  | - Verified Licences |  |
|  | - Notice Period & CTC     |  | - Verified Bullet Points  |  | - GPA / Honors      |  |
|  +---------------------------+  +---------------------------+  +---------------------+  |
|                                                                                         |
|  +-----------------------------------------------------------------------------------+  |
|  |                              Technical Skill Taxonomy                             |  |
|  |  Category         Skills                          Proficiency Level   Evidence    |  |
|  |  -------------------------------------------------------------------------------  |  |
|  |  Languages:       Python, TypeScript, SQL         Expert / Advanced   Project A   |  |
|  |  Frameworks:      FastAPI, React 19, Django       Advanced            Role 1      |  |
|  |  Cloud & Infra:   AWS, Docker, PostgreSQL         Intermediate        Cert X      |  |
|  +-----------------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------------+
```

### 2.1 Relational Schema Design
The profile transitions from an unstructured JSON blob into typed, indexed relational tables:

```sql
-- Core candidate master profile
CREATE TABLE candidate_profiles_v2 (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    headline VARCHAR(255),
    summary TEXT,
    years_experience NUMERIC(4, 1) NOT NULL DEFAULT 0.0,
    relevant_it_experience NUMERIC(4, 1) NOT NULL DEFAULT 0.0,
    highest_education_level VARCHAR(50), -- HighSchool, Bachelors, Masters, Doctorate
    current_location VARCHAR(150),
    preferred_locations TEXT[],
    work_modes TEXT[], -- Remote, Hybrid, On-site
    work_authorization TEXT[], -- Citizen, Permanent Resident, H1B, Tier 2
    current_ctc_inr NUMERIC(12, 2),
    expected_ctc_inr NUMERIC(12, 2),
    notice_period_days INTEGER DEFAULT 30,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_profile UNIQUE (user_id)
);

-- Verified employment history
CREATE TABLE profile_work_experiences (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES candidate_profiles_v2(id) ON DELETE CASCADE,
    company_name VARCHAR(200) NOT NULL,
    job_title VARCHAR(200) NOT NULL,
    standardized_title VARCHAR(100), -- Software Engineer, Backend Dev, DevOps
    location VARCHAR(150),
    start_date DATE NOT NULL,
    end_date DATE, -- NULL indicates current employment
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    achievements TEXT[], -- Fact-checked accomplishment statements
    technologies_used TEXT[], -- Skills proven in this role
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Verified skill proficiencies
CREATE TABLE profile_skills (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES candidate_profiles_v2(id) ON DELETE CASCADE,
    skill_name VARCHAR(100) NOT NULL,
    normalized_name VARCHAR(100) NOT NULL, -- python, postgresql, aws
    category VARCHAR(50) NOT NULL, -- language, framework, database, cloud, devops
    proficiency_level VARCHAR(20) NOT NULL DEFAULT 'INTERMEDIATE', -- BEGINNER, INTERMEDIATE, ADVANCED, EXPERT
    years_applied NUMERIC(4, 1),
    is_verified BOOLEAN NOT NULL DEFAULT FALSE, -- True if proven by work experience or cert
    evidence_source VARCHAR(100), -- 'work_experience_12', 'cert_aws_solutions_architect'
    CONSTRAINT uq_profile_skill UNIQUE (profile_id, normalized_name)
);
```

---

## 3. Deterministic Job Description Intelligence

Job descriptions (JDs) are processed through a structured pipeline using regex rule engines, dictionary tokenizers, and the `RapidFuzz` string matching library against our curated `config/skills_taxonomy.yaml`.

### 3.1 Extraction Pipeline
1. **Text Normalization:**
   - HTML stripping via `selectolax.lexbor` (5x faster than BeautifulSoup).
   - Character decoding and whitespace canonicalization.
2. **Taxonomy & Skill Mapping:**
   - Uses an alias-expanded taxonomy covering 1,800+ IT terms (e.g., `["postgres", "postgresql", "psql"]` $\rightarrow$ `postgresql`; `["react", "reactjs", "react.js"]` $\rightarrow$ `react`).
   - Exact boundary regex matching: `\b(python|django|fastapi)\b` with negative lookarounds (e.g. preventing `Go` from matching `go to`).
3. **Experience & Education Extractor:**
   - Regex patterns for experience bounds:
     - `(?P<min>\d+)(?:\s*(?:to|-)\s*(?P<max>\d+))?\s*\+?\s*(?:years?|yrs?)(?:\s*of)?\s*(?:experience|exp)`
   - Degree patterns:
     - `\b(b\.?tech|b\.?e|m\.?tech|m\.?s|bca|mca|b\.?sc|m\.?sc|ph\.?d|bachelor'?s|master'?s)\b`
4. **Mandatory vs. Preferred Classifier:**
   - Section header segmentation:
     - *Mandatory Section Patterns:* `must have`, `required skills`, `qualifications`, `minimum requirements`, `basic qualifications`.
     - *Preferred Section Patterns:* `nice to have`, `preferred qualifications`, `good to have`, `bonus points`, `plus`.
   - Skills occurring in mandatory sections receive $1.5\times$ match weight.

---

## 4. Multi-Factor Explainable Candidate-to-Job Matching

Matching is broken down into four independent, explainable sub-scores:

$$\text{Total Score} = (0.25 \times \text{Eligibility}) + (0.45 \times \text{Skills}) + (0.20 \times \text{Experience}) + (0.10 \times \text{Preferences})$$

```
                   +---------------------------------------------+
                   |           Raw Job Description (JD)          |
                   +----------------------+----------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                        1. HARD ELIGIBILITY GATE (Pass / Fail)                     |
|  - Degree Requirement vs. Candidate Highest Education                             |
|  - Minimum Experience vs. Total Years (Tolerance: -1.0 year)                      |
|  - Work Authorization & Location Mode (Onsite vs Remote vs Citizen)               |
|                                                                                   |
|  * Outcome: If any mandatory hard condition fails, Match Score capped at <= 30.   |
+-----------------------------------------+-----------------------------------------+
                                          |
                                    [ GATE PASSED ]
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                        2. TECHNICAL SKILL OVERLAP (0 - 100)                       |
|  - Mandatory Skills Coverage (Weight: 70%)                                        |
|  - Preferred Skills Coverage (Weight: 30%)                                        |
|  - RapidFuzz Token Set Ratio for fuzzy spelling variations                        |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                     3. EXPERIENCE & SENIORITY FIT (0 - 100)                       |
|  - Candidate Years vs. Role Experience Range                                      |
|  - Seniority Level Alignment (Junior, Mid, Senior, Lead, Staff, Architect)        |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                     4. CANDIDATE PREFERENCE FIT (0 - 100)                         |
|  - Work Mode Alignment (Remote / Hybrid / On-site)                                |
|  - Location Proximity / Relocation Preference                                     |
|  - Expected CTC vs. Published Job Salary Band                                     |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                           FINAL EXPLAINABLE AUDIT BREAKDOWN                       |
|  - Overall Score: 84 / 100                                                        |
|  - Verified Skills Matched: Python, FastAPI, PostgreSQL, Docker (4 / 5)           |
|  - Documented Skill Gaps: Kubernetes (Mandatory), Redis (Preferred)               |
|  - Experience Delta: 4.5 years verified vs. 3 - 5 years required (Perfect fit)   |
|  - Preference Match: Remote preference matches Job Remote designation             |
+-----------------------------------------------------------------------------------+
```

---

## 5. Actionable Skill-Gap Diagnostic Engine

For every evaluated job, the engine outputs an explainable gap breakdown:
1. **Proven Skills:** Candidate's profile contains verified evidence (employment or certification) matching the job requirement.
2. **Partially Demonstrated:** Candidate has complementary technologies (e.g., job requires `FastAPI`, candidate has `Flask` and `Django` + `Python`).
3. **Documented Gaps:** Skills explicitly demanded by the job that are completely absent from the candidate's profile.
4. **Clarification Prompts:** Questions presented to the candidate to verify unentered experience (e.g., *"This role requires AWS Lambda. You have listed AWS and Python—have you built serverless functions?"*).
5. **Deterministic Learning Paths:** Curated official documentation links (e.g. official Python/FastAPI docs, AWS Skill Builder, PostgreSQL tutorial) linked deterministically to the missing skill key.
