"""Timezone-aware time helpers. All application time is local to the configured zone."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Asia/Kolkata")


def set_timezone(name: str) -> None:
    global _TZ
    _TZ = ZoneInfo(name)


def tz() -> ZoneInfo:
    return _TZ


def now() -> datetime:
    return datetime.now(_TZ)


def today() -> date:
    return now().date()


def iso_now() -> str:
    return now().isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=_TZ)


def to_naive_local(value: datetime | None) -> datetime | None:
    """Excel cannot store timezone-aware datetimes; convert to naive local time."""
    if value is None:
        return None
    return value.astimezone(_TZ).replace(tzinfo=None) if value.tzinfo else value
