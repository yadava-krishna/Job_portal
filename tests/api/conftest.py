from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from support import SYNTHETIC_RESUME_LINES, make_pdf  # noqa: E402



def _fresh_postgres(url: str) -> None:
    """Reset the test Postgres database and apply the Alembic migrations (exercises the real schema)."""
    import subprocess

    from sqlalchemy import create_engine, text

    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    eng.dispose()
    subprocess.run([sys.executable, "-m", "alembic", "-c", str(ROOT / "backend" / "alembic.ini"), "upgrade", "head"],
                   check=True, env={**os.environ, "DATABASE_URL": url}, capture_output=True)


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    # TEST_POSTGRES_URL runs the API suite against PostgreSQL + Alembic instead of SQLite.
    pg = os.environ.get("TEST_POSTGRES_URL")
    if pg:
        _fresh_postgres(pg)
    monkeypatch.setenv("DATABASE_URL", pg or f"sqlite:///{tmp_path / 'portal.db'}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("JWT_SECRET", "test-secret-" + "x" * 40)
    monkeypatch.setenv("LLM_PROVIDER", "rule_based")
    monkeypatch.setenv("AUTH_RATE_LIMIT_PER_MINUTE", "1000")
    monkeypatch.delenv("REGISTRATION_INVITE_CODE", raising=False)
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    from backend.config import get_settings
    from backend.security import rate_limiter

    get_settings.cache_clear()
    rate_limiter.reset()
    yield tmp_path
    get_settings.cache_clear()


@pytest.fixture
def client(app_env):
    from fastapi.testclient import TestClient

    from backend.main import create_app

    with TestClient(create_app(start_scheduler=False)) as c:
        yield c


@pytest.fixture
def resume_bytes(tmp_path) -> bytes:
    return make_pdf(tmp_path / "r.pdf", SYNTHETIC_RESUME_LINES).read_bytes()


