"""Eightfold careers search (Microsoft, Qualcomm). Gives postedTs; no description in the search API,
so these rows come out as 'no_text' and need the posting opened on the site."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

from ..common import Context, SourceResult, dicts, sweep
from ..model import Job
from ..text import text
from ..timeutil import from_epoch

SOURCE = "eightfold"


@dataclass(frozen=True)
class Site:
    company: str
    host: str  # e.g. apply.careers.microsoft.com
    domain: str  # e.g. microsoft.com
    queries: tuple[str, ...]

    def __str__(self) -> str:
        return self.company


def _locations(p: dict) -> list[str]:
    raw = p.get("locations")
    if not isinstance(raw, list):
        raw = [p.get("location")]
    out = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            name = text(item.get("name")) or text(item.get("location"))
            if name:
                out.append(name)
    return out


def fetch_site(ctx: Context, site: Site) -> list[Job]:
    jobs: dict[str, Job] = {}
    for query in site.queries:
        data = ctx.http.get_json(
            f"https://{site.host}/api/pcsx/search",
            params={"domain": site.domain, "query": query, "location": "United States", "start": 0, "sort_by": "timestamp"},
        )
        payload = data.get("data") if isinstance(data, dict) else None
        positions = dicts(payload, "positions") if isinstance(payload, dict) else []
        for p in positions:
            pid = p.get("id")
            title = text(p.get("name")) or text(p.get("title"))
            if pid is None or not title:
                raise ValueError(f"unexpected position shape; keys={sorted(p)[:15]}")
            pid = str(pid)
            if pid in jobs:
                continue
            link = text(p.get("positionUrl")) or f"/careers/job/{pid}"
            jobs[pid] = Job(
                source=SOURCE,
                board=site.company.lower(),
                job_id=pid,
                company=site.company,
                title=title,
                locations=_locations(p),
                url=urljoin(f"https://{site.host}", link),
                posted_at=from_epoch(p.get("postedTs")),
                date_basis="postedTs",
            )
    return list(jobs.values())


def fetch(ctx: Context, sites: list[Site]) -> SourceResult:
    result = SourceResult(SOURCE)
    sweep(ctx, result, sites, fetch_site)
    return result
