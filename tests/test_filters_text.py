import pytest

from jobsweep.filters import classify_location, job_us_status
from jobsweep.text import dedupe_key, html_to_text, strip_tracking


@pytest.mark.parametrize(
    "loc, expected",
    [
        ("San Francisco, CA", True),
        ("US, CA, Santa Clara", True),
        ("Remote - US", True),
        ("Plano, TX", True),
        ("Albuquerque, New Mexico", True),
        ("Remote - US or Canada", True),
        ("London, UK", False),
        ("Chennai, TN", False),
        ("Berlin, DE", False),
        ("Toronto, ON", False),
        ("Bengaluru, Karnataka, India", False),
        ("Remote", None),
        ("Some Small Town", None),
    ],
)
def test_classify_location(loc, expected):
    assert classify_location(loc) is expected


def test_job_us_status_mixed():
    assert job_us_status(["London, UK", "New York, NY"]) is True
    assert job_us_status(["London, UK", "Paris, France"]) is False
    assert job_us_status(["London, UK", "Remote"]) is None
    assert job_us_status([]) is None


def test_html_to_text_handles_greenhouse_escaping():
    raw = "&lt;p&gt;Hello &amp;amp; welcome&lt;/p&gt;&lt;ul&gt;&lt;li&gt;MS in EE&lt;/li&gt;&lt;/ul&gt;"
    assert html_to_text(raw) == "Hello & welcome\nMS in EE"


def test_dedupe_key_ignores_case_punctuation_and_suffixes():
    assert dedupe_key("Anthropic, Inc.", "Research Engineer, Knowledge") == dedupe_key("anthropic", "Research Engineer - Knowledge")


def test_strip_tracking():
    assert strip_tracking("https://x.io/jobs/1?utm_source=Simplify&ref=Simplify&gh_jid=5") == "https://x.io/jobs/1?gh_jid=5"
