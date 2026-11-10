"""Builds mapping/part_*.csv for source items not yet mapped by hand.

Each item gets (1) its section's requirement IDs, refined by (2) keyword rules over the item text. Headings and
document furniture become INFO. Hand-reviewed parts (part_A.csv, and any part_*_manual.csv) always win: rows
already present in them are skipped. Re-run after editing rules:  python docs/requirements/mapping/build_mapping.py
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
INVENTORY = HERE.parents[2] / "JobPilot_FULL_SOURCE_COVERAGE_INVENTORY.csv"

# Section title (prefix match, case-insensitive) -> default requirement IDs.
SECTIONS: list[tuple[str, str]] = [
    # 01 vision
    ("1. The Big Idea", "INFO"), ("2. The JobPilot Loop", "ARC-01;PRF-10"), ("3. The Product Promise", "NEG-01;MAT-05"),
    ("4. Profile, Resume & Application Readiness", "PRF-01;RES-01"), ("5. A Candidate's First 10 Minutes", "PRF-08"),
    ("6. Progressive Disclosure", "PRF-11"), ("7. Local and International", "INTL-08;PRF-07"),
    ("8. Who We Are Building For", "PRF-11"), ("9. Why We Are Different", "MAT-07;MAT-09"),
    ("10. Competitive Reality", "INFO"), ("11. The Founder Philosophy", "NEG-01;NEG-05"),
    ("12. Mentoring", "MEN-06;MEN-01"), ("13. What Feedback We Need", "ANA-07;GTM-01"), ("14. Launch Strategy", "GTM-02"),
    ("15. Launch Recommendation", "GTM-02"), ("16. North Star", "ANA-04"), ("17. Founder Roadmap", "GATE-10"),
    ("Sources & Reference Notes", "INFO"), ("Document opening", "INFO"),
    # 02 / .pages technical spec
    ("0. Technical North Star", "ARC-01"), ("1. Reference Architecture", "ARC-05;ARC-02"), ("2. Product Modules", "ARC-01"),
    ("3. Resume Builder", "RES-01"), ("4. Resume Template System", "RES-05;RES-06"), ("5. Resume Editor Data Model", "RES-16;ARC-01"),
    ("6. Dynamic Editing Flow", "RES-01;RES-04"), ("1. Candidate opens Resume Builder", "RES-01"),
    ("2. Load the candidate's master profile", "RES-01;PRF-01"), ("3. User selects a template", "RES-05"),
    ("4. User edits text", "RES-01;RES-02"), ("5. System validates required fields", "RES-06;RES-07"),
    ("6. Optional job target", "RES-08;RES-17"), ("7. System calculates job-specific feedback", "RES-17"),
    ("8. User accepts or rejects", "RES-13"), ("9. Live preview updates", "RES-04;RES-10;RES-08"),
    ("7. ATS-Safe Resume Mode", "RES-07"), ("8. Resume-to-Job Feedback", "RES-17;RES-14"),
    ("9. Core Data Model", "ARC-01"), ("10. Job Discovery Pipeline", "DSC-04"), ("1. Create a DiscoveryRun", "DSC-04;DSC-03"),
    ("2. Load target roles", "DSC-04;PRF-06"), ("3. Fetch from permitted sources", "DSC-05;DSC-13"),
    ("4. Normalise raw jobs", "DSC-06;JOB-03"), ("5. Extract structured requirements", "DSC-15"),
    ("6. Canonicalise title", "DSC-06"), ("7. Deduplicate", "DSC-07;JOB-04"), ("8. Persist source provenance", "DSC-08"),
    ("9. Run deterministic hard filters", "MAT-01;JOB-05;MAT-07;NOT-01"), ("11. Matching and Eligibility", "MAT-01;MAT-02"),
    ("12. Gap + Evidence Engine", "MAT-07;MAT-09;MAT-10"), ("13. Learning Engine", "LRN-01;LRN-03"),
    ("14. Application + Browser Extension", "APP-01;APP-09;APP-10"), ("15. Application State Machine", "APP-03;APP-04"),
    ("16. Mentor & Reflection Engine", "MEN-01;MEN-02"), ("17. International Mobility Engine", "INTL-02;INTL-03"),
    ("18. API Surface", "ARC-02"), ("19. Background Jobs", "JOB-16"), ("20. Security & Privacy", "SEC-01;ID-03"),
    ("21. Testing & Quality Gates", "TST-01;TST-02"), ("22. Definition of Done", "RES-01;GATE-02"),
    ("23. Delivery Sequence", "GATE-10"),
    # 03 AWS
    ("1. What We Are Optimising For", "AWS-03"), ("2. Document Generation & File Handling", "RES-11;ARC-03;SEC-02"),
    ("3. Recommended Beta Architecture", "AWS-01"), ("4. Lean Beta Cost", "AWS-03"), ("5. Small Production Cost", "AWS-03"),
    ("6. Growth Cost", "AWS-03"), ("7. Document Generation Cost", "RES-11;AWS-04"), ("8. AI and External Data Costs", "AWS-04;ARC-04"),
    ("9. AWS Cost Controls", "AWS-02"), ("10. Cost Per Candidate", "AWS-04"), ("11. When to Upgrade", "AWS-05"),
    ("12. Infrastructure as Code", "AWS-02"), ("13. Founder Budget Rule", "AWS-03;AWS-06"),
    # 04 PRD
    ("0. MVP Definition", "GATE-10"), ("1. MVP North Star Journey", "TST-03;PRF-08"), ("2. Priority System", "INFO"),
    ("3. Screen Map", "ARC-02"), ("4. Onboarding PRD", "PRF-08"), ("5. Discover PRD", "DSC-10;DSC-11;DSC-12"),
    ("6. Resume & Document PRD", "RES-01"), ("7. Resume & Document UX Principles", "RES-03;RES-04"),
    ("8. Application PRD", "APP-01;APP-04"), ("9. Applications & Tracker PRD", "APP-06;APP-07"),
    ("10. Gap & Learning PRD", "MAT-07;LRN-01"), ("11. Mentor PRD", "MEN-01;MEN-02"), ("12. International PRD", "INTL-03;INTL-07"),
    ("13. Analytics & Events", "ANA-03"), ("14. Suggested MVP Sprint Plan", "GATE-10"), ("15. Beta Launch Gates", "GATE-10"),
    ("16. What We Should Explicitly Avoid", "NEG-04"), ("17. Developer Handoff Checklist", "GATE-10"),
    ("18. The Beta Success Test", "GATE-09"),
    # Beta hosting plan (40 sections)
    ("JobPilot", "INFO"), ("Free Private Beta Hosting", "INFO"), ("Objective", "DEP-01"), ("1. Target Architecture", "DEP-01;DEP-02"),
    ("2. Host Machine Requirements", "DEP-11"), ("3. Why We Should Use Docker", "DEP-01"),
    ("4. Recommended Repository Structure", "DEP-10"), ("5. Docker Compose Architecture", "DEP-01;DEP-03"),
    ("6. PostgreSQL", "DEP-07;DEP-03"), ("7. Backend", "DEP-02;DEP-04"), ("8. Frontend", "DEP-02"), ("9. Nginx", "DEP-02"),
    ("Static frontend", "DEP-02"), ("API reverse proxy", "DEP-02"), ("10. No Domain Requirement", "DEP-08;DEP-01"),
    ("11. Important Limitation of the Quick Tunnel", "DEP-09"), ("Private beta", "DEP-09"), ("Public production", "AWS-01"),
    ("12. Installation on Linux", "DEP-11;DEP-04"), ("AI provider credentials", "DEP-04;ARC-04"),
    ("Email credentials if enabled", "DEP-04;NOT-05"), ("13. Start JobPilot", "DEP-01;DEP-13"), ("14. Database Migration", "DEP-06"),
    ("15. Health Check", "DEP-05;OPS-06"), ("16. Start the Public Beta Tunnel", "DEP-08"),
    ("17. Only Nginx Should Be Public", "DEP-03"), ("18. Authentication", "ID-01;ID-10"), ("19. User Isolation", "ID-03;TST-05"),
    ("20. Resume File Storage", "ARC-03;DEP-07"), ("Simplest", "ARC-03;DEP-07"), ("Better", "ARC-03;AWS-01"),
    ("21. Resume PDF Generation", "RES-10;RES-11"), ("22. Job Discovery Scheduler", "DEP-15;JOB-01"),
    ("Option 1 — Linux cron", "DEP-15"), ("Option 2 — Internal application scheduler", "DEP-15;JOB-16"),
    ("23. Background Jobs", "ARC-05;JOB-16"), ("24. Backups", "OPS-01"), ("Daily PostgreSQL backup", "OPS-01;OPS-02"),
    ("25. Host Machine Failure Strategy", "OPS-08;OPS-03"), ("26. Deployment Update Procedure", "DEP-13"),
    ("27. Rollback", "DEP-14"), ("28. Logging", "OPS-04;OPS-05"), ("29. Monitoring", "OPS-06"), ("30. Disk Protection", "OPS-07"),
    ("31. Security Rules", "DEP-03;SEC-03"), ("32. Development vs Beta Configuration", "DEP-10"), ("Development", "DEP-10"),
    ("Beta", "DEP-10;DEP-04"), ("33. Recommended Beta Environment", "DEP-04;DEP-10"),
    ("34. What We Are Deliberately NOT Building Yet", "NEG-04;AWS-06"), ("35. Future Migration Path", "AWS-01"),
    ("Today", "DEP-01"), ("Later", "AWS-01"), ("36. Developer Definition of Done", "GATE-10"), ("Application", "TST-03"),
    ("Hosting", "DEP-01;DEP-05"), ("Recovery", "OPS-03"), ("37. Expected Cost", "AWS-03"), ("AWS", "AWS-03"),
    ("Domain", "DEP-08"), ("Cloudflare Quick Tunnel", "DEP-08"), ("Linux machine", "DEP-11"),
    ("38. Important Beta Limitation", "DEP-09;DEP-11"), ("39. Recommended First Deployment", "DEP-01;DEP-13"),
    ("40. The Principle", "DEP-01"),
]

# Keyword rules: regex over item text -> extra IDs (added in front of the section default when they match).
RULES: list[tuple[str, str]] = [
    (r"\bregister|login|logout|password|session|jwt|bcrypt|argon", "ID-01"),
    (r"\brole|admin only|least privilege|mentor role|candidate role", "ID-02"),
    (r"user_?id|own(ed|er)?ship|isolation|another user|idor|bola|tenant", "ID-03"),
    (r"rate.?limit|brute", "ID-10"), (r"\binvite", "ID-11"),
    (r"export (my|your|their)? ?data|data export|delete (account|profile|my)|deletion|right to", "ID-05;ID-06"),
    (r"consent|opt.?in", "ID-07"), (r"retention|purge|cleanup", "ID-08;JOB-15"), (r"\baudit", "ID-09"),
    (r"master profile|candidateprofile|candidate profile", "PRF-01"), (r"provenance|verified fact|verification flag", "PRF-02"),
    (r"upload|parse status|parsing", "PRF-03"), (r"without (a|an existing) resume|manual(ly)? (profile|create)|student", "PRF-04"),
    (r"confirm|correct", "PRF-05"), (r"career ?goal|target (role|title)|seniority|relocat|notice period", "PRF-06"),
    (r"india ?/ ?international|international|work authori[sz]ation|sponsor", "PRF-07"),
    (r"snapshot|completeness", "PRF-09"), (r"next (step|action)|call to action|\bcta\b", "PRF-10"),
    (r"progressive", "PRF-11"), (r"proficien", "PRF-12"),
    (r"jobsource|job source|source registry|source health", "DSC-01;ADM-01"), (r"run discovery|daily discovery|run now", "DSC-02;JOB-01"),
    (r"discoveryrun|progress|run status", "DSC-03"), (r"adapter|greenhouse|lever|ashby|\bapi\b.*job|pagination|retry|backoff|circuit", "DSC-05"),
    (r"normali[sz]", "DSC-06"), (r"dedup|duplicate|hash", "DSC-07"), (r"provenance|raw (job|reference)|source url|canonical url", "DSC-08"),
    (r"stale|closed (post|job)|expired", "DSC-09"), (r"search|filter", "DSC-10"), (r"\bsave\b|dismiss", "DSC-11"),
    (r"job detail", "DSC-12"), (r"robots|terms of service|tos\b|scrap|captcha|anti.?bot", "DSC-13;NEG-02"),
    (r"jobrequirement|requirement extraction|extract.*requirement", "DSC-15"),
    (r"eligib|hard filter|work permit", "MAT-01"), (r"30%|20%|15%|weight", "MAT-02"), (r"score_version|scoreversion|breakdown", "MAT-03"),
    (r"unknown", "MAT-04"), (r"explain|why (this|it) match", "MAT-05"), (r"alias|skill normal|taxonomy", "MAT-06"),
    (r"\bgap", "MAT-07"), (r"best next gap|single (best|next)", "MAT-08"),
    (r"aware|practising|practicing|interview ready|project evidence|professional experience", "MAT-09"),
    (r"evidence", "MAT-10"), (r"recompute", "MAT-11"), (r"calibrat|predict", "MAT-12;FUT-01"),
    (r"template", "RES-05"), (r"reorder|hide section|visibility", "RES-02"), (r"autosave|auto-save|saved state", "RES-03"),
    (r"preview|page break", "RES-04"), (r"\bats\b", "RES-07"), (r"version|clone|copy", "RES-08"), (r"immutable|locked", "RES-09"),
    (r"\bpdf\b|selectable|searchable", "RES-10"), (r"cache|checksum", "RES-11"), (r"docx|\bword\b", "RES-12"),
    (r"suggest|rewrite|accept|reject", "RES-13"), (r"keyword stuff|weak bullet|unsupported claim|overflow|length", "RES-14"),
    (r"fabricat|invent|never (add|claim)", "RES-15;NEG-05"),
    (r"resumetemplate|resumeversion|resumesection|resumeblock|resumebullet|resumeexport|resumefeedback", "RES-16"),
    (r"application package|prepared|checklist", "APP-01"), (r"resume_version_id|resume version used", "APP-02"),
    (r"saved\s*(→|->)|prepared\s*(→|->)|opened|pending|applied|screening|assessment|withdrawn|archived", "APP-03"),
    (r"submit", "APP-04;NEG-01"), (r"event|timestamp|history", "APP-05"), (r"tracker|kanban", "APP-06"),
    (r"follow.?up|reminder|recruiter|reference number", "APP-07"), (r"rejection|rejected", "APP-08;INT-05"),
    (r"extension|manifest|content script|\bpair", "APP-09"), (r"autofill|prefill|field map|demographic|overwrite", "APP-10"),
    (r"unsupported site|fallback|copy.?(and|/).?paste", "APP-11"),
    (r"interview question|question set|competenc", "INT-01"), (r"mock|practice", "INT-02"),
    (r"glassdoor|reddit|ambitionbox|indeed", "INT-03"), (r"interviewfeedback|interview feedback|interview record", "INT-04"),
    (r"funnel|conversion", "INT-06;ANA-02"),
    (r"learningresource|learning resource|course|resource", "LRN-01"), (r"rank", "LRN-02"),
    (r"learningsession|session start|idle|active time", "LRN-03"), (r"knowledge check|exercise|\blabs?\b", "LRN-04"),
    (r"mentor", "MEN-01"), (r"reflection|outcome, obstacle|weekly", "MEN-02"), (r"bottleneck|diagnos", "MEN-03"),
    (r"action (plan|list|checklist)|checklist", "MEN-04"), (r"one.on.one|1-on-1|virtual|human mentor", "MEN-07"),
    (r"country|countries", "INTL-01"), (r"visa", "INTL-02"), (r"country.fit|country fit", "INTL-03"),
    (r"sponsor", "INTL-04"), (r"relocation", "INTL-05"), (r"source change|monitor", "INTL-06"),
    (r"legal advice|not.*approval", "INTL-07;NEG-06"),
    (r"notif|alert", "NOT-01"), (r"follow.?up alert|upcoming schedule|reminder", "NOT-02"),
    (r"dashboard", "ANA-01"), (r"onboarding_completed|job_viewed|resume_exported|application_submitted|reflection_completed|analytics event|instrument", "ANA-03"),
    (r"north star|weekly active|activation", "ANA-04"), (r"report", "ANA-06"), (r"feedback", "ANA-07"),
    (r"admin", "ADM-05"), (r"\bai\b|llm|prompt", "ARC-04"), (r"queue|worker", "ARC-05"),
    (r"\bs3\b|storage", "ARC-03"), (r"index|transaction", "ARC-06"),
    (r"daily_discovery", "JOB-01"), (r"source_refresh", "JOB-02"), (r"job_normali[sz]ation", "JOB-03"),
    (r"job_deduplication", "JOB-04"), (r"job_matching", "JOB-05"), (r"gap_generation", "JOB-06"),
    (r"resume_feedback_generation", "JOB-07"), (r"resource_refresh", "JOB-08"), (r"notification_dispatch", "JOB-09"),
    (r"alert_email_ingestion", "JOB-10"), (r"report_generation", "JOB-11"), (r"visa_source_check", "JOB-12"),
    (r"visa_change_detection", "JOB-13"), (r"analytics_rollup", "JOB-14"), (r"cleanup_and_retention", "JOB-15"),
    (r"validat|sanitiz|path traversal|file type|size limit|mime", "SEC-01"), (r"signed url|download", "SEC-02"),
    (r"cors|csrf|header|https|tls", "SEC-03"), (r"secret|token|\.env", "SEC-06;DEP-04"),
    (r"nginx|proxy_pass|location /|/api", "DEP-02"), (r"5432|6379|:5000|\bports?\b|expose|0\.0\.0\.0|127\.0\.0\.1", "DEP-03"),
    (r"/api/health|health", "DEP-05"), (r"migrat|prisma|alembic", "DEP-06"), (r"volume|/opt/jobpilot/data|uploads|exports", "DEP-07"),
    (r"cloudflared|tunnel|trycloudflare", "DEP-08"), (r"\bsse\b|server-sent|in-flight", "DEP-09"),
    (r"docker-compose\.dev|docker-compose\.beta|node_env|development|\bdev\b", "DEP-10"),
    (r"ubuntu|cpu|ram|\bgb\b|ssd|broadband|sleep|power", "DEP-11"), (r"reboot|systemd|restart", "DEP-12"),
    (r"git pull|docker compose build|up -d|deploy", "DEP-13"), (r"rollback|roll back|previous (image|release)", "DEP-14"),
    (r"cron|scheduler|schedule", "DEP-15"), (r"pg_dump|backup", "OPS-01"), (r"encrypt|off.?host|gpg|rclone", "OPS-02"),
    (r"restore|rpo|rto|second machine", "OPS-03"), (r"\blogs?\b|logging|logger", "OPS-04"), (r"rotat", "OPS-05"),
    (r"monitor|uptime|docker compose ps|docker compose logs", "OPS-06"), (r"disk|df -h|70%|80%|90%", "OPS-07"),
    (r"terraform|iac|ci/cd", "AWS-02"), (r"\$\d|cost|price|pricing|budget", "AWS-03"),
    (r"eks|opensearch|nat gateway|kubernetes|kafka|microservice|redis", "AWS-06;NEG-04"),
    (r"route 53|cloudfront|rds|ecs|fargate|ec2|eventbridge|\bses\b|cloudwatch|secrets manager", "AWS-01"),
    (r"\bbots?\b|mass appl|auto.?submit|auto.?apply", "NEG-01"), (r"guarantee", "NEG-03"),
]

HEADING_INFO = re.compile(r"^(jobpilot|table of contents|contents|page \d+|\d+\.?|text|bash|env|ini|yaml|yml|nginx|json|sql|or:?|and:?|[^a-z0-9]{1,6}|#+ ?)$", re.I)


def ids_for(row: dict) -> tuple[str, str]:
    text = row["source_content"].strip()
    section = row["source_section"].strip()
    if section.lower().startswith("sources & reference"):
        return "INFO", "reference citation"
    default = next((ids for prefix, ids in SECTIONS if section.lower().startswith(prefix.lower())), "INFO")
    low = text.lower()
    if not text or HEADING_INFO.match(text) or len(text) < 4:
        return "INFO", "blank, page marker or document furniture"
    extra = []
    for pattern, ids in RULES:
        if re.search(pattern, low):
            for i in ids.split(";"):
                if i not in extra:
                    extra.append(i)
    if row["item_kind"] == "HEADING" and default == "INFO" and not extra:
        return "INFO", "heading with no requirement"
    if default == "INFO" and not extra:
        return "INFO", "context/narrative"
    base = [] if default == "INFO" else default.split(";")
    # Section default first (it is the item's home), then up to three keyword refinements.
    ids = list(dict.fromkeys(base + [e for e in extra if e not in base][:3]))
    return ";".join(ids), f"section default ({section[:40]}) + keywords" if extra else f"section default ({section[:40]})"


def main() -> None:
    with INVENTORY.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    done = set()
    for part in HERE.glob("part_*.csv"):
        if part.name.startswith("part_auto"):
            continue
        with part.open(newline="") as f:
            done |= {r["source_item_id"] for r in csv.DictReader(f)}
    out = HERE / "part_auto.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source_item_id", "requirement_ids", "mapping_note"])
        n = 0
        for row in rows:
            if row["source_item_id"] in done:
                continue
            ids, note = ids_for(row)
            w.writerow([row["source_item_id"], ids, note])
            n += 1
    print(f"hand-mapped: {len(done)}  auto-mapped: {n}  -> {out.name}")


if __name__ == "__main__":
    main()
