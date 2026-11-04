"""One job schema for every source, plus the helpers that make sources comparable.

Every discovery path (official ATS boards, Adzuna, alert emails, the browser clipper, URL and file imports)
produces a NormalizedJob; ingestion, deduplication and matching only ever see this type.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core import timeutil
from core.models import JobPosting
from core.skills import normalize_text
from intelligence.jd_analyzer import JDAnalyzer

# Posting-date provenance, strongest first. Only these count as "verified" for date filters.
VERIFIED_DATE_SOURCES = ("platform_api", "platform_page", "user_provided")
ESTIMATED_DATE_SOURCES = ("alert_email",)
DATE_SOURCE_RANK = {"platform_api": 4, "platform_page": 3, "user_provided": 2, "alert_email": 1, None: 0}

ATS_SOURCES = ("greenhouse", "lever", "ashby")
SOURCE_PLATFORM = {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby", "adzuna_api": "Adzuna"}


@dataclass
class NormalizedJob:
    source: str                      # greenhouse | lever | ashby | adzuna_api | alert_email | browser_clipper | user_job_url | file_import
    source_key: str                  # stable per source, e.g. "greenhouse:razorpay:4745511005"
    platform: str                    # display platform: Greenhouse, Lever, Ashby, Adzuna, LinkedIn, Indeed, Naukri
    company: str
    title: str
    job_key: str | None = None       # legacy unique key (CLI JobPosting.job_key); defaults to source_key
    external_job_id: str | None = None
    location: str | None = None
    locations: list[str] = field(default_factory=list)
    work_mode: str | None = None     # Remote | Hybrid | On-site
    employment_type: str | None = None  # Full-time | Part-time | Contract | Internship | Temporary
    experience_required: str | None = None
    experience_min: float | None = None
    experience_max: float | None = None
    salary_range: str | None = None
    salary_min_lpa: float | None = None
    salary_max_lpa: float | None = None
    description: str | None = None   # plain text, never HTML
    description_is_snippet: bool = False
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    education_requirements: list[str] = field(default_factory=list)
    mandatory_qualifications: list[str] = field(default_factory=list)
    screening_questions: list[str] = field(default_factory=list)
    verification_flags: list[str] = field(default_factory=list)
    job_url: str | None = None
    application_method: str | None = None
    posted_at: date | None = None
    posted_at_source: str | None = None
    industry: str | None = None
    department: str | None = None
    company_id: int | None = None
    fingerprint: str | None = None   # legacy CLI fingerprint, kept for reports

    @property
    def key(self) -> str:
        return self.job_key or self.source_key

    @property
    def canonical_url(self) -> str | None:
        return canonical_url(self.job_url)

    @property
    def dedup_key(self) -> str | None:
        return dedup_key(self.company, self.title)

    def job_columns(self) -> dict[str, Any]:
        """Columns for backend.models.Job (identity and dates are handled by the ingest service)."""
        return dict(
            platform=self.platform, external_job_id=self.external_job_id, fingerprint=self.fingerprint, company=self.company or "",
            title=self.title or "", location=self.location, work_mode=self.work_mode, employment_type=self.employment_type,
            experience_required=self.experience_required, experience_min=self.experience_min, experience_max=self.experience_max,
            salary_range=self.salary_range, salary_min_lpa=self.salary_min_lpa, salary_max_lpa=self.salary_max_lpa,
            description=self.description, required_skills=self.required_skills, preferred_skills=self.preferred_skills,
            education_requirements=self.education_requirements, mandatory_qualifications=self.mandatory_qualifications,
            screening_questions=self.screening_questions, verification_flags=self.verification_flags, job_url=self.job_url,
            application_method=self.application_method, source=self.source, canonical_url=self.canonical_url,
            dedup_key=self.dedup_key, industry=self.industry, department=self.department, company_id=self.company_id,
        )


# ---- posting dates -------------------------------------------------------------------------

def posted_confidence(posted_at: date | None, source: str | None) -> str:
    """verified | estimated | unknown. Mirrors the backfill in migration 0002."""
    if posted_at is None:
        return "unknown"
    if source in VERIFIED_DATE_SOURCES:
        return "verified"
    return "estimated" if source in ESTIMATED_DATE_SOURCES else "unknown"


def parse_timestamp(value: Any) -> datetime | None:
    """ISO-8601 string or epoch milliseconds → aware datetime; None for anything unparseable."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def local_date(value: Any) -> date | None:
    """The calendar date of a timestamp in the portal's timezone (what "posted today" means to the user)."""
    dt = parse_timestamp(value)
    return dt.astimezone(timeutil.tz()).date() if dt else None


