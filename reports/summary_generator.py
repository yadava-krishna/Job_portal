"""Daily statistics (pandas) shared by the Excel report and the console summary."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pandas as pd

from core.models import Platform
from database.db import Database

SHORTLIST_STATES = {"SHORTLISTED", "LIMIT_DEFERRED", "APPLICATION_CREATED", "CROSS_PLATFORM_DUPLICATE"}
# CLI statuses plus the web portal's PREPARED / OPENED / CONFIRMATION_PENDING.
PENDING_MANUAL = {"PENDING_MANUAL_SUBMISSION", "APPROVED", "NEEDS_VERIFICATION", "SUBMITTING", "PREPARED", "OPENED", "CONFIRMATION_PENDING"}
FAILED = {"FAILED", "BLOCKED"}

METRICS = [
    ("total_discovered", "Total jobs discovered (records received)"),
    ("total_unique", "Total unique jobs (new today)"),
    ("total_shortlisted", "Total jobs shortlisted"),
    ("excellent", "Total excellent matches (85-100)"),
    ("good", "Total good matches (70-84)"),
    ("moderate", "Total moderate matches (55-69)"),
    ("low", "Total low matches (<55)"),
    ("submitted", "Total successfully applied (confirmed)"),
    ("awaiting_approval", "Total awaiting approval"),
    ("pending_manual", "Total pending manual application"),
    ("failed", "Total failed applications"),
    ("duplicates_skipped", "Total duplicates skipped"),
]


def application_status_label(row: Any) -> str:
    return row["app_status"] or row["pipeline_status"]


def frame_for_day(db: Database, day: date) -> pd.DataFrame:
    rows = db.report_rows(day)
    cols = ["id", "platform", "first_seen_at", "match_score", "match_category", "pipeline_status", "app_status", "submitted_at", "eligibility_status"]
    df = pd.DataFrame([{c: r[c] for c in cols} for r in rows], columns=cols)
    if df.empty:
        return df
    d = day.isoformat()
    df["new_today"] = df["first_seen_at"].str[:10] == d
    df["submitted_today"] = (df["app_status"] == "SUBMITTED") & (df["submitted_at"].fillna("").str[:10] == d)
    df["status"] = df["app_status"].fillna(df["pipeline_status"])
    return df


def run_totals(db: Database, day: date) -> dict[str, dict[str, int]]:
    """Per-platform records seen and duplicates skipped, summed over the day's runs."""
    totals: dict[str, dict[str, int]] = {p.value: {"records_seen": 0, "duplicates_skipped": 0} for p in Platform}
    for run in db.runs_on(day):
        stats = json.loads(run["stats_json"] or "{}")
        for platform, s in stats.get("platforms", {}).items():
            t = totals.setdefault(platform, {"records_seen": 0, "duplicates_skipped": 0})
            t["records_seen"] += int(s.get("records_seen", 0))
            t["duplicates_skipped"] += int(s.get("duplicates_skipped", 0))
    return totals


def _metrics(df: pd.DataFrame, records_seen: int, dups: int) -> dict[str, int]:
    if df.empty:
        base = {k: 0 for k, _ in METRICS}
        base.update(total_discovered=records_seen, duplicates_skipped=dups)
        return base
    cat = df["match_category"].fillna("")
    return {
        "total_discovered": records_seen,
        "total_unique": int(df["new_today"].sum()),
        "total_shortlisted": int(df["pipeline_status"].isin(SHORTLIST_STATES).sum()),
        "excellent": int((cat == "Excellent match").sum()),
        "good": int((cat == "Good match").sum()),
        "moderate": int((cat == "Moderate match").sum()),
        "low": int((cat == "Low match").sum()),
        "submitted": int(df["submitted_today"].sum()),
        "awaiting_approval": int((df["status"] == "AWAITING_APPROVAL").sum()),
        "pending_manual": int(df["status"].isin(PENDING_MANUAL).sum()),
        "failed": int(df["status"].isin(FAILED).sum()),
        "duplicates_skipped": dups,
    }


def daily_summary(db: Database, day: date) -> dict[str, Any]:
    df = frame_for_day(db, day)
    totals = run_totals(db, day)
    overall = _metrics(df, sum(t["records_seen"] for t in totals.values()), sum(t["duplicates_skipped"] for t in totals.values()))
    per_platform = {}
    for p in Platform:
        sub = df[df["platform"] == p.value] if not df.empty else df
        t = totals.get(p.value, {"records_seen": 0, "duplicates_skipped": 0})
        per_platform[p.value] = _metrics(sub, t["records_seen"], t["duplicates_skipped"])
    return {"date": day.isoformat(), "overall": overall, "platforms": per_platform}


def console_summary(summary: dict[str, Any], *, report_path: str | None, mode: str, scoring: str, warnings: list[str]) -> str:
    o = summary["overall"]
    lines = [
        "",
        f"Daily run summary - {summary['date']}  (mode {mode}, scoring {scoring})",
        "-" * 64,
    ]
    for key, label in METRICS:
        lines.append(f"  {label:<44} {o[key]:>6}")
    lines.append("  Per platform (unique / shortlisted / submitted):")
    for p, m in summary["platforms"].items():
        lines.append(f"    {p:<10} {m['total_unique']:>4} / {m['total_shortlisted']:>4} / {m['submitted']:>4}")
    if report_path:
        lines.append(f"  Report: {report_path}")
    for w in warnings:
        lines.append(f"  ! {w}")
    return "\n".join(lines)
