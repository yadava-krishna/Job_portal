# JobPilot — Open Source Technology & Repository Review

**Document Status:** Technical Evaluation & Due Diligence Report  
**Date:** November 2026  
**Scope:** Open-Source Repositories, Python Libraries & Architecture Paradigms  
**Code Reuse Policy:** Permissive Open-Source Only (MIT / Apache 2.0 / BSD). Strict prohibition on unlicensed code, proprietary reverse engineering, or importing heavy monolithic second backends.

---

## 1. Primary Open-Source Repositories Evaluated

### 1.1 Scrapling (Web Scraping & Adaptive Parsing Framework)
- **Repository URL:** `https://github.com/D4Vinci/Scrapling`
- **Official Documentation:** `https://scrapling.readthedocs.io/en/latest/`
- **License:** BSD 3-Clause (Permissive)
- **Stars / Community:** 3,800+ stars (Verified November 2026), actively maintained.
- **Language / Architecture:** Python 3.10+, built on `curl_cffi`, `lxml`, `patchright`, `cssselect`.
- **Useful Components for JobPilot:**
  - `Fetcher`: High-speed static HTTP client using `curl_cffi` with connection pooling and fast response extraction.
  - `StealthyFetcher`: Headless browser-assisted fetcher utilizing `patchright` for legitimate JavaScript-rendered vacancy pages.
  - Adaptive CSS/XPath selectors and automatic Schema.org JSON-LD extraction.
- **JobPilot Compatibility:** **100% Compatible.** Already integrated in `backend/services/scrapling_client.py` and 12 discovery connectors with custom DNS-level SSRF defenses.
- **Code Reuse Decision:** **Reuse as Direct Python Dependency** (`scrapling[fetchers]==0.5.1`).

---

### 1.2 Reactive Resume (Full-Stack Resume Builder)
- **Repository URL:** `https://github.com/AmruthPillai/Reactive-Resume`
- **License:** MIT License (Permissive)
- **Stars / Community:** 24,000+ stars, highly active community.
- **Language / Architecture:** Monorepo with NestJS backend, PostgreSQL, MinIO S3 storage, React frontend, Tailwind CSS.
- **Useful Components for JobPilot:**
  - Strongly-typed JSON Resume Schema for sections (Summary, Experience, Education, Skills, Projects, Certifications).
  - Clean UI design patterns for section re-ordering and bullet point management.
- **JobPilot Compatibility:** **Incompatible as a full application.** Importing Reactive Resume would require standing up a second NestJS/Node.js backend, S3 object store, and redundant PostgreSQL database.
- **Code Reuse Decision:** **Adapt Architecture & Schema Only.** Re-implement its JSON resume section schema in JobPilot's native React 19 frontend and FastAPI backend.

---

### 1.3 ResumeFold (Lightweight Client-Side Resume Builder)
- **Repository URL:** `https://github.com/delta-dog/resumefold`
- **License:** MIT License
- **Stars / Community:** 1,200+ stars.
- **Language / Architecture:** React, Vite, Tailwind CSS. Completely client-side execution.
- **Useful Components for JobPilot:**
  - DOM-to-Canvas rendering and instant real-time live preview without server lag.
  - Clean modular CSS printing stylesheets for multi-page PDF generation.
- **JobPilot Compatibility:** **High.** Fits directly into JobPilot's existing Vite + React frontend stack.
- **Code Reuse Decision:** **Inspiration & Pattern Adaptation** for client-side live rendering in `ResumeStudioPage.tsx`.

---

### 1.4 OpenResume (Minimal ATS-Friendly Resume Builder)
- **Repository URL:** `https://github.com/xitanggg/open-resume`
- **License:** MIT License
- **Stars / Community:** 6,500+ stars.
- **Language / Architecture:** Next.js, React-PDF, Tailwind CSS.
- **Useful Components for JobPilot:**
  - Strict single-column ATS templates optimized for machine readability.
  - Direct PDF text extraction diagnostic testing using PDF.js to verify parser reading order.
