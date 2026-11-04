"""Screening answers from verified candidate information only.

Personal-commitment questions (salary, CTC, notice period, relocation, work
authorization, start date, shifts...) are answered only from values the candidate
has confirmed in config/candidate_profile.json. Anything that cannot be answered
from the resume or those facts is returned as NEEDS_CANDIDATE_INPUT.
"""

from __future__ import annotations

import re
from typing import Any

from core.models import NEEDS_CANDIDATE_INPUT
from core.skills import SkillTaxonomy
from resume.profile_builder import current_role

DEFAULT_QUESTIONS = [
    "Total years of experience",
    "Current location",
    "Highest qualification",
    "Current employer and designation",
    "Current CTC",
    "Expected CTC",
    "Notice period",
    "Willing to relocate?",
]

# (category, pattern, verified-fact key). Order matters: first match wins.
_SENSITIVE = [
    ("expected_ctc", r"expect\w*\s+(ctc|salary|compensation|pay)|salary\s+expectation|desired\s+(salary|pay)", "expected_ctc"),
    ("current_ctc", r"current\s+(ctc|salary|compensation|pay)|\bctc\b|present\s+salary|annual\s+salary|salary", "current_ctc"),
    ("notice_period", r"notice\s+period|how\s+soon|serving\s+notice|last\s+working\s+day", "notice_period"),
    ("start_date", r"start\s+date|join(ing)?\s+date|when\s+can\s+you\s+(start|join)|availability\s+to\s+join|available\s+to\s+(start|join)", "earliest_start_date"),
    ("relocation", r"relocat", "willing_to_relocate"),
    ("work_authorization", r"authori[sz]ed\s+to\s+work|work\s+(authori[sz]ation|permit)|visa|sponsorship|citizen", "work_authorization"),
    ("shift", r"\bshift|night|rotational|us\s+hours|uk\s+hours", "shift_flexibility"),
]
_PERSONAL_NEVER = r"\b(gender|age|date\s+of\s+birth|dob|marital|religion|caste|disabilit|pan\b|aadhaar|passport\s+number|bank)"


class ScreeningAnswerer:
    def __init__(self, profile: dict[str, Any], verified_facts: dict[str, Any], taxonomy: SkillTaxonomy):
        self.profile = profile
        self.facts = {k: v for k, v in (verified_facts or {}).items() if v not in (None, "")}
        self.taxonomy = taxonomy

    def answer_all(self, questions: list[str]) -> list[dict[str, str]]:
        qs = questions or DEFAULT_QUESTIONS
        return [self.answer(q) for q in qs]

    def answer(self, question: str) -> dict[str, str]:
        q = question.strip()
        ql = q.lower()

        if re.search(_PERSONAL_NEVER, ql):
            return _needs(q, "personal/legal information is never answered automatically")

        for category, pattern, fact_key in _SENSITIVE:
            if re.search(pattern, ql):
                if fact_key in self.facts:
                    return {"question": q, "answer": _fmt(self.facts[fact_key]), "source": f"verified_facts.{fact_key}", "status": "ANSWERED"}
                return _needs(q, f"{category.replace('_', ' ')} must be confirmed by the candidate")

        te = self.profile["total_experience"]
        if re.search(r"(total|overall|how many)\s+(years|yrs)|years\s+of\s+(total\s+)?experience|total\s+experience", ql) and not self._mentions_skill(q):
            return {
                "question": q,
                "answer": f"{te['years']:g} years ({te['years_months']}), calculated from employment dates on the resume",
                "source": "resume employment dates",
                "status": "ANSWERED",
            }
        if re.search(r"current(ly)?\s+(location|city|based)|where\s+are\s+you\s+(based|located)|^current location", ql):
            loc = self.profile.get("contact", {}).get("location")
            return {"question": q, "answer": loc, "source": "resume header", "status": "ANSWERED"} if loc else _needs(q, "location not on resume")
        if re.search(r"qualification|education|degree", ql):
            edu = self.profile.get("education") or []
            if edu and edu[0].get("degree"):
                e = edu[0]
                parts = [e["degree"], e.get("institution"), e.get("university"), str(e["year"]) if e.get("year") else None]
                return {"question": q, "answer": ", ".join(p for p in parts if p), "source": "resume education", "status": "ANSWERED"}
            return _needs(q, "education not parsed from resume")
        if re.search(r"current\s+(employer|company|organi[sz]ation|designation|role|title)|currently\s+work", ql):
            role = current_role(self.profile)
            if role and role.get("is_current"):
                return {"question": q, "answer": f"{role['title']} at {role['company']} (since {role['start']})", "source": "resume experience", "status": "ANSWERED"}
            return _needs(q, "no current role on resume")

        # "Do you have experience with X?" -> only "Yes" with evidence; never "No".
        skill = self._mentions_skill(q)
        if skill and re.search(r"experience|worked|familiar|knowledge|hands[\s-]on|used|do you have", ql) and not re.search(r"how many|rate|scale|level|proficien", ql):
            evidence = self._evidence(skill)
            if evidence:
                return {"question": q, "answer": f"Yes - resume: \"{evidence}\"", "source": "resume text", "status": "ANSWERED_FROM_RESUME"}
        return _needs(q, "cannot be answered from verified information")

    def _mentions_skill(self, q: str) -> str | None:
        hits = self.taxonomy.find(q)
        return hits[0].skill if hits else None

    def _evidence(self, skill: str) -> str | None:
        hits = [h for h in self.taxonomy.find(self.profile.get("resume_text", "")) if h.skill == skill]
        return hits[0].snippet if hits else None


def _needs(q: str, reason: str) -> dict[str, str]:
    return {"question": q, "answer": NEEDS_CANDIDATE_INPUT, "source": reason, "status": NEEDS_CANDIDATE_INPUT}


def _fmt(v: Any) -> str:
    if isinstance(v, bool):
        return "Yes" if v else "No"
    return str(v)
