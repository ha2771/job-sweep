import io
import urllib.error
from pathlib import Path

import pytest

from jobsweep.config import ConfigError, load_config
from jobsweep.http import Http, HttpError

ROOT = Path(__file__).resolve().parents[1]


def test_shipped_config_loads():
    cfg = load_config(ROOT / "config.toml")
    assert len(cfg.greenhouse) == 70 and len(cfg.ashby) == 73 and len(cfg.lever) == 13
    assert cfg.state_path == ROOT / "out" / "state.json"


def _write(tmp_path, body):
    p = tmp_path / "c.toml"
    p.write_text(body, encoding="utf-8")
    return p


FILTERS = "[filters]\ntitle_exclude='a'\ntitle_include='b'\nearly_career='c'\nrole_noun='d'\n"


@pytest.mark.parametrize(
    "extra, message",
    [
        ('[greenhouse]\ntokens = ["ok", "../etc"]\n', "invalid board names"),
        ("[run]\nwindow_hours = 0\n", "window_hours"),
        ('[simplify]\nurl = "http://insecure"\n', "https"),
        ('[[workday]]\ncompany="X"\nhost="bad host"\ntenant="x"\nsite="y"\n', "invalid host"),
    ],
)
def test_bad_config_rejected(tmp_path, extra, message):
    with pytest.raises(ConfigError, match=message):
        load_config(_write(tmp_path, FILTERS + extra))


def test_bad_regex_rejected(tmp_path):
    with pytest.raises(ConfigError, match="not a valid regex"):
        load_config(_write(tmp_path, FILTERS.replace("'a'", "'(unclosed'")))


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code, headers=None):
    return urllib.error.HTTPError("https://x.test", code, "err", headers or {}, None)


def test_retries_429_then_succeeds(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        if len(calls) == 1:
            raise _http_error(429, {"Retry-After": "2"})
        return _Resp(b'{"ok": true}')

    sleeps = []
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    http = Http("ua", sleep=sleeps.append)
    assert http.get_json("https://x.test/a", params={"q": "machine learning"}) == {"ok": True}
    assert calls[0] == "https://x.test/a?q=machine+learning"
    assert sleeps == [2.0]


def test_404_is_not_retried(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        raise _http_error(404)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(HttpError, match="HTTP 404"):
        Http("ua", sleep=lambda s: None).get_json("https://x.test/a")
    assert len(calls) == 1


def test_non_json_and_non_https(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: _Resp(b"<html>"))
    with pytest.raises(HttpError, match="not JSON"):
        Http("ua").get_json("https://x.test/a")
    with pytest.raises(HttpError, match="non-https"):
        Http("ua").get_json("http://x.test/a")


@pytest.mark.parametrize(
    "title, keep",
    [
        ("Member of Technical Staff, New Grad", True),
        ("Member of Technical Staff, Machine Learning", True),
        ("Staff Machine Learning Engineer", False),
        ("Associate Software Development Engineer - Conversion", False),
        ("Machine Learning Engineer", True),
        ("Senior Applied Scientist", False),
        ("Software Engineer, New Grad", True),
        ("Junior Accountant", False),
    ],
)
def test_shipped_title_rules(title, keep):
    from jobsweep.filters import TitleRules

    cfg = load_config(ROOT / "config.toml")
    rules = TitleRules.from_strings(cfg.title_exclude, cfg.title_include, cfg.early_career, cfg.role_noun)
    assert rules.screen(title)[0] is keep
