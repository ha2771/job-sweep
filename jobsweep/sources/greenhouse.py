"""Greenhouse job board API: list has first_published; full text needs one call per job."""

from __future__ import annotations

from urllib.parse import quote

from ..common import Context, SourceResult, dicts, sweep
from ..model import Job
from ..text import html_to_text, split_locations, text
from ..timeutil import parse_iso

API = "https://boards-api.greenhouse.io/v1/boards"
SOURCE = "greenhouse"


def fetch_board(ctx: Context, token: str) -> list[Job]:
    data = ctx.http.get_json(f"{API}/{quote(token, safe='')}/jobs")
    jobs = []
    for j in dicts(data, "jobs"):
        jid = j.get("id")
        if not isinstance(jid, (int, str)) or not str(jid).strip():
            continue
        posted, basis = parse_iso(j.get("first_published")), "first_published"
        if posted is None:
            posted, basis = parse_iso(j.get("updated_at")), "updated_at (no first_published)"
        location = text((j.get("location") or {}).get("name")) if isinstance(j.get("location"), dict) else ""
        jobs.append(
            Job(
                source=SOURCE,
                board=token,
                job_id=str(jid),
                company=text(j.get("company_name")) or token,
                title=text(j.get("title")),
                locations=split_locations(location),
                url=text(j.get("absolute_url")) or f"https://job-boards.greenhouse.io/{token}/jobs/{jid}",
                posted_at=posted,
                date_basis=basis,
            )
        )
    return jobs


def fetch(ctx: Context, tokens: list[str]) -> SourceResult:
    result = SourceResult(SOURCE)
    sweep(ctx, result, tokens, fetch_board)
    return result


def enrich(ctx: Context, job: Job) -> None:
    detail = ctx.http.get_json(f"{API}/{quote(job.board, safe='')}/jobs/{quote(job.job_id, safe='')}")
    if not isinstance(detail, dict):
        return
    job.description = html_to_text(text(detail.get("content")))
    for office in dicts(detail, "offices"):
        name = text(office.get("location")) or text(office.get("name"))
        if name and name not in job.locations:
            job.locations.append(name)
