"""Turns raw records into normalised JobPosting objects."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from core import timeutil
from core.models import JobPosting, RawJobRecord
from core.skills import SkillTaxonomy
from discovery.deduplication import fingerprint, job_key
from intelligence.jd_analyzer import (
    EMPLOYMENT_TYPE_PATTERNS,
    WORK_MODE_PATTERNS,
    JDAnalyzer,
    detect_first,
    parse_experience,
    parse_posted_date,
    parse_salary,
)

if TYPE_CHECKING:
    from platforms.base_platform import BasePlatform

# Phrases that commonly indicate recruitment scams.
SCAM_PATTERNS = [
    r"registration\s+fee", r"pay\s+(?:a\s+)?(?:fee|deposit)", r"security\s+deposit", r"processing\s+fee",
    r"training\s+fee", r"whats\s*app\s+only", r"no\s+interview\s+required", r"earn\s+\d+.*per\s+day",
]


class JobExtractor:
    def __init__(self, adapter: "BasePlatform", taxonomy: SkillTaxonomy | None = None):
        self.adapter = adapter
        if taxonomy is None:
            from core.settings import PROJECT_ROOT

            taxonomy = SkillTaxonomy.from_file(
                adapter.settings.taxonomy_path if adapter.settings is not None else PROJECT_ROOT / "config" / "skills_taxonomy.yaml"
            )
        self.analyzer = JDAnalyzer(taxonomy)

    def to_posting(self, record: RawJobRecord) -> JobPosting:
        details = self.adapter.extract_job_details(record)
        description = self.adapter.extract_job_description(record)
        analysis = self.analyzer.analyze(description, title=details["title"])

        exp_min, exp_max, exp_text = parse_experience(record.experience)
        if exp_min is None:
            exp_min, exp_max, exp_text = analysis.exp_min, analysis.exp_max, analysis.experience_text
        sal_min, sal_max, sal_text = parse_salary(record.salary)
        if sal_min is None and sal_max is None:
            sal_min, sal_max, sal_text = analysis.salary_min_lpa, analysis.salary_max_lpa, analysis.salary_text

        work_mode = _norm_mode(record.work_mode) or detect_first(details["location"] or "", WORK_MODE_PATTERNS) or analysis.work_mode
        employment_type = detect_first(record.employment_type or "", EMPLOYMENT_TYPE_PATTERNS) or record.employment_type or analysis.employment_type

        flags: list[str] = []
        if details["url"] and not self.adapter.is_official_url(details["url"]):
            flags.append(f"URL is not on an official {self.adapter.platform} https domain")
        if not details["company"]:
            flags.append("Company name missing")
        for pattern in SCAM_PATTERNS:
            if description and re.search(pattern, description, re.I):
                flags.append(f"Possible recruitment-scam wording: '{re.search(pattern, description, re.I).group(0)}'")
        if record.extra.get("extraction_confidence") == "low":
            flags.append("Details extracted from an alert email with low confidence")

        key = job_key(self.adapter.platform, details["platform_job_id"], details["company"], details["title"], details["url"])
        return JobPosting(
            job_key=key,
            platform=self.adapter.platform,
            platform_job_id=details["platform_job_id"],
            company=details["company"],
            title=details["title"],
            url=details["url"],
            location=details["location"],
            work_mode=work_mode,
            employment_type=employment_type,
            experience_required=record.experience or exp_text,
            exp_min_years=exp_min,
            exp_max_years=exp_max,
            salary_range=record.salary or sal_text,
            salary_min_lpa=sal_min,
            salary_max_lpa=sal_max,
            posted_date=parse_posted_date(record.posted_date, timeutil.today()),
            description=description,
            required_skills=analysis.required_skills,
            preferred_skills=analysis.preferred_skills,
            education_requirements=analysis.education,
            mandatory_qualifications=analysis.mandatory_qualifications,
            application_method=details["application_method"],
            source=record.source,
            screening_questions=record.screening_questions,
            cover_letter_required=record.cover_letter_required if record.cover_letter_required is not None else (analysis.mentions_cover_letter or None),
            fingerprint=fingerprint(details["company"], details["title"]),
            verification_flags=flags,
        )


def _norm_mode(value: str | None) -> str | None:
    if not value:
        return None
    return detect_first(value, WORK_MODE_PATTERNS) or value.strip()
