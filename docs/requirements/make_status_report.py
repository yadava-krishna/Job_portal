"""Fill the generated blocks of JobPilot_STATUS_REPORT.md (summary, full checklist, source coverage) from the CSVs.

Run after the tracker sync (audit_progress.py does this automatically). Text outside the AUTO blocks is hand-written
and left untouched.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORT = ROOT / "JobPilot_STATUS_REPORT.md"
REQS = HERE / "jobpilot-requirements.csv"
INVENTORY = ROOT / "JobPilot_FULL_SOURCE_COVERAGE_INVENTORY.csv"

PLAIN = {"DONE_VERIFIED": "Done and tested", "PARTIAL": "Partly done", "MISSING": "Not started",
         "BLOCKED_EXTERNAL": "Needs something from you / outside", "PLANNED_FUTURE": "Later by design",
         "BROKEN": "Broken", "UNAUDITED": "Not reviewed"}
DOCS = [("JobPilot_01", "01 Product vision, strategy & launch"), ("JobPilot_02", "02 Technical specification"),
        ("JobPilot_03", "03 AWS cost plan"), ("JobPilot_04", "04 Product requirements (PRD)"),
        (".pages", "Edited specification (.pages)"), ("Pasted text", "Beta hosting plan (pasted text)")]


def _doc_name(filename: str) -> str:
    for key, name in DOCS:
        if key.lower() in filename.lower():
            return name
    return filename


def _cell(text: str) -> str:
    return (text or "").replace("|", "/").replace("\n", " ").strip()


def build() -> dict[str, str]:
    reqs = [r for r in csv.DictReader(REQS.open()) if r["req_id"] != "INFO"]
    rows = list(csv.DictReader(INVENTORY.open(encoding="utf-8-sig")))
    st = Counter(r["status"] for r in reqs)
    by_pri = defaultdict(Counter)
    for r in reqs:
        by_pri[r["priority"]][r["status"] == "DONE_VERIFIED"] += 1

    lines = ["| | Count |", "|---|---|", f"| Requirements in total | **{len(reqs)}** |"]
    for k in ("DONE_VERIFIED", "PARTIAL", "MISSING", "BLOCKED_EXTERNAL", "PLANNED_FUTURE", "BROKEN"):
        if st[k]:
            lines.append(f"| {'☑ ' if k == 'DONE_VERIFIED' else '☐ '}{PLAIN[k]} | {st[k]} |")
    actionable = [r for r in rows if r["done"] != "N/A"]
    done_rows = sum(1 for r in actionable if r["done"] == "☑")
    lines += ["", f"**{st['DONE_VERIFIED']} of {len(reqs)} requirements ({st['DONE_VERIFIED'] * 100 // len(reqs)}%) are done and tested.** "
              f"Of the {len(rows)} lines in the six source documents, {len(rows) - len(actionable)} are background text with nothing to build; "
              f"{done_rows} of the remaining {len(actionable)} ({done_rows * 100 // max(1, len(actionable))}%) are fully covered by finished work.",
              "", "| Priority | Done | Not done |", "|---|---|---|"]
    for p in sorted(by_pri):
        label = {"P0": "P0 (needed for the private beta)", "P1": "P1", "P2": "P2", "P3": "P3 (future)"}.get(p, p)
        lines.append(f"| {label} | {by_pri[p][True]} | {by_pri[p][False]} |")
    summary = "\n".join(lines)

    areas = defaultdict(list)
    for r in reqs:
        areas[r["area"]].append(r)
    out = []
    for area, items in areas.items():
        n = sum(1 for r in items if r["status"] == "DONE_VERIFIED")
        out += [f"### {area}: {n} of {len(items)} done", "",
                "| | ID | Priority | Requirement | Status / what's missing |", "|---|---|---|---|---|"]
        for r in items:
            done = r["status"] == "DONE_VERIFIED"
            note = PLAIN.get(r["status"], r["status"])
            if not done and r["notes"]:
                note += f": {r['notes']}"
            out.append(f"| {'☑' if done else '☐'} | {r['req_id']} | {r['priority']} | {_cell(r['title'])} | {_cell(note)} |")
        out += [""]
    checklist = "\n".join(out).rstrip()

    per = defaultdict(Counter)
    for r in rows:
        per[_doc_name(r["source_filename"])][r["done"]] += 1
    cov = ["| Source document | Lines | Background (N/A) | ☑ Covered | ☐ Not yet | Covered % |", "|---|---|---|---|---|---|"]
    for _key, name in DOCS:
        c = per.get(name)
        if not c:
            continue
        act = c["☑"] + c["☐"]
        cov.append(f"| {name} | {sum(c.values())} | {c['N/A']} | {c['☑']} | {c['☐']} | {c['☑'] * 100 // max(1, act)}% |")
    tot = Counter()
    for c in per.values():
        tot.update(c)
    act = tot["☑"] + tot["☐"]
    cov.append(f"| **All six** | **{sum(tot.values())}** | **{tot['N/A']}** | **{tot['☑']}** | **{tot['☐']}** | **{tot['☑'] * 100 // max(1, act)}%** |")
    cov += ["", "Every line has been reviewed and linked to a requirement or marked as background. No line is left unreviewed."
            if all(r["audit_status"] != "NOT_AUDITED" for r in rows) else "Some lines are not yet reviewed."]
    return {"summary": summary, "checklist": checklist, "coverage": "\n".join(cov)}


def write() -> None:
    text = REPORT.read_text()
    for key, body in build().items():
        text = re.sub(rf"(<!-- AUTO:{key} -->)(.*?)(<!-- /AUTO -->)", lambda m: f"{m.group(1)}\n{body}\n{m.group(3)}", text, count=1, flags=re.S)
    REPORT.write_text(text)
    print(f"updated {REPORT.name}")


if __name__ == "__main__":
    write()
