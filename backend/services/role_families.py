"""Related job titles, so a search for "Accounts Receivable Associate" also finds "Sr. Collections Analyst".

Employers title the same work differently. A family is activated when a user's titles, keywords or domains mention
one of its triggers; a job title then matches if it contains one of the family's phrases. Matches made this way are
broader than exact titles, so they are ranked by the resume match score, never shortlisted on title alone.
"""

from __future__ import annotations

import re

from core.skills import normalize_text

# family -> (triggers in the user's titles/keywords/domains, phrases that identify a job title in the family)
FAMILIES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "receivables": (
        ("receivable", "collections", "collection", "billing", "revenue cycle", "rcm", "order to cash", "o2c", "cash application",
         "ar analyst", "ar associate", "ar executive", "ar specialist", "ar caller", "credit control"),
        ("accounts receivable", "receivable", "receivables", "collections", "collection", "credit and collections", "credit control",
         "billing", "cash application", "order to cash", "o2c", "revenue cycle", "rcm", "ar analyst", "ar associate", "ar executive",
         "ar specialist", "ar caller", "dunning", "denial management", "medical billing"),
    ),
    "accounting": (
        ("accounting", "accountant", "accounts payable", "payable", "general ledger", "bookkeeping", "reconciliation", "receivable"),
        ("accountant", "accounting", "accounts payable", "payables", "general ledger", "gl analyst", "reconciliation", "bookkeeper",
         "bookkeeping", "accounts executive", "accounts associate", "accounts officer", "payroll accountant", "record to report", "r2r",
         "procure to pay", "p2p"),
    ),
    "fpa": (
        ("fp and a", "fpa", "financial planning", "financial analyst", "finance analyst", "business finance", "budgeting", "forecasting"),
        ("fp and a", "fpa", "financial planning", "financial analyst", "finance analyst", "business finance", "finance business partner",
         "finance associate", "finance executive", "finance specialist", "finance and strategy", "budgeting", "forecasting",
         "management reporting", "commercial finance", "corporate finance"),
    ),
}

# A related-title match is rejected when the job is clearly a different profession (e.g. "Staff Engineer, Billing").
FOREIGN_ROLES = ("engineer", "engineering", "developer", "architect", "designer", "scientist", "creator", "recruiter", "marketing",
                 "account executive", "sales", "solutions consultant", "product manager", "product analyst", "data scientist")


def _has(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def families_for(*texts: str) -> list[str]:
    """Families triggered by any of the user's titles, keywords or domains."""
    joined = " | ".join(normalize_text(t) for t in texts if t)
    return [name for name, (triggers, _) in FAMILIES.items() if any(_has(joined, t) for t in triggers)]


def related_title(title: str, families: list[str]) -> str | None:
    """The family a job title belongs to (among the active ones), or None."""
    t = normalize_text(title)
    if not t or any(_has(t, f) for f in FOREIGN_ROLES):
        return None
    for name in families:
        if any(_has(t, p) for p in FAMILIES[name][1]):
            return name
    return None
