"""Remembers when each relevant posting was first seen, across runs."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .model import Job
from .timeutil import parse_iso

log = logging.getLogger("jobsweep")
VERSION = 1


def empty() -> dict[str, Any]:
    return {"version": VERSION, "jobs": {}}


def load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty()
    except (OSError, ValueError) as exc:
        log.warning("state file unreadable (%s); starting fresh", exc)
        return empty()
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), dict):
        log.warning("state file has an unexpected shape; starting fresh")
        return empty()
    return data


def update(state: dict[str, Any], jobs: list[Job], now: datetime) -> set[str]:
    """Record jobs; return the keys seen for the first time in this run."""
    stamp = now.isoformat(timespec="seconds")
    new = set()
    for job in jobs:
        rec = state["jobs"].get(job.key)
        if not isinstance(rec, dict):
            rec = state["jobs"][job.key] = {"first_seen": stamp}
            new.add(job.key)
        rec.update({"last_seen": stamp, "company": job.company, "title": job.title, "url": job.url})
    return new


def prune(state: dict[str, Any], now: datetime, days: int) -> int:
    cutoff = now - timedelta(days=days)
    stale = [k for k, v in state["jobs"].items() if not isinstance(v, dict) or (parse_iso(v.get("last_seen")) or cutoff) < cutoff]
    for k in stale:
        del state["jobs"][k]
    return len(stale)


def write_json_atomic(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def save(path: Path, state: dict[str, Any]) -> None:
    write_json_atomic(path, state)
