"""Permitted job sources.

* ImportInboxSource -- JSON / CSV / TXT files the candidate drops into <data_root>/inbox
  (or creates with `main.py add-job`).
* EmailAlertSource  -- the candidate's own job-alert emails from LinkedIn, Indeed and
  Naukri, read over IMAP in read-only mode. Only links and text inside the emails
  are used; job pages are never fetched.
"""

from __future__ import annotations

import csv
import email
import imaplib
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import timedelta
from email.header import decode_header, make_header
from email.message import Message
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Protocol
from urllib.parse import parse_qs, unquote, urlsplit

from core import timeutil
from core.models import Platform, RawJobRecord
from platforms import detect_platform, get_adapter
from platforms.base_platform import PlatformError

log = logging.getLogger(__name__)


class JobSource(Protocol):
    name: str

    def fetch(self, platform: Platform) -> list[RawJobRecord]:
        ...


def normalise_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip().strip("<>\"'")
    if not url:
        return None
    if not re.match(r"^[a-z][a-z0-9+.\-]*://", url, re.I):
        url = "https://" + url.lstrip("/")
    return url


# ---------------------------------------------------------------------------
# Import inbox
# ---------------------------------------------------------------------------

_FIELD_ALIASES = {
    "url": ("url", "job_url", "link"),
    "title": ("title", "job_title", "position"),
    "company": ("company", "company_name", "employer"),
    "location": ("location", "city"),
    "description": ("description", "job_description", "jd"),
    "posted_date": ("posted_date", "posted", "date_posted"),
    "salary": ("salary", "salary_range", "ctc"),
    "experience": ("experience", "experience_required"),
    "employment_type": ("employment_type", "job_type"),
    "work_mode": ("work_mode", "workplace", "remote"),
    "job_id": ("job_id", "id"),
    "platform": ("platform", "site", "source"),
    "application_method": ("application_method", "apply_method"),
    "screening_questions": ("screening_questions", "questions"),
    "cover_letter_required": ("cover_letter_required",),
}


