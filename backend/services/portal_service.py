"""Portal Connections and portal profile review (LinkedIn, Naukri, Indeed).

Each portal reports every capability separately, never one "connected" flag:
  identity_auth           the portal's official sign-in is set up on this JobPilot server (LinkedIn OIDC, Indeed OAuth)
  account_linked          the user actually linked an account through it (connection_service)
  profile_access          the fields that account shared under the scopes the user granted
  job_retrieval           approved API access to the portal's jobs: none exists for JobPilot, so always unavailable
  application_submission  approved API access to apply there: none exists, so always unavailable
  native_handoff          JobPilot opens the original job on the portal, in the user's own browser (always)
  reconnect_required      the link expired or was revoked
  listings                how many of the user's JobPilot jobs came from the portal (by link, clipper or alert e-mail)
plus the V3 ones that stay true: jobs reach JobPilot through links, alert e-mails and the clipper (source), profile
checklists (profile_guidance), the Apply Workspace hand-off (application_handoff), and no automation on the portals
(assisted_submission).

The profile review is built only from your confirmed JobPilot profile, preferences and saved answers. It suggests
wording made of facts you already confirmed, never new achievements, and never edits the portal for you. Limits used:
LinkedIn headline 220 characters and About 2,600 (enforced by LinkedIn's profile editor); Naukri resume headline 250
characters (Naukri's own guidance). Nothing else is claimed about a portal's rules.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import CandidateProfile, ExternalIdentity, JobPreference, User, utcnow
from backend.schemas.profile import EditableProfile

PORTALS = ("linkedin", "naukri", "indeed")  # the order of the cards
NAMES = {"linkedin": "LinkedIn", "naukri": "Naukri", "indeed": "Indeed"}
HOME = {"linkedin": "https://www.linkedin.com/jobs/", "naukri": "https://www.naukri.com/", "indeed": "https://in.indeed.com/"}
LINKEDIN_HEADLINE, LINKEDIN_ABOUT, NAUKRI_HEADLINE = 220, 2600, 250
SIGN_IN = {
    "linkedin": "Sign In with LinkedIn (OpenID Connect): LinkedIn shares your name, photo and e-mail address. Nothing else.",
    "indeed": "Indeed's official sign-in (OAuth): Indeed shares your e-mail address. Nothing else.",
    "naukri": "Naukri offers no official sign-in for apps like JobPilot. You sign in on naukri.com yourself; JobPilot never sees your Naukri password or OTP.",
}
NO_JOBS_API = {
    "linkedin": "LinkedIn's job APIs are for approved partners only, and signing in doesn't grant them.",
    "indeed": "Indeed hasn't published a job-seeker API JobPilot is approved for. JobPilot never calls undocumented APIs.",
    "naukri": "Naukri has no public job API for apps like JobPilot.",
}
NO_SUBMIT_API = {
    "linkedin": "Easy Apply has no API for apps like JobPilot.",
    "indeed": "Indeed Apply is built for employers' hiring systems, not job-seeker apps.",
    "naukri": "Naukri has no application API for apps like JobPilot.",
}
NO_AUTOMATION = {
    "linkedin": "LinkedIn's rules forbid automating its site, Easy Apply included. You click apply there yourself.",
    "naukri": "Naukri's terms forbid automated tools. You click apply there yourself.",
    "indeed": "Indeed's terms forbid automating Indeed Apply. You click apply there yourself.",
}


def _cap(available: bool, detail: str, **extra: Any) -> dict[str, Any]:
    return {"available": available, "detail": detail, **extra}


SUMMARY = {
    "linkedin": "Link your LinkedIn sign-in, bring LinkedIn jobs in, and tune your profile there.",
    "naukri": "Opens naukri.com in your browser. Bring Naukri jobs in by link and prep applications here.",
    "indeed": "Link your Indeed sign-in and bring Indeed jobs in by link.",
}
LABELS = {"not_configured": "Not configured", "not_linked": "Ready to connect", "linked": "Connected",
          "reconnect_required": "Reconnect required", "authorization_required": "Provider authorization required",
          "native_only": "Opens in browser"}


def _listing_counts(db: Session, user: User) -> dict[str, int]:
    """How many jobs in the user's feed (new or shortlisted, as Discover shows them) came from each portal, by any
    source they were seen on. Applied and dismissed jobs aren't counted: Discover's feed doesn't list them either."""
    from sqlalchemy import func, or_

    from backend.models import Job, JobSourceLink, UserJob

    out = {}
    for p in PORTALS:
        linked = select(JobSourceLink.id).where(JobSourceLink.job_id == Job.id, JobSourceLink.platform == NAMES[p]).exists()
        out[p] = db.execute(select(func.count(UserJob.id)).join(Job, Job.id == UserJob.job_id)
                            .where(UserJob.user_id == user.id, UserJob.status.in_(["new", "shortlisted"]), or_(Job.platform == NAMES[p], linked))).scalar_one()
    return out