# ---- text ------------------------------------------------------------------------------------

_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "header", "footer"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(value: str | None) -> str:
    """Plain text from (possibly entity-escaped) HTML. Markup is dropped, never rendered."""
    if not value:
        return ""
    raw = html.unescape(value) if "&lt;" in value else value
    p = _TextExtractor()
    p.feed(raw)
    p.close()
    text = "".join(p.parts).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    out: list[str] = []
    for line in lines:
        if line in ("", "-"):
            if out and out[-1] != "":
                out.append("")
            continue
        out.append(line)
    return "\n".join(out).strip()


# ---- vocabularies ----------------------------------------------------------------------------

def work_mode(*values: Any) -> str | None:
    for v in values:
        n = normalize_text(str(v)) if v is not None else ""
        if not n:
            continue
        if "hybrid" in n:
            return "Hybrid"
        if "remote" in n:
            return "Remote"
        if n in ("onsite", "on site", "in office", "office") or "on site" in n or "onsite" in n:
            return "On-site"
    return None


def employment_type(value: Any) -> str | None:
    n = normalize_text(str(value)) if value else ""
    n = n.replace(" ", "")
    if not n:
        return None
    if "intern" in n:
        return "Internship"
    if "contract" in n or "freelance" in n or "consult" in n:
        return "Contract"
    if "temp" in n:
        return "Temporary"
    if "parttime" in n:
        return "Part-time"
    if "fulltime" in n or "permanent" in n or "regular" in n:
        return "Full-time"
    return None


# ---- locations -------------------------------------------------------------------------------

_CITY_ALIASES = {
    "bangalore": "bengaluru", "bengaluru": "bengaluru", "gurgaon": "gurugram", "gurugram": "gurugram", "bombay": "mumbai",
    "mumbai": "mumbai", "new delhi": "delhi", "delhi": "delhi", "ncr": "delhi ncr", "delhi ncr": "delhi ncr", "noida": "noida",
    "madras": "chennai", "chennai": "chennai", "calcutta": "kolkata", "kolkata": "kolkata", "hyderabad": "hyderabad",
    "secunderabad": "hyderabad", "pune": "pune", "ahmedabad": "ahmedabad", "kochi": "kochi", "cochin": "kochi",
    "trivandrum": "thiruvananthapuram", "thiruvananthapuram": "thiruvananthapuram", "mysore": "mysuru", "mysuru": "mysuru",
    "jaipur": "jaipur", "chandigarh": "chandigarh", "coimbatore": "coimbatore", "indore": "indore",
}
_REMOTE_FRIENDLY = ("india", "anywhere", "worldwide", "global", "apac", "asia")
_LOC_SPLIT = re.compile(r"\s*(?:;|\||/|\bor\b|\band\b)\s*")


def split_locations(*values: Any) -> list[str]:
    out: list[str] = []
    for v in values:
        items = v if isinstance(v, (list, tuple)) else [v]
        for item in items:
            if not item:
                continue
            for part in _LOC_SPLIT.split(str(item)):
                part = part.strip(" ,")
                if part and part.lower() not in (o.lower() for o in out):
                    out.append(part)
    return out


def location_tokens(location: str | None) -> set[str]:
    """Canonical city names mentioned in a location string (aliases folded)."""
    n = normalize_text(location)
    if not n:
        return set()
    found = {canon for alias, canon in _CITY_ALIASES.items() if re.search(rf"\b{re.escape(alias)}\b", n)}
    if "delhi ncr" in found:
        found |= {"delhi", "gurugram", "noida"}
    return found


def is_remote_text(location: str | None) -> bool:
    return "remote" in normalize_text(location)


def remote_ok_for_india(location: str | None) -> bool:
    """A remote role open to someone in India: no location, or one naming India/anywhere/APAC."""
    n = normalize_text(location)
    stripped = n.replace("remote", "").strip()
    return not stripped or any(k in n for k in _REMOTE_FRIENDLY)


