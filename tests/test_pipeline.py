"""End-to-end: every source, with canned API responses shaped like the real ones."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from jobsweep.config import load_config
from jobsweep.pipeline import run
from tests.fakes import FakeHttp

NOW = datetime(2026, 10, 7, 16, 0, tzinfo=timezone.utc)  # noon ET
GH = "https://boards-api.greenhouse.io/v1/boards"
UUID = "080a2b88-f724-4585-8d16-2d4839a1d563"


def iso(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


CONFIG = """
[run]
window_hours = 72
state_path = "out/state.json"
out_dir = "out"

[filters]
title_exclude = '\\b(senior|sr|staff|lead|manager|intern)\\b'
title_include = 'machine learning|applied scien|research engineer|computer vision|signal processing|deep learning|\\bai\\b'
early_career = 'new grad'
role_noun = 'engineer|scientist'

[discovery]
enabled = true
include_in_sweep = false
sweep_workday = false

[simplify]
url = "https://raw.example.test/listings.json"

[greenhouse]
tokens = ["acme"]

[ashby]
boards = ["wavelabs"]

[lever]
companies = ["levco"]

[[workday]]
company = "NVIDIA"
host = "nvidia.wd5.myworkdayjobs.com"
tenant = "nvidia"
site = "NVIDIAExternalCareerSite"
queries = [""]
max_pages = 2

[[eightfold]]
company = "Microsoft"
host = "apply.careers.microsoft.com"
domain = "microsoft.com"
queries = ["machine learning"]