def connections(db: Session | None = None, settings: BackendSettings | None = None, user: User | None = None) -> list[dict[str, Any]]:
    """What JobPilot can and can't do with each portal for this user, as the code and this server's setup support it.

    status: not_configured | not_linked (ready to connect) | linked | reconnect_required | authorization_required (the
    portal refused JobPilot's app in the admin's last real test) | native_only (Naukri: opens in the browser).
    `reason` is the one thing standing in the way, said once; capability details stay short."""
    from backend.services import connection_service, identity_providers, portal_setup_service

    linked: dict[str, ExternalIdentity] = {}
    counts: dict[str, int] = {}
    tests: dict[str, dict[str, Any] | None] = {}
    if db is not None and user is not None:
        linked = {r.provider: r for r in db.execute(select(ExternalIdentity).where(ExternalIdentity.user_id == user.id)).scalars()}
        counts = _listing_counts(db, user)
    if db is not None:
        tests = {p: portal_setup_service.last_test(portal_setup_service._row(db, p)) for p in identity_providers.PROVIDERS}
    is_admin = getattr(user, "role", "user") == "admin"
    out = []
    for p in PORTALS:
        name = NAMES[p]
        prov = identity_providers.get(settings, p, db) if settings is not None else None
        ident = linked.get(p)
        view = connection_service.public(ident, prov) if ident else None
        setup = portal_setup_service.setup_state(prov, tests.get(p)) if prov is not None else None
        reason = None
        if p == "naukri":
            prov_state, prov_detail = "unavailable", SIGN_IN["naukri"]
        elif prov is None or not prov.configured:
            prov_state, prov_detail = "not_configured", "Not set up on this JobPilot server yet."
            reason = (f"{name} sign-in isn't set up on this JobPilot server yet. "
                                    + ("Set it up with your developer app's credentials." if is_admin else
                                       f"A JobPilot admin needs to add {name} developer app credentials."))
        elif setup == "authorization_required":
            prov_state, prov_detail = "authorization_required", f"{name} hasn't accepted JobPilot's app yet."
            reason = (f"{name} refused JobPilot's app in the last test, so connecting won't work yet. "
                                    + ("Check the app in setup, then test again." if is_admin else "A JobPilot admin is sorting it out."))
        else:
            prov_state, prov_detail = "available", SIGN_IN[p]
            if prov.simulated:
                prov_detail = (f"SIMULATED: this server signs in with a local test server, not {name}. "
                               f"It never sees your real {name} account.")
        if p == "naukri":
            status_ = "native_only"
        elif view:
            status_ = view["status"]
        else:
            status_ = {"available": "not_linked"}.get(prov_state, prov_state)
        if view and view["status"] == "reconnect_required":
            reason = view["status_detail"] or f"{name} needs you to sign in again before JobPilot can use the link."
        granted = view["scopes"] if view and view["status"] == "linked" else []
        requested = list(prov.scopes) if prov else []
        limited = bool(granted) and not set(requested) <= set(granted)
        label = LABELS[status_]
        if status_ == "linked" and limited:
            label = "Connected with limited permissions"
        if (view and view.get("simulated")) or (prov and prov.simulated and status_ in ("not_linked", "linked")):
            label += " (simulated)"
        fields = sorted({f for s in granted for f in identity_providers.SCOPE_FIELDS.get(p, {}).get(s, [])})
        n = counts.get(p, 0)
        caps = {
            # Account
            "identity_auth": _cap(prov_state == "available", prov_detail, state=prov_state),
            "account_linked": _cap(bool(view and view["status"] == "linked"),
                                   (f"Linked{' as ' + view['name'] if view and view.get('name') else ''}." if view and view["status"] == "linked" else
                                    "Reconnect to use it again." if view else
                                    "Nothing to link: Naukri has no official sign-in." if p == "naukri" else
                                    "Not linked.")),
            "profile_access": _cap(bool(fields), (f"{', '.join(fields)}. Shown here only; your JobPilot profile stays as you confirmed it."
                                                  if fields else "None." if p == "naukri" or not view else "Nothing shared.")
                                   , fields=fields),
            # Discovery
            "listings": _cap(n > 0, (f"{n} {name} job{'s' if n != 1 else ''} in your JobPilot feed." if n else
                                     f"No {name} jobs in JobPilot yet."), count=n),
            "source": _cap(True, "Paste a job link, use the clipper, or forward job-alert e-mails."),
            "job_retrieval": _cap(False, NO_JOBS_API[p]),
            # Applications
            "application_handoff": _cap(True, "The Apply Workspace keeps your chosen resume and answers and records the outcome you report."),
            "native_handoff": _cap(True, f"Opens the original job on {name} in this browser, so you stay signed in there."),
            "assisted_submission": _cap(False, NO_AUTOMATION[p]),
            "application_submission": _cap(False, NO_SUBMIT_API[p]),
            # Profile improvement
            "profile_guidance": _cap(p != "indeed", ("A checklist built from your confirmed JobPilot profile." if p != "indeed" else
                                                     "Not offered: JobPilot has no verified Indeed profile requirements.")),
            # State
            "reconnect_required": _cap(bool(view and view["status"] == "reconnect_required"),
                                       (view["status_detail"] if view and view["status"] == "reconnect_required" else "No.")),
        }
        actions: list[str] = []
        if p != "naukri" and prov_state == "available":
            actions += ["reconnect", "disconnect"] if view and view["status"] == "reconnect_required" else \
                       ["check", "reconnect", "disconnect"] if view else ["connect"]
        elif view:  # linked earlier, sign-in no longer usable on this server: they can still remove it
            actions.append("disconnect")
        actions += (["optimize"] if p != "indeed" else []) + ["open", "import", "prepare", "browse"]
        if p != "naukri" and is_admin:
            actions.append("setup")
        out.append({"portal": p, "name": name, "url": HOME[p], "kind": "native" if p == "naukri" else "oauth",
                    "simulated": bool(prov and prov.simulated), "summary": SUMMARY[p], "reason": reason,
                    "status": status_, "status_label": label, "limited": limited, "identity": view,
                    "setup_state": setup if is_admin else None,
                    "scopes": {"requested": requested, "granted": granted},
                    "capabilities": caps, "actions": actions})
    return out


