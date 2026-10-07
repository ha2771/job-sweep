"""The normalized job record every source produces."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class Job:
    source: str  # greenhouse, ashby, lever, workday, eightfold, amazon, simplify
    board: str  # board token, tenant, or company the posting came from
    job_id: str
    company: str
    title: str
    locations: list[str]
    url: str
    posted_at: datetime | None = None  # timezone-aware UTC, when the source gives a timestamp
    posted_date: date | None = None  # date-only sources (Workday list, Amazon)
    date_basis: str = ""  # which field the date came from, shown in the report
    description: str = ""  # plain text; only an excerpt is written out
    notes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.board}:{self.job_id}"
