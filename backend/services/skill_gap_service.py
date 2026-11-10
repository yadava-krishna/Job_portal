"""Actionable Skill Gap Diagnostics & Learning Roadmap Engine.

Deterministic comparison between candidate profile skills and JD requirements.
Provides explainable gap categorization (proven, transferable, missing) and
constructs targeted, evidence-based learning paths with official documentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Technology equivalence / transferable skills graph
TRANSFERABLE_SKILLS: dict[str, list[str]] = {
    "fastapi": ["flask", "django", "express", "nestjs"],
    "django": ["fastapi", "flask", "rails", "laravel"],
    "flask": ["fastapi", "django"],
    "react": ["next.js", "vue", "angular"],
    "vue": ["react", "angular"],
    "postgresql": ["mysql", "sqlite", "mariadb"],
    "mysql": ["postgresql", "mariadb"],
    "aws": ["gcp", "azure"],
    "gcp": ["aws", "azure"],
    "azure": ["aws", "gcp"],
    "docker": ["kubernetes", "podman", "containerd"],
    "kubernetes": ["docker", "helm", "openshift"],
    "typescript": ["javascript"],
    "javascript": ["typescript"],
    "go": ["c++", "rust"],
}

# Verified learning resources and reference standards
OFFICIAL_LEARNING_RESOURCES: dict[str, dict[str, str]] = {
    "kubernetes": {
        "title": "Kubernetes Official Documentation & Interactive Tutorials",
        "url": "https://kubernetes.io/docs/home/",
        "est_hours": "20",
    },
    "docker": {
        "title": "Docker Get Started Guide & Multi-Stage Builds",
        "url": "https://docs.docker.com/get-started/",
        "est_hours": "10",
    },
    "fastapi": {
        "title": "FastAPI Tutorial - User Guide",
        "url": "https://fastapi.tiangolo.com/tutorial/",
        "est_hours": "12",
    },
    "react": {
        "title": "React Official Documentation (Learn React)",
        "url": "https://react.dev/learn",
        "est_hours": "25",
    },
    "postgresql": {
        "title": "PostgreSQL Documentation & SQL Indexing Best Practices",
        "url": "https://www.postgresql.org/docs/",
        "est_hours": "15",
    },
    "aws": {
        "title": "AWS Cloud Practitioner & Solutions Architect Essentials",
        "url": "https://aws.amazon.com/training/",
        "est_hours": "30",
    },
    "typescript": {
        "title": "TypeScript Handbook & Type System Deep Dive",
        "url": "https://www.typescriptlang.org/docs/handbook/intro.html",
        "est_hours": "15",
    },
    "redis": {
        "title": "Redis Documentation & Caching Architecture Patterns",
        "url": "https://redis.io/docs/",
        "est_hours": "8",
    },
    "terraform": {
        "title": "HashiCorp Terraform Documentation & Tutorials",
        "url": "https://developer.hashicorp.com/terraform/tutorials",
        "est_hours": "16",
    },
    "kafka": {
        "title": "Apache Kafka Quickstart & Event Streaming Design",
        "url": "https://kafka.apache.org/documentation/#quickstart",
        "est_hours": "18",
    },
}


@dataclass
class SkillGapReport:
    proven_skills: list[str] = field(default_factory=list)
    transferable_skills: list[dict[str, str]] = field(default_factory=list)
    missing_required_skills: list[str] = field(default_factory=list)
    missing_preferred_skills: list[str] = field(default_factory=list)
    learning_roadmap: list[dict[str, Any]] = field(default_factory=list)
    match_percentage: float = 0.0


class SkillGapService:
    """Evaluates skills and constructs deterministic learning roadmaps."""

    @classmethod
    def analyze_skill_gaps(
        cls, candidate_skills: list[str], required_skills: list[str], preferred_skills: list[str]
    ) -> SkillGapReport:
        candidate_norm = {s.lower().strip(): s for s in candidate_skills}

        proven: list[str] = []
        transferable: list[dict[str, str]] = []
        missing_req: list[str] = []
        missing_pref: list[str] = []

        # Check required skills
        for req in required_skills:
            req_lower = req.lower().strip()
            if req_lower in candidate_norm:
                proven.append(candidate_norm[req_lower])
            else:
                # Check transferable
                equivalent_found = False
                for equiv in TRANSFERABLE_SKILLS.get(req_lower, []):
                    if equiv in candidate_norm:
                        transferable.append({
                            "requested": req,
                            "candidate_has": candidate_norm[equiv],
                            "rationale": f"Demonstrated proficiency in {candidate_norm[equiv]} transfers to {req}.",
                        })
                        equivalent_found = True
                        break
                if not equivalent_found:
                    missing_req.append(req)

        # Check preferred skills
        for pref in preferred_skills:
            pref_lower = pref.lower().strip()
            if pref_lower in candidate_norm:
                proven.append(candidate_norm[pref_lower])
            else:
                missing_pref.append(pref)

        # Remove duplicates from proven
        proven = sorted(list(dict.fromkeys(proven)))

        # Build learning roadmap for missing skills
        roadmap: list[dict[str, Any]] = []
        for miss in missing_req + missing_pref[:3]:
            miss_lower = miss.lower().strip()
            resource = OFFICIAL_LEARNING_RESOURCES.get(
                miss_lower,
                {
                    "title": f"{miss} Official Developer Guide & Documentation",
                    "url": f"https://duckduckgo.com/?q={miss}+official+documentation",
                    "est_hours": "10-15",
                },
            )
            roadmap.append({
                "skill": miss,
                "importance": "High" if miss in missing_req else "Medium",
                "resource_title": resource["title"],
                "resource_url": resource["url"],
                "estimated_hours": resource["est_hours"],
            })

        total_targeted = len(required_skills) + (0.5 * len(preferred_skills))
        if total_targeted > 0:
            effective_matches = len(proven) + (0.7 * len(transferable))
            pct = min(100.0, round((effective_matches / total_targeted) * 100.0, 1))
        else:
            pct = 100.0

        return SkillGapReport(
            proven_skills=proven,
            transferable_skills=transferable,
            missing_required_skills=missing_req,
            missing_preferred_skills=missing_pref,
            learning_roadmap=roadmap,
            match_percentage=pct,
        )