# ---- profile review --------------------------------------------------------------------------------------------

def _profile(db: Session, user: User) -> tuple[CandidateProfile | None, EditableProfile | None]:
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    ep = EditableProfile.model_validate(prof.confirmed_profile) if prof and prof.confirmed_profile else None
    return prof, ep


def _item(key: str, label: str, state: str, *, existing: str | None = None, suggestion: str | None = None,
          why: str, copy: bool = False) -> dict[str, Any]:
    return {"key": key, "label": label, "state": state, "existing": existing, "suggestion": suggestion, "why": why, "copy": copy}


def _has_number(s: str) -> bool:
    return bool(re.search(r"\d", s or ""))


def _years(ep: EditableProfile) -> float | None:
    from backend.services.resume_service import experience_summary

    s = experience_summary(ep)
    return s.years if s.months else None


def _current(ep: EditableProfile):
    return next((r for r in ep.experience if r.is_current), ep.experience[0] if ep.experience else None)


def _headline_from_facts(ep: EditableProfile, targets: list[str], limit: int) -> str | None:
    """A headline made only of confirmed facts: current title, target title, top skills."""
    cur = _current(ep)
    parts = []
    if cur and cur.title:
        parts.append(cur.title + (f" at {cur.company}" if cur.company else ""))
    if targets and not any(t.lower() in " ".join(parts).lower() for t in targets[:1]):
        parts.append(f"Seeking {targets[0]} roles")
    if ep.skills:
        parts.append(" · ".join(ep.skills[:4]))
    text = " | ".join(parts)
    return text[:limit].rstrip(" |·") or None


