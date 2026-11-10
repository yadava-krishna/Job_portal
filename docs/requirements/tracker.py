"""Requirement tracker: keeps the source inventory, requirement list and matrix in step.

    python docs/requirements/tracker.py            # sync everything
    python docs/requirements/tracker.py --summary  # print counts only

Sources of truth (edit these, then re-run):
  docs/requirements/jobpilot-requirements.csv   one row per requirement: status, evidence, tests, notes
  docs/requirements/mapping/part_*.csv          which requirement IDs cover each source item

Generated (do not edit by hand):
  JobPilot_FULL_SOURCE_COVERAGE_INVENTORY.csv   audit_status / requirement_ids / code_evidence / notes columns
  docs/requirements/JobPilot_COMPLETE_REQUIREMENTS_MATRIX.md
"""

from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INVENTORY = ROOT / "JobPilot_FULL_SOURCE_COVERAGE_INVENTORY.csv"
CATALOGUE = HERE / "catalogue.txt"
REQS = HERE / "jobpilot-requirements.csv"
MATRIX = HERE / "JobPilot_COMPLETE_REQUIREMENTS_MATRIX.md"
REQ_FIELDS = ["req_id", "priority", "area", "title", "acceptance", "status", "code_evidence", "tests", "notes", "updated"]

# A source item covered by several requirements takes the least-finished status among them.
PRECEDENCE = ["BROKEN", "MISSING", "UNAUDITED", "PARTIAL", "UNVERIFIABLE", "BLOCKED_EXTERNAL", "PLANNED_FUTURE",
              "NOT_APPLICABLE_JUSTIFIED", "DONE_VERIFIED"]
SHORT = {"JobPilot_01_Product_Vision_Strategy_Launch.docx": "01 Vision",
         "JobPilot_02_Technical_Developer_Specification.docx": "02 Tech spec",
         "JobPilot_03_AWS_Hosting_Cost_Plan.docx": "03 AWS cost",
         "JobPilot_04_MVP_PRD_Sprint_Plan_AESTHETIC.docx": "04 PRD",
         "Technical Specification for JobPilot.pages": "Edited spec (.pages)",
         "Pasted text(20261110-071236).txt": "Beta hosting plan"}


def _catalogue() -> list[dict]:
    out = []
    for line in CATALOGUE.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        head, _, acceptance = line.partition("::")
        rid, prio, area, title = (p.strip() for p in head.split("|", 3))
        out.append({"req_id": rid, "priority": prio, "area": area, "title": title, "acceptance": acceptance.strip(),
                    "status": "NOT_APPLICABLE_JUSTIFIED" if rid == "INFO" else "UNAUDITED",
                    "code_evidence": "", "tests": "", "notes": "", "updated": ""})
    return out


def load_reqs() -> dict[str, dict]:
    cat = _catalogue()
    existing = {}
    if REQS.exists():
        with REQS.open(newline="") as f:
            existing = {r["req_id"]: r for r in csv.DictReader(f)}
    merged = {}
    for c in cat:  # catalogue defines the set and wording; the CSV keeps the audit state
        r = existing.get(c["req_id"], c)
        for k in ("priority", "area", "title", "acceptance"):
            r[k] = c[k]
        merged[c["req_id"]] = {k: r.get(k, "") for k in REQ_FIELDS}
    for rid, r in existing.items():  # requirements added straight to the CSV are kept
        merged.setdefault(rid, {k: r.get(k, "") for k in REQ_FIELDS})
    return merged


# Checkbox for readers: done and tested / not done yet / no work needed (context text only).
DONE_MARK = {"DONE_VERIFIED": "☑", "INFORMATIONAL_ONLY": "N/A", "NOT_APPLICABLE_JUSTIFIED": "N/A"}


def save_reqs(reqs: dict[str, dict]) -> None:
    with REQS.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["done", *REQ_FIELDS])
        w.writeheader()
        w.writerows({"done": DONE_MARK.get(r["status"], "☐"), **r} for r in reqs.values())


def load_mapping() -> dict[str, tuple[list[str], str]]:
    mapping = {}
    for part in sorted((HERE / "mapping").glob("part_*.csv")):
        with part.open(newline="") as f:
            for r in csv.DictReader(f):
                ids = [i.strip() for i in r["requirement_ids"].replace(",", ";").split(";") if i.strip()]
                mapping[r["source_item_id"].strip()] = (ids, r.get("mapping_note", "").strip())
    return mapping


def row_status(ids: list[str], reqs: dict[str, dict]) -> str:
    real = [i for i in ids if i != "INFO"]
    if not real:
        return "INFORMATIONAL_ONLY" if ids else "NOT_AUDITED"
    statuses = [reqs[i]["status"] if i in reqs else "UNAUDITED" for i in real]
    return min(statuses, key=lambda s: PRECEDENCE.index(s) if s in PRECEDENCE else 0)


