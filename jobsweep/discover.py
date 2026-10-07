"""Find more company job boards from the links in Simplify's listings, and parse board URLs."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_GH = re.compile(r"^https?://(?:boards|job-boards)\.greenhouse\.io/([^/?#]+)/jobs/(\d+)", re.I)
_GH_EMBED = re.compile(r"^https?://(?:boards|job-boards)\.greenhouse\.io/embed/job_app\?", re.I)
_ASHBY = re.compile(r"^https?://jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f]{8}-[0-9a-f-]{27})", re.I)
_LEVER = re.compile(r"^https?://jobs\.lever\.co/([^/?#]+)/([0-9a-f]{8}-[0-9a-f-]{27})", re.I)
_WORKDAY = re.compile(
    r"^https?://([a-z0-9-]+)\.(wd\d{1,3})\.myworkdayjobs\.com/(?:[a-z]{2}-[a-z]{2}/)?([a-z0-9_-]+)/(?:job|details)/", re.I
)


@dataclass(frozen=True)
class BoardRef:
    kind: str  # greenhouse | ashby | lever
    token: str
    job_id: str | None


def valid_token(token: str) -> bool:
    return bool(TOKEN_RE.match(token))


def parse_board_url(url: str) -> BoardRef | None:
    """Greenhouse/Ashby/Lever board + job id from a posting URL. Tokens are validated
    because they get interpolated into API URLs."""
    if not isinstance(url, str):
        return None
    for kind, pattern in (("greenhouse", _GH), ("ashby", _ASHBY), ("lever", _LEVER)):
        m = pattern.match(url)
        if m:
            token = unquote(m.group(1))
            return BoardRef(kind, token, m.group(2).lower()) if valid_token(token) else None
    if _GH_EMBED.match(url):
        q = parse_qs(urlsplit(url).query)
        token = (q.get("for") or [""])[0]
        job = (q.get("token") or [""])[0]
        if valid_token(token) and job.isdigit():
            return BoardRef("greenhouse", token, job)
    return None


@dataclass(frozen=True)
class WorkdaySite:
    host: str
    tenant: str
    site: str


def parse_workday_url(url: str) -> WorkdaySite | None:
    m = _WORKDAY.match(url) if isinstance(url, str) else None
    if not m:
        return None
    tenant, wd, site = m.group(1).lower(), m.group(2).lower(), m.group(3)
    return WorkdaySite(f"{tenant}.{wd}.myworkdayjobs.com", tenant, site)


@dataclass
class Discovery:
    boards: dict[str, dict[str, str]] = field(default_factory=lambda: {"greenhouse": {}, "ashby": {}, "lever": {}})
    workday: dict[WorkdaySite, str] = field(default_factory=dict)
    other_hosts: Counter = field(default_factory=Counter)
    listings_considered: int = 0

    def tokens(self, kind: str) -> list[str]:
        return sorted(self.boards.get(kind, {}))

    def company_names(self) -> dict[str, dict[str, str]]:
        return {kind: {t.lower(): name for t, name in names.items()} for kind, names in self.boards.items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "listings_considered": self.listings_considered,
            "greenhouse": self.boards["greenhouse"],
            "ashby": self.boards["ashby"],
            "lever": self.boards["lever"],
            "workday": [
                {"host": s.host, "tenant": s.tenant, "site": s.site, "company": name}
                for s, name in sorted(self.workday.items(), key=lambda kv: kv[0].host)
            ],
            "not_yet_supported_hosts": dict(self.other_hosts.most_common(40)),
        }


def discover(listings: list[dict], now: datetime, max_age_days: int) -> Discovery:
    out = Discovery()
    cutoff = now.timestamp() - max_age_days * 86400
    for item in listings:
        if not item.get("active") or item.get("is_visible") is False:
            continue
        updated = item.get("date_updated") or item.get("date_posted") or 0
        if not isinstance(updated, (int, float)) or updated < cutoff:
            continue
        url = item.get("url")
        company = item.get("company_name") if isinstance(item.get("company_name"), str) else ""
        out.listings_considered += 1
        ref = parse_board_url(url)
        if ref:
            existing = {t.lower() for t in out.boards[ref.kind]}
            if ref.token.lower() not in existing:
                out.boards[ref.kind][ref.token] = company or ref.token
            continue
        site = parse_workday_url(url)
        if site:
            out.workday.setdefault(site, company or site.tenant)
            continue
        if isinstance(url, str):
            out.other_hosts[urlsplit(url).netloc.lower()] += 1
    return out
