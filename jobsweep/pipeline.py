"""One sweep: fetch -> screen -> full text -> verify Simplify dates -> merge duplicates -> triage -> write."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Iterable

from . import report
from . import state as state_mod
from .common import Context, SourceResult
from .config import Config
from .discover import BoardRef, discover, parse_board_url
from .filters import TitleRules, job_us_status, track_rank
from .http import Http, HttpError
from .model import Job
from .sources import amazon, ashby, eightfold, greenhouse, lever, simplify, workday
from .text import dedupe_key
from .timeutil import ET, age_hours
from .triage import triage

log = logging.getLogger("jobsweep")

ALL_SOURCES = ("simplify", "greenhouse", "ashby", "lever", "workday", "eightfold", "amazon")
BOARD_MODULES = {"greenhouse": greenhouse, "ashby": ashby, "lever": lever}
ENRICHERS = {"greenhouse": greenhouse.enrich, "workday": workday.enrich}
SOURCE_PRIORITY = {name: i for i, name in enumerate(("greenhouse", "ashby", "lever", "workday", "eightfold", "amazon", "simplify"))}
VERDICT_ORDER = {"looks_ok": 0, "stretch": 1, "check": 2, "no_text": 3, "likely_drop": 4}
SIMPLIFY_HINTS = {
    "U.S. Citizenship is Required": "citizenship",
    "Does Not Offer Sponsorship": "no_sponsorship",
    "Offers Sponsorship": "sponsorship_positive",
}


def is_fresh(job: Job, ctx: Context) -> bool:
    if job.posted_at is not None:
        hours = (ctx.now - job.posted_at).total_seconds() / 3600
        return -2 <= hours <= ctx.window_hours
    if job.posted_date is not None:
        return 0 <= (ctx.today_et - job.posted_date).days <= ctx.window_days
    return False


def _unique_ci(items: Iterable[str]) -> list[str]:
    seen, out = set(), []
    for item in items:
        if item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out


def _screen(job: Job, res: SourceResult, ctx: Context, rules: TitleRules) -> bool:
    res.scanned += 1
    if not is_fresh(job, ctx):
        return False
    res.fresh += 1
    keep, track = rules.screen(job.title)
    if not keep:
        res.title_skipped += 1
        return False
    us = job_us_status(job.locations)
    if us is False:
        res.location_skipped += 1
        return False
    if us is None:
        job.notes.append("location not confirmed as US")
    job.extra["track"] = track
    res.relevant += 1
    return True


def _run_concurrently(ctx: Context, jobs: list[Job], fn, results: dict[str, SourceResult]) -> None:
    if not jobs:
        return
    with ThreadPoolExecutor(max_workers=max(1, min(ctx.max_workers, len(jobs)))) as pool:
        futures = {pool.submit(fn(job), ctx, job): job for job in jobs}
        for fut in as_completed(futures):
            job = futures[fut]
            try:
                fut.result()
            except Exception as exc:  # noqa: BLE001
                msg = exc.short() if isinstance(exc, HttpError) else f"{type(exc).__name__}: {exc}"
                job.notes.append(f"could not fetch full text ({msg})")
                results[job.source].errors.append(f"detail {job.job_id}: {msg}")


def _board_index(results: dict[str, SourceResult]) -> tuple[dict[tuple[str, str], dict[str, Job]], set[tuple[str, str]]]:
    index: dict[tuple[str, str], dict[str, Job]] = {}
    for kind in BOARD_MODULES:
        res = results.get(kind)
        if res is None:
            continue
        for job in res.jobs:
            index.setdefault((kind, job.board.lower()), {})[job.job_id.lower()] = job
    fetched = set(index)
    return index, fetched


def _verify_simplify(
    ctx: Context,
    kept: list[Job],
    results: dict[str, SourceResult],
    index: dict[tuple[str, str], dict[str, Job]],
    fetched: set[tuple[str, str]],
    stale: list[dict[str, Any]],
) -> list[Job]:
    """Replace Simplify's date with the company board's own date when the link points to a board."""
    simplify_jobs = [j for j in kept if j.source == "simplify"]
    if not simplify_jobs:
        return kept
    refs: dict[str, BoardRef] = {}
    missing: set[tuple[str, str]] = set()
    for job in simplify_jobs:
        ref = parse_board_url(job.url)
        if ref and ref.job_id:
            refs[job.key] = ref
            if (ref.kind, ref.token.lower()) not in fetched:
                missing.add((ref.kind, ref.token))
    # Boards we did not sweep: fetch just those, once each.
    if missing:
        with ThreadPoolExecutor(max_workers=max(1, min(ctx.max_workers, len(missing)))) as pool:
            futures = {pool.submit(BOARD_MODULES[k].fetch_board, ctx, t): (k, t) for k, t in missing}
            for fut in as_completed(futures):
                kind, token = futures[fut]
                try:
                    board_jobs = fut.result()
                except Exception:  # nosec B112 - an unreachable board is reported on each affected job below
                    continue
                fetched.add((kind, token.lower()))
                index[(kind, token.lower())] = {j.job_id.lower(): j for j in board_jobs}

    kept_by_key = {j.key: j for j in kept}
    out = []
    for job in kept:
        if job.source != "simplify":
            out.append(job)
            continue
        ref = refs.get(job.key)
        if ref is None:
            job.notes.append("date from Simplify only; confirm on the company site")
            out.append(job)
            continue
        board_key = (ref.kind, ref.token.lower())
        if board_key not in fetched:
            job.notes.append(f"could not reach the {ref.kind} board; date from Simplify only")
            out.append(job)
            continue
        board_job = index.get(board_key, {}).get(ref.job_id.lower())
        if board_job is None:
            job.notes.append(f"not found on the {ref.kind} board (may be closed)")
            out.append(job)
            continue
        if board_job.key in kept_by_key:
            kept_by_key[board_job.key].notes.append("also listed on Simplify")
            hint = job.extra.get("simplify_sponsorship")
            if hint:
                kept_by_key[board_job.key].extra.setdefault("simplify_sponsorship", hint)
            continue
        job.posted_at, job.posted_date = board_job.posted_at, board_job.posted_date
        job.date_basis = f"{ref.kind} board {board_job.date_basis} (Simplify link)"
        if not is_fresh(job, ctx):
            results["simplify"].relevant -= 1
            stale.append({"company": job.company, "title": job.title, "url": job.url,
                          "board_date": job.posted_at.isoformat(timespec="seconds") if job.posted_at else None})
            continue
        if not board_job.description and ref.kind == "greenhouse":
            try:
                greenhouse.enrich(ctx, board_job)
            except Exception as exc:  # noqa: BLE001
                job.notes.append(f"could not fetch full text ({exc})")
        job.description = board_job.description
        out.append(job)
    return out


def _merge_duplicates(jobs: list[Job]) -> list[Job]:
    """Same company + same title (other locations, or the same job on two sites) becomes one row."""
    jobs = sorted(jobs, key=lambda j: SOURCE_PRIORITY.get(j.source, 99))
    primary: dict[str, Job] = {}
    for job in jobs:
        key = dedupe_key(job.company, job.title)
        first = primary.get(key)
        if first is None:
            primary[key] = job
            continue
        first.extra.setdefault("also", []).append({"source": job.source, "url": job.url, "locations": job.locations})
        for loc in job.locations:
            if loc not in first.locations:
                first.locations.append(loc)
        if not first.description and job.description:
            first.description = job.description
    return list(primary.values())


def _hints(job: Job) -> dict[str, str]:
    label = job.extra.get("simplify_sponsorship") or ""
    kind = SIMPLIFY_HINTS.get(label)
    return {kind: f"Simplify: {label}"} if kind else {}


def run(cfg: Config, *, http: Any = None, now: datetime | None = None, only: set[str] | None = None) -> tuple[dict, int]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    http = http or Http(cfg.user_agent, timeout=cfg.timeout, per_host=cfg.per_host)
    ctx = Context(http=http, now=now, today_et=now.astimezone(ET).date(), window_hours=cfg.window_hours, max_workers=cfg.max_workers)
    rules = TitleRules.from_strings(cfg.title_exclude, cfg.title_include, cfg.early_career, cfg.role_noun)
    wanted = set(only or ALL_SOURCES)
    results: dict[str, SourceResult] = {}

    listings: list[dict] = []
    if "simplify" in wanted and cfg.simplify_url:
        results["simplify"], listings = simplify.fetch(ctx, cfg.simplify_url)
    disc = discover(listings, now, cfg.discovery_max_age_days) if (cfg.discovery_enabled and listings) else None
    add_disc = disc is not None and cfg.discovery_include
    names = disc.company_names() if disc else {}

    def boards(kind: str, configured: tuple[str, ...]) -> list[str]:
        return _unique_ci([*configured, *(disc.tokens(kind) if add_disc else [])])

    if "greenhouse" in wanted:
        results["greenhouse"] = greenhouse.fetch(ctx, boards("greenhouse", cfg.greenhouse))
    if "ashby" in wanted:
        results["ashby"] = ashby.fetch(ctx, boards("ashby", cfg.ashby), names.get("ashby"))
    if "lever" in wanted:
        results["lever"] = lever.fetch(ctx, boards("lever", cfg.lever), names.get("lever"))
    if "workday" in wanted:
        tenants = list(cfg.workday)
        if disc is not None and cfg.discovery_workday:
            known = {(t.host, t.site.lower()) for t in tenants}
            for site, company in disc.workday.items():
                if (site.host, site.site.lower()) not in known:
                    tenants.append(workday.Tenant(company, site.host, site.tenant, site.site, ("",), cfg.discovery_workday_pages))
        results["workday"] = workday.fetch(ctx, tenants)
    if "eightfold" in wanted:
        results["eightfold"] = eightfold.fetch(ctx, list(cfg.eightfold))
    if "amazon" in wanted:
        results["amazon"] = amazon.fetch(ctx, list(cfg.amazon_queries))
    for name, res in results.items():
        log.info("%-10s boards %d/%d ok, %d postings", name, res.boards_ok, res.boards_total, len(res.jobs))

    index, fetched = _board_index(results)
    kept = [job for res in results.values() for job in res.jobs if _screen(job, res, ctx, rules)]

    _run_concurrently(ctx, [j for j in kept if j.source in ENRICHERS and not j.description], lambda j: ENRICHERS[j.source], results)
    still_us = []
    for job in kept:  # full text can reveal the real location (Workday "3 Locations", Greenhouse offices)
        if job_us_status(job.locations) is False:
            results[job.source].relevant -= 1
            results[job.source].location_skipped += 1
        else:
            still_us.append(job)

    stale: list[dict[str, Any]] = []
    kept = _merge_duplicates(_verify_simplify(ctx, still_us, results, index, fetched, stale))
    for job in kept:
        job.extra["triage"] = triage(job.description, _hints(job))

    st = state_mod.load(cfg.state_path)
    bootstrap = not st["jobs"]
    new_keys = state_mod.update(st, kept, now)
    state_mod.prune(st, now, cfg.prune_days)
    state_mod.save(cfg.state_path, st)

    def sort_key(job: Job) -> tuple:
        age = age_hours(job.posted_at, job.posted_date, now)
        return (VERDICT_ORDER.get(job.extra["triage"].verdict, 9), track_rank(job.extra.get("track", "")), age if age is not None else 1e9)

    kept.sort(key=sort_key)
    doc = report.build(
        now=now,
        window_hours=cfg.window_hours,
        rows=[report.job_row(j, now, new_keys, st) for j in kept],
        sources={name: res.stats() for name, res in results.items()},
        stale_simplify=stale,
        bootstrap=bootstrap,
    )
    report.write(cfg.out_dir, doc, disc.to_dict() if disc else None)
    log.info("wrote %d jobs to %s (%s)", len(kept), cfg.out_dir, doc["verdict_counts"])
    any_ok = any(res.boards_ok for res in results.values())
    return doc, 0 if (any_ok or not results) else 2