- **JobPilot Compatibility:** **High.** The text extraction diagnostic patterns can be adapted into JobPilot's 3-Tier ATS compatibility suite.
- **Code Reuse Decision:** **Adapt Template Architecture & PDF Diagnostic Algorithms.**

---

### 1.5 FreeHire (ATS Job Aggregation Engine)
- **Repository URL:** `https://github.com/FreeHire/freehire`
- **License:** MIT License
- **Stars / Community:** 850+ stars.
- **Language / Architecture:** Python, FastAPI, SQLite/PostgreSQL.
- **Useful Components for JobPilot:**
  - Token discovery patterns for public Greenhouse, Lever, and SmartRecruiters boards.
  - Location normalization rules for Indian and international tech clusters.
- **Code Reuse Decision:** **Inspiration** for expanding employer token catalogues.

---

### 1.6 JobSync (Curated ATS Company Boards)
- **Repository URL:** `https://github.com/Gsync/jobsync`
- **License:** MIT License
- **Useful Components for JobPilot:**
  - Curated JSON lists of public Greenhouse, Lever, and Ashby tokens.
- **JobPilot Compatibility:** **Already Reused Legally.** Verified copies of `jobsync_greenhouse.json`, `jobsync_lever.json`, and `jobsync_ashby.json` are maintained in `backend/data/ats_companies/` with full license attribution.

---

## 2. High-Performance Python Libraries Evaluated

| Package | Purpose & Function | License | Replaces / Complements | Integration Effort | Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`python-docx`** | Native OpenXML `.docx` resume generation with Word styles | MIT | Enables required DOCX export alongside PDF | Low (Python API) | **Adopt in Phase 11** for native DOCX resume export. |
| **`reportlab`** | Programmatic, exact-coordinate vector PDF generation | BSD | Complements PyMuPDF by producing pristine machine-readable PDF streams | Medium | **Adopt in Phase 11** for backend single-column ATS PDF builds. |
| **`pymupdf` (fitz)** | High-speed PDF text, metadata, and structural extraction | AGPL / Commercial | Already installed in JobPilot (`backend/requirements.txt`) | Zero (Installed) | **Retain** for file upload validation & Tier 1 ATS parser diagnostics. |
| **`selectolax`** | Ultra-fast HTML parsing using Modest/Lexbor C engines | MIT | 5x to 10x faster than BeautifulSoup for high-volume JD cleaning | Low | **Adopt in Phase 10** for zero-overhead HTML description sanitization. |
| **`rapidfuzz`** | C++ optimized Levenshtein and token-set string matching | MIT | Replaces slow Python `difflib` and fuzzywuzzy | Low | **Adopt in Phase 10** for deterministic skill taxonomy matching. |
| **`dateparser`** | Multi-format human date parsing ("3 days ago", "12 Oct 2026") | BSD | Complements standard `datetime.strptime` | Low | **Adopt in Phase 9** for robust posting date normalization. |
| **`extruct`** | Microdata, JSON-LD, and RDFa metadata extraction | BSD | Complements Scrapling JSON-LD connector | Low | Optional evaluation for edge-case Microdata. |

---

## 3. Libraries Rejected or Deferred

1. **Monolithic AI Frameworks (LangChain, LlamaIndex, AutoGen):**
   - *Reason for Rejection:* Massive dependency trees (100+ sub-packages), frequent breaking changes, high runtime overhead, and explicit conflict with our **Zero-LLM Mandate**.
2. **GPU Inference Engines (Ollama, vLLM, TensorRT-LLM):**
   - *Reason for Rejection:* Prohibited by project constraints. Consumes heavy server memory/GPU resources and creates operational fragility.
3. **External Message Brokers (RabbitMQ, Redis):**
   - *Reason for Deferral:* Unnecessary infrastructure complexity for current scale. PostgreSQL-backed queues (`SELECT ... FOR UPDATE SKIP LOCKED`) provide fully durable, transactionally consistent task dispatching without running additional services.
