"""Lever postings API: one call per company returns createdAt (ms) and the description lists."""

from __future__ import annotations

from urllib.parse import quote

from ..common import Context, SourceResult, dicts, sweep
from ..model import Job
from ..text import html_to_text, pretty_name, text
from ..timeutil import from_epoch

API = "https://api.lever.co/v0/postings"
SOURCE = "lever"


def _description(j: dict) -> str:
    parts = [text(j.get("descriptionPlain"))]
    for block in dicts(j, "lists"):
        parts.append(text(block.get("text")))
        parts.append(html_to_text(text(block.get("content"))))
    parts.append(text(j.get("additionalPlain")))
    return "\n".join(p for p in parts if p)


def fetch_board(ctx: Context, co: str, company: str | None = None) -> list[Job]:
    data = ctx.http.get_json(f"{API}/{quote(co, safe='')}", params={"mode": "json"})
    if not isinstance(data, list):
        raise ValueError("unexpected Lever response shape")
    jobs = []
    for j in dicts(data):
        jid = text(j.get("id"))
        if not jid:
            continue
        cats = j.get("categories") if isinstance(j.get("categories"), dict) else {}
        all_locs = cats.get("allLocations")
        locations = [text(x) for x in all_locs if text(x)] if isinstance(all_locs, list) else []
        if not locations and text(cats.get("location")):
            locations = [text(cats.get("location"))]
        if text(j.get("country")).upper() == "US":
            locations.append("United States")
        jobs.append(
            Job(
                source=SOURCE,
                board=co,
                job_id=jid,
                company=company or pretty_name(co),
                title=text(j.get("text")),
                locations=locations,
                url=text(j.get("hostedUrl")) or f"https://jobs.lever.co/{co}/{jid}",
                posted_at=from_epoch(j.get("createdAt"), ms=True),
                date_basis="createdAt",
                description=_description(j),
            )
        )
    return jobs


def fetch(ctx: Context, companies_list: list[str], companies: dict[str, str] | None = None) -> SourceResult:
    companies = companies or {}
    result = SourceResult(SOURCE)
    sweep(ctx, result, companies_list, lambda c, n: fetch_board(c, n, companies.get(n.lower())))
    return result
