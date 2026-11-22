"""Portal Connections and portal profile review (LinkedIn, Naukri, Indeed).

Three separate things, never mixed up:
  * job source      how jobs from the portal can reach JobPilot (links you paste, alert e-mails, the clipper)
  * account connection  an approved sign-in with the portal: none exists today, so nothing is ever "connected"
  * application     how you apply: on the portal itself (native hand-off); JobPilot never fills or submits there

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

from backend.models import CandidateProfile, JobPreference, User, utcnow
from backend.schemas.profile import EditableProfile

PORTALS = ("linkedin", "naukri", "indeed")
NAMES = {"linkedin": "LinkedIn", "naukri": "Naukri", "indeed": "Indeed"}
HOME = {"linkedin": "https://www.linkedin.com/jobs/", "naukri": "https://www.naukri.com/", "indeed": "https://in.indeed.com/"}
LINKEDIN_HEADLINE, LINKEDIN_ABOUT, NAUKRI_HEADLINE = 220, 2600, 250
NO_CONNECTION = {
    "linkedin": "LinkedIn's job and apply APIs are open only to approved partners. JobPilot has no approved connection, so it never signs in to LinkedIn or reads your account.",
    "naukri": "Naukri offers no approved connection for tools like JobPilot. JobPilot never signs in to Naukri or reads your account.",
    "indeed": "Indeed offers no approved connection for tools like JobPilot. JobPilot never signs in to Indeed or reads your account.",
}
NO_AUTOMATION = {
    "linkedin": "LinkedIn's rules forbid tools that automate activity on its site, including Easy Apply. You apply there yourself.",
    "naukri": "Naukri's terms forbid automated tools on its site. You apply there yourself.",
    "indeed": "Indeed's terms forbid automating Indeed Apply. You apply there yourself.",
}


def connections() -> list[dict[str, Any]]:
    """What JobPilot can and can't do with each portal, as the code actually supports it."""
    out = []
    for p in PORTALS:
        out.append({
            "portal": p, "name": NAMES[p], "url": HOME[p],
            "capabilities": {
                "source": {"available": True, "detail": "Jobs reach JobPilot when you paste a job link, forward its alert e-mails, or use the clipper."},
                "profile_guidance": {"available": p != "indeed",
                                     "detail": ("A checklist for your profile there, built from your confirmed JobPilot profile." if p != "indeed" else
                                                "Not offered: JobPilot doesn't have verified Indeed profile requirements, so it gives no Indeed checklist.")},
                "account_connection": {"available": False, "status": "unavailable", "detail": NO_CONNECTION[p]},
                "application_handoff": {"available": True, "detail": "The Apply Workspace prepares your resume and answers, opens the job there, and tracks the outcome you report."},
                "assisted_submission": {"available": False, "detail": NO_AUTOMATION[p]},
            },
            "actions": (["optimize"] if p != "indeed" else []) + ["open", "import"],
        })
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
