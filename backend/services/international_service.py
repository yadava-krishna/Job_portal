"""International mobility: countries, visa routes with sourced rules, country fit, saved routes and official-source
change monitoring.

Everything here is informational and links to the official government page. Routes start as `unverified`
(summaries were written from the official pages but not re-checked by a person in JobPilot); a route becomes
`stale` after its review date, and a changed official page is flagged to everyone watching that route. JobPilot
never states fees, salary thresholds or processing times: those change too often. Not legal advice.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (CandidateProfile, Country, JobPreference, Notification, User, VisaRoute, VisaRule, VisaWatch,
                            utcnow)

DATA = Path(__file__).resolve().parents[1] / "data" / "visa_routes.json"
REVIEW_DAYS = 90
NOTICE = ("General information only, not legal or immigration advice and not a prediction of approval. Rules change: "
          "always confirm on the official page before you act.")
USER_AGENT = "JobPilot/2.0 (+private job-search assistant; official source check)"
EDU_RANK = {"none": 0, "diploma": 1, "bachelor": 2, "master": 3, "doctorate": 4}


def seed(db: Session) -> int:
    data = json.loads(DATA.read_text())
    have_c = {c.code for c in db.execute(select(Country)).scalars()}
    for c in data["countries"]:
        if c["code"] not in have_c:
            db.add(Country(**c))
    have_r = {(r.country_code, r.code) for r in db.execute(select(VisaRoute)).scalars()}
    n = 0
    for r in data["routes"]:
        if (r["country_code"], r["code"]) in have_r:
            continue
        route = VisaRoute(country_code=r["country_code"], code=r["code"], name=r["name"], summary=r["summary"],
                          requires_sponsorship=r.get("requires_sponsorship"), source_url=r["source_url"], confidence="unverified",
                          review_by=(utcnow() + timedelta(days=REVIEW_DAYS)).date())
        for rule in r.get("rules", []):
            route.rules.append(VisaRule(kind=rule["kind"], description=rule["description"], value=rule.get("value") or {},
                                        source_url=r["source_url"]))
        db.add(route)
        n += 1
    db.commit()
    return n


def _ensure(db: Session) -> None:
    if db.execute(select(Country.id).limit(1)).first() is None:
        seed(db)


def _freshness(r: VisaRoute) -> str:
    if r.review_by and r.review_by < utcnow().date():
        return "stale"
    return r.confidence


def route_out(r: VisaRoute, watching: bool = False) -> dict[str, Any]:
    return {"id": r.id, "country_code": r.country_code, "code": r.code, "name": r.name, "summary": r.summary,
            "requires_sponsorship": r.requires_sponsorship, "source_url": r.source_url, "confidence": _freshness(r),
            "verified_at": r.verified_at, "last_checked_at": r.last_checked_at, "review_by": r.review_by,
            "source_changed_at": r.source_changed_at, "watching": watching, "notice": NOTICE,
            "rules": [{"kind": x.kind, "description": x.description, "source_url": x.source_url} for x in r.rules]}


def countries(db: Session) -> list[dict[str, Any]]:
    _ensure(db)
    routes = db.execute(select(VisaRoute)).scalars().all()
    count = {}
    for r in routes:
        count[r.country_code] = count.get(r.country_code, 0) + 1
    return [{"code": c.code, "name": c.name, "region": c.region, "currency": c.currency, "official_source_url": c.official_source_url,
             "routes": count.get(c.code, 0)} for c in db.execute(select(Country).order_by(Country.name)).scalars()]


def routes(db: Session, user: User, country: str | None = None) -> list[dict[str, Any]]:
    _ensure(db)
    q = select(VisaRoute)
    if country:
        q = q.where(VisaRoute.country_code == country.upper())
    watched = {w.route_id for w in db.execute(select(VisaWatch).where(VisaWatch.user_id == user.id)).scalars()}
    return [route_out(r, r.id in watched) for r in db.execute(q.order_by(VisaRoute.country_code, VisaRoute.name)).scalars()]


def _education_level(conf: dict[str, Any]) -> str | None:
    text = " ".join(f"{e.get('degree') or ''}" for e in conf.get("education") or []).lower()
    if not text.strip():
        return None
    if re.search(r"ph\.?d|doctor", text):
        return "doctorate"
    if re.search(r"\bm\.?\s?(com|sc|tech|a|ba)\b|master|mba|\bmca\b", text):
        return "master"
    if re.search(r"\bb\.?\s?(com|sc|tech|e|a|ba|ca)\b|bachelor|\bbca\b|graduat", text):
        return "bachelor"
    if re.search(r"diploma", text):
        return "diploma"
    return None


def country_fit(db: Session, user: User, country: str) -> dict[str, Any]:
    _ensure(db)
    c = db.execute(select(Country).where(Country.code == country.upper())).scalar_one_or_none()
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Country not in the catalogue yet")
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    conf = (prof.confirmed_profile if prof else None) or {}
    years = round((prof.experience_months or 0) / 12, 1) if prof else 0
    edu = _education_level(conf)
    langs = [x.lower() for x in conf.get("languages") or []]
    prefs = db.execute(select(JobPreference).where(JobPreference.user_id == user.id)).scalar_one_or_none()
    authorised = c.code in [a.upper() for a in ((prefs.work_authorization if prefs else None) or [])]
    watched = {w.route_id for w in db.execute(select(VisaWatch).where(VisaWatch.user_id == user.id)).scalars()}
    out_routes = []
    for r in db.execute(select(VisaRoute).where(VisaRoute.country_code == c.code)).scalars():
        strengths, gaps, unknown = [], [], []
        for rule in r.rules:
            v = rule.value or {}
            if rule.kind == "education" and v.get("min_education"):
                need = EDU_RANK[v["min_education"]]
                if edu is None:
                    unknown.append("Education level couldn't be read from your profile.")
                elif EDU_RANK[edu] >= need:
                    strengths.append(f"Your education ({edu}) meets the general level ({v['min_education']}).")
                else:
                    gaps.append(f"Generally needs a {v['min_education']} degree; your profile shows {edu}.")
            elif rule.kind == "experience" and v.get("min_years"):
                (strengths if years >= v["min_years"] else gaps).append(
                    f"{years:g} years of experience vs a general minimum of {v['min_years']}.")
            elif rule.kind == "language" and v.get("language"):
                wanted = [x.strip().lower() for x in re.split(r" or |,", v["language"])]
                if any(w in langs for w in wanted):
                    strengths.append(f"You list {v['language']} — a test result is usually still required.")
                else:
                    unknown.append(f"{v['language']} language evidence (test results) isn't in your profile.")
            elif rule.kind == "sponsorship" and v.get("job_offer_required"):
                unknown.append("Needs a job offer from an eligible employer: filter jobs by sponsorship 'verified'.")
            elif rule.kind == "salary":
                unknown.append("A salary threshold applies: compare your offer with the official page.")
        out_routes.append({**route_out(r, r.id in watched), "fit": {"strengths": strengths, "gaps": gaps, "unknown": unknown,
                                                   "summary": "Possible pathway" if not gaps else "Gaps to close first"}})
    return {"country": {"code": c.code, "name": c.name, "official_source_url": c.official_source_url},
            "already_authorised": authorised, "profile_used": {"years_experience": years, "education": edu, "languages": conf.get("languages") or []},
            "routes": out_routes, "notice": NOTICE,
            "relocation_tips": ["Search with your target country selected and sponsorship 'verified' first.",
                                "Ask recruiters early whether the role offers visa sponsorship and relocation support.",
                                "Prepare documents the routes usually need: degree certificates, experience letters, passport."]}


def watch(db: Session, user: User, route_id: int, on: bool) -> None:
    r = db.get(VisaRoute, route_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Route not found")
    w = db.execute(select(VisaWatch).where(VisaWatch.user_id == user.id, VisaWatch.route_id == route_id)).scalar_one_or_none()
    if on and w is None:
        db.add(VisaWatch(user_id=user.id, route_id=route_id))
    elif not on and w is not None:
        db.delete(w)
    db.commit()


def _page_fingerprint(html: str) -> str:
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(text.encode()).hexdigest()


def check_sources(db: Session, fetch=None) -> dict[str, int]:
    """visa_source_check + visa_change_detection: fetch each official page, compare a text fingerprint with the last
    one, flag changes to watchers, and mark routes stale after their review date."""
    _ensure(db)
    out = {"checked": 0, "changed": 0, "failed": 0, "stale": 0}

    def default_fetch(url: str) -> str:
        with httpx.Client(timeout=25, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as c:
            r = c.get(url)
            r.raise_for_status()
            return r.text

    fetch = fetch or default_fetch
    for r in db.execute(select(VisaRoute)).scalars().all():
        try:
            fp = _page_fingerprint(fetch(r.source_url))
        except Exception:
            out["failed"] += 1
            continue
        out["checked"] += 1
        r.last_checked_at = utcnow()
        if r.source_hash and fp != r.source_hash:
            out["changed"] += 1
            r.source_changed_at = utcnow()
            if r.confidence == "verified":
                r.confidence = "unverified"  # a person needs to re-check it
            for w in db.execute(select(VisaWatch).where(VisaWatch.route_id == r.id)).scalars():
                db.add(Notification(user_id=w.user_id, kind="source_change", title=f"{r.name}: the official page changed",
                                    body="Review the official page before relying on this route.", link="/international",
                                    dedupe_key=f"visa:{r.id}:{fp[:12]}"))
        r.source_hash = fp
        if r.review_by and r.review_by < utcnow().date():
            out["stale"] += 1
    db.commit()
    return out
