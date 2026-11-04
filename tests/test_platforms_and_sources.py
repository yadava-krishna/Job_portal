import json

import pytest

from core.models import Platform
from discovery.deduplication import fingerprint, job_key
from discovery.sources import (
    EmailAlertSource,
    ImportInboxSource,
    parse_alert_email,
    parse_text_jobs,
    record_from_mapping,
)
from applications.submission_verifier import match_confirmation_email
from platforms import detect_platform, get_adapter
from platforms.base_platform import PlatformError, SubmissionNotPermitted


@pytest.mark.parametrize("platform,url,expected", [
    (Platform.LINKEDIN, "https://www.linkedin.com/jobs/view/4012345678/?trackingId=x", "4012345678"),
    (Platform.LINKEDIN, "https://www.linkedin.com/comm/jobs/view/4012345678?refId=y", "4012345678"),
    (Platform.LINKEDIN, "https://www.linkedin.com/jobs/view/financial-analyst-at-acme-4012345678", "4012345678"),
    (Platform.LINKEDIN, "https://www.linkedin.com/jobs/search/?currentJobId=4012345678&keywords=x", "4012345678"),
    (Platform.INDEED, "https://in.indeed.com/viewjob?jk=0123456789abcdef&from=serp", "0123456789abcdef"),
    (Platform.INDEED, "https://in.indeed.com/rc/clk?jk=ABCDEF0123456789&fccid=1", "abcdef0123456789"),
    (Platform.NAUKRI, "https://www.naukri.com/job-listings-financial-analyst-initech-bengaluru-3-to-6-years-031125012345?src=jobsearch", "031125012345"),
    (Platform.LINKEDIN, "https://www.linkedin.com/company/acme", None),
])
def test_job_id_parsing(platform, url, expected):
    assert get_adapter(platform).identify_job_id(url) == expected


def test_canonical_urls():
    assert get_adapter(Platform.LINKEDIN).canonical_url("4012345678") == "https://www.linkedin.com/jobs/view/4012345678/"
    assert get_adapter(Platform.INDEED).canonical_url("0123456789abcdef") == "https://in.indeed.com/viewjob?jk=0123456789abcdef"
    assert get_adapter(Platform.NAUKRI).canonical_url("031125012345") is None


def test_detect_platform_requires_official_https_domain():
    assert detect_platform("https://www.naukri.com/job-listings-x-123456789") == Platform.NAUKRI
    assert detect_platform("https://linkedin.com.evil.example/jobs/view/1") is None
    assert detect_platform("http://www.linkedin.com/jobs/view/1") is None


def test_search_links_cover_titles_and_locations(settings):
    for p in Platform:
        links = get_adapter(p, settings).build_search_links(settings.search)
        assert len(links) == len(settings.search.job_titles) * len(settings.search.locations)
        assert all(l.url.startswith("https://") for l in links)
    li = get_adapter(Platform.LINKEDIN, settings).build_search_links(settings.search)
    assert "f_TPR=r86400" in li[0].url
    assert any("f_WT=2" in l.url for l in li if "Remote" in l.location)


def test_submission_is_never_automated():
    adapter = get_adapter(Platform.LINKEDIN)
    assert not adapter.capabilities.automated_apply and not adapter.capabilities.automated_search
    with pytest.raises(SubmissionNotPermitted):
        adapter.submit_application(None, {})


def test_job_key_with_and_without_id():
    assert job_key(Platform.LINKEDIN, "123", "A", "B", None) == "linkedin:123"
    k1 = job_key(Platform.NAUKRI, None, "Acme Pvt Ltd", "Financial Analyst", "https://www.naukri.com/x?utm_source=a")
    k2 = job_key(Platform.NAUKRI, None, "ACME Private Limited", "financial analyst", "https://www.naukri.com/x/")
    assert k1 == k2 and k1.startswith("naukri:h:")
    assert fingerprint("Acme India Pvt. Ltd.", "Sr. Financial Analyst") == fingerprint("ACME", "Senior Financial Analyst")


