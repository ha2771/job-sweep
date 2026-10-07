"""Ashby posting API: one call per board returns publishedAt and the full plain-text description."""

from __future__ import annotations

from urllib.parse import quote

from ..common import Context, SourceResult, dicts, sweep
from ..model import Job
from ..text import html_to_text, pretty_name, text
from ..timeutil import parse_iso

API = "https://api.ashbyhq.com/posting-api/job-board"
SOURCE = "ashby"


def fetch_board(ctx: Context, name: str, company: str | None = None) -> list[Job]:
    data = ctx.http.get_json(f"{API}/{quote(name, safe='')}")
    jobs = []
    for j in dicts(data, "jobs"):
        if j.get("isListed") is False:
            continue
        url = text(j.get("jobUrl")) or text(j.get("applyUrl"))
        jid = text(j.get("id")) or url.rstrip("/").rsplit("/", 1)[-1]
        if not jid:
            continue
        locations = [text(j.get("location"))]
        for sec in dicts(j, "secondaryLocations"):
            locations.append(text(sec.get("location")))
        address = j.get("address") if isinstance(j.get("address"), dict) else {}
        postal = address.get("postalAddress") if isinstance(address.get("postalAddress"), dict) else {}
        country = text(postal.get("addressCountry"))
        if country:
            locations.append(country)
        if j.get("isRemote") is True and not any(locations):
            locations.append("Remote")
        jobs.append(
            Job(
                source=SOURCE,
                board=name,
                job_id=jid,
                company=company or pretty_name(name),
                title=text(j.get("title")),
                locations=[loc for loc in locations if loc],
                url=url or f"https://jobs.ashbyhq.com/{name}/{jid}",
                posted_at=parse_iso(j.get("publishedAt")),
                date_basis="publishedAt",
                description=text(j.get("descriptionPlain")) or html_to_text(text(j.get("descriptionHtml"))),
            )
        )
    return jobs


def fetch(ctx: Context, names: list[str], companies: dict[str, str] | None = None) -> SourceResult:
    companies = companies or {}
    result = SourceResult(SOURCE)
    sweep(ctx, result, names, lambda c, n: fetch_board(c, n, companies.get(n.lower())))
    return result
