"""Verifies that an application was actually submitted.

An application is SUBMITTED only with evidence:
  * a platform confirmation email that names the job's company/title, or
  * the candidate's confirmation with a reference ID or the confirmation text shown
    by the platform.
Opening a job page is never treated as applying.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html import unescape

from core.models import ApplicationStatus, Platform
from discovery.deduplication import normalize_company, normalize_title

log = logging.getLogger(__name__)

CONFIRMATION_TEXT_RE = re.compile(
    r"(application (was |has been )?(sent|submitted|received)|applied (successfully|on)|successfully applied|"
    r"thank(s| you) for (applying|your application)|you applied|application complete|we('| ha)ve received your application)",
    re.I,
)


@dataclass
class Evidence:
    reference_id: str | None
    confirmation_text: str | None
    source: str  # candidate | email:<message-id>


class VerificationError(ValueError):
    pass


def check_candidate_evidence(reference_id: str | None, confirmation_text: str | None) -> Evidence:
    ref = (reference_id or "").strip() or None
    text = (confirmation_text or "").strip() or None
    if not ref and not text:
        raise VerificationError(
            "Submission evidence is required: pass --reference <application ID shown by the platform> "
            "and/or --confirmation \"<confirmation message text>\"."
        )
    if text and not ref and not CONFIRMATION_TEXT_RE.search(text):
        raise VerificationError(
            "The confirmation text does not look like a submission confirmation "
            "(e.g. 'Your application was sent to ...'). Paste the platform's exact message or give --reference."
        )
    return Evidence(ref, text, "candidate")


def _plain(body: str) -> str:
    text = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(unescape(text).split())


def match_confirmation_email(subject: str, body: str, company: str, title: str) -> bool:
    """True if a confirmation email clearly refers to this company and job title."""
    text = normalize_title(subject + " " + _plain(body))
    comp = normalize_company(company)
    if not comp or comp not in text:
        return False
    t = normalize_title(title)
    if t and t in text:
        return True
    words = [w for w in t.split() if len(w) > 2]
    return bool(words) and sum(w in text.split() for w in words) / len(words) >= 0.8


def find_email_confirmations(db, email_source, run_id: int | None) -> list[int]:
    """Mark pending applications SUBMITTED when a matching platform confirmation email exists."""
    from applications.application_manager import ApplicationManager
    from discovery.sources import confirmation_emails

    pending = db.list_applications((ApplicationStatus.PENDING_MANUAL_SUBMISSION.value, ApplicationStatus.APPROVED.value,
                                    ApplicationStatus.NEEDS_VERIFICATION.value, ApplicationStatus.AWAITING_APPROVAL.value))
    if not pending:
        return []
    confirmed = []
    for platform, mail in confirmation_emails(email_source):
        for app in pending:
            if app["id"] in confirmed or Platform(app["platform"]) != platform:
                continue
            if match_confirmation_email(mail.subject, mail.body, app["company"] or "", app["title"] or ""):
                ApplicationManager.record_submission(
                    db, app["id"], Evidence(None, mail.subject[:500], f"email:{mail.message_id}"), run_id=run_id
                )
                confirmed.append(app["id"])
                log.info("Application %s confirmed by %s email.", app["id"], platform)
    return confirmed
