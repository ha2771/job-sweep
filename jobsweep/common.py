"""Types and helpers shared by the sources and the pipeline."""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Iterable, TypeVar

from .http import HttpError
from .model import Job

log = logging.getLogger("jobsweep")
T = TypeVar("T")


@dataclass
class Context:
    http: Any
    now: datetime
    today_et: date
    window_hours: int
    max_workers: int = 16

    @property
    def window_days(self) -> int:
        return max(1, math.ceil(self.window_hours / 24))


@dataclass
class SourceResult:
    name: str
    jobs: list[Job] = field(default_factory=list)
    boards_total: int = 0
    boards_ok: int = 0
    errors: list[str] = field(default_factory=list)
    scanned: int = 0
    fresh: int = 0
    title_skipped: int = 0
    location_skipped: int = 0
    relevant: int = 0

    def stats(self, max_errors: int = 25) -> dict[str, Any]:
        return {
            "boards_checked": self.boards_total,
            "boards_ok": self.boards_ok,
            "boards_failed": len(self.errors),
            "postings_scanned": self.scanned,
            "fresh_in_window": self.fresh,
            "skipped_by_title": self.title_skipped,
            "skipped_non_us": self.location_skipped,
            "relevant": self.relevant,
            "errors": self.errors[:max_errors],
            "errors_truncated": max(0, len(self.errors) - max_errors),
        }


def dicts(data: Any, key: str | None = None) -> list[dict]:
    """The list of JSON objects at data[key] (or data itself), ignoring anything malformed."""
    seq = data.get(key) if (key is not None and isinstance(data, dict)) else data
    if not isinstance(seq, list):
        return []
    return [x for x in seq if isinstance(x, dict)]


def sweep(
    ctx: Context,
    result: SourceResult,
    items: Iterable[T],
    fetch_one: Callable[[Context, T], list[Job]],
    label: Callable[[T], str] = str,
) -> None:
    """Fetch every board concurrently. One failing board is recorded, never fatal."""
    items = list(items)
    result.boards_total += len(items)
    if not items:
        return
    seen = {j.key for j in result.jobs}
    workers = max(1, min(ctx.max_workers, len(items)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_one, ctx, item): item for item in items}
        for fut in as_completed(futures):
            name = label(futures[fut])
            try:
                jobs = fut.result()
            except HttpError as exc:
                result.errors.append(f"{name}: {exc.short()}")
                continue
            except Exception as exc:  # noqa: BLE001 - an odd response from one board must not sink the run
                log.warning("%s %s: %s: %s", result.name, name, type(exc).__name__, exc)
                result.errors.append(f"{name}: {type(exc).__name__}: {exc}")
                continue
            result.boards_ok += 1
            for job in jobs:
                if job.key not in seen:
                    seen.add(job.key)
                    result.jobs.append(job)
