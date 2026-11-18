"""JPSE Phase 4 quality gate: do jp-searchd's candidates contain every posting JobPilot's exact saved-search rules accept?

For every enabled saved search (titles, related roles, prefix rule, location), over every fresh board snapshot in the
catalogue: exact = postings passing title_ok and location_ok (the full scan); candidates = the engine's title-only query.
Recall must be 100%: the exact rules run on the candidates afterwards, so a miss is a lost job, an extra is only work.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from datetime import date

from sqlalchemy import select

from backend.config import get_settings
from backend.db import init_engine, session_factory
from backend.models import CrawlState, SavedSearch, User
from backend.services import saved_search_service as sss
from backend.services.crawler import catalogue
from backend.services.crawler import service as crawler

init_engine(get_settings().database_url)
assert "@postgres:" not in get_settings().database_url, "scratch databases only"
db = session_factory()()
today = date.today()
report = []
for row in db.execute(select(SavedSearch).where(SavedSearch.enabled.is_(True))).scalars():
    user = db.get(User, row.user_id)
    crit = sss.criteria_for(db, user, row)
    if not crit.title_sets:
        continue
    companies = sss._companies(db, user, crit.c)
    t0 = time.perf_counter()
    exact: dict[int, str] = {}
    scanned = 0
    for c in companies:
        st = db.execute(select(CrawlState).where(CrawlState.target_key == crawler.board_key(c))).scalar_one_or_none()
        if st is None or st.last_success_at is None:
            continue
        res, ids = catalogue.board_result(db, st, c)
        scanned += len(ids)
        for pid, nj in zip(ids, res.jobs):
            if crit.title_ok(nj.title) and crit.location_ok(nj) and not (nj.expires_at and nj.expires_at < today):
                exact[pid] = nj.title
    scan_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    cands = sss._engine_candidates(crit, companies)
    engine_s = time.perf_counter() - t1
    missed = {pid: t for pid, t in exact.items() if cands is not None and pid not in cands}
    report.append({"search": row.id, "user": row.user_id, "titles": crit.titles, "families": crit.families, "boards": len(companies),
                   "scanned": scanned, "exact": len(exact), "candidates": None if cands is None else len(cands),
                   "recall": None if cands is None else (1 - len(missed) / len(exact) if exact else 1.0),
                   "missed": list(missed.values())[:10], "full_scan_s": round(scan_s, 2), "engine_s": round(engine_s, 3)})
    print(json.dumps(report[-1]), flush=True)
Path(__file__).with_name("recall_results.json").write_text(json.dumps(report, indent=1))