def _quantified(ep: EditableProfile) -> list[str]:
    bullets = [b for r in ep.experience for b in r.bullets] + list(ep.achievements)
    return [b for b in bullets if _has_number(b)]


def review(db: Session, user: User, portal: str) -> dict[str, Any]:
    if portal not in PORTALS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown portal.")
    if portal == "indeed":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "JobPilot doesn't offer an Indeed profile checklist.")
    prof, ep = _profile(db, user)
    if ep is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Confirm your JobPilot profile first: the checklist is built from it.")
    pref = db.execute(select(JobPreference).where(JobPreference.user_id == user.id)).scalar_one_or_none()
    targets = list(pref.job_titles) if pref else []
    places = list(pref.locations) if pref else []
    items = _linkedin(ep, targets, places) if portal == "linkedin" else _naukri(db, user, ep, prof, targets, places, pref)
    done = (prof.portal_review or {}).get(portal, {}) if prof else {}
    for it in items:
        it["done_at"] = (done.get(it["key"]) or {}).get("done_at")
    ok = sum(1 for it in items if it["state"] == "ok" or it["done_at"])
    return {"portal": portal, "name": NAMES[portal], "items": items, "completeness": round(100 * ok / len(items)) if items else 0,
            "source": "Built from your confirmed JobPilot profile and preferences. JobPilot never changes your profile on " + NAMES[portal] + "."}


