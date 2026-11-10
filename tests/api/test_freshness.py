"""Unit tests for job freshness scoring and expired listing reaper."""

from __future__ import annotations

from datetime import date, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db import Base
from backend.models import Job, utcnow
from backend.services.discovery_service import calculate_freshness, reap_expired_jobs


def test_calculate_freshness_values():
    today = date(2026, 11, 6)

    # 1. Undated posting -> 0.70 baseline
    assert calculate_freshness(None, reference_date=today) == 0.70

    # 2. Today / yesterday -> 1.0
    assert calculate_freshness(today, reference_date=today) == 1.0
    assert calculate_freshness(today - timedelta(days=1), reference_date=today) == 1.0

    # 3. 5 days ago -> 0.85
    assert calculate_freshness(today - timedelta(days=5), reference_date=today) == 0.85

    # 4. 12 days ago -> 0.70
    assert calculate_freshness(today - timedelta(days=12), reference_date=today) == 0.70

    # 5. 25 days ago -> 0.50
    assert calculate_freshness(today - timedelta(days=25), reference_date=today) == 0.50

    # 6. 45 days ago -> 0.30
    assert calculate_freshness(today - timedelta(days=45), reference_date=today) == 0.30

    # 7. 90 days ago -> 0.15
    assert calculate_freshness(today - timedelta(days=90), reference_date=today) == 0.15


def test_reap_expired_jobs_sqlite():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        # Create fresh job
        fresh_job = Job(
            job_key="fresh:1",
            platform="greenhouse",
            company="Acme",
            title="Junior Dev",
            source="ats",
            posted_at=date.today() - timedelta(days=5),
            freshness_score=0.85,
            is_expired=False,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        # Create stale job (60 days old)
        stale_job = Job(
            job_key="stale:2",
            platform="lever",
            company="Legacy Corp",
            title="Senior Dev",
            source="ats",
            posted_at=date.today() - timedelta(days=60),
            freshness_score=0.30,
            is_expired=False,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.add_all([fresh_job, stale_job])
        db.commit()

        # Run reaper with cutoff of 45 days
        reaped = reap_expired_jobs(db, max_age_days=45)
        assert reaped == 1

        db.refresh(fresh_job)
        db.refresh(stale_job)

        assert fresh_job.is_expired is False
        assert stale_job.is_expired is True
        assert stale_job.closed_at is not None
        assert stale_job.freshness_score == 0.05
