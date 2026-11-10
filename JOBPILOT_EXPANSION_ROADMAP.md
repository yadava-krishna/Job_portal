# JobPilot — Strategic Expansion Roadmap (Phases 9–16)

**Document Status:** Complete Phased Implementation Specification  
**Execution Standard:** Zero Regressions, Additive Database Migrations, Preserved Production State  
**Total Expansion Phases:** 8 Phases (Phase 9 through Phase 16)

---

## 1. Roadmap Dependency Graph

```
                                [ CURRENT STATE: PHASE 8 VERIFIED ]
                                                 │
                                                 ▼
                             [ Phase 9: Source Coverage & Quality ]
                                                 │
                                                 ▼
                        [ Phase 10: Career Intelligence Engine (Core) ]
                                                 │
                 ┌───────────────────────────────┴───────────────────────────────┐
                 ▼                                                               ▼
  [ Phase 11: Resume Studio & Exports ]                    [ Phase 14: IT Government Benefits ]
                 │                                                               │
                 ▼                                                               │
  [ Phase 12: Unified Apply Orchestrator ]                                       │
                 │                                                               │
                 ▼                                                               │
  [ Phase 13: Application Intelligence ]                                         │
                 │                                                               │
                 └───────────────────────────────┬───────────────────────────────┘
                                                 ▼
                         [ Phase 15: Specialized Rule-Based Agents ]
                                                 │
                                                 ▼
                       [ Phase 16: Performance Hardening & uv Migration ]
```

---

## 2. Phase-by-Phase Technical Specifications

---

### Phase 9: Global IT Job Discovery Expansion & Source Quality
- **Objective:** Scale discovery across 100+ vetted technology sources, enhance deduplication, implement job freshness tracking, and automate ATS detection.
- **Modifications to Existing Files:**
  - `backend/services/discovery_service.py`: Add batch insertion pipeline, freshness scoring, and expired listing reaper.
  - `backend/services/normalization.py`: Extend technology field normalizers.
  - `backend/services/source_policies.py`: Ingest 100+ approved employer domains and rate limits.
- **New Files to Create:**
  - `backend/services/connectors/workday_connector.py`: Public Workday RSS/JSON parser.
  - `backend/services/connectors/smartrecruiters_connector.py`: Public postings client.
  - `backend/services/ats_detector.py`: Heuristic detector for employer career pages.
- **Database Schema Changes:**
  - Add `freshness_score` (FLOAT), `is_expired` (BOOLEAN), and `last_scraped_at` (TIMESTAMPTZ) to `jobs` table.
- **API Endpoints:**
  - `GET /api/v1/discovery/sources/catalog`: Paginated list of 100+ sources with live health status.
  - `POST /api/v1/discovery/sources/detect-ats`: Detects ATS platform and feeds from any career URL.
- **Frontend Screens:**
  - Update `frontend/src/pages/SearchesPage.tsx` with enhanced Sources Directory filtering.
- **Dependencies:** `selectolax`, `dateparser`.
- **Complexity:** Medium (3–4 days).
- **Acceptance Criteria:** Successfully ingests and deduplicates 500+ technology job openings across 20+ live sources with zero SSRF vulnerabilities.

---

### Phase 10: Career Intelligence Engine (Deterministic Matching & Skill Gaps)
- **Objective:** Transition to the structured Master Candidate Profile schema, implement deterministic JD understanding, and build the explainable 4-factor matching engine.
- **Modifications to Existing Files:**
  - `backend/services/matching_service.py`: Replace heuristic scoring with multi-factor mathematical weights.
  - `backend/models/__init__.py`: Add relational profile and skill tables.
- **New Files to Create:**
  - `backend/services/profile_master_service.py`: CRUD and verification for Master Profile.
  - `backend/services/jd_intelligence_service.py`: Deterministic requirement & qualification extraction.
  - `backend/services/skill_gap_service.py`: Actionable skill gap diagnostic engine.
  - `frontend/src/pages/CareerIntelligencePage.tsx`: Visual breakdown of match scores and gaps.
- **Database Schema Changes:**
  - Add tables `candidate_profiles_v2`, `profile_work_experiences`, `profile_skills`, and `job_match_reports`.
- **API Endpoints:**
  - `GET /api/v1/profile/master`: Retrieve structured master candidate profile.
  - `PUT /api/v1/profile/master`: Update verified facts, proficiencies, and career history.
  - `GET /api/v1/jobs/{job_id}/intelligence`: Detailed explainable match score, proven skills, and gap report.
- **Frontend Screens:**
  - `CareerIntelligencePage.tsx` with interactive Radar Chart / Skill Fit meters.
- **Dependencies:** `rapidfuzz`.
- **Complexity:** High (5–6 days).
- **Acceptance Criteria:** Every job match displays a transparent mathematical audit breakdown; hard disqualifiers correctly cap scores $\le 30$.

---

### Phase 11: Resume Studio & ATS Optimization (PDF & DOCX)
- **Objective:** Build an integrated in-browser resume editor, dual PDF and DOCX export engines, truthful job-specific tailoring, and 3-Tier ATS compatibility diagnostic suite.
- **Modifications to Existing Files:**
  - `backend/services/resume_service.py`: Connect to new document generation services.
- **New Files to Create:**
  - `backend/services/resume_tailor_service.py`: Truthful bullet re-ordering and anti-fabrication audit engine.
  - `backend/services/docx_generator.py`: Native Microsoft Word OpenXML generator (`python-docx`).
  - `backend/services/pdf_generator.py`: ATS-pure machine-readable PDF generator (`reportlab`).
  - `backend/services/ats_diagnostic_service.py`: 3-Tier compatibility testing engine.
  - `frontend/src/pages/ResumeStudioPage.tsx`: Interactive WYSIWYG editor with live canvas preview.
- **Database Schema Changes:**
  - Add tables `tailored_resumes`, `resume_versions`, and `ats_diagnostic_reports`.
- **API Endpoints:**
  - `POST /api/v1/resumes/tailor`: Tailor master resume for a specific job description.
  - `GET /api/v1/resumes/{resume_id}/export/pdf`: Stream pristine machine-readable PDF.
  - `GET /api/v1/resumes/{resume_id}/export/docx`: Stream standard Word document.
  - `POST /api/v1/resumes/{resume_id}/ats-compatibility`: Execute 3-Tier ATS compatibility diagnostic.
- **Frontend Screens:**
  - `ResumeStudioPage.tsx` (Split-pane editor and live ATS text-view diagnostic).
- **Dependencies:** `python-docx`, `reportlab`.
- **Complexity:** Very High (6–7 days).
- **Acceptance Criteria:** Generates both valid PDF and DOCX documents that parse cleanly in standard PDF text extractors with zero fabricated information.

---

### Phase 12: Unified Apply Orchestration Service
- **Objective:** Implement the Central Apply Orchestration service supporting Routes A, B, C, and D, with browser extension form-fill assistance and recruiter email drafting.
- **Modifications to Existing Files:**
  - `backend/services/application_service.py`: Integrate 4-route dynamic dispatcher.
  - `extension/src/content/core.js`: Add Ashby/Lever/Greenhouse tailored resume injection.
- **New Files to Create:**
  - `backend/services/apply_orchestrator.py`: Route selector, answer provisioner, and confirmation manager.
  - `backend/services/recruiter_email_service.py`: Recruiter email validator, draft builder, and consent dispatcher.
  - `frontend/src/components/app/ApplyOrchestratorModal.tsx`: Step-by-step route guidance modal.
- **Database Schema Changes:**
  - Enhance `applications` table with `application_route`, `tailored_resume_id`, and `route_metadata`.
- **API Endpoints:**
  - `POST /api/v1/applications/{job_id}/orchestrate`: Initialize application assistance route.
  - `POST /api/v1/applications/{app_id}/email-draft`: Generate recruiter email draft with attachments.
  - `POST /api/v1/applications/{app_id}/send-email`: Dispatch approved recruiter email.
  - `POST /api/v1/applications/{app_id}/confirm`: Manually confirm external submission with evidence.
- **Frontend Screens:**
  - `ApplyOrchestratorModal.tsx` mounted across all job cards in Discover and Searches pages.
- **Complexity:** High (5–6 days).
- **Acceptance Criteria:** Candidate can complete applications across all 4 routes with complete state tracking and zero unapproved automated actions.

---

### Phase 13: Application Intelligence & Post-Submission Analytics
- **Objective:** Track application conversion rates, response velocity, interview stage progression, and generate deterministic interview preparation briefs.
- **Modifications to Existing Files:**
  - `backend/services/tracker_service.py`: Add post-submission analytics and metrics aggregation.
- **New Files to Create:**
  - `backend/services/interview_prep_service.py`: Role-specific technical question banks.
  - `frontend/src/pages/ApplicationAnalyticsPage.tsx`: Funnel conversion visualization.
- **Database Schema Changes:**
  - Add `stage_transitions` table to record timestamps between application stages.