def test_inbox_formats(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.json").write_text(json.dumps([{"url": "www.linkedin.com/jobs/view/4000000009", "title": "FA", "company": "X"}]))
    (inbox / "b.csv").write_text("job_url,job_title,company_name,platform\n,MIS Analyst,Y,Naukri\n")
    (inbox / "c.txt").write_text("URL: https://in.indeed.com/viewjob?jk=0123456789abcdef\nTitle: Revenue Analyst\nCompany: Z\n---\nFull description here.\n")
    (inbox / "d.json").write_text(json.dumps({"url": "https://example.com/job/1", "title": "Unknown site"}))
    src = ImportInboxSource(inbox)
    assert [r.title for r in src.fetch(Platform.LINKEDIN)] == ["FA"]
    assert [r.title for r in src.fetch(Platform.NAUKRI)] == ["MIS Analyst"]
    indeed = src.fetch(Platform.INDEED)
    assert indeed[0].description == "Full description here."
    assert any("platform could not be determined" in e for _, e in src.errors())
    src.archive("2026-11-04")
    assert not list(inbox.glob("*.json"))
    assert (inbox / "failed" / "2026-11-04" / "d.json").exists()


def test_text_format_multiple_jobs():
    jobs = parse_text_jobs("Title: A\nPlatform: Naukri\n---\nJD one\n===\nTitle: B\nPlatform: Indeed\n---\nJD two")
    assert [j["title"] for j in jobs] == ["A", "B"]
    assert jobs[1]["description"] == "JD two"


def test_record_requires_title_or_url():
    with pytest.raises(ValueError):
        record_from_mapping({"platform": "Naukri", "company": "X"}, source="manual")


LINKEDIN_ALERT = """
<html><body>
<a href="https://www.linkedin.com/comm/jobs/view/4011111111/?trackingId=abc"><img src="logo.png"></a>
<a href="https://www.linkedin.com/comm/jobs/view/4011111111/?trackingId=abc">Financial Analyst</a>
<p>Acme Corp · Bengaluru, Karnataka, India</p>
<a href="https://www.linkedin.com/comm/jobs/view/4022222222/">FP&amp;A Analyst</a>
<p>Globex · Remote</p>
<a href="https://www.linkedin.com/comm/jobs/view/4022222222/">View job</a>
<a href="https://www.linkedin.com/comm/jobs/search">See all jobs</a>
</body></html>"""


def test_parse_linkedin_alert_email():
    records = parse_alert_email(LINKEDIN_ALERT, Platform.LINKEDIN)
    by_id = {r.job_id: r for r in records}
    assert set(by_id) == {"4011111111", "4022222222"}
    assert by_id["4011111111"].title == "Financial Analyst"
    assert by_id["4011111111"].company == "Acme Corp"
    assert by_id["4011111111"].location == "Bengaluru, Karnataka, India"
    assert by_id["4022222222"].title == "FP&A Analyst"
    assert all(r.description is None for r in records)  # job pages are never fetched


def test_confirmation_email_matching():
    assert match_confirmation_email("Your application was sent to Acme Health", "<p>Accounts Receivable Analyst</p>", "Acme Health Pvt Ltd", "Accounts Receivable Analyst")
    assert not match_confirmation_email("Your application was sent to Globex", "Accounts Receivable Analyst", "Acme Health", "Accounts Receivable Analyst")
    assert not match_confirmation_email("Your application was sent to Acme Health", "Data Engineer", "Acme Health", "Accounts Receivable Analyst")


class FakeIMAP:
    def __init__(self, messages):
        self.messages = messages
        self.readonly = None

    def login(self, user, password):
        pass

    def select(self, folder, readonly=False):
        self.readonly = readonly
        return "OK", [b"1"]

    def search(self, charset, *criteria):
        domain = criteria[-1]
        ids = [str(i + 1).encode() for i, (frm, _, _) in enumerate(self.messages) if domain in frm]
        return "OK", [b" ".join(ids)]

    def fetch(self, msg_id, spec):
        assert "PEEK" in spec  # never marks mail as read
        frm, subject, body = self.messages[int(msg_id) - 1]
        raw = f"From: {frm}\r\nSubject: {subject}\r\nMessage-ID: <{msg_id.decode()}@x>\r\nContent-Type: text/html\r\n\r\n{body}".encode()
        return "OK", [(b"1", raw)]

    def logout(self):
        pass


def test_email_alert_source_reads_alerts_readonly(settings, monkeypatch):
    monkeypatch.setenv("IMAP_USERNAME", "u")
    monkeypatch.setenv("IMAP_PASSWORD", "p")
    imap = FakeIMAP([("LinkedIn <jobalerts-noreply@linkedin.com>", "New jobs for you", LINKEDIN_ALERT),
                     ("LinkedIn <jobs-noreply@linkedin.com>", "Your application was sent to Acme", "<p>Financial Analyst</p>")])
    src = EmailAlertSource(settings.sources.email_alerts, imap_factory=lambda: imap)
    records = src.fetch(Platform.LINKEDIN)
    assert len(records) == 2  # the confirmation email is not treated as an alert
    assert imap.readonly is True
    assert src.fetch(Platform.INDEED) == []


def test_email_source_without_credentials(settings):
    src = EmailAlertSource(settings.sources.email_alerts, imap_factory=lambda: FakeIMAP([]))
    with pytest.raises(PlatformError, match="IMAP_USERNAME"):
        src.fetch(Platform.LINKEDIN)
