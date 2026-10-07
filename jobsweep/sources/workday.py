"""Workday CXS API. The list gives only 'Posted Today / Yesterday / N Days Ago'; full text needs a detail call."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import quote

from ..common import Context, SourceResult, dicts, sweep
from ..model import Job
from ..text import html_to_text, split_locations, text

SOURCE = "workday"
PAGE = 20  # Workday rejects larger pages


@dataclass(frozen=True)
class Tenant:
    company: str
    host: str  # e.g. nvidia.wd5.myworkdayjobs.com
    tenant: str  # e.g. nvidia
    site: str  # e.g. NVIDIAExternalCareerSite
    queries: tuple[str, ...] = ("",)
    max_pages: int = 3

    def __str__(self) -> str:
        return f"{self.company} ({self.host}/{self.site})"

    @property
    def api(self) -> str:
        return f"https://{self.host}/wday/cxs/{quote(self.tenant, safe='')}/{quote(self.site, safe='')}"


def posted_days(label: object) -> int | None:
    t = text(label).lower()
    if not t:
        return None
    if "today" in t:
        return 0
    if "yesterday" in t:
        return 1
    m = re.search(r"(\d+)\+?\s*days?", t)
    return int(m.group(1)) if m else None


def fetch_tenant(ctx: Context, t: Tenant) -> list[Job]:
    found: dict[str, Job] = {}
    for query in t.queries:
        for page in range(t.max_pages):
            data = ctx.http.post_json(
                f"{t.api}/jobs", {"appliedFacets": {}, "limit": PAGE, "offset": page * PAGE, "searchText": query}
            )
            posts = dicts(data, "jobPostings")
            fresh_here = 0
            for p in posts:
                ext = text(p.get("externalPath"))
                days = posted_days(p.get("postedOn"))
                if not ext.startswith("/"):
                    continue
                if days is not None and days <= ctx.window_days:
                    fresh_here += 1
                bullets = p.get("bulletFields")
                req_id = text(bullets[0]) if isinstance(bullets, list) and bullets else ""
                jid = req_id or ext.rsplit("_", 1)[-1]
                if jid in found:
                    continue
                found[jid] = Job(
                    source=SOURCE,
                    board=t.tenant,
                    job_id=jid,
                    company=t.company,
                    title=text(p.get("title")),
                    locations=split_locations(text(p.get("locationsText"))),
                    url=f"https://{t.host}/{t.site}{ext}",
                    posted_date=ctx.today_et - timedelta(days=days) if days is not None else None,
                    date_basis=f"Workday '{text(p.get('postedOn'))}'",
                    extra={"detail_url": f"{t.api}{ext}"},
                )
            if len(posts) < PAGE:
                break
            if query == "" and fresh_here == 0:
                break  # empty search is newest-first: nothing fresh on this page means nothing fresh after it
    return list(found.values())


def fetch(ctx: Context, tenants: list[Tenant]) -> SourceResult:
    result = SourceResult(SOURCE)
    sweep(ctx, result, tenants, fetch_tenant)
    return result


def enrich(ctx: Context, job: Job) -> None:
    url = job.extra.get("detail_url")
    if not isinstance(url, str):
        return
    data = ctx.http.get_json(url)
    info = data.get("jobPostingInfo") if isinstance(data, dict) else None
    if not isinstance(info, dict):
        return
    job.description = html_to_text(text(info.get("jobDescription")))
    locs = [text(info.get("location"))]
    extra_locs = info.get("additionalLocations")
    if isinstance(extra_locs, list):
        locs += [text(x) for x in extra_locs]
    country = info.get("country")
    if isinstance(country, dict) and text(country.get("descriptor")):
        locs.append(text(country.get("descriptor")))
    locs = [loc for loc in locs if loc]
    if locs:
        job.locations = locs
    if text(info.get("startDate")):
        job.extra["workday_start_date"] = text(info.get("startDate"))