- **API Endpoints:**
  - `GET /api/v1/applications/analytics/funnel`: Application conversion metrics (Applied -> Interview -> Offer).
  - `GET /api/v1/applications/{app_id}/prep-brief`: Technical interview preparation brief based on tech stack.
- **Complexity:** Medium (3–4 days).

---

### Phase 14: IT Industry & Government Benefits Intelligence Module
- **Objective:** Deploy a dedicated module for Indian IT industry government programmes, prioritizing Karnataka (KITS, KDEM, ELEVATE), Central (MeitY, STPI, Startup India, MSME), Telangana, and Tamil Nadu.
- **New Files to Create:**
  - `backend/models/government_schemes.py`: Scheme models, eligibility rules, and benefit types.
  - `backend/services/government_benefits_service.py`: Scheme directory and deterministic eligibility matcher.
  - `backend/api/routes/government_benefits.py`: Government benefits API endpoints.
  - `frontend/src/pages/GovernmentBenefitsPage.tsx`: Interactive benefits portal with beneficiary filters.
- **Database Schema Changes:**
  - Create table `it_government_schemes` and `user_saved_schemes`.
- **API Endpoints:**
  - `GET /api/v1/government-benefits/schemes`: Filter schemes by beneficiary (`INDIVIDUAL`, `STARTUP`, `MSME_TECH`, `SOFTWARE_EXPORTER`) and jurisdiction (`Karnataka`, `Central`, etc.).
  - `POST /api/v1/government-benefits/check-eligibility`: Evaluate candidate/startup profile against scheme criteria.
- **Frontend Screens:**
  - `GovernmentBenefitsPage.tsx` with search, state filters, and step-by-step application guides.
- **Complexity:** Medium (4–5 days).
- **Acceptance Criteria:** Displays verified schemes (ELEVATE Karnataka ₹50L, SISFS ₹20L, KDEM Lease Subsidy, FutureSkills Prime) with official links, distinguishing individual vs company benefits.

---

### Phase 15: Specialized Rule-Based Subject Matter Expert Agents
- **Objective:** Implement the central agent coordinator managing 10 specialized rule-based agents with evidence-backed outputs and zero ungrounded claims.
- **New Files to Create:**
  - `backend/services/agents/orchestrator.py`: Central coordination and state controller.
  - `backend/services/agents/discovery_agent.py`: Source health and crawl scheduler.
  - `backend/services/agents/jd_analyst_agent.py`: Technical requirement parser.
  - `backend/services/agents/matching_agent.py`: Multi-factor fit calculator.
  - `backend/services/agents/resume_agent.py`: Truthful tailoring and bullet selector.
  - `backend/services/agents/ats_agent.py`: Parser compatibility evaluator.
  - `backend/services/agents/application_agent.py`: Application Q&A bank assistant.
  - `backend/services/agents/recruiter_agent.py`: Professional email drafter.
  - `backend/services/agents/schemes_agent.py`: Government policy matching agent.
  - `backend/services/agents/growth_agent.py`: Skill gap learning roadmap agent.
- **Complexity:** High (5–6 days).
- **Acceptance Criteria:** All agents execute deterministically in Python without requiring external LLM API keys or local GPU models.

---

### Phase 16: Performance Hardening, `uv` Migration & Production Verification
- **Objective:** Adopt Astral `uv` package management, optimize Docker multi-stage builds, implement PostgreSQL-backed durable task queues, and execute end-to-end load tests.
- **Modifications to Existing Files:**
  - Convert `backend/requirements.txt` $\rightarrow$ `pyproject.toml` and generate `uv.lock`.
  - Update `backend/Dockerfile` to use multi-stage `uv` builder.
  - Update `docker-compose.yml` resource limits and health checks.
- **New Files to Create:**
  - `backend/services/queue_service.py`: Durable task queue using `SELECT ... FOR UPDATE SKIP LOCKED`.
  - `deploy/benchmark.sh`: Automated build and response benchmarking script.
- **Complexity:** Medium (3–4 days).
- **Acceptance Criteria:** Docker builds utilize cached wheels; zero loss of database data; test suite executes 100% green.

---

## 3. Rollback & Disaster Recovery Strategy

1. **Database Rollbacks:** Every Alembic migration script will include a fully functional, verified `downgrade()` function. Migrations are strictly additive to existing tables to avoid breaking running containers.
2. **Zero Data Loss Guarantee:** Never run `docker compose down -v`. Pre-migration backups are created via `./deploy/backup.sh` storing timestamped dumps in `./backups/` with verified `SHA256SUMS`.
3. **Environment Preservation:** Current credentials, JWT secrets, and encryption keys are preserved unchanged throughout all phases.
