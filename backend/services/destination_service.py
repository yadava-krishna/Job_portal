"""Where an application is actually submitted: the canonical employer destination of a job.

A job can be discovered on one site (an aggregator, an alert e-mail, LinkedIn, Indeed, Naukri, a pasted link) and be
applied to on another (the employer's Greenhouse, Lever or Ashby form). Resolution order, strongest evidence first:

  1. the listing itself is a hosted Greenhouse/Lever/Ashby page (employer posting id in the URL);
  2. the same deduplicated job was also seen on the employer's ATS board (a job_source_links row whose key is the
     ATS board + posting id), including Greenhouse's hosted form for a job listed on the employer's own site;
  3. for listings on restricted platforms or aggregators: open postings in JobPilot's employer catalogue with the
     same employer and the same normalised title, and a compatible location. These are SUGGESTIONS ONLY: the user
     must confirm one ("same job") before it is used, and textual similarity is never treated as proof;
  4. otherwise the original listing stays the destination.

LinkedIn, Indeed and Naukri are never automated (their terms forbid it): they get a native hand-off.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Job, JobSourceLink
from backend.services import normalization

ATS_NAMES = {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby"}
RESTRICTED = (("LinkedIn", re.compile(r"(^|\.)linkedin\.com$")), ("Indeed", re.compile(r"(^|\.)indeed\.(com|co\.in|co\.uk|ca|de|fr|com\.au)$")),
              ("Naukri", re.compile(r"(^|\.)naukri(gulf)?\.com$")))
FILL_ON_PERMISSION = (("Workday", re.compile(r"(^|\.)(myworkdayjobs|myworkdaysite)\.com$")),
                      ("SmartRecruiters", re.compile(r"(^|\.)smartrecruiters\.com$")), ("iCIMS", re.compile(r"(^|\.)icims\.com$")),
                      ("SAP SuccessFactors", re.compile(r"(^|\.)(successfactors\.(com|eu)|sapsf\.(com|eu|cn))$")),
                      ("Oracle Taleo", re.compile(r"(^|\.)taleo\.net$")), ("Zoho Recruit", re.compile(r"(^|\.)zohorecruit\.(com|in|eu)$")),
                      ("Freshteam", re.compile(r"(^|\.)freshteam\.com$")), ("Darwinbox", re.compile(r"(^|\.)darwinbox\.(in|com)$")))
MAX_SUGGESTIONS = 3


def _host(url: str | None) -> str:
    try:
        return (urlsplit(url or "").hostname or "").lower()
    except ValueError:
        return ""


def restricted_platform(url: str | None) -> str | None:
    h = _host(url)
    return next((name for name, rx in RESTRICTED if rx.search(h)), None)


def _hosted_url(ats: str, board: str, jid: str, link_url: str | None) -> str | None:
    from backend.services.extension_service import job_ref

    if link_url and job_ref(link_url):
        return link_url
    if ats == "lever":
        return f"https://jobs.lever.co/{board}/{jid}"
    if ats == "ashby":
        return f"https://jobs.ashbyhq.com/{board}/{jid}"
    return None  # Greenhouse: only the probed hosted form (greenhouse_hosted_form) is trusted


def capabilities(kind: str, ats: str | None, platform_name: str | None) -> dict[str, Any]:
    if kind == "ats":
        return {"prepare": True, "autofill": True, "assisted_submit": True, "native_handoff": False, "verified_confirmation": True,
                "summary": f"JobPilot fills this {platform_name} form; you review it and confirm the submission."}
    if kind == "ats_permission":
        return {"prepare": True, "autofill": True, "assisted_submit": False, "native_handoff": False, "verified_confirmation": False,
                "summary": f"Smart Apply can fill this {platform_name} form once you allow the site in the extension. You submit it yourself."}
    if kind == "restricted":
        return {"prepare": True, "autofill": False, "assisted_submit": False, "native_handoff": True, "verified_confirmation": False,
                "summary": f"{platform_name}'s rules don't allow automated tools. Apply on {platform_name} with your answers ready to copy, "
                           "then tell JobPilot you applied."}
    return {"prepare": True, "autofill": False, "assisted_submit": False, "native_handoff": True, "verified_confirmation": False,
            "summary": "Apply on the employer's site with your prepared answers, then tell JobPilot you applied."}


def resolve(db: Session, job: Job, *, confirmed: dict[str, Any] | None = None, probe_hosted: bool = True) -> dict[str, Any]:
    from backend.services.extension_service import greenhouse_hosted_form, job_ref

    original = job.job_url or job.application_url
    out: dict[str, Any] = {"original_url": original, "source_platform": job.platform, "url": original, "kind": "employer_site",
                           "ats": None, "platform_name": job.platform, "verified": False, "evidence": [], "suggestions": [],
                           "confirmed_by_user": False}

    def ats_dest(url: str, ats: str, evidence: str) -> dict[str, Any]:
        out.update(url=url, kind="ats", ats=ats, platform_name=ATS_NAMES[ats], verified=True, evidence=[evidence])
        out["capabilities"] = capabilities("ats", ats, ATS_NAMES[ats])
        return out

    for candidate in (job.application_url, job.job_url):
        ref = job_ref(candidate) if candidate else None
        if ref:
            return ats_dest(candidate, ref[0], f"Employer posting {ref[2]} on {ATS_NAMES[ref[0]]} (board '{ref[1]}').")

    links = list(db.execute(select(JobSourceLink).where(JobSourceLink.job_id == job.id)).scalars())
    for link in links:
        parts = link.source_key.split(":")
        if link.source in ("lever", "ashby") and len(parts) == 3:
            url = _hosted_url(link.source, parts[1], parts[2], link.url)
            if url:
                return ats_dest(url, link.source, f"The same posting ({parts[2]}) is on the employer's {ATS_NAMES[link.source]} board.")
    if probe_hosted and any(l.source == "greenhouse" for l in links):
        hosted = greenhouse_hosted_form(job, links)
        if hosted:
            jid = re.search(r"token=(\d+)", hosted)
            return ats_dest(hosted, "greenhouse", f"Greenhouse hosts the application form for this posting ({jid.group(1) if jid else ''}).")

    if confirmed and confirmed.get("url"):
        ref = job_ref(confirmed["url"])
        if ref:
            ats_dest(confirmed["url"], ref[0], "You confirmed this is the same job on the employer's site.")
            out.update(confirmed_by_user=True, verified=False,
                       evidence=["You confirmed this is the same job on the employer's site.", *confirmed.get("evidence", [])])
            return out

    restricted = restricted_platform(original)
    host = _host(original)
    permission = next((name for name, rx in FILL_ON_PERMISSION if rx.search(host)), None)
    if restricted:
        out.update(kind="restricted", platform_name=restricted, capabilities=capabilities("restricted", None, restricted))
    elif permission:
        out.update(kind="ats_permission", platform_name=permission, verified=True,
                   evidence=[f"The listing is the employer's {permission} page."], capabilities=capabilities("ats_permission", None, permission))
    else:
        out.update(kind="employer_site", platform_name=job.platform or "the employer's site",
                   capabilities=capabilities("manual", None, job.platform))
    if restricted or job.source in ("adzuna", "alert_email", "browser_clipper", "user_job_url") or not original:
        out["suggestions"] = suggestions(db, job)
    return out


def suggestions(db: Session, job: Job) -> list[dict[str, Any]]:
    """Open catalogue postings that may be the same vacancy on the employer's ATS. Never applied automatically."""
    from backend.models import CataloguePosting
    from backend.services.extension_service import job_ref

    ck, tk = normalization.company_key(job.company), normalization.title_key(job.title)
    if not ck or not tk:
        return []
    rows = db.execute(select(CataloguePosting).where(CataloguePosting.closed_at.is_(None),
                                                     CataloguePosting.source.in_(tuple(ATS_NAMES)))
                      .where(CataloguePosting.company.ilike(f"%{job.company.split()[0][:40]}%")).limit(400)).scalars()
    out: list[dict[str, Any]] = []
    for p in rows:
        if normalization.company_key(p.company) != ck or normalization.title_key(p.title) != tk:
            continue
        loc = normalization.locations_compatible(job.location, p.location)
        remote = normalization.is_remote_text(job.location) or normalization.is_remote_text(p.location)
        if loc is False or (loc is None and job.location and p.location and not remote):
            continue  # different (or not comparable) cities: not offered as the same vacancy
        ref = job_ref(p.job_url or "")
        parts = p.source_key.split(":")
        url = p.job_url if ref else (_hosted_url(p.source, parts[1], parts[2], None) if len(parts) == 3 else None)
        if not url:
            continue
        evidence = ["Same employer name", "Same job title"]
        evidence.append("Same city" if loc else "Location could not be compared")
        if job.posted_at and p.posted_at and abs((job.posted_at - p.posted_at).days) <= 14:
            evidence.append("Posted within two weeks of each other")
        out.append({"url": url, "ats": p.source, "platform_name": ATS_NAMES[p.source], "company": p.company, "title": p.title,
                    "location": p.location, "posted_at": p.posted_at.isoformat() if p.posted_at else None, "evidence": evidence,
                    "strength": "strong" if loc and len(evidence) >= 4 else "possible", "posting_id": p.id})
    out.sort(key=lambda s: (s["strength"] != "strong", s["url"]))
    return out[:MAX_SUGGESTIONS]


def confirm_suggestion(db: Session, job: Job, url: str) -> dict[str, Any] | None:
    """The suggestion the user confirmed, re-checked: it must still be one of the current suggestions."""
    for s in suggestions(db, job):
        if s["url"] == url:
            return {"url": s["url"], "evidence": s["evidence"], "posting_id": s["posting_id"]}
    return None
