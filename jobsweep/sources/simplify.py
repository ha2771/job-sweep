"""SimplifyJobs New-Grad listings.json. Its date_posted can be a refresh of an old posting,
so the pipeline re-checks each fresh row against the company's own board when it can."""

from __future__ import annotations

from ..common import Context, SourceResult, dicts
from ..http import HttpError
from ..model import Job
from ..text import strip_tracking, text
from ..timeutil import from_epoch

SOURCE = "simplify"


def fetch(ctx: Context, url: str) -> tuple[SourceResult, list[dict]]:
    result = SourceResult(SOURCE, boards_total=1)
    try:
        data = ctx.http.get_json(url)
    except HttpError as exc:
        result.errors.append(f"listings.json: {exc.short()}")
        return result, []
    if not isinstance(data, list):
        result.errors.append("listings.json: unexpected shape (not a list)")
        return result, []
    result.boards_ok = 1
    listings = dicts(data)
    for item in listings:
        if not item.get("active") or item.get("is_visible") is False:
            continue
        jid = text(item.get("id"))
        if not jid:
            continue
        locations = item.get("locations")
        job = Job(
            source=SOURCE,
            board="new-grad",
            job_id=jid,
            company=text(item.get("company_name")),
            title=text(item.get("title")),
            locations=[text(x) for x in locations if text(x)] if isinstance(locations, list) else [],
            url=strip_tracking(text(item.get("url"))),
            posted_at=from_epoch(item.get("date_posted")),
            date_basis="Simplify date_posted (can be a refresh)",
        )
        job.extra["simplify_sponsorship"] = text(item.get("sponsorship"))
        result.jobs.append(job)
    return result, listings
