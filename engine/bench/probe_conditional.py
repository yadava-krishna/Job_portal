"""JPSE Phase 0: which ATS APIs support conditional requests, and what does connection reuse save?

Read-only. Makes ~6 requests per board to a few boards per ATS, sequentially, with JobPilot's identifiable user agent.
Run inside the backend container:  python /tmp/probe_conditional.py
"""
from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, "/app")
import httpx
from sqlalchemy import select

from backend.db import init_engine, session_factory
from backend.config import get_settings
from backend.models import Company
from backend.services.ats import ashby, greenhouse, lever, recruitee, smartrecruiters
from backend.services.ats.base import USER_AGENT

URLS = {
    "greenhouse": lambda c: (greenhouse.API.format(token=c.board_token), {"content": "true"}),
    "lever": lambda c: (lever.API.get(c.region, lever.API[None]).format(token=c.board_token), {"mode": "json"}),
    "ashby": lambda c: (ashby.API.format(token=c.board_token), {"includeCompensation": "true"}),
    "smartrecruiters": lambda c: (smartrecruiters.API.format(token=c.board_token), {"limit": 100, "offset": 0}),
    "recruitee": lambda c: (recruitee.API.format(token=c.board_token.lower()), None),
}

init_engine(get_settings().database_url)
db = session_factory()()
companies = db.execute(select(Company).where(Company.enabled.is_(True)).order_by(Company.id)).scalars().all()
by: dict[str, list[Company]] = {}
for c in companies:
    by.setdefault(c.ats, []).append(c)

H = {"User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Encoding": "gzip"}
report = {}
shared = httpx.Client(timeout=25, headers=H, follow_redirects=True)
for ats, lst in sorted(by.items()):
    rows = []
    for c in lst[:3]:
        url, params = URLS[ats](c)
        t = time.perf_counter(); r = shared.get(url, params=params); first = time.perf_counter() - t
        etag, lm = r.headers.get("etag"), r.headers.get("last-modified")
        cond = {}
        if etag:
            cond["If-None-Match"] = etag
        if lm:
            cond["If-Modified-Since"] = lm
        status2 = None
        if cond:
            r2 = shared.get(url, params=params, headers=cond); status2 = r2.status_code
        # connection reuse: 2 requests on a fresh client each vs the warm shared client
        t = time.perf_counter()
        for _ in range(2):
            with httpx.Client(timeout=25, headers=H) as fresh:
                fresh.get(url, params=params)
        cold = (time.perf_counter() - t) / 2
        t = time.perf_counter()
        for _ in range(2):
            shared.get(url, params=params)
        warm = (time.perf_counter() - t) / 2
        rows.append({"board": c.board_token, "status": r.status_code, "bytes": len(r.content), "first_s": round(first, 2),
                     "etag": bool(etag), "last_modified": bool(lm), "cache_control": r.headers.get("cache-control"),
                     "conditional_status": status2, "fresh_conn_s": round(cold, 2), "reused_conn_s": round(warm, 2)})
        time.sleep(0.5)
    report[ats] = rows
print(json.dumps(report, indent=1))
