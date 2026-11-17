"""JPSE Phase 3 acceptance benchmark: jp-searchd vs the PostgreSQL GIN baseline, on a scratch copy of live data.

  DATABASE_URL=postgresql+psycopg://...scratch...  JPSE_SEARCH_SOCKET=/path/searchd.sock  python engine/bench/search_bench.py

Measures latency (p50/p95/p99) at 1, 5 and 20 concurrent clients over a query mix built from real preference titles,
common roles and filter-only queries, and checks exact-filter agreement: for filter-only queries both engines must
return exactly the same set of postings.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.config import get_settings
from backend.db import init_engine, session_factory
from backend.services import search_engine as se

settings = get_settings()
assert "@postgres:" not in settings.database_url, "scratch databases only"
init_engine(settings.database_url)

ROLES = ["accounts receivable", "accounts payable", "order to cash", "collections analyst", "credit controller", "billing analyst",
         "fp&a analyst", "financial analyst", "data analyst", "devops engineer", "software engineer", "product manager",
         "investment specialist", "senior associate", "backend developer python", "react frontend", "sales development",
         "customer success", "hr generalist", "recruiter", "c++ developer", "machine learning engineer", "site reliability",
         "business analyst", "operations associate", "tax associate", "audit", "payroll", "treasury", "controller"]
FILTERS = [dict(), dict(countries=["IN"], remote_open_to=["IN", "*"]), dict(countries=["US"]), dict(work_modes=["Remote"]),
           dict(countries=["IN"], posted_within_days=30), dict(employment_types=["Full-time"], countries=["GB", "DE"])]
queries = [se.Query(terms=[r], limit=200, **f) for r in ROLES for f in FILTERS]
filter_only = [se.Query(limit=2000, **f) for f in FILTERS[1:]]
out: dict = {"queries": len(queries)}


def timed_engine(q):
    t = time.perf_counter(); se.engine_search(q); return (time.perf_counter() - t) * 1000


def timed_pg(q):
    db = session_factory()()
    try:
        t = time.perf_counter(); se.postgres_search(db, q); return (time.perf_counter() - t) * 1000
    finally:
        db.close()


def pct(xs):
    xs = sorted(xs)
    return {"p50": round(statistics.median(xs), 2), "p95": round(xs[int(len(xs) * .95) - 1], 2), "p99": round(xs[int(len(xs) * .99) - 1], 2),
            "max": round(xs[-1], 2)}


for name, fn in (("jp-searchd", timed_engine), ("postgres_gin", timed_pg)):
    for conc in (1, 5, 20):
        work = queries * (3 if conc > 1 else 1)
        with ThreadPoolExecutor(conc) as pool:
            t = time.perf_counter()
            lat = list(pool.map(fn, work))
            wall = time.perf_counter() - t
        out[f"{name}_c{conc}"] = {**pct(lat), "qps": round(len(work) / wall)}
        print(name, conc, out[f"{name}_c{conc}"], flush=True)

# exact filters: same sets
db = session_factory()()
agree = []
for q in filter_only:
    e = set(se.engine_search(q).ids)
    p = set(se.postgres_search(db, q).ids)
    agree.append({"filters": q.groups(), "posted_within_days": q.posted_within_days, "engine": len(e), "postgres": len(p),
                  "identical": e == p, "only_engine": sorted(e - p)[:5], "only_pg": sorted(p - e)[:5]})
out["filter_agreement"] = agree
print(json.dumps(agree, indent=1))
print("health", se.engine_health())
Path(__file__).with_name("search_results.json").write_text(json.dumps(out, indent=1))
