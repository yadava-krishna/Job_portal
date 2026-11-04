"""Stable identifiers for jobs and duplicate detection."""

from __future__ import annotations

import hashlib
import re

from core.models import Platform
from core.skills import normalize_text
from platforms.base_platform import strip_tracking

_COMPANY_SUFFIXES = re.compile(
    r"\b(private|pvt|limited|ltd|llp|llc|inc|incorporated|corp|corporation|co|company|india|technologies|technology|solutions|services|global)\b"
)


def normalize_company(name: str | None) -> str:
    n = normalize_text(name)
    n = _COMPANY_SUFFIXES.sub(" ", n)
    return " ".join(n.split())


def normalize_title(title: str | None) -> str:
    n = normalize_text(title)
    n = re.sub(r"\b(sr|senior)\b", "senior", n)
    n = re.sub(r"\b(jr|junior)\b", "junior", n)
    n = re.sub(r"\b(i|ii|iii|1|2|3)\b$", "", n)
    return " ".join(n.split())


def job_key(platform: Platform, job_id: str | None, company: str | None, title: str | None, url: str | None) -> str:
    """platform + job ID; otherwise a hash of normalised company, title and URL."""
    p = platform.value.lower()
    if job_id:
        return f"{p}:{job_id.strip().lower()}"
    basis = "|".join([normalize_company(company), normalize_title(title), strip_tracking(url).lower() if url else ""])
    if not basis.strip("|"):
        raise ValueError("cannot build a job key without an ID, company, title or URL")
    return f"{p}:h:{hashlib.sha1(basis.encode()).hexdigest()[:16]}"


def fingerprint(company: str | None, title: str | None) -> str:
    """Platform-independent identity used to detect the same job on several platforms."""
    c, t = normalize_company(company), normalize_title(title)
    return f"{c}|{t}" if c and t else ""