def _linkedin(ep: EditableProfile, targets: list[str], places: list[str]) -> list[dict[str, Any]]:
    items = []
    head = (ep.headline or "").strip()
    sugg = _headline_from_facts(ep, targets, LINKEDIN_HEADLINE)
    if not head:
        items.append(_item("headline", "Headline", "missing", suggestion=sugg, copy=bool(sugg),
                           why=f"Your headline shows next to your name everywhere on LinkedIn (up to {LINKEDIN_HEADLINE} characters)."))
    elif len(head) > LINKEDIN_HEADLINE:
        items.append(_item("headline", "Headline", "improve", existing=head, suggestion=head[:LINKEDIN_HEADLINE].rstrip(), copy=True,
                           why=f"LinkedIn allows {LINKEDIN_HEADLINE} characters; yours has {len(head)}."))
    elif targets and not any(t.lower() in head.lower() for t in targets):
        items.append(_item("headline", "Headline", "improve", existing=head, suggestion=sugg, copy=bool(sugg),
                           why=f"It doesn't mention the role you're after ({targets[0]}). Recruiters search by title."))
    else:
        items.append(_item("headline", "Headline", "ok", existing=head, why="Has your target role and fits LinkedIn's limit."))

    summary = (ep.summary or "").strip()
    if not summary:
        items.append(_item("about", "About section", "missing",
                           why=f"Write a few lines in your own words: what you do, for whom, and a result you're proud of (up to {LINKEDIN_ABOUT} characters). "
                               "JobPilot won't write achievements for you."))
    elif len(summary) > LINKEDIN_ABOUT:
        items.append(_item("about", "About section", "improve", existing=summary[:300] + "…",
                           why=f"LinkedIn allows {LINKEDIN_ABOUT} characters; yours has {len(summary)}. Shorten it."))
    else:
        items.append(_item("about", "About section", "ok", existing=summary, suggestion=summary, copy=True,
                           why="Your confirmed summary. Paste it into About if it isn't there yet."))

    bare = [f"{r.title} at {r.company}" for r in ep.experience if not [b for b in r.bullets if b.strip()]]
    if not ep.experience:
        items.append(_item("experience", "Experience", "missing", why="Add your roles to your JobPilot profile first."))
    elif bare:
        items.append(_item("experience", "Experience", "improve", existing=", ".join(bare),
                           why="These roles have no description. Add what you did there, in your words, on LinkedIn and in JobPilot."))
    else:
        items.append(_item("experience", "Experience", "ok", why="Every role has a description."))

    q = _quantified(ep)
    items.append(_item("achievements", "Quantified achievements", "ok" if len(q) >= 2 else "improve",
                       existing="\n".join(q[:6]) or None, suggestion="\n".join(f"• {b}" for b in q[:6]) or None, copy=bool(q),
                       why=("Results with numbers, from your confirmed profile. Use them in About or under each role." if q else
                            "None of your confirmed bullets has a number. Add real figures (volumes, time saved, accuracy) where you have them.")))

    items.append(_item("skills", "Skills", "ok" if len(ep.skills) >= 5 else "improve", existing=", ".join(ep.skills) or None,
                       suggestion=", ".join(ep.skills[:15]) or None, copy=bool(ep.skills),
                       why="Your confirmed skills. Add the ones you use most to LinkedIn's Skills section." if ep.skills else
                           "Add your skills to your JobPilot profile first."))

    loc = (ep.location or "").strip()
    if not loc:
        items.append(_item("location", "Location", "missing", why="Recruiters filter by location. Add yours to your JobPilot profile."))
    elif places and not any(p.split(" -")[0].lower() in loc.lower() or "remote" in p.lower() for p in places):
        items.append(_item("location", "Location", "improve", existing=loc,
                           why=f"You're looking in {', '.join(places[:3])}. If you're open to it, say so in your headline or About."))
    else:
        items.append(_item("location", "Location", "ok", existing=loc, why="Matches where you're looking."))

    items.append(_item("target_titles", "Target job titles", "ok" if targets else "missing", existing=", ".join(targets) or None,
                       suggestion=", ".join(targets[:5]) or None, copy=bool(targets),
                       why="Add these to LinkedIn's 'Open to work' job titles." if targets else "Set the titles you want in Job preferences."))
    return items