[amazon]
queries = ["machine learning", "applied scientist"]
"""


def gh_job(jid, title, loc, hours_ago):
    return {"id": jid, "title": title, "location": {"name": loc}, "first_published": iso(hours_ago),
            "updated_at": iso(1), "absolute_url": f"https://job-boards.greenhouse.io/acme/jobs/{jid}", "company_name": "Acme AI"}


def routes():
    wd_api = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite"
    return {
        "https://raw.example.test/listings.json": [
            {"id": "s-dup", "active": True, "is_visible": True, "company_name": "Acme AI", "title": "Machine Learning Engineer",
             "url": "https://job-boards.greenhouse.io/acme/jobs/101?utm_source=Simplify&ref=Simplify", "locations": ["San Francisco, CA"],
             "date_posted": NOW.timestamp() - 3600, "date_updated": NOW.timestamp(), "sponsorship": "Offers Sponsorship"},
            {"id": "s-stale", "active": True, "is_visible": True, "company_name": "Astera Labs", "title": "Applied AI Engineer, New Grad",
             "url": "https://job-boards.greenhouse.io/astera/jobs/4731594005", "locations": ["San Jose, CA"],
             "date_posted": NOW.timestamp() - 7200, "date_updated": NOW.timestamp(), "sponsorship": "Other"},
            {"id": "s-offsite", "active": True, "is_visible": True, "company_name": "Defense Co", "title": "AI Engineer",
             "url": "https://careers.example.com/123", "locations": ["Boston, MA"],
             "date_posted": NOW.timestamp() - 36000, "date_updated": NOW.timestamp(), "sponsorship": "U.S. Citizenship is Required"},
            {"id": "s-inactive", "active": False, "is_visible": True, "company_name": "Gone", "title": "AI Engineer",
             "url": "https://x.test/1", "locations": [], "date_posted": NOW.timestamp(), "date_updated": NOW.timestamp(), "sponsorship": "Other"},
        ],
        f"{GH}/acme/jobs": {"jobs": [
            gh_job(101, "Machine Learning Engineer", "San Francisco, CA", 2),
            gh_job(102, "Senior Machine Learning Engineer", "San Francisco, CA", 2),
            gh_job(103, "Machine Learning Engineer, EMEA", "London, UK", 2),
            gh_job(104, "Applied Scientist", "Seattle, WA", 240),
            gh_job(105, "Research Engineer", "New York, NY", 3),
            gh_job(106, "Machine Learning Engineer", "New York, NY", 4),
        ]},
        f"{GH}/acme/jobs/101": {"content": "&lt;p&gt;Minimum Qualifications&lt;/p&gt;&lt;ul&gt;&lt;li&gt;MS in CS. 0-2 years of experience.&lt;/li&gt;&lt;/ul&gt;"},
        f"{GH}/acme/jobs/105": {"content": "&lt;p&gt;Minimum Qualifications&lt;/p&gt;&lt;p&gt;PhD in Computer Science.&lt;/p&gt;"},
        f"{GH}/acme/jobs/106": {"content": "&lt;p&gt;Minimum Qualifications&lt;/p&gt;&lt;p&gt;MS in CS.&lt;/p&gt;"},
        f"{GH}/astera/jobs": {"jobs": [{"id": 4731594005, "title": "Applied AI Engineer, New Grad", "location": {"name": "San Jose, CA"},
                                         "first_published": "2026-09-15T09:00:00-04:00", "absolute_url": "https://job-boards.greenhouse.io/astera/jobs/4731594005"}]},
        "https://api.ashbyhq.com/posting-api/job-board/wavelabs": {"jobs": [
            {"id": UUID, "title": "Computer Vision Engineer, New Grad", "location": "Seattle", "publishedAt": iso(5), "isListed": True,
             "jobUrl": f"https://jobs.ashbyhq.com/wavelabs/{UUID}",
             "descriptionPlain": "Requirements:\nBS/MS in EE with 1+ years of experience in computer vision."},
            {"id": "hidden", "title": "Computer Vision Engineer", "location": "Seattle", "publishedAt": iso(5), "isListed": False},
        ]},
        "https://api.lever.co/v0/postings/levco": [
            {"id": "lev-1", "text": "Signal Processing Engineer", "categories": {"allLocations": ["Austin, TX"]},
             "createdAt": (NOW.timestamp() - 30 * 3600) * 1000, "hostedUrl": "https://jobs.lever.co/levco/lev-1",
             "descriptionPlain": "Build radar pipelines.", "lists": [{"text": "Requirements", "content": "<li>We are unable to sponsor visas.</li>"}]},
        ],
        f"{wd_api}/job/US-CA-Santa-Clara/DL-Perf_JR1": {"jobPostingInfo": {
            "jobDescription": "<p>What we need to see:</p><ul><li>Master's degree or equivalent experience.</li><li>2+ years of experience with CUDA.</li></ul>",
            "location": "US, CA, Santa Clara", "startDate": "2026-10-07"}},
        "https://apply.careers.microsoft.com/api/pcsx/search": {"data": {"positions": [
            {"id": 555, "name": "Applied Scientist", "locations": ["Redmond, Washington, United States"],
             "postedTs": NOW.timestamp() - 3600, "positionUrl": "/careers/job/555"}]}},
        "https://www.amazon.jobs/en/search.json": {"jobs": [
            {"id_icims": "999", "title": "Applied Scientist, AGI", "posted_date": "October  7, 2026",
             "basic_qualifications": "- PhD, or Master's degree and 4+ years of applied research experience",
             "preferred_qualifications": "- Experience with LLMs", "country_code": "USA",
             "normalized_location": "Seattle, Washington, USA", "job_path": "/en/jobs/999/applied-scientist"}]},
    }


def workday_posts():
    wd_api = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite"

    def handler(body):
        if body["offset"] > 0:
            return {"jobPostings": []}
        return {"total": 2, "jobPostings": [
            {"title": "Deep Learning Performance Engineer", "externalPath": "/job/US-CA-Santa-Clara/DL-Perf_JR1",
             "postedOn": "Posted Today", "locationsText": "US, CA, Santa Clara", "bulletFields": ["JR1"]},
            {"title": "Deep Learning Engineer", "externalPath": "/job/US-CA-Santa-Clara/Old_JR0",
             "postedOn": "Posted 30+ Days Ago", "locationsText": "US, CA, Santa Clara", "bulletFields": ["JR0"]},
        ]}

    return {f"{wd_api}/jobs": handler}


@pytest.fixture()
def sweep(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(CONFIG, encoding="utf-8")
    cfg = load_config(cfg_path)
    http = FakeHttp(routes(), workday_posts())
    doc, code = run(cfg, http=http, now=NOW)
    return cfg, doc, code, http


def by_title(doc):
    return {(r["company"], r["title"]): r for r in doc["jobs"]}


def test_exit_code_and_outputs(sweep):
    cfg, doc, code, _ = sweep
    assert code == 0
    assert (cfg.out_dir / "candidates.json").exists()
    assert (cfg.out_dir / "candidates.md").exists()
    assert (cfg.out_dir / "discovered_boards.json").exists()
    assert json.loads((cfg.out_dir / "candidates.json").read_text())["jobs"] == doc["jobs"]


def test_screening(sweep):
    _, doc, _, _ = sweep
    titles = by_title(doc)
    assert ("Acme AI", "Senior Machine Learning Engineer") not in titles
    assert ("Acme AI", "Machine Learning Engineer, EMEA") not in titles
    assert ("Acme AI", "Applied Scientist") not in titles  # 10 days old
    gh = doc["sources"]["greenhouse"]
    assert (gh["postings_scanned"], gh["fresh_in_window"], gh["skipped_by_title"], gh["skipped_non_us"]) == (6, 5, 1, 1)


def test_duplicates_merge_and_simplify_dedupe(sweep):
    _, doc, _, _ = sweep
    row = by_title(doc)[("Acme AI", "Machine Learning Engineer")]
    assert row["source"] == "greenhouse"
    assert "New York, NY" in row["locations"]
    assert row["also_posted_as"][0]["url"].endswith("/106")
    assert "also listed on Simplify" in row["notes"]
    assert row["sponsorship_positive"] is True
    assert row["verdict"] == "looks_ok"
    assert not any(r["source"] == "simplify" and r["title"] == "Machine Learning Engineer" for r in doc["jobs"])


def test_simplify_refresh_is_caught_on_the_board(sweep):
    _, doc, _, http = sweep
    assert ("Astera Labs", "Applied AI Engineer, New Grad") not in by_title(doc)
    assert doc["simplify_stale_after_board_check"][0]["company"] == "Astera Labs"
    assert f"{GH}/astera/jobs" in http.calls


def test_verdicts(sweep):
    _, doc, _, _ = sweep
    t = by_title(doc)
    assert t[("Acme AI", "Research Engineer")]["verdict"] == "likely_drop"
    assert "PhD required" in t[("Acme AI", "Research Engineer")]["reasons"]
    assert t[("Wavelabs", "Computer Vision Engineer, New Grad")]["verdict"] == "stretch"
    assert t[("Levco", "Signal Processing Engineer")]["verdict"] == "likely_drop"
    assert t[("NVIDIA", "Deep Learning Performance Engineer")]["verdict"] == "stretch"
    assert t[("Microsoft", "Applied Scientist")]["verdict"] == "no_text"
    assert t[("Amazon", "Applied Scientist, AGI")]["verdict"] == "likely_drop"
    offsite = t[("Defense Co", "AI Engineer")]
    assert offsite["verdict"] == "likely_drop"
    assert "date from Simplify only; confirm on the company site" in offsite["notes"]


def test_workday_skips_old_and_paginates_sensibly(sweep):
    _, doc, _, http = sweep
    assert ("NVIDIA", "Deep Learning Engineer") not in by_title(doc)
    nvidia = by_title(doc)[("NVIDIA", "Deep Learning Performance Engineer")]
    assert nvidia["posted_date"] == "2026-10-07"
    assert sum(1 for c in http.calls if c.startswith("POST")) == 1  # short page -> stop


def test_sorted_best_first(sweep):
    _, doc, _, _ = sweep
    order = {"looks_ok": 0, "stretch": 1, "check": 2, "no_text": 3, "likely_drop": 4}
    ranks = [order[r["verdict"]] for r in doc["jobs"]]
    assert ranks == sorted(ranks)


def test_second_run_marks_nothing_new(sweep):
    cfg, doc, _, _ = sweep
    assert doc["bootstrap_run"] is True
    doc2, _ = run(cfg, http=FakeHttp(routes(), workday_posts()), now=NOW + timedelta(hours=2))
    assert doc2["bootstrap_run"] is False
    assert not any(r["new_this_run"] for r in doc2["jobs"])
    assert {r["key"] for r in doc2["jobs"]} == {r["key"] for r in doc["jobs"]}


def test_a_failing_board_is_recorded_not_fatal(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(CONFIG.replace('tokens = ["acme"]', 'tokens = ["acme", "missing"]'), encoding="utf-8")
    doc, code = run(load_config(cfg_path), http=FakeHttp(routes(), workday_posts()), now=NOW)
    assert code == 0
    assert doc["sources"]["greenhouse"]["errors"] == ["missing: HTTP 404 Not Found"]


def test_everything_failing_returns_2(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(CONFIG, encoding="utf-8")
    _, code = run(load_config(cfg_path), http=FakeHttp({}), now=NOW)
    assert code == 2
