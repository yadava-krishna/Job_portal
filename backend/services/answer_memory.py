"""Answer memory: questions application forms keep asking, answered once by the user and reused where they fit.

Deterministic only (no AI model). A question is normalised and mapped to a canonical key from CATALOGUE:

    "How many years of Python experience do you have?"      -> experience_years.python
    "Total professional Python experience?"                  -> experience_years.python
    "Python development experience in years?"                -> experience_years.python
    "Years working professionally with Python?"              -> experience_years.python
    "Total software experience"                              -> experience_years.software      (a different answer)
    "Total experience including internships"                 -> experience_years.total.incl_internships
    "Are you authorised to work in the United States?"       -> work_authorization.us        (per country)
    "Have you worked for this company before?"               -> previously_employed (this employer only)

Rules that keep it honest:
  * sensitive questions (gender, ethnicity, disability, date of birth, ID numbers...) are never answered or stored;
  * a question about someone else (referrer, emergency contact, "this company's website") is not mapped to the
    user's own details;
  * nothing is invented: an answer is VERIFIED only when the user confirmed it (here, or in Settings), SUGGESTED when
    worked out from the confirmed profile or resume, otherwise NEEDS_INPUT;
  * time-dependent answers (salary, notice period, start date) carry a revalidation period and come back as
    SUGGESTED ("check it's still right") once it has passed;
  * a question that mixes two topics, or a long unrecognised subject, is never auto-reused;
  * answers are saved only on an explicit user action, with type and unit validation; private answers (salary,
    work authorisation, sponsorship) are stored encrypted.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import AnswerMemory, CandidateProfile, User, utcnow

# ---- normalisation ---------------------------------------------------------------------------

_ZERO_WIDTH = re.compile("[​-‍⁠﻿]")


def normalize(question: str) -> str:
    """Lower case, zero-width characters and punctuation to spaces (so word boundaries survive), single spaces."""
    q = _ZERO_WIDTH.sub(" ", str(question or "")).lower()
    q = re.sub(r"\((optional|required)\)|[*✱]", " ", q)
    q = q.replace("’", "'").replace("–", "-").replace("—", "-")
    q = re.sub(r"[^a-z0-9+#.'/& -]+", " ", q)
    q = re.sub(r"(?<![a-z0-9])[.'/-]+|[.'/-]+(?![a-z0-9])", " ", q)
    return re.sub(r"\s+", " ", q).strip()


# ---- the catalogue ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Canon:
    key: str
    label: str
    group: str  # personal | professional | preferences | eligibility | links | other
    value_type: str  # text | number | boolean | money | days | date_text | url | email | phone | choice
    unit: str | None = None
    sensitivity: str = "personal"  # public | personal | private
    commitment: bool = False  # the user ticks it before an assisted submission
    revalidate_days: int | None = None  # time-dependent: re-confirm after this many days
    scope: str = "global"  # global | company | job
    fact_key: str | None = None  # legacy Settings -> Verified answers key, kept in step
    profile_key: str | None = None  # value derivable from the confirmed profile (offered as SUGGESTED)
    patterns: tuple[str, ...] = ()
    guards: tuple[str, ...] = ()  # if any matches, the question is not this field


def _c(*args, **kw) -> Canon:
    return Canon(*args, **kw)


THIRD_PARTY = r"\b(referr\w*|referral (name|email|contact)|emergency|reference\b|references\b|manager'?s|supervisor'?s|spouse|parent'?s|guardian)\b"
THIS_EMPLOYER = r"\b(this|the|our|that) (company|employer|organi[sz]ation|team|role|position|job|office)\b"

CATALOGUE: tuple[Canon, ...] = (
    # personal (from the confirmed profile; remembered only if the user overrides them for forms)
    _c("full_name", "Full name", "personal", "text", profile_key="full_name",
       patterns=(r"^(your |candidate |applicant )?(full |legal |complete )?name$",), guards=(THIRD_PARTY,)),
    _c("first_name", "First name", "personal", "text", profile_key="first_name", patterns=(r"^(legal )?(first|given) name$", r"^forename$")),
    _c("last_name", "Last name", "personal", "text", profile_key="last_name", patterns=(r"^(legal )?(last|family) name$", r"^surname$")),
    _c("email", "Email", "personal", "email", profile_key="email", patterns=(r"^(your )?e ?-?mail( address| id)?$",), guards=(THIRD_PARTY,)),
    _c("phone", "Phone", "personal", "phone", profile_key="phone",
       patterns=(r"^(your )?(phone|mobile|contact|cell|telephone)( phone)?( number| no)?$",), guards=(THIRD_PARTY, r"\bmobile (app|dev|engineer)")),
    _c("current_location", "Current location", "personal", "text", profile_key="location",
       patterns=(r"\bcurrent (location|city)\b", r"\bwhere are you (currently )?(based|located)\b", r"\bcity of residence\b",
                 r"^(your )?location$", r"\bcurrently (based|located|living)\b"), guards=(THIS_EMPLOYER, r"\boffice location\b")),
    _c("country", "Country of residence", "personal", "text", profile_key="country",
       patterns=(r"^(current )?country( of residence)?$", r"\bwhich country do you (live|reside)\b")),
    # links
    _c("linkedin_url", "LinkedIn profile", "links", "url", profile_key="linkedin_url", patterns=(r"\blinked ?in\b",), guards=(THIRD_PARTY,)),
    _c("github_url", "GitHub profile", "links", "url", profile_key="github_url", patterns=(r"\bgit ?hub\b",), guards=(THIRD_PARTY,)),
    _c("portfolio_url", "Portfolio", "links", "url", profile_key="portfolio_url", patterns=(r"\bportfolio\b", r"\bwork samples?\b"), guards=(THIRD_PARTY,)),
    _c("website_url", "Personal website", "links", "url", profile_key="website_url",
       patterns=(r"^(personal )?(website|web site|blog|homepage)( url| link)?$",), guards=(THIRD_PARTY, THIS_EMPLOYER)),
    # professional
    _c("current_title", "Current job title", "professional", "text", profile_key="current_title",
       patterns=(r"\bcurrent (job )?(title|designation|role|position)\b", r"\bmost recent (job )?title\b"), guards=(THIS_EMPLOYER,)),
    _c("current_company", "Current employer", "professional", "text", profile_key="current_company",
       patterns=(r"\b(current|present|most recent) (company|employer|organi[sz]ation)\b", r"\bwhere do you (currently )?work\b"),
       guards=(THIS_EMPLOYER,)),
    _c("highest_qualification", "Highest qualification", "professional", "text", profile_key="degree",
       patterns=(r"\bhighest (level of )?(education|qualification|degree)\b", r"^(highest )?qualification$", r"^degree$")),
    _c("notice_period", "Notice period", "professional", "days", unit="days", commitment=True, revalidate_days=30,
       fact_key="notice_period", patterns=(r"\bnotice ?period\b", r"\bserving (your )?notice\b", r"\blast working day\b")),
    _c("current_ctc", "Current compensation", "professional", "money", unit="currency_per_year", sensitivity="private",
       commitment=True, revalidate_days=90, fact_key="current_ctc",
       patterns=(r"\b(current|present|existing|last drawn) ((annual|fixed|total|base|gross|yearly) )*(ctc|salary|compensation|pay|package)\b",
                 r"^ctc$")),
    _c("expected_ctc", "Expected compensation", "professional", "money", unit="currency_per_year", sensitivity="private",
       commitment=True, revalidate_days=60, fact_key="expected_ctc",
       patterns=(r"\b(expected|desired|target) (annual )?(ctc|salary|compensation|pay|package)\b", r"\bsalary (expectation|requirement)s?\b",
                 r"\bcompensation (expectation|requirement)s?\b", r"\bexpectations? (on|for|regarding) (salary|compensation|ctc)\b")),
    _c("earliest_start_date", "Earliest start date", "professional", "date_text", commitment=True, revalidate_days=14,
       fact_key="earliest_start_date",
       patterns=(r"\b(earliest )?start ?date\b", r"\bjoining date\b", r"\bwhen can you (start|join)\b", r"\bavailab\w* to (start|join)\b",
                 r"\bhow soon can you (start|join)\b", r"\bdate available\b")),
    # preferences
    _c("willing_to_relocate", "Willing to relocate", "preferences", "boolean", commitment=True, fact_key="willing_to_relocate",
       patterns=(r"\brelocat\w*\b",)),
    _c("willing_to_travel", "Willing to travel", "preferences", "boolean",
       patterns=(r"\bwilling(ness)? to travel\b", r"\bcomfortable (with )?travel\w*\b", r"\bopen to travel\w*\b", r"\btravel (requirement|up to)\b")),
    _c("work_mode_preference", "Preferred work mode", "preferences", "choice",
       patterns=(r"\b(preferred )?work (mode|arrangement|setup|model)\b", r"\b(remote|hybrid|on ?site|in ?office) (or|/) (remote|hybrid|on ?site|in ?office)\b")),
    _c("preferred_location", "Preferred job location", "preferences", "text",
       patterns=(r"\bpreferred (job |work )?(location|city)\b", r"\blocation preference\b")),
    _c("shift_flexibility", "Shift flexibility", "preferences", "text", fact_key="shift_flexibility",
       patterns=(r"\b(night|rotational|rotating|us|uk|evening) shifts?\b", r"\bshift (timings|flexibility)\b")),
    _c("referral_source", "How you heard about the job", "other", "text",
       patterns=(r"\bhow did you (hear|find out|learn|come to know) about\b", r"\bwhere did you (hear|find|see|learn) (about )?(this|us|the)\b")),
    # eligibility (per country when the question names one)
    _c("work_authorization", "Authorised to work", "eligibility", "boolean", sensitivity="private", commitment=True,
       fact_key="work_authorization",
       patterns=(r"\b(legally )?(authori[sz]ed|eligible|entitled|permitted) to work\b", r"\bwork (authori[sz]ation|permit)\b", r"\bright to work\b")),
    _c("requires_sponsorship", "Needs visa sponsorship", "eligibility", "boolean", sensitivity="private", commitment=True,
       fact_key="requires_sponsorship", patterns=(r"\bsponsor\w*\b", r"\bh-?1b\b", r"\bvisa (support|transfer)\b")),
    # employer-specific: never reused for another employer
    _c("previously_employed", "Worked for this employer before", "other", "boolean", scope="company",
       patterns=(r"\b(previously|ever|before) (worked|been employed|employed)\b.*\b(for|at|with|by)\b", r"\bformer employee\b",
                 r"\bworked (here|for us) before\b", r"\bhave you worked (for|at) (this|our|the) company\b")),
)
BY_KEY = {c.key: c for c in CATALOGUE}

# Experience questions are parameterised by their subject ("python", "software", total).
EXPERIENCE = Canon("experience_years", "Years of experience", "professional", "number", unit="years", revalidate_days=180,
                   profile_key="total_experience_years")
HAS_EXPERIENCE = Canon("has_experience", "Has experience with", "professional", "boolean")
RELEVANT_EXPERIENCE = Canon("experience_years.relevant", "Relevant experience (years)", "professional", "number", unit="years",
                            scope="job")

NEVER = re.compile(
    r"\b(gender|pronoun|sex|sexual|orientation|race|racial|ethnic\w*|hispanic|latin[oa]|veteran|disabilit\w*|religio\w*|caste|"
    r"date of birth|birth ?date|dob|age|marital|nationality|citizenship number|passport|aadhaar|aadhar|pan (card|number|no)|"
    r"ssn|social security|national insurance|criminal|convict\w*|arrest\w*|salary history|bank|account number|ifsc|"
    r"password|otp|captcha)\b")

COUNTRIES = (
    ("us", r"\b(united states|u\.?s\.?a?|america)\b"), ("uk", r"\b(united kingdom|u\.?k|britain|great britain|england)\b"),
    ("in", r"\bindia\b"), ("ca", r"\bcanada\b"), ("de", r"\bgermany\b"), ("au", r"\baustralia\b"), ("sg", r"\bsingapore\b"),
    ("ie", r"\bireland\b"), ("nl", r"\b(netherlands|holland)\b"), ("ae", r"\b(uae|united arab emirates|dubai)\b"),
    ("fr", r"\bfrance\b"), ("eu", r"\b(european union|eu|eea|schengen)\b"),
)
COUNTRY_NAMES = {"us": "the United States", "uk": "the United Kingdom", "in": "India", "ca": "Canada", "de": "Germany",
                 "au": "Australia", "sg": "Singapore", "ie": "Ireland", "nl": "the Netherlands", "ae": "the UAE", "fr": "France",
                 "eu": "the EU"}

SUBJECT_ALIASES = {
    "py": "python", "python3": "python", "js": "javascript", "java script": "javascript", "ts": "typescript", "golang": "go",
    "k8s": "kubernetes", "postgres": "postgresql", "node": "nodejs", "node.js": "nodejs", "node js": "nodejs", "react.js": "react",
    "reactjs": "react", "react js": "react", "vue.js": "vue", "ms excel": "excel", "microsoft excel": "excel", "advanced excel": "excel",
    "ml": "machine learning", "ai": "artificial intelligence", "software development": "software", "software engineering": "software",
    "c sharp": "c#", "dotnet": ".net", "power bi": "power bi", "powerbi": "power bi", "amazon web services": "aws",
    "accounts receivable": "accounts receivable", "ar": "accounts receivable", "fp&a": "fp&a", "fpa": "fp&a",
}
_EXP_FILLER = {
    "how", "many", "much", "years", "year", "yrs", "yr", "of", "do", "you", "have", "has", "total", "overall", "professional",
    "professionally", "hands-on", "hands", "on", "work", "working", "worked", "experience", "experiences", "with", "in", "using",
    "as", "a", "an", "the", "your", "what", "is", "are", "number", "please", "enter", "specify", "state", "mention", "industry",
    "practical", "commercial", "combined", "approximately", "approx", "including", "excluding", "internship", "internships",
    "relevant", "related", "development", "developing", "field", "domain", "area", "and", "or", "at", "least", "minimum", "full-time",
    "full", "time", "paid", "post", "qualification", "graduation", "graduating", "after", "since", "degree", "qualifying", "post-qualification", "post-graduation", "do", "does", "s", "'s", "worth", "level", "role", "roles", "position", "positions",
}


@dataclass
class Match:
    key: str | None
    canon: Canon | None
    confidence: float = 0.0
    never: bool = False
    reason: str | None = None
    country: str | None = None
    subject: str | None = None
    qualifier: str | None = None
    label: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def scope(self) -> str:
        return self.canon.scope if self.canon else "global"  # unknown questions: remembered by their exact wording


def _country(q: str) -> str | None:
    hits = [cc for cc, rx in COUNTRIES if re.search(rx, q)]
    return hits[0] if len(hits) == 1 else None


def _subject(q: str) -> tuple[str | None, int]:
    """The technology/domain an experience question is about, after removing filler words ("" = total)."""
    words = re.findall(r"[a-z0-9+#.&-]+", q)
    rest = [w for w in words if w not in _EXP_FILLER and not re.fullmatch(r"\d+(\.\d+)?\+?", w)]
    phrase = " ".join(rest).strip(" .-")
    if not phrase:
        return "", 0
    phrase = SUBJECT_ALIASES.get(phrase, phrase)
    return phrase, len(phrase.split())


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9+#.&]+", "_", s).strip("_")[:60]


def classify(question: str, *, page_country: str | None = None) -> Match:
    """Map one form question to a canonical key (or say it is sensitive / unknown). Pure function."""
    q = normalize(question)
    if not q:
        return Match(None, None, reason="empty question")
    if NEVER.search(q) and not re.search(r"\b(sponsor\w*|authori[sz]\w*|eligible to work|work permit)\b", q):
        return Match(None, None, never=True, confidence=1.0,
                     reason="Sensitive personal question: JobPilot never answers or stores it. Answer it yourself.")

    # Experience: "years of X experience", "X experience in years", "experience with X", "including internships".
    exp_q = re.search(r"\bexperience\b|\byoe\b|\byears? (of )?(working|work)\b|\byears? working\b", q)
    if exp_q and not re.search(r"\b(describe|tell us|explain|share|why|example|summar)\w*\b", q):
        asks_years = bool(re.search(r"\b(how many|number of|years?|yrs|yoe|total|overall)\b|\binclud\w* internships?\b", q))
        incl = ("incl_internships" if re.search(r"\binclud\w* internships?\b|\binternships? included\b", q) else
                "post_qualification" if re.search(r"\bpost[ -]?(qualification|graduation|degree)\b|\bafter (your )?(graduation|graduating|degree|qualifying|qualification)\b|\bsince (graduation|graduating)\b", q)
                else None)
        relevant = bool(re.search(r"\b(relevant|related)\b", q))
        subj, n = _subject(q)
        if relevant:
            return Match("experience_years.relevant", RELEVANT_EXPERIENCE, 0.85, label="Relevant experience (years)", subject="relevant",
                         notes=["Depends on the job: remembered for this application only."])
        if asks_years:
            subject = subj or "total"
            conf = 0.9 if n <= 3 else 0.55
            key = f"experience_years.{_slug(subject)}" + (f".{incl}" if incl else "")
            if incl == "post_qualification" and subject in ("after graduation", "graduation", "after graduating", "since graduation"):
                subject, key = "total", "experience_years.total.post_qualification"
            label = ("Total experience (years)" if subject == "total" else f"{subject.title()} experience (years)") + \
                    {"incl_internships": ", including internships", "post_qualification": ", after your qualification"}.get(incl or "", "")
            return Match(key, EXPERIENCE, conf, subject=subject, qualifier=incl, label=label)
        if subj and n <= 3 and re.search(r"\b(do you have|have you|any)\b", q):
            return Match(f"has_experience.{_slug(subj)}", HAS_EXPERIENCE, 0.85, subject=subj, label=f"Experience with {subj}")

    hits: list[Canon] = []
    for c in CATALOGUE:
        if any(re.search(p, q) for p in c.patterns) and not any(re.search(g, q) for g in c.guards):
            hits.append(c)
    # "authorised to work ... without sponsorship" is one question about authorisation, not two.
    if {h.key for h in hits} == {"work_authorization", "requires_sponsorship"}:
        hits = [BY_KEY["requires_sponsorship"]] if re.search(r"\b(require|need)\w*\b.*\bsponsor", q) else [BY_KEY["work_authorization"]]
    if not hits:
        return Match(None, None, reason="Not a question JobPilot recognises yet.")
    canon = hits[0]
    conf = 0.92 if len(hits) == 1 else 0.5  # two topics in one question: never auto-reused
    m = Match(canon.key, canon, conf, label=canon.label)
    if len(hits) > 1:
        m.notes.append("This question mixes several topics (" + ", ".join(h.label.lower() for h in hits) + "). Check the answer.")
    if canon.key in ("work_authorization", "requires_sponsorship"):
        cc = _country(q) or page_country
        if cc:
            m.key, m.country = f"{canon.key}.{cc}", cc
            m.label = f"{canon.label} in {COUNTRY_NAMES[cc]}"
    if canon.key == "willing_to_relocate" and re.search(r"\brelocat\w* to\b", q):
        m.confidence = min(m.confidence, 0.7)
        m.notes.append("Asks about a specific place: check the answer fits.")
    if canon.key == "expected_ctc" and re.search(r"\b(per|a|each) (month|hour)\b|\bmonthly\b|\bhourly\b", q):
        m.notes.append("Asks for a monthly or hourly figure: your saved answer is yearly.")
        m.confidence = min(m.confidence, 0.6)
    return m


def page_country(questions: list[str]) -> str | None:
    """A country named by an authorisation/sponsorship question on the same form applies to the bare ones too."""
    found = {_country(normalize(q)) for q in questions if re.search(r"authori|sponsor|eligible to work|work permit|visa", normalize(q))}
    found.discard(None)
    return found.pop() if len(found) == 1 else None


# ---- values: parse, validate, display --------------------------------------------------------

class InvalidAnswer(ValueError):
    pass


_NUM_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
              "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "half": 0.5}
_YES = {"yes", "y", "true", "1", "yeah", "yep", "sure", "ok", "i am", "i do", "i will"}
_NO = {"no", "n", "false", "0", "nope", "i am not", "i do not", "i don't", "i will not"}


def _number(text: str) -> float | None:
    t = text.lower().replace(",", "")
    for w, n in _NUM_WORDS.items():
        t = re.sub(rf"\b{w}\b", str(n), t)
    m = re.search(r"\d+(\.\d+)?", t)
    return float(m.group()) if m else None


def parse(value_type: str, raw: Any) -> tuple[Any, str]:
    """(typed value, display text) or InvalidAnswer with a plain message."""
    text = " ".join(str(raw if raw is not None else "").split())
    if not text:
        raise InvalidAnswer("Enter an answer.")
    low = text.lower()
    if value_type == "boolean":
        if isinstance(raw, bool):
            return raw, "Yes" if raw else "No"
        if low.rstrip(".!") in _YES or low.startswith("yes"):
            return True, "Yes"
        if low.rstrip(".!") in _NO or low.startswith("no"):
            return False, "No"
        raise InvalidAnswer("Answer Yes or No.")
    if value_type == "number":
        if re.search(r"\d+\s*(-|to)\s*\d+", low):
            raise InvalidAnswer("Give one number, not a range.")
        n = _number(low)
        if n is None:
            raise InvalidAnswer("Enter a number of years, for example 3 or 4.5.")
        if re.search(r"\bmonths?\b", low) and not re.search(r"\byears?\b", low):
            n = round(n / 12, 1)
        if not 0 <= n <= 60:
            raise InvalidAnswer("Years of experience must be between 0 and 60.")
        n = round(n, 1)
        return n, f"{n:g}"
    if value_type == "days":
        if re.search(r"\b(immediate\w*|now|right away|already serving|not serving|no notice)\b", low) and not re.search(r"\d", low):
            return 0, "Immediate"
        n = _number(low)
        if n is None:
            raise InvalidAnswer("Enter the notice period, for example 30 days, 2 months or Immediate.")
        days = n * (30 if re.search(r"\bmonths?\b", low) else 7 if re.search(r"\bweeks?\b", low) else 1)
        days = int(round(days))
        if not 0 <= days <= 365:
            raise InvalidAnswer("A notice period must be between 0 and 365 days.")
        return days, "Immediate" if days == 0 else f"{days} days"
    if value_type == "money":
        return _money(text)
    if value_type == "url":
        u = text if re.match(r"^https?://", low) else "https://" + text
        if not re.match(r"^https?://[a-z0-9.-]+\.[a-z]{2,}(/\S*)?$", u, re.I):
            raise InvalidAnswer("Enter a web address, for example https://github.com/yourname.")
        return u, u
    if value_type == "email":
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", low):
            raise InvalidAnswer("Enter an email address.")
        return text, text
    if value_type == "phone":
        if len(re.sub(r"\D", "", text)) < 7:
            raise InvalidAnswer("Enter a phone number with at least 7 digits.")
        return text, text
    if len(text) > 2000:
        raise InvalidAnswer("Keep the answer under 2000 characters.")
    return text, text


def _money(text: str) -> tuple[dict[str, Any], str]:
    low = text.lower().replace(",", "")
    if re.search(r"\d+\s*(-|to)\s*\d+", low):
        raise InvalidAnswer("Give one figure, not a range (forms usually ask for a single number).")
    n = _number(low)
    if n is None:
        raise InvalidAnswer("Enter an amount, for example 12 LPA, ₹12,00,000 or $120,000.")
    currency = ("USD" if ("$" in text or "usd" in low) else "EUR" if ("€" in text or "eur" in low) else
                "GBP" if ("£" in text or "gbp" in low) else "INR")
    if re.search(r"\b(lpa|lakhs?|lacs?|l)\b|\d\s*l\b", low):
        n *= 100_000
    elif re.search(r"\b(cr|crore)s?\b", low):
        n *= 10_000_000
    elif re.search(r"\d\s*k\b|\bk\b|thousand", low):
        n *= 1000
    period = "month" if re.search(r"\b(per|a|/)\s*month\b|\bmonthly\b|\bpm\b", low) else "year"
    if n <= 0 or n > 10**10:
        raise InvalidAnswer("That amount doesn't look right.")
    value = {"amount": round(n, 2), "currency": currency, "period": period}
    return value, money_display(value)


def money_display(v: dict[str, Any]) -> str:
    amt, cur, per = v["amount"], v["currency"], v.get("period", "year")
    if cur == "INR" and per == "year" and amt >= 100_000:
        return f"{amt / 100_000:g} LPA"
    sym = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(cur, cur + " ")
    return f"{sym}{amt:,.0f}" + (" per month" if per == "month" else "")


# ---- storage ---------------------------------------------------------------------------------

def _cipher(settings):
    from backend.security import CredentialCipher

    return CredentialCipher(settings)


def _scope_ref(scope: str, company: str | None, job_id: int | None) -> str:
    if scope == "company":
        return "company:" + normalize(company or "")[:180] if company else ""
    if scope == "job":
        return f"job:{job_id}" if job_id else ""
    return ""


def custom_key(question: str) -> str:
    """Questions JobPilot has no canonical key for are remembered by their exact normalised wording."""
    return "custom." + hashlib.sha1(normalize(question).encode()).hexdigest()[:16]


def rows_for(db: Session, user: User) -> dict[tuple[str, str], AnswerMemory]:
    return {(r.key, r.scope_ref): r for r in db.execute(select(AnswerMemory).where(AnswerMemory.user_id == user.id)).scalars()}


def display_of(row: AnswerMemory, settings) -> str | None:
    if row.value_encrypted:
        return _cipher(settings).decrypt(row.value_encrypted)
    return row.value_text


def value_of(row: AnswerMemory, settings) -> Any:
    if row.value_encrypted:
        import json

        plain = _cipher(settings).decrypt(row.value_encrypted)
        try:
            return json.loads(plain or "null").get("value")
        except (ValueError, AttributeError):
            return None
    return row.value_json


def _is_stale(row: AnswerMemory) -> bool:
    if not row.revalidate_days or not row.last_confirmed_at:
        return False
    last = row.last_confirmed_at if row.last_confirmed_at.tzinfo else row.last_confirmed_at.replace(tzinfo=utcnow().tzinfo)
    return utcnow() - last > timedelta(days=row.revalidate_days)


def save(db: Session, settings, user: User, *, question: str, answer: Any, key: str | None = None, company: str | None = None,
         job_id: int | None = None, source: str = "user_confirmed", commit: bool = True, mirror: bool = True,
         scope_ref: str | None = None) -> AnswerMemory:
    """Remember an answer the user explicitly confirmed. Validates type and unit; refuses sensitive questions.

    `scope_ref` edits an employer- or job-specific answer that already exists (Settings): it never creates a new scope."""
    m = classify(question) if key is None else _match_for_key(key, question)
    if m.never:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, m.reason or "JobPilot never stores answers to sensitive questions.")
    if m.key is None:
        m = Match(custom_key(question), Canon("custom", (question or "")[:200], "other", "text", scope="global"), 1.0,
                  label=(question or "").strip()[:200])
    canon = m.canon
    try:
        value, shown = parse(canon.value_type, answer)
    except InvalidAnswer as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    if scope_ref:
        if not db.execute(select(AnswerMemory.id).where(AnswerMemory.user_id == user.id, AnswerMemory.key == m.key,
                                                         AnswerMemory.scope_ref == scope_ref)).first():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No remembered answer for that employer.")
    else:
        scope_ref = _scope_ref(m.scope, company, job_id)
    if m.scope != "global" and not scope_ref:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This answer belongs to one employer or job; open it from that job.")
    sensitivity = "private" if (canon.sensitivity == "private" or m.key.startswith(("work_authorization", "requires_sponsorship"))) else canon.sensitivity
    row = db.execute(select(AnswerMemory).where(AnswerMemory.user_id == user.id, AnswerMemory.key == m.key,
                                                AnswerMemory.scope_ref == scope_ref)).scalar_one_or_none()
    now = utcnow()
    if row is None:
        row = AnswerMemory(user_id=user.id, key=m.key, scope_ref=scope_ref, history=[])
        db.add(row)
    import json

    if sensitivity == "private":
        row.value_encrypted = _cipher(settings).encrypt(json.dumps({"value": value, "display": shown}))
        row.value_text, row.value_json = None, None
        stored_display = row.value_encrypted
    else:
        row.value_encrypted, row.value_text, row.value_json = None, shown, value
        stored_display = shown
    row.label = (m.label or canon.label)[:200]
    row.value_type, row.unit, row.sensitivity = canon.value_type, canon.unit, sensitivity
    row.source, row.status, row.confidence = source, "verified", 1.0
    row.question_text, row.question_norm = (question or "")[:500] or None, normalize(question)[:500] or None
    row.last_confirmed_at, row.revalidate_days = now, canon.revalidate_days
    entry = {"at": now.isoformat(), "source": source, "question": (question or "")[:200],
             ("value_encrypted" if sensitivity == "private" else "value"): stored_display}
    row.history = ([entry] + list(row.history or []))[:20]
    if mirror and not scope_ref:  # an answer for one employer never changes the general one in Settings
        _mirror_fact(db, user, m.key, value, shown)
    from backend.services import platform_service

    if not platform_service.has_consent(db, user.id, "answer_memory"):
        platform_service.set_consent_nocommit(db, user, "answer_memory", True)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def _match_for_key(key: str, question: str) -> Match:
    m = classify(question) if question else Match(None, None)
    if m.key == key:
        return m
    base = key.split(".")[0]
    if base == "experience_years":
        subject = key.split(".")[1] if "." in key else "total"
        return Match(key, EXPERIENCE, 1.0, subject=subject,
                     label="Total experience (years)" if subject == "total" else f"{subject.replace('_', ' ').title()} experience (years)")
    if base == "has_experience":
        return Match(key, HAS_EXPERIENCE, 1.0, label=f"Experience with {key.split('.', 1)[-1].replace('_', ' ')}")
    if base in BY_KEY:
        c = BY_KEY[base]
        label = c.label
        if "." in key and base in ("work_authorization", "requires_sponsorship"):
            label = f"{c.label} in {COUNTRY_NAMES.get(key.split('.')[1], key.split('.')[1].upper())}"
        return Match(key, c, 1.0, label=label, country=key.split(".")[1] if "." in key else None)
    if key.startswith("custom."):
        return Match(key, Canon("custom", (question or key)[:200], "other", "text"), 1.0, label=(question or key)[:200])
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown answer field.")


def _mirror_fact(db: Session, user: User, key: str, value: Any, shown: str) -> None:
    """Keep Settings -> Verified answers in step for the keys it shows (generic, not per-country)."""
    c = BY_KEY.get(key)
    if c is None or not c.fact_key:
        return
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    if prof is None:
        return
    facts = dict(prof.verified_facts or {})
    if c.value_type == "boolean" and c.key != "work_authorization":
        facts[c.fact_key] = bool(value)
    elif c.key == "work_authorization":
        return  # the Settings field is free text ("Indian citizen..."): a bare yes/no would lose information
    else:
        facts[c.fact_key] = shown
    meta = dict(facts.get("_updated") or {})
    meta[c.fact_key] = utcnow().isoformat()
    facts["_updated"] = meta
    prof.verified_facts = facts


def sync_from_facts(db: Session, settings, user: User, old: dict[str, Any], new: dict[str, Any]) -> None:
    """Settings -> Verified answers saved: remember the changed standard facts too (source "settings")."""
    for c in CATALOGUE:
        if not c.fact_key or c.key == "work_authorization":
            continue
        v = new.get(c.fact_key)
        if v in (None, "") or v == old.get(c.fact_key):
            continue
        try:
            save(db, settings, user, question=c.label, answer=v, key=c.key, source="settings", commit=False, mirror=False)
        except HTTPException:
            continue  # a free-text value the typed field can't hold (e.g. "negotiable"): Settings keeps it as is


def forget(db: Session, user: User, key: str, scope_ref: str = "") -> None:
    row = db.execute(select(AnswerMemory).where(AnswerMemory.user_id == user.id, AnswerMemory.key == key,
                                                AnswerMemory.scope_ref == scope_ref)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No remembered answer for that question.")
    db.delete(row)
    db.commit()


def listing(db: Session, settings, user: User, *, reveal: bool = False) -> list[dict[str, Any]]:
    out = []
    for r in sorted(rows_for(db, user).values(), key=lambda r: (r.label or "").lower()):
        private = r.sensitivity == "private"
        shown = display_of(r, settings) if (reveal or not private) else None
        if r.value_encrypted and shown is not None:
            import json

            try:
                shown = json.loads(shown).get("display")
            except (ValueError, AttributeError):
                shown = None
        canon = BY_KEY.get(r.key.split(".")[0])
        scope_kind, scope_name = scope_of(db, user, r.scope_ref)
        out.append({"key": r.key, "scope_ref": r.scope_ref, "scope_kind": scope_kind, "scope_name": scope_name,
                    "reusable": scope_kind == "global", "label": r.label, "answer": shown, "masked": private and not reveal,
                    "value_type": r.value_type, "unit": r.unit, "sensitivity": r.sensitivity, "source": r.source, "status": r.status,
                    "stale": _is_stale(r), "question": r.question_text, "last_confirmed_at": r.last_confirmed_at,
                    "revalidate_days": r.revalidate_days, "group": canon.group if canon else ("professional" if r.key.startswith(("experience_years", "has_experience")) else "other"),
                    "history": [{"at": h.get("at"), "source": h.get("source"), "question": h.get("question"),
                                 "answer": h.get("value") if "value" in h else ("(hidden)" if not reveal else _decrypt_history(h, settings))}
                                for h in (r.history or [])]})
    return out


def scope_of(db: Session, user: User, scope_ref: str) -> tuple[str, str | None]:
    """("global", None) | ("company", "<employer>") | ("job", "<title at company>") for a stored scope_ref."""
    if not scope_ref:
        return "global", None
    kind, _, ref = scope_ref.partition(":")
    if kind == "company":
        return "company", ref.title() if ref else None
    if kind == "job" and ref.isdigit():
        from backend.models import Job, UserJob

        job = db.get(Job, int(ref))
        owned = job is not None and db.execute(select(UserJob.id).where(UserJob.user_id == user.id, UserJob.job_id == job.id)).first()
        return "job", (f"{job.title} at {job.company}" if owned else None)
    return kind or "global", None


def same_value(a: Any, b: Any) -> bool:
    """Loose equality for profile-vs-answer checks: case, spacing, punctuation and URL scheme don't matter."""
    def n(v: Any) -> str:
        t = re.sub(r"^https?://(www\.)?", "", str(v or "").strip().lower()).rstrip("/")
        return re.sub(r"[^a-z0-9@+]+", " ", t).strip()
    return n(a) == n(b)


