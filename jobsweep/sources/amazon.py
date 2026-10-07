"""amazon.jobs search.json: date-only posted_date plus basic/preferred qualifications in the listing."""

from __future__ import annotations

from datetime import date, datetime

from ..common import Context, SourceResult, dicts, sweep
from ..model import Job
from ..text import html_to_text, text

URL = "https://www.amazon.jobs/en/search.json"
SOURCE = "amazon"


def parse_amazon_date(value: object) -> date | None:
    s = " ".join(text(value).split())  # the API puts two spaces before single-digit days
    try:
        return datetime.strptime(s, "%B %d, %Y").date()
    except ValueError:
        return None


def fetch_query(ctx: Context, query: str) -> list[Job]:
    data = ctx.http.get_json(
        URL, params={"base_query": query, "country[]": "USA", "sort": "recent", "result_limit": 40, "offset": 0}
    )
    jobs = []
    for j in dicts(data, "jobs"):
        jid = text(str(j.get("id_icims") or j.get("id") or ""))
        if not jid:
            continue
        locations = [text(j.get("normalized_location")) or text(j.get("location"))]
        if text(j.get("country_code")).upper() in ("USA", "US"):
            locations.append("United States")
        desc = "\n".join(
            [
                "Basic qualifications:",
                html_to_text(text(j.get("basic_qualifications"))),
                "Preferred qualifications:",
                html_to_text(text(j.get("preferred_qualifications"))),
                html_to_text(text(j.get("description"))),
            ]
        )
        path = text(j.get("job_path"))
        jobs.append(
            Job(
                source=SOURCE,
                board="amazon",
                job_id=jid,
                company=text(j.get("company_name")) or "Amazon",
                title=text(j.get("title")),
                locations=[loc for loc in locations if loc],
                url=f"https://www.amazon.jobs{path}" if path.startswith("/") else f"https://www.amazon.jobs/en/jobs/{jid}",
                posted_date=parse_amazon_date(j.get("posted_date")),
                date_basis="posted_date (date only)",
                description=desc,
            )
        )
    return jobs


def fetch(ctx: Context, queries: list[str]) -> SourceResult:
    result = SourceResult(SOURCE)
    sweep(ctx, result, queries, fetch_query, label=lambda q: f"query '{q}'")
    return result