def _naukri(db: Session, user: User, ep: EditableProfile, prof: CandidateProfile | None, targets: list[str], places: list[str],
            pref: JobPreference | None) -> list[dict[str, Any]]:
    from backend.services import resume_service

    items = []
    years = _years(ep)
    cur = _current(ep)
    bits = []
    if cur and cur.title:
        bits.append(cur.title)
    if years:
        bits.append(f"{years:g} years' experience")
    if ep.skills:
        bits.append(", ".join(ep.skills[:5]))
    if targets and (not cur or targets[0].lower() not in (cur.title or "").lower()):
        bits.append(f"looking for {targets[0]} roles")
    sugg = (" with ".join(bits[:2]) + (" in " + bits[2] if len(bits) > 2 else "") + ("; " + bits[3] if len(bits) > 3 else ""))[:NAUKRI_HEADLINE] if bits else None
    head = (ep.headline or "").strip()
    items.append(_item("resume_headline", "Resume headline", "improve" if head and len(head) < 60 else "missing" if not head else "ok",
                       existing=head or None, suggestion=sugg, copy=bool(sugg),
                       why=f"Recruiters see it first in search results. Naukri allows {NAUKRI_HEADLINE} characters: use them for your role, "
                           "experience and main skills."))
    summary = (ep.summary or "").strip()
    items.append(_item("profile_summary", "Profile summary", "ok" if summary else "missing", existing=summary or None,
                       suggestion=summary or None, copy=bool(summary),
                       why="Your confirmed summary, ready to paste." if summary else "Write a short summary in your own words; JobPilot won't invent one."))
    items.append(_item("key_skills", "Key skills", "ok" if len(ep.skills) >= 5 else "improve", existing=", ".join(ep.skills) or None,
                       suggestion=", ".join(ep.skills) or None, copy=bool(ep.skills),
                       why="Recruiters search Naukri by key skills. Add the ones from your confirmed profile, one by one."))
    undated = [f"{r.title} at {r.company}" for r in ep.experience if not r.start]
    items.append(_item("employment", "Employment details", "missing" if not ep.experience else "improve" if undated else "ok",
                       existing=", ".join(undated) or None,
                       why=("Add your roles to your JobPilot profile first." if not ep.experience else
                            "These roles have no start date. Naukri asks for joining dates for each job." if undated else
                            "Every role has dates. Keep your current employer and designation up to date.")))
    items.append(_item("desired_titles", "Desired job titles", "ok" if targets else "missing", existing=", ".join(targets) or None,
                       suggestion=", ".join(targets[:5]) or None, copy=bool(targets),
                       why="Put these in Naukri's desired career profile." if targets else "Set the titles you want in Job preferences."))
    items.append(_item("preferred_location", "Preferred locations", "ok" if places else "missing", existing=", ".join(places) or None,
                       suggestion=", ".join(places[:5]) or None, copy=bool(places),
                       why="Naukri matches jobs to your preferred locations." if places else "Set your locations in Job preferences."))
    facts = (prof.verified_facts or {}) if prof else {}
    has_ctc = bool(facts.get("expected_ctc")) or bool(pref and pref.salary_min)
    items.append(_item("expected_salary", "Expected salary", "ok" if has_ctc else "missing",
                       why="Set in JobPilot (not shown here: it's private). Enter it on Naukri yourself." if has_ctc else
                           "Add your expected salary in Settings → Verified answers, then on Naukri."))
    items.append(_item("notice_period", "Notice period", "ok" if facts.get("notice_period") else "missing",
                       existing=str(facts.get("notice_period")) if facts.get("notice_period") else None,
                       why="Recruiters on Naukri filter by notice period. Keep it current."))
    resume = resume_service.active_resume(db, user)
    if resume is None:
        items.append(_item("resume_fresh", "Resume", "missing", why="Upload your resume to JobPilot, then the same file to Naukri."))
    else:
        uploaded = resume.uploaded_at if resume.uploaded_at.tzinfo else resume.uploaded_at.replace(tzinfo=utcnow().tzinfo)
        age = (utcnow() - uploaded).days
        items.append(_item("resume_fresh", "Resume", "improve" if age > 90 else "ok", existing=f"{resume.original_filename}, uploaded {age} days ago",
                           why=("Your resume is over three months old. Update it, then upload the same file to Naukri." if age > 90 else
                                "Recent. Make sure Naukri has this same version.")))
    return items


def mark(db: Session, user: User, portal: str, key: str, done: bool) -> dict[str, Any]:
    if portal not in ("linkedin", "naukri"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown portal.")
    keys = {it["key"] for it in review(db, user, portal)["items"]}
    if key not in keys:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown checklist item.")
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one()
    data = {k: dict(v) for k, v in (prof.portal_review or {}).items()}
    section = data.setdefault(portal, {})
    if done:
        section[key] = {"done_at": utcnow().isoformat()}
    else:
        section.pop(key, None)
    prof.portal_review = data
    db.commit()
    return review(db, user, portal)