def profile_conflicts(db: Session, settings, user: User) -> list[dict[str, Any]]:
    """Remembered general answers that now disagree with the confirmed profile (e.g. a new current employer)."""
    profile = _profile_values(db, user)
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    out = []
    for r in rows_for(db, user).values():
        c = BY_KEY.get(r.key)
        if c is None or not c.profile_key or r.scope_ref or r.sensitivity == "private":
            continue
        pv, mv = profile.get(c.profile_key), display_of(r, settings)
        if pv in (None, "") or mv in (None, "") or same_value(pv, mv):
            continue
        newer_profile = bool(prof and prof.confirmed_at and r.last_confirmed_at and _aware(prof.confirmed_at) > _aware(r.last_confirmed_at))
        out.append({"key": r.key, "label": r.label, "saved": mv, "profile": str(pv), "used": "ask" if newer_profile else "saved"})
    return out


def _aware(t):
    return t if t.tzinfo else t.replace(tzinfo=utcnow().tzinfo)


def _decrypt_history(h: dict[str, Any], settings) -> str | None:
    import json

    plain = _cipher(settings).decrypt(h.get("value_encrypted") or "")
    try:
        return json.loads(plain or "null").get("display")
    except (ValueError, AttributeError):
        return None


def catalogue() -> list[dict[str, Any]]:
    return [{"key": c.key, "label": c.label, "group": c.group, "value_type": c.value_type, "unit": c.unit,
             "sensitivity": c.sensitivity, "time_dependent": bool(c.revalidate_days), "scope": c.scope} for c in CATALOGUE] + [
        {"key": "experience_years.total", "label": "Total experience (years)", "group": "professional", "value_type": "number",
         "unit": "years", "sensitivity": "personal", "time_dependent": True, "scope": "global"}]


