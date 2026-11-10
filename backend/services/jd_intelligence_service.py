"""Deterministic Job Description (JD) Intelligence & Requirement Extraction.

Zero-LLM implementation using compiled regular expressions, keyword graphs,
and structured pattern recognition to extract actionable qualifications,
seniority, required skills, and nice-to-have technologies from raw job descriptions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Tech skill catalog categorized for IT industry roles
TECH_SKILL_PATTERNS: dict[str, list[str]] = {
    "languages": [
        "python", "javascript", "typescript", "java", "golang", "go", "c\\+\\+", "c#", "rust",
        "ruby", "php", "scala", "kotlin", "swift", "sql", "bash", "shell"
    ],
    "frameworks": [
        "fastapi", "django", "flask", "react", "next\\.js", "vue", "angular", "node\\.js",
        "express", "spring boot", "spring", "asp\\.net", "rails", "laravel", "nestjs",
        "tailwind", "bootstrap", "graphql", "rest"
    ],
    "cloud_devops": [
        "aws", "azure", "gcp", "docker", "kubernetes", "k8s", "terraform", "ansible",
        "helm", "ci/cd", "github actions", "gitlab ci", "jenkins", "argocd", "prometheus",
        "grafana", "linux"
    ],
    "databases": [
        "postgresql", "postgres", "mysql", "mongodb", "redis", "elasticsearch", "cassandra",
        "dynamodb", "sqlite", "snowflake", "bigquery", "kafka", "rabbitmq"
    ],
    "architecture_concepts": [
        "microservices", "event-driven", "system design", "distributed systems", "api design",
        "clean architecture", "oop", "tdd", "ci/cd", "performance optimization", "concurrency"
    ],
}

SENIORITY_KEYWORDS: dict[str, list[str]] = {
    "PRINCIPAL": ["principal", "staff", "distinguished", "architect", "fellow"],
    "LEAD": ["tech lead", "team lead", "lead engineer", "lead developer", "engineering lead"],
    "SENIOR": ["senior", "sr\\.", "sr ", "lead", "iv", "iii"],
    "MID": ["mid-level", "mid level", "software engineer ii", "developer ii", "intermediate"],
    "ENTRY": ["junior", "jr\\.", "entry level", "associate", "graduate", "fresher", "intern"],
}

EDUCATION_PATTERNS: list[tuple[str, str]] = [
    (r"\b(ph\.?d|doctorate)\b", "Doctorate"),
    (r"\b(m\.?tech|m\.?s|master'?s|mca)\b", "Master's"),
    (r"\b(b\.?tech|b\.?e|bachelor'?s|bca|b\.?s)\b", "Bachelor's"),
    (r"\b(diploma)\b", "Diploma"),
]

WORK_AUTH_PATTERNS: list[tuple[str, str]] = [
    (r"must be (a )?citizen of india|authorized to work in india|indian citizen", "India Only"),
    (r"us citizen(ship)? required|security clearance required", "US Clearance Required"),
    (r"visa sponsorship available|sponsorship provided", "Sponsorship Available"),
    (r"no visa sponsorship|unable to sponsor", "No Sponsorship"),
]


@dataclass
class JDAnalysisResult:
    title: str
    seniority: str
    min_years_exp: float
    max_years_exp: float | None
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    education_level: str | None = None
    work_authorization: str | None = None
    is_remote: bool = False
    hard_disqualifiers: list[str] = field(default_factory=list)
    extracted_metadata: dict[str, Any] = field(default_factory=dict)


class JDIntelligenceService:
    """Extracts structured requirements and qualifications from job descriptions deterministically."""

    @classmethod
    def analyze_jd(cls, title: str, description: str, raw_location: str = "") -> JDAnalysisResult:
        full_text = f"{title}\n{raw_location}\n{description}".lower()

        # 1. Experience extraction
        min_exp, max_exp = cls._extract_experience_years(description)

        # 2. Seniority detection
        seniority = cls._detect_seniority(title, full_text, min_exp)

        # 3. Education extraction
        education = cls._extract_education(description)

        # 4. Work authorization
        work_auth = cls._extract_work_authorization(description)

        # 5. Remote detection
        is_remote = bool(re.search(r"\b(remote|work from home|wfh|anywhere in india)\b", full_text))

        # 6. Skill extraction (differentiating required vs preferred sections)
        req_skills, pref_skills = cls._extract_skills_by_section(description)

        # 7. Check for hard disqualifiers
        disqualifiers = []
        if work_auth and "US Clearance Required" in work_auth:
            disqualifiers.append("US Security Clearance required")

        return JDAnalysisResult(
            title=title,
            seniority=seniority,
            min_years_exp=min_exp,
            max_years_exp=max_exp,
            required_skills=req_skills,
            preferred_skills=pref_skills,
            education_level=education,
            work_authorization=work_auth,
            is_remote=is_remote,
            hard_disqualifiers=disqualifiers,
            extracted_metadata={
                "tech_count": len(req_skills) + len(pref_skills),
                "has_education_req": education is not None,
                "has_exp_req": min_exp > 0,
            }
        )

    @staticmethod
    def _extract_experience_years(text: str) -> tuple[float, float | None]:
        """Extracts minimum and maximum years of required experience."""
        # Pattern like: 5-8 years, 3 to 5 yrs, 5+ years, 4+ yrs experience
        range_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)", text, re.IGNORECASE)
        if range_match:
            try:
                min_val = float(range_match.group(1))
                max_val = float(range_match.group(2))
                return min_val, max_val
            except (ValueError, TypeError):
                pass

        plus_match = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", text, re.IGNORECASE)
        if plus_match:
            try:
                min_val = float(plus_match.group(1))
                return min_val, None
            except (ValueError, TypeError):
                pass

        min_keyword_match = re.search(r"minimum(?:\s+of)?\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)", text, re.IGNORECASE)
        if min_keyword_match:
            try:
                return float(min_keyword_match.group(1)), None
            except (ValueError, TypeError):
                pass

        return 0.0, None

    @classmethod
    def _detect_seniority(cls, title: str, full_text: str, min_exp: float) -> str:
        for level, keywords in SENIORITY_KEYWORDS.items():
            for kw in keywords:
                if re.search(r"\b" + kw + r"\b", title.lower()):
                    return level

        # Fallback to experience-based seniority
        if min_exp >= 10.0:
            return "PRINCIPAL"
        if min_exp >= 7.0:
            return "LEAD"
        if min_exp >= 5.0:
            return "SENIOR"
        if min_exp >= 2.0:
            return "MID"
        return "ENTRY"

    @staticmethod
    def _extract_education(text: str) -> str | None:
        for pattern, degree in EDUCATION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return degree
        return None

    @staticmethod
    def _extract_work_authorization(text: str) -> str | None:
        for pattern, auth_type in WORK_AUTH_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return auth_type
        return None

    @classmethod
    def _extract_skills_by_section(cls, text: str) -> tuple[list[str], list[str]]:
        """Splits description into required and preferred sections and extracts skills."""
        req_section = ""
        pref_section = ""

        # Identify preferred section
        pref_split = re.split(r"(?:preferred|nice to have|good to have|bonus points|plus points|desirable)[\s\w]*:", text, flags=re.IGNORECASE)
        if len(pref_split) > 1:
            req_section = pref_split[0]
            pref_section = pref_split[1]
        else:
            req_section = text

        def extract_from_chunk(chunk: str) -> list[str]:
            found: set[str] = set()
            for cat, keywords in TECH_SKILL_PATTERNS.items():
                for kw in keywords:
                    pattern = r"(?<![a-zA-Z0-9_])" + kw + r"(?![a-zA-Z0-9_])"
                    if re.search(pattern, chunk, re.IGNORECASE):
                        # clean up escape chars for clean display
                        clean_name = kw.replace("\\.", ".").replace("\\+", "+").strip()
                        found.add(clean_name.capitalize() if len(clean_name) > 3 else clean_name.upper())
            return sorted(list(found))

        req_skills = extract_from_chunk(req_section)
        pref_skills = [s for s in extract_from_chunk(pref_section) if s not in req_skills]

        # If everything fell into req, balance reasonable tech keywords
        if not pref_skills and len(req_skills) > 6:
            # First 6 core, remaining as preferred
            pref_skills = req_skills[6:]
            req_skills = req_skills[:6]

        return req_skills, pref_skills
