"""Daily Excel workbook (openpyxl). Never overwrites an existing report."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from core import timeutil
from core.models import Platform
from database.db import Database
from platforms.base_platform import SearchLink
from reports.summary_generator import METRICS, application_status_label, daily_summary

log = logging.getLogger(__name__)

EXCEL_CELL_LIMIT = 32_000
HEADER_FILL = PatternFill("solid", start_color="1F3864")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14, color="1F3864")
THIN = Side(style="thin", color="D0D7E5")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP_TOP = Alignment(wrap_text=True, vertical="top")
TOP = Alignment(vertical="top")

STATUS_FILLS = {
    "SUBMITTED": "C6EFCE",
    "AWAITING_APPROVAL": "FFEB9C",
    "APPROVED": "FCD5B4",
    "PENDING_MANUAL_SUBMISSION": "FCD5B4",
    "NEEDS_VERIFICATION": "FCD5B4",
    "SUBMITTING": "FCD5B4",
    "FAILED": "FFC7CE",
    "BLOCKED": "FFC7CE",
    "SCORING_FAILED": "FFC7CE",
    "SHORTLISTED": "BDD7EE",
    "LIMIT_DEFERRED": "BDD7EE",
    "REJECTED_BY_CANDIDATE": "D9D9D9",
}

DETAIL_COLUMNS: list[tuple[str, int]] = [
    ("Serial Number", 8), ("Application Date", 13), ("Application Time", 11), ("Candidate Name", 20), ("Platform", 10),
    ("Company Name", 26), ("Job Title", 30), ("Job ID", 16), ("Job URL", 40), ("Location", 20), ("Work Mode", 11),
    ("Employment Type", 13), ("Required Experience", 16), ("Candidate Experience", 16), ("Salary Range", 16),
    ("Job Posted Date", 13), ("Complete Job Description", 90), ("Required Skills", 30), ("Preferred Skills", 28),
    ("Matching Skills", 30), ("Missing Skills", 28), ("Match Percentage", 11), ("Match Category", 15),
    ("Match Explanation", 70), ("Eligibility Status", 14), ("Application Status", 24), ("Application Submission Time", 19),
    ("Application Reference ID", 18), ("Resume Used", 28), ("Cover Letter", 50), ("Screening Questions", 40),
    ("Screening Answers", 45), ("Application Confirmation", 30), ("Error Details", 30), ("Notes", 40),
]
ANALYSIS_COLUMNS = [("Job Title", 32), ("Company", 26), ("Platform", 10), ("Match Score", 11), ("Matching Skills", 34),
                    ("Missing Skills", 30), ("Experience Match", 40), ("Eligibility", 50), ("Recommendation", 60)]
ERROR_COLUMNS = [("Timestamp", 19), ("Platform", 10), ("Job ID", 22), ("Error Type", 22), ("Error Description", 80), ("Recovery Status", 18)]
LINK_COLUMNS = [("Platform", 10), ("Job Title", 30), ("Location", 18), ("Search URL (open and review manually)", 110)]


def report_path_for(root: Path, day: date) -> Path:
    """<root>/<YYYY>/<Month>/<YYYY-MM-DD>_Applications.xlsx, with _run2, _run3... if it exists."""
    folder = root / f"{day.year}" / day.strftime("%B")
    base = folder / f"{day.isoformat()}_Applications.xlsx"
    if not base.exists():
        return base
    n = 2
    while (candidate := folder / f"{day.isoformat()}_Applications_run{n}.xlsx").exists():
        n += 1
    return candidate


class ExcelReportGenerator:
    def __init__(self, db: Database, output_root: Path, candidate_name: str, candidate_years: float, min_match_score: float):
        self.db = db
        self.output_root = output_root
        self.candidate_name = candidate_name
        self.candidate_years = candidate_years
        self.min_match_score = min_match_score

    def generate(self, day: date, search_links: list[SearchLink] | None = None) -> Path:
        wb = Workbook()
        rows = self.db.report_rows(day)
        self._details(wb.active, rows, day)
        self._summary(wb.create_sheet("Daily Summary"), day)
        self._analysis(wb.create_sheet("Job Analysis"), rows)
        self._errors(wb.create_sheet("Errors and Logs"), day)
        self._links(wb.create_sheet("Search Links"), search_links or [])

        path = report_path_for(self.output_root, day)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(suffix=".xlsx", dir=path.parent)
        os.close(fd)
        try:
            wb.save(tmp)
            # os.link fails if the target exists, so a report can never be overwritten.
            os.link(tmp, path)
        finally:
            os.unlink(tmp)
        log.info("Excel report written: %s (%d job rows)", path, len(rows))
        return path

    # ---- sheets ----------------------------------------------------------------
    def _details(self, ws: Worksheet, rows: list[Any], day: date) -> None:
        ws.title = "Application Details"
        _header(ws, DETAIL_COLUMNS)
        for i, r in enumerate(rows, start=1):
            match = json.loads(r["match_json"]) if r["match_json"] else {}
            elig = json.loads(r["eligibility_json"]) if r["eligibility_json"] else {}
            screening = json.loads(r["screening_json"]) if r["screening_json"] else []
            status = application_status_label(r)
            app_dt = timeutil.parse_iso(r["submitted_at"] or r["app_created_at"] or r["first_seen_at"])
            submitted = timeutil.to_naive_local(timeutil.parse_iso(r["submitted_at"]))
            explanation = _explanation(match)
            errors = r["app_error"] or ("; ".join(match.get("notes", [])) if r["pipeline_status"] == "SCORING_FAILED" else None)
            notes = "; ".join(x for x in [r["notes"], r["app_notes"], _stage_note(status, r)] if x)
            values = [
                i, app_dt.date() if app_dt else day, timeutil.to_naive_local(app_dt).time() if app_dt else None,
                self.candidate_name, r["platform"], r["company"], r["title"], r["platform_job_id"] or r["job_key"], r["url"],
                r["location"], r["work_mode"], r["employment_type"], r["experience_required"],
                f"{self.candidate_years:.1f} years", r["salary_range"],
                date.fromisoformat(r["posted_date"]) if r["posted_date"] else None,
                r["description"] or "(description not provided - add it with: python main.py add-jd)",
                _join(r["required_skills"]), _join(r["preferred_skills"]),
                ", ".join(match.get("matching_skills", [])), ", ".join(match.get("missing_skills", []) + [f"{s} (optional)" for s in match.get("missing_optional_skills", [])]),
                r["match_score"], r["match_category"], explanation,
                r["eligibility_status"] + (": " + "; ".join(elig.get("reasons", [])) if elig.get("reasons") and r["eligibility_status"] != "ELIGIBLE" else "") if r["eligibility_status"] else None,
                status, submitted, r["reference_id"], r["app_resume_path"], r["cover_letter"],
                "\n".join(s["question"] for s in screening), "\n".join(f"{s['question']}: {s['answer']}" for s in screening),
                (f"{r['confirmation_source']}: {r['confirmation_text'] or ''}".strip(": ") if r["confirmation_source"] else
                 ("Not submitted - no confirmation" if r["app_id"] else None)),
                errors, notes or None,
            ]
            ws.append([_clean(v) for v in values])
            row = ws.max_row
            for col in range(1, len(DETAIL_COLUMNS) + 1):
                c = ws.cell(row=row, column=col)
                c.alignment = WRAP_TOP if col in (17, 18, 19, 20, 21, 24, 25, 30, 31, 32, 34, 35) else TOP
                c.border = BORDER
            ws.cell(row=row, column=2).number_format = "yyyy-mm-dd"
            ws.cell(row=row, column=3).number_format = "hh:mm:ss"
            ws.cell(row=row, column=16).number_format = "yyyy-mm-dd"
            ws.cell(row=row, column=27).number_format = "yyyy-mm-dd hh:mm"
            ws.cell(row=row, column=22).number_format = "0.0"
            if r["url"]:
                link = ws.cell(row=row, column=9)
                link.hyperlink = r["url"]
                link.style = "Hyperlink"
                link.alignment = TOP
            fill = STATUS_FILLS.get(status)
            if fill:
                ws.cell(row=row, column=26).fill = PatternFill("solid", start_color=fill)
            ws.row_dimensions[row].height = 150 if r["description"] else 45
        _finish(ws, DETAIL_COLUMNS, len(rows))
        _score_formatting(ws, "V", len(rows))

    def _summary(self, ws: Worksheet, day: date) -> None:
        s = daily_summary(self.db, day)
        ws["A1"] = f"Daily Summary - {day.isoformat()}"
        ws["A1"].font = TITLE_FONT
        ws["A2"] = f"Generated {timeutil.now().strftime('%Y-%m-%d %H:%M %Z')} for {self.candidate_name}"
        headers = ["Metric", "All platforms", *[p.value for p in Platform]]
        ws.append([])
        ws.append(headers)
        for c in ws[4]:
            c.fill, c.font, c.border = HEADER_FILL, HEADER_FONT, BORDER
        for key, label in METRICS:
            ws.append([label, s["overall"][key], *[s["platforms"][p.value][key] for p in Platform]])
            for c in ws[ws.max_row]:
                c.border = BORDER
        ws.append([])
        ws.append(["Stage definitions"])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        for line in [
            "Discovered: job received from an alert email or import (not yet assessed).",
            f"Shortlisted: eligible and scored at or above {self.min_match_score:g}.",
            "Awaiting approval: application package prepared; candidate must approve.",
            "Pending manual application: approved/assisted; candidate submits on the platform.",
            "Successfully applied: submission confirmed by a reference ID, confirmation text or confirmation email.",
            "Failed: submission attempted and failed, or blocked by a security check.",
        ]:
            ws.append([line])
        ws.append([])
        ws.append(["Platform access this day"])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        for ps in self.db.platform_status_on(day):
            ws.append([f"{ps['platform']}: {ps['status']} ({ps['access_mode']}), {ps['records_seen']} records" + (f" - {ps['error']}" if ps["error"] else "")])
        ws.column_dimensions["A"].width = 60
        for col in "BCDE":
            ws.column_dimensions[col].width = 15
        ws.freeze_panes = "A5"

    def _analysis(self, ws: Worksheet, rows: list[Any]) -> None:
        _header(ws, ANALYSIS_COLUMNS)
        n = 0
        for r in rows:
            if r["match_score"] is None:
                continue
            match = json.loads(r["match_json"])
            elig = json.loads(r["eligibility_json"]) if r["eligibility_json"] else {}
            exp_comp = next((c for c in match.get("components", []) if c["name"] == "experience"), None)
            exp_text = (f"{exp_comp['score']:.0f}/100 - {exp_comp['evidence']}" if exp_comp else "") + (f" | Gap: {match['experience_gap']}" if match.get("experience_gap") else "")
            ws.append([_clean(v) for v in [
                r["title"], r["company"], r["platform"], r["match_score"], ", ".join(match.get("matching_skills", [])),
                ", ".join(match.get("missing_skills", [])), exp_text,
                f"{r['eligibility_status']}: " + "; ".join(elig.get("reasons", [])), match.get("recommendation", ""),
            ]])
            n += 1
            for c in ws[ws.max_row]:
                c.alignment, c.border = WRAP_TOP, BORDER
            ws.cell(row=ws.max_row, column=4).number_format = "0.0"
        _finish(ws, ANALYSIS_COLUMNS, n)
        _score_formatting(ws, "D", n)

    def _errors(self, ws: Worksheet, day: date) -> None:
        _header(ws, ERROR_COLUMNS)
        errors = self.db.errors_on(day)
        for e in errors:
            ws.append([_clean(v) for v in [timeutil.to_naive_local(timeutil.parse_iso(e["created_at"])), e["platform"], e["job_key"],
                                            e["error_type"], e["description"], e["recovery_status"]]])
            ws.cell(row=ws.max_row, column=1).number_format = "yyyy-mm-dd hh:mm:ss"
            for c in ws[ws.max_row]:
                c.alignment, c.border = WRAP_TOP, BORDER
        if not errors:
            ws.append([None, None, None, "NONE", "No errors recorded for this day.", None])
        _finish(ws, ERROR_COLUMNS, max(1, len(errors)))

    def _links(self, ws: Worksheet, links: list[SearchLink]) -> None:
        _header(ws, LINK_COLUMNS)
        for link in links:
            ws.append([link.platform.value, link.title, link.location, link.url])
            c = ws.cell(row=ws.max_row, column=4)
            c.hyperlink, c.style = link.url, "Hyperlink"
        _finish(ws, LINK_COLUMNS, len(links))


# ---- helpers --------------------------------------------------------------------

def _header(ws: Worksheet, columns: list[tuple[str, int]]) -> None:
    ws.append([c for c, _ in columns])
    for cell in ws[1]:
        cell.fill, cell.font, cell.border = HEADER_FILL, HEADER_FONT, BORDER
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    ws.row_dimensions[1].height = 32


def _finish(ws: Worksheet, columns: list[tuple[str, int]], n_rows: int) -> None:
    for idx, (_, width) in enumerate(columns, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{max(1, n_rows) + 1}"


def _score_formatting(ws: Worksheet, col: str, n_rows: int) -> None:
    if n_rows == 0:
        return
    rng = f"{col}2:{col}{n_rows + 1}"
    ws.conditional_formatting.add(rng, CellIsRule(operator="greaterThanOrEqual", formula=["85"], fill=PatternFill("solid", start_color="63BE7B"), font=Font(bold=True)))
    ws.conditional_formatting.add(rng, CellIsRule(operator="between", formula=["70", "84.99"], fill=PatternFill("solid", start_color="C6EFCE")))
    ws.conditional_formatting.add(rng, CellIsRule(operator="between", formula=["55", "69.99"], fill=PatternFill("solid", start_color="FFEB9C")))
    ws.conditional_formatting.add(rng, CellIsRule(operator="lessThan", formula=["55"], fill=PatternFill("solid", start_color="FFC7CE")))


def _clean(value: Any) -> Any:
    """Make untrusted text safe for a cell: strip control characters, cap length, and never let text become a formula."""
    if not isinstance(value, str):
        return value
    value = ILLEGAL_CHARACTERS_RE.sub("", value)
    if len(value) > EXCEL_CELL_LIMIT:
        value = value[:EXCEL_CELL_LIMIT] + "\n[truncated - full text is in the database]"
    if value[:1] in ("=", "+", "@") or (value[:1] == "-" and not value[1:2].isdigit()):
        value = "​" + value  # zero-width space: text stays visible but can never be read as a formula
    return value


def _join(json_list: str | None) -> str:
    return ", ".join(json.loads(json_list or "[]"))


def _explanation(match: dict[str, Any]) -> str | None:
    if not match:
        return None
    parts = [f"{c['name']}: {c['score']:.0f} x {c['weight']:g}% = {c['weighted']:.1f} ({c['evidence']})" for c in match.get("components", [])]
    text = "\n".join(parts) + f"\nMethod: {match.get('scoring_method')} (confidence {match.get('confidence')})"
    if match.get("reasons_for"):
        text += "\nFor: " + "; ".join(match["reasons_for"])
    if match.get("reasons_against"):
        text += "\nAgainst: " + "; ".join(match["reasons_against"])
    if match.get("notes"):
        text += "\nNotes: " + " ".join(match["notes"])
    return text


def _stage_note(status: str, r: Any) -> str | None:
    return {
        "DISCOVERED": "Discovered; not yet scored",
        "BELOW_THRESHOLD": "Scored below the shortlist threshold",
        "NOT_ELIGIBLE": "Fails a hard eligibility rule",
        "NEEDS_REVIEW": "Eligibility needs candidate review",
        "NEEDS_DESCRIPTION": "Description missing; add it to complete scoring",
        "AWAITING_APPROVAL": "Run: python main.py approve " + str(r["app_id"]) if r["app_id"] else None,
        "PENDING_MANUAL_SUBMISSION": "Submit on the platform, then: python main.py mark-submitted " + str(r["app_id"]) if r["app_id"] else None,
    }.get(status)