def sync(summary_only: bool = False) -> None:
    reqs = load_reqs()
    mapping = load_mapping()
    with INVENTORY.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    covered = defaultdict(list)
    for row in rows:
        ids, note = mapping.get(row["source_item_id"], ([], ""))
        row["requirement_ids"] = ";".join(ids)
        row["audit_status"] = row_status(ids, reqs)
        real = [i for i in ids if i in reqs and i != "INFO"]
        row["code_evidence"] = " | ".join(f"{i}: {reqs[i]['code_evidence']}" for i in real if reqs[i]["code_evidence"])[:900]
        states = ", ".join(f"{i}={reqs[i]['status']}" for i in real)
        row["notes"] = "; ".join(p for p in (note, states) if p)[:600]
        row["done"] = DONE_MARK.get(row["audit_status"], "☐")
        for i in ids:
            covered[i].append(row["source_item_id"])
    unknown_ids = sorted({i for ids, _ in mapping.values() for i in ids if i not in reqs})

    by_source = defaultdict(Counter)
    for row in rows:
        by_source[SHORT.get(row["source_filename"], row["source_filename"])][row["audit_status"]] += 1
    req_status = Counter(r["status"] for rid, r in reqs.items() if rid != "INFO")

    print(f"Source items: {len(rows)}  mapped: {sum(1 for r in rows if r['requirement_ids'])}")
    print("Requirements by status:", dict(req_status))
    for src, c in by_source.items():
        print(f"  {src}: {dict(c)}")
    if unknown_ids:
        print("WARNING unknown requirement IDs in mapping:", unknown_ids)
    if summary_only:
        return

    fields = ["done", *[x for x in fields if x != "done"]]
    with INVENTORY.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    save_reqs(reqs)
    _write_matrix(reqs, rows, covered, by_source, req_status)


def _pct_done(c: Counter) -> str:
    actionable = sum(v for k, v in c.items() if k not in ("INFORMATIONAL_ONLY",))
    done = c.get("DONE_VERIFIED", 0) + c.get("NOT_APPLICABLE_JUSTIFIED", 0)
    return f"{(100 * done / actionable):.0f}%" if actionable else "n/a"


def _write_matrix(reqs, rows, covered, by_source, req_status) -> None:
    statuses = PRECEDENCE + ["INFORMATIONAL_ONLY", "NOT_AUDITED"]
    out = ["# JobPilot — Complete Requirements Matrix", "",
           f"Generated by `docs/requirements/tracker.py` on {date.today().isoformat()}. Do not edit by hand: change "
           "`jobpilot-requirements.csv` (status/evidence) or `mapping/part_*.csv` (source coverage) and re-run.", "",
           "Statuses: `DONE_VERIFIED` = code + passing automated test; `PARTIAL`; `BROKEN`; `MISSING`; `UNVERIFIABLE`; "
           "`BLOCKED_EXTERNAL` (needs a credential/approval/real users only the owner can supply); `PLANNED_FUTURE`; "
           "`NOT_APPLICABLE_JUSTIFIED`. Source items with no buildable requirement are `INFORMATIONAL_ONLY`.", "",
           "## Source coverage", "", "| Source | " + " | ".join(s for s in statuses) + " | Items | Done |",
           "|" + "---|" * (len(statuses) + 3)]
    for src, c in by_source.items():
        out.append(f"| {src} | " + " | ".join(str(c.get(s, 0) or "") for s in statuses)
                   + f" | {sum(c.values())} | {_pct_done(c)} |")
    out += ["", "## Requirements by status", ""]
    out += [f"- **{s}**: {req_status[s]}" for s in PRECEDENCE if req_status.get(s)]
    for prio in ("P0", "P1", "P2", "P3"):
        open_ = [r for r in reqs.values() if r["priority"] == prio and r["status"] not in ("DONE_VERIFIED", "NOT_APPLICABLE_JUSTIFIED")]
        out.append(f"- {prio} not yet done: {len(open_)}")
    out += ["", "## Requirements", "", "| ID | Pri | Area | Requirement | Status | Evidence | Tests | Source items |",
            "|---|---|---|---|---|---|---|---|"]
    for rid, r in reqs.items():
        if rid == "INFO":
            continue
        src = covered.get(rid, [])
        refs = ", ".join(src[:6]) + (f" +{len(src) - 6}" if len(src) > 6 else "")
        cell = lambda s: (s or "").replace("|", "/").replace("\n", " ")  # noqa: E731
        out.append(f"| {rid} | {r['priority']} | {r['area']} | {cell(r['title'])} | {r['status']} | "
                   f"{cell(r['code_evidence'])[:220]} | {cell(r['tests'])[:160]} | {refs} |")
    orphans = [rid for rid in reqs if rid != "INFO" and not covered.get(rid)]
    if orphans:
        out += ["", "Requirements from the master prompt with no direct source item (research or cross-cutting): "
                + ", ".join(orphans)]
    MATRIX.write_text("\n".join(out) + "\n")


def set_status(updates: list[tuple]) -> None:
    """updates: (req_id, status, evidence, tests, notes). Empty strings keep the current value."""
    reqs = load_reqs()
    for rid, st, ev, tests, notes in updates:
        if rid not in reqs:
            raise SystemExit(f"unknown requirement {rid}")
        r = reqs[rid]
        if st not in PRECEDENCE:
            raise SystemExit(f"bad status {st} for {rid}")
        r["status"] = st
        r["code_evidence"] = ev or r["code_evidence"]
        r["tests"] = tests or r["tests"]
        r["notes"] = notes or r["notes"]
        r["updated"] = date.today().isoformat()
    save_reqs(reqs)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "set":  # tracker.py set ID STATUS [evidence] [tests] [notes]
        a = sys.argv[2:] + [""] * 5
        set_status([(a[0], a[1], a[2], a[3], a[4])])
        sync()
    else:
        sync(summary_only="--summary" in sys.argv)
