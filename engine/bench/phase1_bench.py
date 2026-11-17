"""JPSE Phase 0/1 benchmark against a scratch copy of the live database (never production).

  DATABASE_URL=postgresql+psycopg://...scratch... STORAGE_DIR=/tmp/... python engine/bench/phase1_bench.py

1. full crawl of every board and feed into the catalogue (cold: no ETags yet);
2. immediate re-crawl of everything (warm: ETags sent, most boards answer 304);
3. "Discover" for each user with saved searches, served from the catalogue (no board fetches);
4. PostgreSQL GIN full-text baseline over the catalogue (blueprint §9).
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import func, select, text

from backend.config import get_settings
from backend.db import init_engine, session_factory
from backend.models import CataloguePosting, CrawlState, DiscoveryRun, SavedSearch, User, utcnow
from backend.services import discovery_service, saved_search_service
from backend.services.ats import board_cache
from backend.services.crawler import service as crawler

settings = get_settings()
init_engine(settings.database_url)
assert "55432" not in settings.database_url and "@postgres:" not in settings.database_url, "scratch databases only"
db = session_factory()()
out: dict = {}


def force_due():
    db.query(CrawlState).update({CrawlState.next_due_at: utcnow() - timedelta(minutes=1), CrawlState.cooldown_until: None})
    db.commit()


for label in ("cold", "warm"):
    force_due()
    t = time.perf_counter()
    rep = crawler.crawl(db, budget_s=900)
    rep["wall_s"] = round(time.perf_counter() - t, 1)
    out[f"crawl_{label}"] = rep
    print(label, rep, flush=True)

out["catalogue"] = {
    "postings_open": db.scalar(select(func.count()).select_from(CataloguePosting).where(CataloguePosting.closed_at.is_(None))),
    "postings_total": db.scalar(select(func.count()).select_from(CataloguePosting)),
    "targets": dict(db.execute(select(CrawlState.last_status, func.count()).group_by(CrawlState.last_status)).all()),
}
print("catalogue", out["catalogue"], flush=True)

board_cache.clear()
runs = []
for uid in db.execute(select(SavedSearch.user_id).where(SavedSearch.enabled.is_(True)).distinct()).scalars():
    user = db.get(User, uid)
    run = discovery_service.start_run(db, user, "manual", ["all"])
    t = time.perf_counter()
    run = saved_search_service.run_all(db, settings, user, run)
    runs.append({"user": uid, "seconds": round(time.perf_counter() - t, 2), "status": run.status, "found": run.jobs_found,
                 "new": run.jobs_new, "summary": (run.summary or "")[:160]})
    print("discover", runs[-1], flush=True)
out["discover_from_catalogue"] = runs

queries = ["accounts & receivable", "collections", "order & cash", "credit & control", "billing & analyst", "finance & analyst",
           "data & analyst", "software & engineer", "product & manager", "accountant"]
fts = ("setweight(to_tsvector('simple', coalesce(title, '')), 'A') || setweight(to_tsvector('simple', coalesce(company, '')), 'B') || "
       "setweight(to_tsvector('simple', coalesce(location, '')), 'C')")
lat = []
for _ in range(5):
    for q in queries:
        t = time.perf_counter()
        db.execute(text(f"SELECT id FROM catalogue_postings WHERE closed_at IS NULL AND {fts} @@ to_tsquery('simple', :q) "
                        f"ORDER BY ts_rank({fts}, to_tsquery('simple', :q)) DESC LIMIT 200"), {"q": q}).all()
        lat.append((time.perf_counter() - t) * 1000)
lat.sort()
out["gin_baseline_ms"] = {"n": len(lat), "p50": round(statistics.median(lat), 2), "p95": round(lat[int(len(lat) * 0.95) - 1], 2),
                          "max": round(lat[-1], 2)}
print("gin", out["gin_baseline_ms"], flush=True)
Path(__file__).with_name("phase1_results.json").write_text(json.dumps(out, indent=1, default=str))