def locations_compatible(a: str | None, b: str | None) -> bool | None:
    """True/False when both sides name cities; None when either side has no recognisable city."""
    ta, tb = location_tokens(a), location_tokens(b)
    if not ta or not tb:
        return None
    return bool(ta & tb)


# ---- identity --------------------------------------------------------------------------------

_COMPANY_NOISE = re.compile(
    r"\b(private|pvt|limited|ltd|llp|llc|inc|incorporated|corp|corporation|co|company|india|technologies|technology|"
    r"solutions|services|global|software|labs|group|holdings|the)\b"
)
_TITLE_NOISE = re.compile(r"\b(m f d|f m d|all genders|immediate joiner[s]?|urgent(ly)? hiring|hiring|wfh|work from home)\b")


def company_key(name: str | None) -> str:
    n = _COMPANY_NOISE.sub(" ", normalize_text(name))
    return " ".join(n.split())


def title_key(title: str | None) -> str:
    n = normalize_text(title)
    n = re.sub(r"\b(sr|senior)\b", "senior", n)
    n = re.sub(r"\b(jr|junior)\b", "junior", n)
    n = _TITLE_NOISE.sub(" ", n)
    return " ".join(n.split())


def dedup_key(company: str | None, title: str | None) -> str | None:
    c, t = company_key(company), title_key(title)
    return f"{c}|{t}"[:400] if c and t else None


_KEEP_QUERY = {"gh_jid", "jk", "jobid", "job_id", "id", "currentjobid", "vjk"}


def canonical_url(url: str | None) -> str | None:
    """Scheme-less, lower-case host, no tracking query, no fragment or trailing slash. Job-ID params are kept."""
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if not parts.netloc:
        return None
    host = parts.netloc.lower().removeprefix("www.")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if k.lower() in _KEEP_QUERY))
    path = re.sub(r"/+", "/", parts.path).rstrip("/")
    return urlunsplit(("", host, path, query, "")).lstrip("/")[:1000]


# ---- analysis & converters -----------------------------------------------------------------

def enrich(job: NormalizedJob, analyzer: JDAnalyzer) -> NormalizedJob:
    """Fill skills, experience, work mode, employment type and salary from the description when the source lacks them."""
    if not job.description:
        return job
    a = analyzer.analyze(job.description, title=job.title)
    job.required_skills = job.required_skills or a.required_skills
    job.preferred_skills = job.preferred_skills or a.preferred_skills
    job.education_requirements = job.education_requirements or a.education
    job.mandatory_qualifications = job.mandatory_qualifications or a.mandatory_qualifications
    if job.experience_min is None and job.experience_max is None:
        job.experience_min, job.experience_max, job.experience_required = a.exp_min, a.exp_max, a.experience_text
    job.work_mode = job.work_mode or a.work_mode
    job.employment_type = job.employment_type or a.employment_type
    if job.salary_min_lpa is None and job.salary_max_lpa is None and a.salary_text:
        job.salary_min_lpa, job.salary_max_lpa, job.salary_range = a.salary_min_lpa, a.salary_max_lpa, job.salary_range or a.salary_text
    return job


def from_posting(p: JobPosting, posted_at: date | None, posted_source: str | None, *, snippet: bool, source: str) -> NormalizedJob:
    """The CLI's JobPosting (clipper, URL/file import, alert emails) → NormalizedJob. The legacy job_key is preserved."""
    platform = SOURCE_PLATFORM.get(source, p.platform.value)
    return NormalizedJob(
        source=source, source_key=f"{source}:{p.job_key}", job_key=p.job_key, platform=platform, company=p.company or "",
        title=p.title or "", external_job_id=p.platform_job_id, location=p.location, locations=split_locations(p.location),
        work_mode=p.work_mode, employment_type=p.employment_type, experience_required=p.experience_required,
        experience_min=p.exp_min_years, experience_max=p.exp_max_years, salary_range=p.salary_range,
        salary_min_lpa=p.salary_min_lpa, salary_max_lpa=p.salary_max_lpa, description=p.description, description_is_snippet=snippet,
        required_skills=p.required_skills, preferred_skills=p.preferred_skills, education_requirements=p.education_requirements,
        mandatory_qualifications=p.mandatory_qualifications, screening_questions=p.screening_questions,
        verification_flags=p.verification_flags, job_url=p.url, application_method=p.application_method,
        posted_at=posted_at, posted_at_source=posted_source if posted_at else None, fingerprint=p.fingerprint or None,
    )