# ---- answering a form ------------------------------------------------------------------------

COMMON_QUESTIONS = ("Total years of experience", "Notice period", "Current CTC", "Expected CTC", "Willing to relocate?",
                    "Are you legally authorised to work in India?", "Do you require visa sponsorship?")


def resolve(db: Session, settings, user: User, questions: list[str], *, company: str | None = None, job_id: int | None = None,
            overrides: dict[str, Any] | None = None, job_country: str | None = None) -> list[dict[str, Any]]:
    """An answer for each question, never invented. overrides: {question: answer} the user typed for this application."""
    from backend.services.answer_service import answer_questions

    rows = rows_for(db, user)
    # A bare "Do you need sponsorship?" means the country this job is in, or the one another question on the form names.
    cc = {"gb": "uk"}.get((job_country or "").lower(), (job_country or "").lower())
    pc = page_country(questions) or (cc if cc in COUNTRY_NAMES else None)
    profile = _profile_values(db, user)
    facts = _facts(db, user)
    _prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    profile_confirmed_at = _prof.confirmed_at if _prof else None
    legacy_needed: list[str] = []
    out: list[dict[str, Any]] = []
    for q in questions:
        m = classify(q, page_country=pc)
        item: dict[str, Any] = {"question": q, "key": m.key, "label": m.label or q, "answer": None, "value": None,
                                "status": "NEEDS_INPUT", "source": None, "confidence": round(m.confidence, 2),
                                "sensitivity": "never" if m.never else (m.canon.sensitivity if m.canon else "personal"),
                                "confirm": bool(m.canon and m.canon.commitment), "stale": False, "reason": m.reason,
                                "value_type": m.canon.value_type if m.canon else "text", "unit": m.canon.unit if m.canon else None,
                                "scope": m.scope, "notes": list(m.notes), "remember_default": bool(m.key and m.scope == "global" and not m.never)}
        if m.key and m.key.startswith(("work_authorization", "requires_sponsorship")):
            item["sensitivity"] = "private"
        if m.never:
            out.append(item)
            continue
        if overrides and q in overrides and overrides[q] not in (None, ""):
            item.update(answer=str(overrides[q]), status="VERIFIED", source="this_application", reason=None)
            out.append(item)
            continue
        key = m.key or custom_key(q)
        scoped = rows.get((key, _scope_ref(m.scope, company, job_id))) if m.key else rows.get((key, ""))
        if scoped is not None:
            shown = display_of(scoped, settings)
            if scoped.value_encrypted and shown:
                import json

                try:
                    shown = json.loads(shown).get("display")
                except (ValueError, AttributeError):
                    shown = None
            if shown:
                trusted = m.confidence >= 0.75 or m.key is None
                stale = _is_stale(scoped)
                item.update(answer=shown, value=value_of(scoped, settings), source="memory", stale=stale,
                            status="VERIFIED" if trusted and not stale else "SUGGESTED",
                            reason=(f"You confirmed this on {scoped.last_confirmed_at:%d %b %Y}. Check it's still right." if stale else
                                    None if trusted else "The question is worded differently from the one you answered. Check it fits."))
                pk = m.canon.profile_key if m.canon else None
                pv = profile.get(pk) if pk and not scoped.scope_ref else None
                if pv not in (None, "") and not same_value(pv, shown):
                    # Two of the user's own confirmations disagree. The newer one is used; an older saved answer is only
                    # offered, so nothing outdated is filled without a look.
                    newer_profile = bool(profile_confirmed_at and scoped.last_confirmed_at
                                         and _aware(profile_confirmed_at) > _aware(scoped.last_confirmed_at))
                    item["conflict"] = {"saved": shown, "profile": str(pv), "used": "ask" if newer_profile else "saved"}
                    if newer_profile:
                        item.update(status="SUGGESTED", reason=f"Your saved answer is older than your profile, which now says "
                                                               f"\u201c{pv}\u201d. Pick the one that's right.")
                    else:
                        item["notes"] = [*item["notes"], f"Your profile says \u201c{pv}\u201d; your saved answer is newer, so it is used."]
                out.append(item)
                continue
        if m.key is None or m.scope != "global":
            legacy_needed.append(q)
            out.append(item)
            continue
        derived = _derived(m, profile, facts) or _from_years(m, rows, settings)
        if derived:
            item.update(**derived)
        else:
            legacy_needed.append(q)
        out.append(item)
    if legacy_needed:
        legacy = {a["question"]: a for a in answer_questions(db, settings, user, legacy_needed)}
        for item in out:
            a = legacy.get(item["question"])
            if a and item["key"] and not item["key"].startswith("has_experience") and not str(a.get("source") or "").startswith(
                    ("answer_bank.", "verified_facts.", "saved_for_one_job.")):
                # A recognised question gets only the user's own saved answers from the older answer bank, never its
                # resume-based guesses (e.g. total years offered for "years of SAP experience").
                a = None
            if a and item["status"] == "NEEDS_INPUT" and a.get("answer"):
                status_ = a["status"] if item["scope"] == "global" else "SUGGESTED"
                item.update(answer=a["answer"], status=status_, source=a.get("source"),
                            reason=a.get("reason") or ("Saved for another job: check it fits this one." if item["scope"] != "global" else None))
            elif a and item["status"] == "NEEDS_INPUT" and a.get("reason") and not item.get("reason"):
                item["reason"] = a["reason"]
    return out