@dataclass
class InboxFileResult:
    path: Path
    records: list[RawJobRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ImportInboxSource:
    name = "import_inbox"

    def __init__(self, inbox_dir: Path):
        self.inbox_dir = inbox_dir
        self._loaded: list[InboxFileResult] | None = None

    def files(self) -> list[Path]:
        if not self.inbox_dir.exists():
            return []
        return sorted(p for p in self.inbox_dir.iterdir() if p.is_file() and p.suffix.lower() in {".json", ".csv", ".txt", ".md"})

    def load(self) -> list[InboxFileResult]:
        if self._loaded is None:
            self._loaded = [self._load_file(p) for p in self.files()]
        return self._loaded

    def fetch(self, platform: Platform) -> list[RawJobRecord]:
        return [r for f in self.load() for r in f.records if r.platform == platform]

    def errors(self) -> list[tuple[str, str]]:
        return [(f.path.name, e) for f in self.load() for e in f.errors]

    def archive(self, run_date: str, keep: set[str] | None = None) -> None:
        """Move processed files out of the inbox (unreadable files go to failed/). Files named in `keep` stay."""
        for f in self.load():
            if not f.path.exists() or (keep and f.path.name in keep):
                continue
            sub = "failed" if f.errors and not f.records else "processed"
            target_dir = self.inbox_dir / sub / run_date
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f.path.name
            n = 1
            while target.exists():
                target = target_dir / f"{f.path.stem}_{n}{f.path.suffix}"
                n += 1
            shutil.move(str(f.path), target)

    # -- parsing --
    def _load_file(self, path: Path) -> InboxFileResult:
        result = InboxFileResult(path)
        try:
            text = path.read_text(encoding="utf-8-sig")
            if path.suffix.lower() == ".json":
                data = json.loads(text)
                rows = data if isinstance(data, list) else [data]
            elif path.suffix.lower() == ".csv":
                rows = list(csv.DictReader(text.splitlines()))
            else:
                rows = parse_text_jobs(text)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
            result.errors.append(f"Could not read {path.name}: {exc}")
            return result
        for i, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                result.errors.append(f"{path.name} item {i}: expected an object, got {type(row).__name__}")
                continue
            try:
                result.records.append(record_from_mapping(row, source="import_inbox", source_ref=f"{path.name}#{i}"))
            except ValueError as exc:
                result.errors.append(f"{path.name} item {i}: {exc}")
        return result


def record_from_mapping(row: dict, *, source: str, source_ref: str | None = None) -> RawJobRecord:
    lowered = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
    values: dict[str, object] = {}
    for fld, aliases in _FIELD_ALIASES.items():
        for a in aliases:
            v = lowered.get(a)
            if v not in (None, ""):
                values[fld] = v
                break
    url = normalise_url(str(values["url"])) if values.get("url") else None
    platform = None
    if values.get("platform"):
        try:
            platform = Platform.parse(str(values["platform"]))
        except ValueError:
            platform = None
    platform = platform or detect_platform(url)
    if platform is None:
        raise ValueError("platform could not be determined; give a LinkedIn/Indeed/Naukri URL or a 'platform' field")
    if not (values.get("title") or url):
        raise ValueError("a job needs at least a title or a URL")
    questions = values.get("screening_questions") or []
    if isinstance(questions, str):
        questions = [q.strip() for q in re.split(r"\n|\|", questions) if q.strip()]
    clr = values.get("cover_letter_required")
    if isinstance(clr, str):
        clr = clr.strip().lower() in {"1", "true", "yes", "y"}
    return RawJobRecord(
        platform=platform,
        source=source,
        url=url,
        title=_s(values.get("title")),
        company=_s(values.get("company")),
        location=_s(values.get("location")),
        description=_s(values.get("description")),
        posted_date=_s(values.get("posted_date")),
        salary=_s(values.get("salary")),
        experience=_s(values.get("experience")),
        employment_type=_s(values.get("employment_type")),
        work_mode=_s(values.get("work_mode")),
        job_id=_s(values.get("job_id")),
        application_method=_s(values.get("application_method")),
        screening_questions=[str(q) for q in questions],
        cover_letter_required=clr if isinstance(clr, bool) else None,
        source_ref=source_ref,
    )


def _s(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def parse_text_jobs(text: str) -> list[dict]:
    """Parse the plain-text import format.

    Each job is a block of 'Key: value' header lines, a line containing only '---',
    then the free-text job description. Jobs are separated by a line of '==='.
    """
    jobs = []
    for block in re.split(r"^\s*={3,}\s*$", text, flags=re.M):
        if not block.strip():
            continue
        head, sep, body = block.partition("\n---")
        row: dict[str, str] = {}
        for line in head.strip().splitlines():
            m = re.match(r"\s*([A-Za-z _]+?)\s*:\s*(.*)$", line)
            if m:
                row[m.group(1).strip().lower().replace(" ", "_")] = m.group(2).strip()
        if sep:
            row["description"] = body.lstrip("-\n").strip()
        jobs.append(row)
    return jobs


# ---------------------------------------------------------------------------
# Email alerts
# ---------------------------------------------------------------------------

PLATFORM_EMAIL_DOMAINS = {
    Platform.LINKEDIN: ("linkedin.com",),
    Platform.INDEED: ("indeed.com",),
    Platform.NAUKRI: ("naukri.com",),
}
_GENERIC_LINK_TEXT = re.compile(r"^(view( job)?|apply( now)?|see (all )?jobs?|easy apply|view details|more jobs|save|unsubscribe|.{0,2})$", re.I)


class _LinkCollector(HTMLParser):
    """Collects (href, anchor text, following text) triples from an HTML email."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict] = []
        self._href: str | None = None
        self._text: list[str] = []
        self._after: list[dict] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "head"):
            self._skip += 1
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head") and self._skip:
            self._skip -= 1
        if tag == "a" and self._href is not None:
            item = {"href": self._href, "text": " ".join(" ".join(self._text).split()), "after": []}
            self.items.append(item)
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._href is not None:
            self._text.append(text)
        else:
            for item in self.items[-3:]:
                if len(item["after"]) < 4:
                    item["after"].append(text)


def _unwrap_redirect(href: str) -> str:
    """Some alert links wrap the real URL in a query parameter; use it if present."""
    try:
        qs = parse_qs(urlsplit(href).query)
    except ValueError:
        return href
    for key in ("url", "u", "dest", "redirect", "target"):
        if qs.get(key) and qs[key][0].startswith("http"):
            return unquote(qs[key][0])
    return href


def parse_alert_email(html: str, platform: Platform, *, source_ref: str | None = None) -> list[RawJobRecord]:
    """Extract job links from a platform alert email body (HTML or text)."""
    adapter = get_adapter(platform)
    collector = _LinkCollector()
    collector.feed(html)
    by_id: dict[str, dict] = {}
    for item in collector.items:
        href = _unwrap_redirect(item["href"] or "")
        job_id = adapter.identify_job_id(href)
        if not job_id:
            continue
        entry = by_id.setdefault(job_id, {"url": href, "title": None, "after": []})
        text = item["text"]
        if text and not _GENERIC_LINK_TEXT.match(text) and (entry["title"] is None or len(text) > len(entry["title"])):
            entry["title"], entry["after"] = text, item["after"]
    if not collector.items:  # plain-text email
        for href in re.findall(r"https?://\S+", html):
            job_id = adapter.identify_job_id(href)
            if job_id:
                by_id.setdefault(job_id, {"url": href, "title": None, "after": []})

    records = []
    for job_id, entry in by_id.items():
        company = location = None
        after = [a for a in entry["after"] if not _GENERIC_LINK_TEXT.match(a)]
        if after:
            first = after[0]
            if "·" in first:
                company, _, location = (p.strip() for p in first.partition("·"))
            else:
                company = first
                if len(after) > 1 and len(after[1]) < 60:
                    location = after[1]
        records.append(
            RawJobRecord(
                platform=platform,
                source="email_alert",
                url=entry["url"],
                job_id=job_id,
                title=entry["title"],
                company=company,
                location=location or None,
                source_ref=source_ref,
                extra={"extraction_confidence": "medium" if entry["title"] and company else "low"},
            )
        )
    return records


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _body(msg: Message) -> str:
    html, text = None, None
    for part in msg.walk() if msg.is_multipart() else [msg]:
        ctype = part.get_content_type()
        if part.get_content_maintype() == "multipart" or part.get("Content-Disposition", "").startswith("attachment"):
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        decoded = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if ctype == "text/html" and html is None:
            html = decoded
        elif ctype == "text/plain" and text is None:
            text = decoded
    return html or text or ""


@dataclass
class MailItem:
    message_id: str
    sender: str
    subject: str
    date: str
    body: str


class EmailAlertSource:
    """Reads the candidate's mailbox read-only. Credentials come from IMAP_USERNAME / IMAP_PASSWORD."""

    name = "email_alerts"

    def __init__(self, cfg, *, imap_factory=None, username: str | None = None, password: str | None = None):
        self.cfg = cfg
        self._imap_factory = imap_factory or (lambda: imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port, timeout=60))
        self._messages: list[MailItem] | None = None
        # Explicit credentials (web portal, per user); the CLI falls back to the environment.
        self._username = username
        self._password = password

    def _connect(self):
        user = self._username or os.environ.get("IMAP_USERNAME")
        password = self._password or os.environ.get("IMAP_PASSWORD")
        if not user or not password:
            raise PlatformError("IMAP_USERNAME / IMAP_PASSWORD are not set in .env; email alerts are skipped.")
        try:
            conn = self._imap_factory()
            conn.login(user, password)
        except imaplib.IMAP4.abort as exc:
            raise PlatformError(f"IMAP connection dropped: {exc}", transient=True) from exc
        except (imaplib.IMAP4.error, OSError) as exc:
            # Do not include server responses verbatim; they can echo the username.
            raise PlatformError(f"IMAP login/connection failed ({type(exc).__name__}). Check host, port and app password.", transient=isinstance(exc, OSError)) from exc
        return conn

    def messages(self) -> list[MailItem]:
        """Fetch recent messages from the supported platforms' domains (cached per run)."""
        if self._messages is not None:
            return self._messages
        since = (timeutil.today() - timedelta(days=self.cfg.lookback_days)).strftime("%d-%b-%Y")
        conn = self._connect()
        items: list[MailItem] = []
        try:
            status, _ = conn.select(self.cfg.folder, readonly=True)
            if status != "OK":
                raise PlatformError(f"Could not open mailbox folder {self.cfg.folder!r}")
            ids: list[bytes] = []
            for domains in PLATFORM_EMAIL_DOMAINS.values():
                for domain in domains:
                    status, data = conn.search(None, "SINCE", since, "FROM", domain)
                    if status == "OK" and data and data[0]:
                        ids.extend(data[0].split())
            for msg_id in list(dict.fromkeys(ids))[-self.cfg.max_messages :]:
                status, data = conn.fetch(msg_id, "(BODY.PEEK[])")  # PEEK: do not mark as read
                if status != "OK" or not data or not isinstance(data[0], tuple):
                    continue
                msg = email.message_from_bytes(data[0][1])
                items.append(
                    MailItem(
                        message_id=_decode(msg.get("Message-ID")) or msg_id.decode(),
                        sender=_decode(msg.get("From")).lower(),
                        subject=_decode(msg.get("Subject")),
                        date=_decode(msg.get("Date")),
                        body=_body(msg),
                    )
                )
        except imaplib.IMAP4.abort as exc:
            raise PlatformError(f"IMAP connection dropped: {exc}", transient=True) from exc
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        log.info("Email: %d platform messages in the last %d day(s).", len(items), self.cfg.lookback_days)
        self._messages = items
        return items

    def fetch(self, platform: Platform) -> list[RawJobRecord]:
        records: list[RawJobRecord] = []
        for m in self.messages():
            if not _from_platform(m.sender, platform) or looks_like_confirmation(m.subject):
                continue
            for record in parse_alert_email(m.body, platform, source_ref=f"email:{m.message_id}"):
                record.extra["alert_date"] = m.date
                records.append(record)
        return records


def _from_platform(sender: str, platform: Platform) -> bool:
    return any(re.search(rf"[@.]{re.escape(d)}\b", sender) for d in PLATFORM_EMAIL_DOMAINS[platform])


CONFIRMATION_SUBJECT_RE = re.compile(
    r"(your application (was|has been) (sent|submitted|received)|application (sent|submitted|received)|"
    r"you applied|applied successfully|successfully applied|thank(s| you) for applying|indeed application:)",
    re.I,
)


def looks_like_confirmation(subject: str) -> bool:
    return bool(CONFIRMATION_SUBJECT_RE.search(subject or ""))


def confirmation_emails(source: EmailAlertSource) -> Iterable[tuple[Platform, MailItem]]:
    for m in source.messages():
        if not looks_like_confirmation(m.subject):
            continue
        for platform in Platform:
            if _from_platform(m.sender, platform):
                yield platform, m
