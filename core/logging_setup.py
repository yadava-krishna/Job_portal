"""Logging with one file per day and redaction of secrets and personal data."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from core import timeutil

_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), "[REDACTED_KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"), "[REDACTED_KEY]"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]{8,}"), r"\1 [REDACTED]"),
    (re.compile(r"(?i)\b(password|passwd|pwd|token|api[_-]?key|secret|cookie|session)\b(\s*[=:]\s*)\S+"), r"\1\2[REDACTED]"),
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    (re.compile(r"(?<!\d)(?:\+?91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}(?!\d)"), "[PHONE]"),
]


def redact(text: str) -> str:
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # malformed format args: leave record untouched
            return True
        record.msg = redact(message)
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
        elif record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


class _ConsoleFilter(logging.Filter):
    """Records logged with extra={"file_only": True} go to the log file but not the console."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not getattr(record, "file_only", False)


class DailyFileHandler(logging.Handler):
    """Writes to <dir>/YYYY-MM-DD.log, switching files when the local date changes."""

    def __init__(self, directory: Path):
        super().__init__()
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._date = None
        self._stream = None

    def _ensure_stream(self) -> None:
        current = timeutil.today()
        if current != self._date:
            if self._stream:
                self._stream.close()
            self._date = current
            self._stream = open(self.directory / f"{current.isoformat()}.log", "a", encoding="utf-8")

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.acquire()
            self._ensure_stream()
            self._stream.write(self.format(record) + "\n")
            self._stream.flush()
        except Exception:
            self.handleError(record)
        finally:
            self.release()

    def close(self) -> None:
        if self._stream:
            self._stream.close()
            self._stream = None
        super().close()


class _LocalTimeFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        from datetime import datetime

        return datetime.fromtimestamp(record.created, timeutil.tz()).strftime("%Y-%m-%d %H:%M:%S%z")


def setup_logging(logs_dir: Path, level: str = "INFO", console: bool = True) -> None:
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    root.setLevel(level.upper())
    fmt = _LocalTimeFormatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s")
    redactor = RedactingFilter()

    file_handler = DailyFileHandler(logs_dir)
    file_handler.setFormatter(fmt)
    file_handler.addFilter(redactor)
    root.addHandler(file_handler)

    if console:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
        stream.addFilter(redactor)
        stream.addFilter(_ConsoleFilter())
        root.addHandler(stream)

    # Third-party HTTP clients can log request details; keep them quiet.
    for noisy in ("httpx", "httpx2", "httpcore", "anthropic", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
