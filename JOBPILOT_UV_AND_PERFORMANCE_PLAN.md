# JobPilot — Python Performance, `uv` Migration & Worker Scaling Plan

**Document Status:** Technical Architecture & Infrastructure Blueprint  
**Tooling Standard:** Astral `uv` (Fast Python Package & Project Manager)  
**Performance Principle:** Measured benchmarks and factual profiling. No unverified runtime speedup claims.

---

## 1. Objectives & Scope of `uv` Migration

JobPilot's backend currently manages dependencies using a standard `backend/requirements.txt` file and pip within Docker. While functional, this approach introduces:
- Non-deterministic builds across developer environments and Docker images due to unpinned transitive dependencies.
- Prolonged Docker container rebuild times (3 to 5 minutes) when packages are invalidated.
- Difficulty managing isolated dependency groups (e.g. testing libraries vs. core production code).

### 1.1 What `uv` Solves (and What It Does Not)
- **What `uv` Accelerates:**
  - **Dependency Resolution:** Resolves complex version constraints in milliseconds (written in Rust).
  - **Package Installation:** 10x to 100x faster installation via global content-addressable wheel caching and copy-on-write hardlinks.
  - **Reproducible Lockfiles:** Generates a universal, cryptographically pinned `uv.lock`.
  - **Docker Build Time:** Reduces container image assembly time through cache mounts.
- **What `uv` Does NOT Do:**
  - `uv` is a package and project manager, **not an alternative Python runtime or JIT compiler**. It does not accelerate raw Python execution speed, database query times, or network HTTP latencies.

---

## 2. Phased Migration Architecture: `pyproject.toml` & `uv.lock`

### 2.1 Proposed `pyproject.toml` Specification

```toml
[project]
name = "jobpilot"
version = "1.0.0"
description = "Intelligent IT career discovery, matching, and application-orchestration platform."
readme = "README.md"
requires-python = ">=3.11"
authors = [
    { name = "Yadava Krishna", email = "the owner account" }
]
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.6.0",
    "sqlalchemy>=2.0.36",
    "psycopg[binary]>=3.2.3",
    "alembic>=1.14.0",
    "pyjwt>=2.10.0",
    "argon2-cffi>=23.1.0",
    "cryptography>=44.0.0",
    "httpx>=0.28.0",
    "scrapling[fetchers]==0.5.1",
    "pymupdf>=1.25.0",
    "python-docx>=1.1.2",
    "reportlab>=4.2.5",
    "rapidfuzz>=3.10.0",
    "selectolax>=0.3.27",
    "dateparser>=1.2.0",
    "protego>=0.3.1",
    "openpyxl>=3.1.5",
]

[dependency-groups]
dev = [
    "ruff>=0.8.0",
    "mypy>=1.13.0",
]
test = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.28.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

---

## 3. Docker Multi-Stage Build Optimization with `uv`

To achieve high build performance and minimal final image size:

```dockerfile
# -------------------------------------------------------------
# Stage 1: Dependency Builder using official Astral uv
# -------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:0.5.1 AS uv_builder

FROM python:3.11-slim-bookworm AS builder

# Copy uv binary from the official image
COPY --from=uv_builder /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Cache mount preserves downloaded wheels across builds
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --no-dev

# -------------------------------------------------------------
# Stage 2: Final Production Runtime (Zero build tools included)
# -------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

# Non-root secure application user
RUN groupadd -g 10001 jobpilot && \
    useradd -u 10001 -g jobpilot -s /bin/bash -m jobpilot

# Copy virtual environment from builder stage
COPY --from=builder --chown=jobpilot:jobpilot /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application source code
COPY --chown=jobpilot:jobpilot ./backend /app/backend
COPY --chown=jobpilot:jobpilot ./core /app/core
COPY --chown=jobpilot:jobpilot ./discovery /app/discovery
COPY --chown=jobpilot:jobpilot ./intelligence /app/intelligence
COPY --chown=jobpilot:jobpilot ./platforms /app/platforms

USER jobpilot

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 4. Crawling Concurrency & Discovery Performance

### 4.1 Bounded Asynchronous Concurrency
- **Problem:** Uncontrolled crawling can saturate backend memory, trigger upstream IP rate limits, or degrade API responsiveness for users.
- **Solution:** Concurrency is bounded hierarchically:
  1. *Global Crawl Semaphore:* `asyncio.Semaphore(4)` ensures no more than 4 concurrent extraction processes execute on the host.
  2. *Per-Domain Token Bucket:* Every target host (e.g., `boards-api.greenhouse.io`, `api.lever.co`, `himalayas.app`) is governed by an independent rate limiter ($\le 10$ req/min).

### 4.2 Selective Browser Rendering
- **Rule:** Static HTTP fetching via Scrapling `Fetcher` is the mandatory default.
- **Headless Execution:** Headless browser rendering (`StealthyFetcher`) is invoked **only** if:
  1. The static HTTP response yields no structured text or JSON-LD.
  2. The page content explicitly contains `<noscript>You need to enable JavaScript to run this app</noscript>` or client-side single-page app mounting roots (`<div id="root"></div>` without initial HTML).

---

## 5. Durable PostgreSQL-Backed Task Queue (No Redis / RabbitMQ)

JobPilot avoids unnecessary operational overhead by utilizing PostgreSQL's native row-level locking for background task scheduling:

```sql
CREATE TABLE discovery_crawl_queue (
    id SERIAL PRIMARY KEY,
    source_id VARCHAR(50) NOT NULL,
    target_url VARCHAR(1000) NOT NULL,
    priority INTEGER DEFAULT 10,
    status VARCHAR(20) DEFAULT 'PENDING', -- PENDING, PROCESSING, COMPLETED, FAILED
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    scheduled_for TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_queue_claim ON discovery_crawl_queue(status, scheduled_for, priority DESC);
```

### 5.1 Atomic Worker Claim Pattern
Workers claim jobs transactionally without race conditions or locks blocking the entire table:

```sql
-- Atomically claim the highest-priority pending task
UPDATE discovery_crawl_queue
SET status = 'PROCESSING',
    started_at = NOW()
WHERE id = (
    SELECT id
    FROM discovery_crawl_queue
    WHERE status = 'PENDING' AND scheduled_for <= NOW()
    ORDER BY priority DESC, scheduled_for ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING *;
```

**Benefits:**
- **Zero Additional Containers:** Eliminates Redis, RabbitMQ, and Celery worker pods.
- **Transactional Consistency:** If a database transaction rolls back, the queue state rolls back atomically.
- **Crash Recovery:** Tasks stuck in `PROCESSING` for $>15$ minutes are automatically released back to `PENDING` by a heartbeat reaper.
