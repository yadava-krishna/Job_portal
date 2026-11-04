"""LinkedIn adapter (assisted mode).

LinkedIn offers no job-search or apply API to individual job seekers (its Job
Posting / Apply Connect APIs are for approved ATS partners), and its User
Agreement prohibits bots and scraping. This adapter therefore:
  * reads job links from the candidate's own LinkedIn job-alert emails and
    from jobs the candidate imports,
  * parses job IDs from LinkedIn URLs for deduplication,
  * builds pre-filtered search URLs for manual review,
  * leaves submission (including Easy Apply) to the candidate.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, quote_plus, urlsplit

from core.models import Platform
from core.settings import SearchConfig
from platforms.base_platform import AccessCapabilities, BasePlatform, SearchLink

_JOB_VIEW_RE = re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(?:[^/?#]*?-)?(\d{6,})", re.I)

# f_WT: 1 on-site, 2 remote, 3 hybrid.  f_JT: F full-time, C contract.  f_E: 2 entry, 3 associate, 4 mid-senior.
_WORK_MODE = {"On-site": "1", "Remote": "2", "Hybrid": "3"}
_JOB_TYPE = {"Full-time": "F", "Contract": "C", "Part-time": "P", "Temporary": "T", "Internship": "I"}


class LinkedInPlatform(BasePlatform):
    platform = Platform.LINKEDIN
    official_domains = ("linkedin.com",)
    capabilities = AccessCapabilities(
        automated_search=False,
        automated_apply=False,
        discovery_channels=("email_alert", "import_inbox"),
        application_method="Manual on LinkedIn (Easy Apply or company site) by the candidate",
        notes="LinkedIn job data and apply APIs are partner-only; automated access by third-party tools is not permitted.",
    )

    def identify_job_id(self, url: str | None) -> str | None:
        if not url:
            return None
        m = _JOB_VIEW_RE.search(url)
        if m:
            return m.group(1)
        try:
            qs = parse_qs(urlsplit(url).query)
        except ValueError:
            return None
        for key in ("currentJobId", "jobId"):
            if qs.get(key) and qs[key][0].isdigit():
                return qs[key][0]
        return None

    def canonical_url(self, job_id: str) -> str | None:
        return f"https://www.linkedin.com/jobs/view/{job_id}/" if job_id.isdigit() else None

    def build_search_links(self, criteria: SearchConfig) -> list[SearchLink]:
        lo, hi = self.experience_band(criteria)
        levels = sorted({"2" if y < 2 else "3" if y < 5 else "4" for y in (lo, hi)} | ({"3", "4"} if lo < 5 <= hi else set()))
        hours = criteria.posted_within_hours
        job_types = ",".join(_JOB_TYPE[t] for t in criteria.employment_types if t in _JOB_TYPE)
        links: list[SearchLink] = []
        for location in criteria.locations:
            remote = self.is_remote_location(location)
            modes = ["Remote"] if remote else [m for m in criteria.work_modes if m != "Remote"] or criteria.work_modes
            wt = ",".join(_WORK_MODE[m] for m in modes if m in _WORK_MODE)
            loc = "India" if remote else self.city_of(location)
            for title in criteria.job_titles:
                url = (
                    "https://www.linkedin.com/jobs/search/?keywords=" + quote_plus(title)
                    + "&location=" + quote_plus(loc)
                    + f"&f_TPR=r{hours * 3600}"
                    + (f"&f_WT={quote_plus(wt)}" if wt else "")
                    + (f"&f_JT={quote_plus(job_types)}" if job_types else "")
                    + (f"&f_E={quote_plus(','.join(levels))}" if levels else "")
                    + "&sortBy=DD"
                )
                links.append(SearchLink(self.platform, title, location, url))
        return links
