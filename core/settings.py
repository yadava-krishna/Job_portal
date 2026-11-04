"""Configuration loading and validation.

Settings come from config/settings.yaml, with a few environment-variable
overrides (RESUME_PATH, JOB_AUTOMATION_DATA_ROOT, APPLICATION_MODE, LLM_PROVIDER).
Secrets are read from the environment only, never from the YAML file.
"""

from __future__ import annotations

import json
import os
import re
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"
LOCAL_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.local.yaml"  # personal values, gitignored


class ConfigError(Exception):
    """Raised when the configuration is missing or invalid."""


class ApplicationMode(StrEnum):
    DISCOVERY_ONLY = "DISCOVERY_ONLY"
    ASSISTED = "ASSISTED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    PERMITTED_AUTO_APPLY = "PERMITTED_AUTO_APPLY"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PathsConfig(_Strict):
    data_root: Path = Path("~/Job_Applications")


class CandidateConfig(_Strict):
    name: str
    resume_path: Path
    location: str = "Bengaluru, Karnataka, India"
    stated_experience_years: float | None = None
    education: str | None = None
    primary_domains: list[str] = Field(default_factory=list)
    verified_facts_file: Path = Path("config/candidate_profile.json")
    seed_skills: list[str] = Field(default_factory=list)


class SearchConfig(_Strict):
    job_titles: list[str] = Field(min_length=1)
    locations: list[str] = Field(min_length=1)
    posted_within_hours: int = Field(default=24, ge=1, le=24 * 30)
    experience_min_years: float = Field(default=0, ge=0)
    experience_max_years: float = Field(default=50, ge=0)
    min_salary_lpa: float | None = Field(default=None, ge=0)
    employment_types: list[str] = Field(default_factory=lambda: ["Full-time", "Contract"])
    work_modes: list[str] = Field(default_factory=lambda: ["Remote", "Hybrid", "On-site"])

    @model_validator(mode="after")
    def _range(self) -> "SearchConfig":
        if self.experience_min_years > self.experience_max_years:
            raise ValueError("search.experience_min_years must be <= experience_max_years")
        return self


class MatchWeights(_Strict):
    core_skills: float = 35
    experience: float = 25
    responsibilities: float = 20
    education: float = 10
    location: float = 10

    @model_validator(mode="after")
    def _positive(self) -> "MatchWeights":
        if any(v < 0 for v in self.model_dump().values()) or sum(self.model_dump().values()) <= 0:
            raise ValueError("matching.weights must be non-negative and sum to more than 0")
        return self


class MatchCategories(_Strict):
    excellent: float = 85
    good: float = 70
    moderate: float = 55

    @model_validator(mode="after")
    def _order(self) -> "MatchCategories":
        if not (self.excellent > self.good > self.moderate):
            raise ValueError("matching.categories must satisfy excellent > good > moderate")
        return self


class MatchingConfig(_Strict):
    min_match_score: float = Field(default=70, ge=0, le=100)
    weights: MatchWeights = Field(default_factory=MatchWeights)
    categories: MatchCategories = Field(default_factory=MatchCategories)
    require_description_for_shortlist: bool = True


class EligibilityConfig(_Strict):
    max_experience_gap_years: float = 2.0
    allowed_work_modes: list[str] = Field(default_factory=lambda: ["Remote", "Hybrid", "On-site"])
    allowed_employment_types: list[str] = Field(default_factory=lambda: ["Full-time", "Contract"])
    allowed_locations: list[str] = Field(default_factory=list)
    enforce_min_salary: bool = False
    excluded_companies: list[str] = Field(default_factory=list)
    excluded_title_keywords: list[str] = Field(default_factory=list)
    qualifications_candidate_lacks: list[str] = Field(default_factory=list)
    max_job_age_days: int = Field(default=30, ge=1)


class CoverLetterConfig(_Strict):
    enabled: bool = False
    generate_when_required: bool = True


class ApplicationsConfig(_Strict):
    mode: ApplicationMode = ApplicationMode.APPROVAL_REQUIRED
    max_per_day: int = Field(default=15, ge=0)
    reprocess_seen_jobs: bool = False
    block_cross_platform_duplicates: bool = True
    cover_letter: CoverLetterConfig = Field(default_factory=CoverLetterConfig)
    open_browser_on_approve: bool = True


class PlatformToggle(_Strict):
    enabled: bool = True
    domain: str | None = None


class PlatformsConfig(_Strict):
    linkedin: PlatformToggle = Field(default_factory=PlatformToggle)
    indeed: PlatformToggle = Field(default_factory=lambda: PlatformToggle(domain="in.indeed.com"))
    naukri: PlatformToggle = Field(default_factory=PlatformToggle)


class ImportInboxConfig(_Strict):
    enabled: bool = True


class EmailAlertsConfig(_Strict):
    enabled: bool = False
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    folder: str = "INBOX"
    lookback_days: int = Field(default=2, ge=1, le=30)
    max_messages: int = Field(default=200, ge=1)


class SourcesConfig(_Strict):
    import_inbox: ImportInboxConfig = Field(default_factory=ImportInboxConfig)
    email_alerts: EmailAlertsConfig = Field(default_factory=EmailAlertsConfig)


class LLMProvider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI_COMPATIBLE = "openai_compatible"
    RULE_BASED = "rule_based"


