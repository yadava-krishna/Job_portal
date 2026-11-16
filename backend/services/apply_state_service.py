"""Smart Apply state: the fine-grained progress of one application that the browser extension fills.

The extension reports what it observed; this module decides whether the move is legal and what it means for the
application's main status. Rules:

* nothing is "submitted" because a button was clicked: only `submitted_confirmed` with a confirmation signal the
  extension saw on the employer's page (or the user's own statement through /confirm) marks the application SUBMITTED;
* `submission_authorized` requires a completed review, and is refused once the application is already submitted
  (duplicate prevention), so a second submission can never be authorised by mistake;
* an unclear outcome stays `submission_uncertain` (status CONFIRMATION_PENDING) until the user says what happened;
* every move is kept in the application's event timeline.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models import Application, ApplicationEvent, Resume, User, utcnow

PRE_SUBMIT = ("draft", "ready_to_fill", "filling", "needs_information", "ready_for_review", "reviewed")
STATES = PRE_SUBMIT + ("submission_authorized", "submission_pending", "submitted_confirmed", "submission_uncertain",
                       "failed", "cancelled")
MODES = ("autofill_review", "assisted_submit", "manual_handoff")

LABELS = {
    "draft": "Draft", "ready_to_fill": "Ready to fill", "filling": "Filling", "needs_information": "Needs information",
    "ready_for_review": "Ready for review", "reviewed": "Reviewed", "submission_authorized": "Submission authorised",
    "submission_pending": "Submission pending", "submitted_confirmed": "Submitted (confirmed)",
    "submission_uncertain": "Submission uncertain: please check", "failed": "Failed", "cancelled": "Cancelled",
}

# Which states may follow which. Anything not listed is refused with 409.
_NEXT: dict[str | None, set[str]] = {
    None: set(PRE_SUBMIT) | {"submission_pending", "cancelled"},
    **{s: set(PRE_SUBMIT) | {"submission_pending", "failed", "cancelled"} for s in PRE_SUBMIT},
    "submission_authorized": {"submission_pending", "failed", "cancelled", *PRE_SUBMIT},
    "submission_pending": {"submitted_confirmed", "submission_uncertain", "failed", "needs_information", "ready_for_review"},
    "submission_uncertain": {"submitted_confirmed", "cancelled", "failed", "ready_for_review", "needs_information"},
    "failed": set(PRE_SUBMIT) | {"cancelled"},
    "cancelled": set(PRE_SUBMIT),
    "submitted_confirmed": set(),
}
_NEXT["reviewed"] = _NEXT["reviewed"] | {"submission_authorized"}

SESSION_KEYS = {"platform": 40, "page": 300, "step": 120, "fingerprint": 80, "signal": 200, "message": 500}
COUNT_KEYS = ("filled", "review", "needs", "skipped", "steps_done")


def _page(url: Any) -> str | None:
    """Scheme, host and path only: query strings can carry tokens and are never stored."""
    try:
        p = urlsplit(str(url or ""))
    except ValueError:
        return None
    if p.scheme != "https" or not p.hostname:
        return None
    return f"https://{p.hostname}{p.path}"[:300]


def _clean_session(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    out: dict[str, Any] = {}
    for k, n in SESSION_KEYS.items():
        v = raw.get(k)
        if v is None:
            continue
        v = _page(v) if k == "page" else " ".join(str(v).split())[:n]
        if v:
            out[k] = v
    counts = raw.get("counts")
    if isinstance(counts, dict):
        out["counts"] = {k: int(counts[k]) for k in COUNT_KEYS if isinstance(counts.get(k), int) and 0 <= counts[k] < 10000}
    res = raw.get("resume")
    if isinstance(res, dict) and res.get("kind") in ("upload", "studio"):
        out["resume"] = {"kind": res["kind"], "id": int(res["id"]) if str(res.get("id", "")).isdigit() else None,
                         "format": res.get("format") if res.get("format") in ("pdf", "docx") else "pdf",
                         "name": " ".join(str(res.get("name") or "").split())[:200] or None,
                         "verified": bool(res.get("verified"))}
    return out


def record(db: Session, user: User, app: Application, state: str, *, mode: str | None = None,
           session: dict[str, Any] | None = None, reference_id: str | None = None) -> Application:
    from backend.services import application_service as svc

    if state not in STATES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown application state.")
    if mode is not None and mode not in MODES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown apply mode.")
    current = app.apply_state if app.apply_state in STATES else None
    if app.status == "SUBMITTED" and state != "submitted_confirmed":
        when = app.submitted_at.date().isoformat() if app.submitted_at else "earlier"
        raise HTTPException(status.HTTP_409_CONFLICT, f"This application was already submitted ({when}). JobPilot will not submit it again.")
    if app.status == "WITHDRAWN":
        raise HTTPException(status.HTTP_409_CONFLICT, "This application was withdrawn.")
    if state == current and state in PRE_SUBMIT:
        pass  # progress update within the same state (counts, step)
    elif state not in _NEXT.get(current, set()):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot go from {LABELS.get(current, 'not started')} to {LABELS[state]}.")
    info = _clean_session(session)
    if state == "submitted_confirmed" and not info.get("signal"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A confirmation signal from the employer's page is required.")

    # Main status effects.
    if state in PRE_SUBMIT or state in ("submission_authorized", "submission_pending", "failed"):
        svc.mark_in_progress(db, user, app, "smart_apply")
    elif state == "submission_uncertain" and app.status != "CONFIRMATION_PENDING":
        svc._transition(db, user, app, "CONFIRMATION_PENDING", "SUBMISSION_UNCERTAIN",
                        "Smart Apply could not see a confirmation on the employer's page. Please check and confirm.")
    elif state == "cancelled" and app.status in ("OPENED", "CONFIRMATION_PENDING"):
        svc._transition(db, user, app, "PREPARED", "NOT_SUBMITTED", "Smart Apply session cancelled.")

    res = info.get("resume")
    if res and res.get("id"):
        _remember_resume(db, user, app, res)
    if state == "submitted_confirmed":
        svc.mark_submitted(db, user, app, reference_id=reference_id or None, confirmation_text=info.get("signal"),
                           source="smart_apply_" + ("assisted" if (mode or app.apply_mode) == "assisted_submit" else "detected"))

    prev = current
    app.apply_state, app.apply_state_at = state, utcnow()
    if mode:
        app.apply_mode = mode
    merged = {**(app.apply_session or {}), **info}
    if state == "submission_authorized":
        merged["authorized_at"] = utcnow().isoformat()
    if state == "reviewed":
        merged["reviewed_at"] = utcnow().isoformat()
    app.apply_session = merged
    if state != prev:
        db.add(ApplicationEvent(application_id=app.id, user_id=user.id, event_type="APPLY_STATE", from_status=prev, to_status=state,
                                details=info.get("message") or info.get("signal") or LABELS[state]))
    db.commit()
    db.refresh(app)
    return app


def _remember_resume(db: Session, user: User, app: Application, res: dict[str, Any]) -> None:
    """The exact resume chosen for this application (an uploaded file, or a Resume Studio version)."""
    from backend.models import ResumeVersion

    if res["kind"] == "upload":
        r = db.get(Resume, res["id"])
        if r is not None and r.user_id == user.id:
            app.resume_id, app.resume_used = r.id, r.original_filename
    else:
        v = db.get(ResumeVersion, res["id"])
        if v is not None and v.user_id == user.id:
            app.resume_version_id, app.resume_used = v.id, (res.get("name") or v.name)[:255]


def after_user_confirm(db: Session, app: Application, submitted: bool | None) -> None:
    """Keep the Smart Apply state in step when the user answers 'did it go through?' themselves."""
    if app.apply_state is None:
        return
    new = "submitted_confirmed" if submitted else ("cancelled" if submitted is False else app.apply_state)
    if new != app.apply_state:
        db.add(ApplicationEvent(application_id=app.id, user_id=app.user_id, event_type="APPLY_STATE", from_status=app.apply_state,
                                to_status=new, details="Confirmed by you." if submitted else "You said it was not submitted."))
        app.apply_state, app.apply_state_at = new, utcnow()
        db.commit()


def summary(app: Application) -> dict[str, Any]:
    s = app.apply_session or {}
    return {"apply_state": app.apply_state, "apply_state_label": LABELS.get(app.apply_state or "", None),
            "apply_mode": app.apply_mode, "apply_state_at": app.apply_state_at,
            "apply_step": s.get("step"), "apply_counts": s.get("counts") or {}, "apply_resume": s.get("resume")}
