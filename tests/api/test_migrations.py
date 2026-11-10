"""Migration safety on PostgreSQL: data survives upgrade, downgrade and re-upgrade; the schema matches the models.

Runs only when TEST_POSTGRES_URL points at a disposable database (it drops the public schema).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PG = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not PG, reason="needs TEST_POSTGRES_URL (disposable PostgreSQL)")

V2_TABLES = {"invites", "audit_logs", "job_sources", "notifications", "notification_prefs", "user_activity_sessions",
             "job_views", "ai_calls", "extension_tokens", "interviews", "offers", "application_contacts",
             "saved_searches", "user_achievements"}
V3_TABLES = {"companies", "user_companies", "job_source_links"}
V4_TABLES = {"source_connectors", "user_career_urls"}


def _alembic(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "alembic", "-c", str(ROOT / "backend" / "alembic.ini"), *args],
                   check=True, env={**os.environ, "DATABASE_URL": PG}, capture_output=True)


@pytest.fixture
def engine():
    from sqlalchemy import create_engine, text

    eng = create_engine(PG)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    yield eng
    eng.dispose()


def _seed_v1(conn) -> None:
    from sqlalchemy import text

    conn.execute(text("""
        INSERT INTO users (id, email, password_hash, full_name, is_active, created_at, updated_at)
        VALUES (1, 'existing@example.com', 'argon2-hash', 'Existing User', true, now(), now())"""))
    conn.execute(text("""
        INSERT INTO resumes (id, user_id, original_filename, stored_path, sha256, size_bytes, page_count, is_active, uploaded_at)
        VALUES (1, 1, 'cv.pdf', 'users/1/resumes/x.pdf', repeat('a', 64), 1000, 2, true, now())"""))
    for i, (posted, src) in enumerate([("2026-11-01", "platform_api"), ("2026-11-02", "alert_email"),
                                       (None, None), ("2026-11-03", "user_provided"), ("2026-11-03", "something_else")], 1):
        conn.execute(text("""
            INSERT INTO jobs (id, job_key, platform, company, title, description_is_snippet, required_skills, preferred_skills,
                              education_requirements, mandatory_qualifications, screening_questions, verification_flags,
                              posted_at, posted_at_source, source, created_at, updated_at)
            VALUES (:id, :key, 'linkedin', 'Acme', 'Analyst', false, '[]', '[]', '[]', '[]', '[]', '[]',
                    :posted, :src, 'clip', '2026-11-01T10:00:00+00', now())"""),
                     {"id": i, "key": f"k{i}", "posted": posted, "src": src})
    conn.execute(text("""
        INSERT INTO applications (id, user_id, job_id, status, screening_answers, checklist, notes, created_at, updated_at)
        VALUES (1, 1, 1, 'SUBMITTED', '[]', '[]', 'keep me', now(), now())"""))
    conn.execute(text("""
        INSERT INTO discovery_runs (id, user_id, trigger, sources, started_at, status, jobs_found, jobs_new, jobs_matched,
                                    duplicates, error_details, platform_stats)
        VALUES (1, 1, 'manual', '[]', now(), 'completed', 5, 5, 1, 0, '[]', '{}')"""))


def _v1_snapshot(conn) -> dict:
    from sqlalchemy import text

    q = lambda sql: [tuple(r) for r in conn.execute(text(sql))]  # noqa: E731
    return {
        "users": q("SELECT id, email, password_hash, full_name, is_active FROM users ORDER BY id"),
        "resumes": q("SELECT id, user_id, stored_path, sha256 FROM resumes ORDER BY id"),
        "jobs": q("SELECT id, job_key, posted_at, posted_at_source, created_at FROM jobs ORDER BY id"),
        "applications": q("SELECT id, user_id, job_id, status, notes FROM applications ORDER BY id"),
        "discovery_runs": q("SELECT id, user_id, status, jobs_found FROM discovery_runs ORDER BY id"),
    }


def test_0002_upgrade_downgrade_preserves_data(engine):
    from sqlalchemy import inspect, text

    _alembic("upgrade", "0001")
    with engine.begin() as conn:
        _seed_v1(conn)
        before = _v1_snapshot(conn)

    _alembic("upgrade", "0002")
    with engine.begin() as conn:
        assert _v1_snapshot(conn) == before
        assert conn.execute(text("SELECT role FROM users WHERE id = 1")).scalar() == "user"
        conf = dict(conn.execute(text("SELECT id, posted_at_confidence FROM jobs")).all())
        assert conf == {1: "verified", 2: "estimated", 3: "unknown", 4: "verified", 5: "unknown"}
        assert conn.execute(text("SELECT count(*) FROM jobs WHERE discovered_at = created_at")).scalar() == 5
    assert V2_TABLES <= set(inspect(engine).get_table_names())

    _alembic("downgrade", "0001")
    with engine.begin() as conn:
        assert _v1_snapshot(conn) == before
    insp = inspect(engine)
    assert not V2_TABLES & set(insp.get_table_names())
    assert "role" not in {c["name"] for c in insp.get_columns("users")}

    _alembic("upgrade", "0002")
    with engine.begin() as conn:
        assert _v1_snapshot(conn) == before


V3_TABLES = {"companies", "user_companies", "job_source_links"}


def test_0003_backfills_links_and_keys_and_downgrades_cleanly(engine):
    from sqlalchemy import inspect, text

    from backend.services.normalization import canonical_url, dedup_key

    _alembic("upgrade", "0001")
    with engine.begin() as conn:
        _seed_v1(conn)
        conn.execute(text("UPDATE jobs SET job_url = 'https://www.linkedin.com/jobs/view/42/?trk=abc', company = 'Acme Technologies Pvt Ltd', "
                          "title = 'Sr. Accounts Receivable Analyst' WHERE id = 1"))
        before = _v1_snapshot(conn)
    _alembic("upgrade", "0002")
    _alembic("upgrade", "0003")
    with engine.begin() as conn:
        assert _v1_snapshot(conn) == before
        links = conn.execute(text("SELECT job_id, source, platform, source_key FROM job_source_links ORDER BY job_id")).all()
        assert [(l[0], l[1], l[2], l[3]) for l in links] == [(i, "clip", "linkedin", f"clip:k{i}") for i in range(1, 6)]
        row = conn.execute(text("SELECT dedup_key, canonical_url FROM jobs WHERE id = 1")).one()
        # The migration's frozen rules agree with the application's normaliser.
        assert row == (dedup_key("Acme Technologies Pvt Ltd", "Sr. Accounts Receivable Analyst"),
                       canonical_url("https://www.linkedin.com/jobs/view/42/?trk=abc"))
        assert row[0] == "acme|senior accounts receivable analyst" and row[1] == "linkedin.com/jobs/view/42"
    assert V3_TABLES <= set(inspect(engine).get_table_names())

    _alembic("downgrade", "0002")
    with engine.begin() as conn:
        assert _v1_snapshot(conn) == before
    assert not V3_TABLES & set(inspect(engine).get_table_names())
    assert "dedup_key" not in {c["name"] for c in inspect(engine).get_columns("jobs")}
    _alembic("upgrade", "head")


def test_migrated_schema_matches_models(engine):
    """Alembic autogenerate finds no difference between the migrated database and the ORM models."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    import backend.models  # noqa: F401
    from backend.db import Base

    _alembic("upgrade", "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == []
