from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import timeutil  # noqa: E402
from core.settings import load_settings  # noqa: E402
from core.skills import SkillTaxonomy  # noqa: E402

from support import SYNTHETIC_RESUME_LINES, make_pdf  # noqa: E402,F401  (re-exported for existing tests)


class FakeLLM:
    name = "fake-llm"

    def __init__(self, response: dict[str, Any] | Exception | None = None):
        self.response = response
        self.calls = 0

    def complete_json(self, system, user, schema, *, max_tokens=16000):
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def llm_response(**overrides) -> dict[str, Any]:
    base = {
        "core_skills": {"score": 90, "evidence": "AR and payment posting match"},
        "experience_relevance": {"score": 80, "evidence": "healthcare AR roles"},
        "responsibilities": {"score": 85, "evidence": "claims follow-up and posting"},
        "education": {"score": 100, "evidence": "B.Com meets requirement"},
        "matching_skills": ["Accounts Receivable", "Payment Posting"],
        "missing_required_skills": ["Power BI"],
        "missing_optional_skills": [],
        "relevant_experience": "3 AR roles",
        "matching_responsibilities": ["payment posting"],
        "reasons_for": ["Direct AR experience"],
        "reasons_against": [],
        "recommendation": "Apply.",
    }
    base.update(overrides)
    return base


@pytest.fixture
def resume_pdf(tmp_path) -> Path:
    return make_pdf(tmp_path / "resume.pdf", SYNTHETIC_RESUME_LINES)


@pytest.fixture
def settings_factory(tmp_path, resume_pdf, monkeypatch):
    for var in ("RESUME_PATH", "JOB_AUTOMATION_DATA_ROOT", "APPLICATION_MODE", "LLM_PROVIDER", "LLM_MODEL", "IMAP_USERNAME", "IMAP_PASSWORD"):
        monkeypatch.delenv(var, raising=False)

    def factory(**overrides):
        raw = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text())
        raw["paths"]["data_root"] = str(tmp_path / "data")
        raw["candidate"]["resume_path"] = str(resume_pdf)
        raw["candidate"]["name"] = "Test Candidate"
        raw["candidate"]["verified_facts_file"] = str(tmp_path / "facts.json")
        raw["candidate"]["seed_skills"] = ["Accounts Receivable", "Payment Posting", "Quantum Computing"]
        raw["llm"]["provider"] = "rule_based"
        for dotted, value in overrides.items():
            node = raw
            keys = dotted.split("__")
            for k in keys[:-1]:
                node = node.setdefault(k, {})
            node[keys[-1]] = value
        cfg_dir = tmp_path / "proj" / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "settings.yaml").write_text(yaml.safe_dump(raw))
        if not (tmp_path / "facts.json").exists():
            (tmp_path / "facts.json").write_text(json.dumps({"verified_facts": {}, "profile_overrides": {}}))
        s = load_settings(cfg_dir / "settings.yaml", env_file=tmp_path / "no.env")
        timeutil.set_timezone(s.timezone)
        s.ensure_directories()
        return s

    return factory


@pytest.fixture
def settings(settings_factory):
    return settings_factory()


@pytest.fixture
def taxonomy() -> SkillTaxonomy:
    return SkillTaxonomy.from_file(ROOT / "config" / "skills_taxonomy.yaml")


@pytest.fixture
def profile(settings):
    from resume.profile_builder import ProfileBuilder

    return ProfileBuilder(settings).load_or_build()


AR_JD = """About the role
We are hiring an Accounts Receivable Analyst for our US healthcare team.
Responsibilities:
- Perform payment posting using remittance information
- Follow up on unpaid claims with insurance companies
- Prepare Excel reports using PivotTables for management
Requirements:
- 3-6 years of experience in accounts receivable
- Bachelor's degree in Commerce
Good to have:
- Power BI
Full time role."""


def inbox_job(**kw) -> dict[str, Any]:
    job = {
        "url": "https://www.linkedin.com/jobs/view/4000000001/",
        "title": "Accounts Receivable Analyst",
        "company": "Acme Health",
        "location": "Bengaluru",
        "description": AR_JD,
    }
    job.update(kw)
    return job
