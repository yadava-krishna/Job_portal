"""Platform adapter registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models import Platform
from platforms.base_platform import BasePlatform
from platforms.indeed import IndeedPlatform
from platforms.linkedin import LinkedInPlatform
from platforms.naukri import NaukriPlatform

if TYPE_CHECKING:
    from core.settings import Settings
    from discovery.sources import JobSource

ADAPTERS: dict[Platform, type[BasePlatform]] = {
    Platform.LINKEDIN: LinkedInPlatform,
    Platform.INDEED: IndeedPlatform,
    Platform.NAUKRI: NaukriPlatform,
}


def enabled_platforms(settings: "Settings") -> list[Platform]:
    toggles = {Platform.LINKEDIN: settings.platforms.linkedin, Platform.INDEED: settings.platforms.indeed, Platform.NAUKRI: settings.platforms.naukri}
    return [p for p, t in toggles.items() if t.enabled]


def get_adapter(platform: Platform, settings: "Settings | None" = None, sources: "list[JobSource] | None" = None) -> BasePlatform:
    return ADAPTERS[platform](sources=sources, settings=settings)


def detect_platform(url: str | None) -> Platform | None:
    """Identify which supported platform a URL belongs to (official https domains only)."""
    if not url:
        return None
    for platform, cls in ADAPTERS.items():
        if cls(sources=[]).is_official_url(url):
            return platform
    return None
