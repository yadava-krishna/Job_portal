# JobPilot backend: FastAPI + the existing automation modules (resume, discovery, intelligence, reports...).
# Build context is the repository root.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY requirements.txt /tmp/req-core.txt
COPY backend/requirements.txt /tmp/req-backend.txt
RUN grep -v '^pytest' /tmp/req-core.txt > /tmp/req-core-runtime.txt \
 && pip install -r /tmp/req-core-runtime.txt -r /tmp/req-backend.txt

# Application code: the existing modules are reused as-is.
COPY core ./core
COPY config/skills_taxonomy.yaml ./config/skills_taxonomy.yaml
COPY resume ./resume
COPY platforms ./platforms
COPY discovery ./discovery
COPY intelligence ./intelligence
COPY applications ./applications
COPY database ./database
COPY reports ./reports
COPY backend ./backend

RUN useradd --create-home --uid 10001 jobpilot && mkdir -p /data && chown jobpilot:jobpilot /data
USER jobpilot
ENV STORAGE_DIR=/data ENVIRONMENT=production
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready', timeout=4); sys.exit(0 if r.status==200 else 1)"

# Apply migrations, then serve. One worker: in-process scheduler and auth rate limiter.
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