def _derived(m: Match, profile: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any] | None:
    """An answer from Settings (VERIFIED) or the confirmed profile/resume (SUGGESTED); None if there is none."""
    c = m.canon
    if c.fact_key and facts.get(c.fact_key) not in (None, ""):
        v = facts[c.fact_key]
        if m.country and c.key in ("work_authorization", "requires_sponsorship"):
            # Settings hold one general answer; a question about a named country is only a suggestion.
            shown = v if isinstance(v, str) else ("Yes" if v else "No")
            return {"answer": shown, "status": "SUGGESTED", "source": "settings",
                    "reason": f"From your general answer in Settings; this form asks about {COUNTRY_NAMES[m.country]}."}
        shown = ("Yes" if v else "No") if isinstance(v, bool) else str(v)
        updated = (facts.get("_updated") or {}).get(c.fact_key)
        stale = False
        if c.revalidate_days and updated:
            from datetime import datetime

            try:
                stale = utcnow() - datetime.fromisoformat(updated) > timedelta(days=c.revalidate_days)
            except (TypeError, ValueError):
                stale = False
        return {"answer": shown, "status": "SUGGESTED" if stale else "VERIFIED", "source": "settings", "stale": stale,
                "reason": "Saved in Settings a while ago. Check it's still right." if stale else None}
    if c is EXPERIENCE and m.subject == "total" and not m.qualifier and profile.get("total_experience_years") is not None:
        return {"answer": f"{profile['total_experience_years']:g}", "value": profile["total_experience_years"], "status": "SUGGESTED",
                "source": "resume", "reason": "Worked out from the dates on your resume. Check it."}
    if c.profile_key and c is not EXPERIENCE and profile.get(c.profile_key) not in (None, ""):
        return {"answer": str(profile[c.profile_key]), "status": "VERIFIED" if c.group in ("personal", "links") else "SUGGESTED",
                "source": "profile", "reason": None if c.group in ("personal", "links") else "From your confirmed profile."}
    return None


def _from_years(m: Match, rows: dict[tuple[str, str], AnswerMemory], settings) -> dict[str, Any] | None:
    """"Do you have Python experience?" from a remembered "years of Python experience" (a suggestion)."""
    if m.canon is not HAS_EXPERIENCE or not m.subject:
        return None
    row = rows.get((f"experience_years.{_slug(m.subject)}", ""))
    years = value_of(row, settings) if row is not None else None
    if not isinstance(years, (int, float)):
        return None
    return {"answer": "Yes" if years > 0 else "No", "status": "SUGGESTED", "source": "memory",
            "reason": f"From your answer of {years:g} years of {m.subject} experience."}


def _facts(db: Session, user: User) -> dict[str, Any]:
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    return dict(prof.verified_facts or {}) if prof else {}


def _profile_values(db: Session, user: User) -> dict[str, Any]:
    from backend.services.extension_service import autofill_profile

    try:
        return dict(autofill_profile(db, user).get("fields") or {})
    except Exception:  # noqa: BLE001  (an unparsable profile: answer nothing from it)
        return {}
