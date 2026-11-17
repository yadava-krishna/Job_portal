"""JPSE Phase 3: search every catalogued posting (all permitted boards and feeds), not only the jobs in your feed.

Answers come from jp-searchd when JPSE_SEARCH=on, from PostgreSQL otherwise (shadow mode also asks the engine and logs
how well the two agree). Filters are exact: an unknown country or mode matches nothing, never everything.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from backend.api.deps import CurrentUser, DbSession
from backend.models import CataloguePosting
from backend.services import search_engine

router = APIRouter(prefix="/catalogue", tags=["catalogue"])


class CatalogueHit(BaseModel):
    id: int
    title: str
    company: str
    location: str | None = None
    country: str | None = None
    remote_scope: list[str] | None = None
    work_mode: str | None = None
    employment_type: str | None = None
    salary: str | None = None
    posted_at: date | None = None
    job_url: str | None = None
    source: str
    score: float | None = None


class CatalogueSearchOut(BaseModel):
    items: list[CatalogueHit]
    engine: str
    took_ms: float


def _salary(p: CataloguePosting) -> str | None:
    from types import SimpleNamespace

    from backend.services.normalization import salary_label

    return salary_label(SimpleNamespace(salary_currency=p.salary_currency, salary_min=p.salary_min, salary_max=p.salary_max,
                                        salary_period=p.salary_period, salary_period_assumed=False))


@router.get("/search", response_model=CatalogueSearchOut)
def search(user: CurrentUser, db: DbSession,
           q: str | None = Query(None, max_length=200, description="Words to look for: titles, skills, companies"),
           country: list[str] = Query([], max_length=10), remote_open_to: list[str] = Query([], max_length=10),
           work_mode: list[str] = Query([], max_length=3), employment_type: list[str] = Query([], max_length=5),
           posted_within_days: int | None = Query(None, ge=1, le=365),
           salary_currency: str | None = Query(None, min_length=3, max_length=3), salary_min: float | None = Query(None, gt=0),
           salary_unknown_ok: bool = False, all_terms: bool = False, limit: int = Query(50, ge=1, le=100)) -> CatalogueSearchOut:
    query = search_engine.Query(terms=[q] if q and q.strip() else [], countries=[c.upper() for c in country],
                                remote_open_to=[c.upper() if c != "*" else c for c in remote_open_to], work_modes=work_mode,
                                employment_types=employment_type, posted_within_days=posted_within_days,
                                salary_currency=salary_currency.upper() if salary_currency else None, salary_min=salary_min,
                                salary_unknown_ok=salary_unknown_ok, all_terms=all_terms, limit=limit)
    res = search_engine.search(db, query)
    rows = {p.id: p for p in db.execute(select(CataloguePosting).where(CataloguePosting.id.in_(res.ids))).scalars()} if res.ids else {}
    scores = dict(zip(res.ids, res.scores)) if res.scores else {}
    items = [CatalogueHit(id=p.id, title=p.title, company=p.company, location=p.location_normalized or p.location, country=p.country,
                          remote_scope=p.remote_scope, work_mode=p.work_mode, employment_type=p.employment_type, salary=_salary(p),
                          posted_at=p.posted_at, job_url=p.job_url, source=p.source, score=scores.get(p.id))
             for i in res.ids if (p := rows.get(i)) is not None and p.closed_at is None]  # in ranked order; one batch query
    return CatalogueSearchOut(items=items, engine=res.engine, took_ms=round(res.took_ms, 2))
