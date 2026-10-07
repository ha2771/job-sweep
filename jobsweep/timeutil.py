"""Date parsing and the US Eastern day boundary used for date-only sources."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any

try:
    from zoneinfo import ZoneInfo

    ET: tzinfo = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001 - Windows without the tzdata package
    logging.getLogger("jobsweep").warning("tz database missing; using UTC-5 for 'today'")
    ET = timezone(timedelta(hours=-5))


def parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def from_epoch(value: Any, *, ms: bool = False) -> datetime | None:
    if isinstance(value, bool):
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if ms:
        seconds /= 1000.0
    if seconds <= 0:
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def age_hours(posted_at: datetime | None, posted_date: date | None, now: datetime) -> float | None:
    """Hours since posting. For date-only postings, hours since that day began in US Eastern."""
    if posted_at is not None:
        return (now - posted_at).total_seconds() / 3600
    if posted_date is not None:
        start = datetime.combine(posted_date, time(0), ET)
        return (now - start).total_seconds() / 3600
    return None


def posted_label(posted_at: datetime | None, posted_date: date | None, now: datetime) -> str:
    if posted_at is not None:
        hours = (now - posted_at).total_seconds() / 3600
        if hours < 1:
            return "<1h ago"
        if hours < 48:
            return f"{hours:.0f}h ago"
        return f"{hours / 24:.1f}d ago"
    if posted_date is not None:
        return f"{posted_date.isoformat()} (date only)"
    return "no date"