class LLMConfig(_Strict):
    provider: LLMProvider = LLMProvider.ANTHROPIC
    model: str = "claude-opus-5"
    effort: str = "medium"
    base_url: str | None = None
    api_key_env: str = "ANTHROPIC_API_KEY"
    timeout_seconds: float = Field(default=180, gt=0)
    max_concurrency: int = Field(default=3, ge=1, le=16)
    fallback_to_rule_based: bool = True

    @field_validator("effort")
    @classmethod
    def _effort(cls, v: str) -> str:
        if v not in {"low", "medium", "high", "xhigh", "max"}:
            raise ValueError("llm.effort must be one of low, medium, high, xhigh, max")
        return v


class SchedulerConfig(_Strict):
    run_time: str = "09:00"
    run_missed_on_startup: bool = True
    misfire_grace_hours: float = Field(default=6, ge=0)
    retry_attempts: int = Field(default=3, ge=1, le=10)
    retry_backoff_seconds: float = Field(default=120, ge=0)

    @field_validator("run_time")
    @classmethod
    def _time(cls, v: str) -> str:
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", v.strip())
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise ValueError("scheduler.run_time must be HH:MM (24-hour)")
        return f"{int(m.group(1)):02d}:{m.group(2)}"

    @property
    def hour(self) -> int:
        return int(self.run_time.split(":")[0])

    @property
    def minute(self) -> int:
        return int(self.run_time.split(":")[1])


class LoggingConfig(_Strict):
    level: str = "INFO"


class Settings(_Strict):
    timezone: str = "Asia/Kolkata"
    paths: PathsConfig = Field(default_factory=PathsConfig)
    candidate: CandidateConfig
    search: SearchConfig
    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    eligibility: EligibilityConfig = Field(default_factory=EligibilityConfig)
    applications: ApplicationsConfig = Field(default_factory=ApplicationsConfig)
    platforms: PlatformsConfig = Field(default_factory=PlatformsConfig)
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # Set by load_settings(); not part of the YAML file.
    project_root: Path = Field(default=PROJECT_ROOT, exclude=True)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone {v!r}") from exc
        return v

    # ---- derived paths -------------------------------------------------
    def resolve(self, p: Path) -> Path:
        p = Path(os.path.expanduser(str(p)))
        return p if p.is_absolute() else (self.project_root / p)

    @property
    def data_root(self) -> Path:
        return self.resolve(self.paths.data_root)

    @property
    def resume_path(self) -> Path:
        return self.resolve(self.candidate.resume_path)

    @property
    def db_path(self) -> Path:
        return self.data_root / "database" / "job_applications.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_root / "logs"

    @property
    def inbox_dir(self) -> Path:
        return self.data_root / "inbox"

    @property
    def cache_dir(self) -> Path:
        return self.data_root / "cache"

    @property
    def packages_dir(self) -> Path:
        return self.data_root / "applications"

    @property
    def taxonomy_path(self) -> Path:
        local = self.project_root / "config" / "skills_taxonomy.yaml"
        return local if local.exists() else PROJECT_ROOT / "config" / "skills_taxonomy.yaml"

    def ensure_directories(self) -> None:
        for d in (
            self.data_root,
            self.db_path.parent,
            self.logs_dir,
            self.inbox_dir,
            self.cache_dir,
            self.packages_dir,
            self.data_root / "config",
            self.data_root / "reports",
        ):
            d.mkdir(parents=True, exist_ok=True)

    def load_verified_facts(self) -> dict[str, Any]:
        """Return the candidate-confirmed facts file content ({} if absent)."""
        path = self.resolve(self.candidate.verified_facts_file)
        if not path.exists():
            return {"verified_facts": {}, "profile_overrides": {}}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
        data.setdefault("verified_facts", {})
        data.setdefault("profile_overrides", {})
        return data


_ENV_OVERRIDES = {
    "RESUME_PATH": ("candidate", "resume_path"),
    "JOB_AUTOMATION_DATA_ROOT": ("paths", "data_root"),
    "APPLICATION_MODE": ("applications", "mode"),
    "LLM_PROVIDER": ("llm", "provider"),
    "LLM_MODEL": ("llm", "model"),
}


def load_settings(path: Path | str | None = None, *, env_file: Path | None = None) -> Settings:
    """Load, override from environment and validate the settings file."""
    load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)
    default = LOCAL_SETTINGS_PATH if LOCAL_SETTINGS_PATH.exists() else DEFAULT_SETTINGS_PATH
    path = Path(path) if path else Path(os.environ.get("JOB_AUTOMATION_SETTINGS", default))
    if not path.exists():
        raise ConfigError(f"Settings file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Settings file {path} is not valid YAML: {exc}") from exc

    for env_name, (section, key) in _ENV_OVERRIDES.items():
        value = os.environ.get(env_name)
        if value:
            raw.setdefault(section, {})[key] = value

    try:
        settings = Settings.model_validate(raw)
    except ValidationError as exc:
        lines = [f"  - {'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        raise ConfigError(f"Invalid settings in {path}:\n" + "\n".join(lines)) from exc
    settings.project_root = path.resolve().parent.parent if path.parent.name == "config" else PROJECT_ROOT
    return settings


def validate_resume_path(settings: Settings) -> Path:
    """Return the resume path or raise ConfigError with an actionable message."""
    p = settings.resume_path
    if not p.exists():
        raise ConfigError(
            f"Resume not found at {p}. Set candidate.resume_path in config/settings.yaml "
            "or RESUME_PATH in .env to the absolute path of the PDF."
        )
    if not p.is_file():
        raise ConfigError(f"Resume path {p} is not a file.")
    if p.suffix.lower() != ".pdf":
        raise ConfigError(f"Resume must be a PDF file, got {p.name}.")
    return p
