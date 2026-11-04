"""Candidate-facing approval workflow (used by the CLI)."""

from __future__ import annotations

import logging
import webbrowser
from typing import Any

from applications.application_manager import ApplicationManager, TransitionError, transition
from applications.submission_verifier import check_candidate_evidence
from core.models import ApplicationStatus
from core.settings import ApplicationMode, Settings
from database.db import Database
from platforms import get_adapter
from core.models import Platform

log = logging.getLogger(__name__)
S = ApplicationStatus


class ApprovalManager:
    def __init__(self, settings: Settings, db: Database, manager: ApplicationManager | None = None):
        self.settings = settings
        self.db = db
        self.manager = manager

    def pending(self) -> list[Any]:
        return self.db.list_applications((S.AWAITING_APPROVAL.value,))

    def to_submit(self) -> list[Any]:
        return self.db.list_applications((S.PENDING_MANUAL_SUBMISSION.value, S.APPROVED.value, S.NEEDS_VERIFICATION.value, S.BLOCKED.value))

    def approve(self, app_id: int, *, open_browser: bool | None = None) -> str:
        app = self._get(app_id)
        if app["status"] != S.AWAITING_APPROVAL.value:
            raise TransitionError(f"Application {app_id} is {app['status']}, not awaiting approval.")
        adapter = get_adapter(Platform(app["platform"]), self.settings)
        transition(self.db, app_id, S.APPROVED, event_type="APPROVED_BY_CANDIDATE", approved_at=_now())
        if (self.settings.applications.mode == ApplicationMode.PERMITTED_AUTO_APPLY and adapter.capabilities.automated_apply
                and self.manager is not None):
            ok = self.manager.try_submit(app_id, None)
            return "submitted and confirmed" if ok else f"automated submission did not complete; status {self._get(app_id)['status']}"
        transition(self.db, app_id, S.PENDING_MANUAL_SUBMISSION, event_type="ASSISTED_SUBMISSION",
                   details=f"{app['platform']}: {adapter.capabilities.application_method}")
        if open_browser if open_browser is not None else self.settings.applications.open_browser_on_approve:
            self.open(app_id)
        return "approved - submit it on the platform, then run mark-submitted"

    def reject(self, app_id: int, reason: str | None = None) -> None:
        transition(self.db, app_id, S.REJECTED_BY_CANDIDATE, event_type="REJECTED_BY_CANDIDATE", details=reason, notes=reason)

    def open(self, app_id: int) -> str | None:
        """Open the job page for manual submission. This is NOT recorded as applying."""
        app = self._get(app_id)
        if not app["url"]:
            return None
        self.db.add_event(event_type="OPENED_FOR_MANUAL_SUBMISSION", application_id=app_id, details="Job page opened; not a submission.")
        try:
            webbrowser.open(app["url"], new=2)
        except webbrowser.Error as exc:
            log.warning("Could not open a browser (%s); open the URL manually.", exc)
        return app["url"]

    def mark_submitted(self, app_id: int, reference: str | None, confirmation: str | None) -> None:
        evidence = check_candidate_evidence(reference, confirmation)
        ApplicationManager.record_submission(self.db, app_id, evidence)

    def mark_failed(self, app_id: int, reason: str) -> None:
        transition(self.db, app_id, S.FAILED, event_type="FAILED", details=reason, error=reason)

    def retry(self, app_id: int) -> None:
        transition(self.db, app_id, S.PENDING_MANUAL_SUBMISSION, event_type="RETRY_MANUAL")

    def _get(self, app_id: int):
        app = self.db.get_application(app_id)
        if app is None:
            raise TransitionError(f"Application {app_id} not found.")
        return app


def _now() -> str:
    from core import timeutil

    return timeutil.iso_now()
