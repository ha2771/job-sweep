from datetime import datetime, timezone

from jobsweep.discover import BoardRef, discover, parse_board_url, parse_workday_url

NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
UUID = "080a2b88-f724-4585-8d16-2d4839a1d563"


def test_parse_board_urls():
    assert parse_board_url("https://job-boards.greenhouse.io/genevatrading/jobs/5085231007") == BoardRef("greenhouse", "genevatrading", "5085231007")
    assert parse_board_url("https://boards.greenhouse.io/spacex/jobs/8865057002?gh_src=x") == BoardRef("greenhouse", "spacex", "8865057002")
    assert parse_board_url("https://boards.greenhouse.io/embed/job_app?for=acme&token=123") == BoardRef("greenhouse", "acme", "123")
    assert parse_board_url("https://boards.greenhouse.io/embed/job_app?token=7669159003") is None
    assert parse_board_url(f"https://jobs.ashbyhq.com/dyna-robotics/{UUID}/application") == BoardRef("ashby", "dyna-robotics", UUID)
    assert parse_board_url(f"https://jobs.lever.co/ivo/{UUID}") == BoardRef("lever", "ivo", UUID)
    assert parse_board_url("https://stripe.com/jobs/search?gh_jid=7737124") is None


def test_rejects_unsafe_tokens():
    assert parse_board_url("https://boards.greenhouse.io/..%2F..%2Fadmin/jobs/1") is None


def test_parse_workday_url():
    s = parse_workday_url("https://micron.wd1.myworkdayjobs.com/External/job/Richardson-TX/New-College-Grad_JR93183-1")
    assert (s.host, s.tenant, s.site) == ("micron.wd1.myworkdayjobs.com", "micron", "External")
    s = parse_workday_url("https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/US-CA/X_JR1")
    assert s.site == "NVIDIAExternalCareerSite"


def test_discover_counts_active_recent_only():
    ts = NOW.timestamp()
    listings = [
        {"active": True, "is_visible": True, "date_updated": ts, "company_name": "Geneva", "url": "https://job-boards.greenhouse.io/genevatrading/jobs/1"},
        {"active": True, "is_visible": True, "date_updated": ts, "company_name": "Dyna", "url": f"https://jobs.ashbyhq.com/dyna-robotics/{UUID}"},
        {"active": False, "is_visible": True, "date_updated": ts, "company_name": "Old", "url": "https://job-boards.greenhouse.io/oldco/jobs/2"},
        {"active": True, "is_visible": True, "date_updated": ts - 200 * 86400, "company_name": "Stale", "url": "https://job-boards.greenhouse.io/staleco/jobs/3"},
        {"active": True, "is_visible": True, "date_updated": ts, "company_name": "Micron", "url": "https://micron.wd1.myworkdayjobs.com/External/job/x/y_JR1"},
        {"active": True, "is_visible": True, "date_updated": ts, "company_name": "TikTok", "url": "https://lifeattiktok.com/search/1"},
    ]
    d = discover(listings, NOW, 120)
    assert d.tokens("greenhouse") == ["genevatrading"]
    assert d.tokens("ashby") == ["dyna-robotics"]
    assert len(d.workday) == 1
    assert d.other_hosts["lifeattiktok.com"] == 1
    assert d.company_names()["ashby"]["dyna-robotics"] == "Dyna"
