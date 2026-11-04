from datetime import date

import pytest

from conftest import make_pdf
from core.settings import ConfigError
from resume.profile_builder import ProfileBuilder, merge_intervals, months_between, split_role_header, total_experience_months
from resume.resume_parser import ResumeParseError, parse_date_range, parse_month


def test_months_inclusive():
    assert months_between(date(2020, 1, 1), date(2020, 1, 1)) == 1
    assert months_between(date(2020, 11, 1), date(2021, 12, 1)) == 14


def test_overlapping_periods_counted_once():
    intervals = [(date(2020, 1, 1), date(2020, 12, 1)), (date(2020, 6, 1), date(2021, 5, 1)), (date(2022, 1, 1), date(2022, 3, 1))]
    assert total_experience_months(intervals) == 17 + 3
    assert len(merge_intervals(intervals)) == 2


def test_adjacent_periods_merge_without_gap_double_count():
    assert total_experience_months([(date(2020, 1, 1), date(2020, 6, 1)), (date(2020, 7, 1), date(2020, 12, 1))]) == 12


@pytest.mark.parametrize("token,expected", [("Oct 2022", date(2022, 10, 1)), ("Sept. 2019", date(2019, 9, 1)), ("03/2019", date(2019, 3, 1)),
                                            ("10.2020", date(2020, 10, 1)), ("January 2021", date(2021, 1, 1))])
def test_parse_month(token, expected):
    assert parse_month(token) == expected


def test_present_uses_current_month():
    start, end, current = parse_date_range("Oct 2022 – Present", date(2026, 11, 3))
    assert (start, end, current) == (date(2022, 10, 1), date(2026, 11, 1), True)


@pytest.mark.parametrize("header,title,company", [
    ("Associate - Membership operations I Example Global solutions", "Associate - Membership operations", "Example Global solutions"),
    ("senior Accounts Receivable Associate I Sample Healthcare", "senior Accounts Receivable Associate", "Sample Healthcare"),
    ("Accounts Receivable Associate delta Healthcare", "Accounts Receivable Associate", "delta Healthcare"),
    ("Alpha Ltd | Senior Analyst", "Senior Analyst", "Alpha Ltd"),
])
def test_split_role_header(header, title, company):
    t, c, _ = split_role_header(header)
    assert (t, c) == (title, company)


def test_synthetic_profile(settings):
    p = ProfileBuilder(settings).build(settings.resume_path, today=date(2026, 11, 3))
    assert p["name"] == "TEST CANDIDATE"
    assert [r["company"] for r in p["experience"]] == ["Alpha Finance Ltd", "Beta Services"]
    # Jun 2020 - Mar 2022 overlaps Jan 2022 - Nov 2026: union is Jun 2020 - Nov 2026 = 78 months
    assert p["total_experience"]["months"] == 78
    skills = {s["name"] for s in p["skills"]}
    assert {"Accounts Receivable", "Payment Posting", "PivotTables", "Data Validation"} <= skills
    assert p["education"][0]["year"] == 2019
    assert any("30%" in a["metrics"] for a in p["achievements"])
    seed = {x["skill"]: x["found_in_resume"] for x in p["seed_skill_verification"]}
    assert seed == {"Accounts Receivable": True, "Payment Posting": True, "Quantum Computing": False}
    assert "Quantum Computing" not in skills
    assert any("Quantum Computing" in w for w in p["warnings"])


def test_profile_cache_refreshes_when_resume_changes(settings, resume_pdf):
    pb = ProfileBuilder(settings)
    first = pb.load_or_build()
    assert pb.load_or_build()["resume"]["sha256"] == first["resume"]["sha256"]
    make_pdf(resume_pdf, ["NEW PERSON", "Bengaluru | x", "HEADLINE", "PROFESSIONAL EXPERIENCE", "Analyst | Gamma Co",
                          "Jan 2021 - Dec 2021", "• Did accounts receivable work for many clients across regions."])
    second = pb.load_or_build()
    assert second["resume"]["sha256"] != first["resume"]["sha256"]
    assert second["name"] == "NEW PERSON"


def test_missing_resume_path(settings_factory, tmp_path):
    s = settings_factory(candidate__resume_path=str(tmp_path / "nope.pdf"))
    with pytest.raises(ConfigError, match="Resume not found"):
        ProfileBuilder(s).load_or_build()


def test_malformed_pdf(settings_factory, tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf at all")
    s = settings_factory(candidate__resume_path=str(bad))
    with pytest.raises(ResumeParseError):
        ProfileBuilder(s).load_or_build()
