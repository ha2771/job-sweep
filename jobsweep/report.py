"""Writes candidates.json (for Claude) and candidates.md (for a quick human look)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .model import Job
from .state import write_json_atomic
from .text import dedupe_key
from .timeutil import ET, age_hours, posted_label

SECTIONS = [
    ("looks_ok", "Looks OK"),
    ("stretch", "Stretch (1-2 years)"),
    ("check", "Check wording"),
    ("no_text", "No description from source (read on site)"),
    ("likely_drop", "Likely drop (verify the quoted reason)"),
]


def job_row(job: Job, now: datetime, new_keys: set[str], state: dict[str, Any]) -> dict[str, Any]:
    tri = job.extra["triage"]
    age = age_hours(job.posted_at, job.posted_date, now)
    return {
        "key": job.key,
        "dedupe_key": dedupe_key(job.company, job.title),
        "source": job.source,
        "board": job.board,
        "company": job.company,
        "title": job.title,
        "locations": job.locations,
        "url": job.url,
        "posted": posted_label(job.posted_at, job.posted_date, now),
        "posted_at": job.posted_at.isoformat(timespec="seconds") if job.posted_at else None,
        "posted_date": job.posted_date.isoformat() if job.posted_date else None,
        "age_hours": round(age, 1) if age is not None else None,
        "within_24h": bool(job.extra.get("within_24h")),
        "date_basis": job.date_basis,
        "first_seen": (state["jobs"].get(job.key) or {}).get("first_seen"),
        "new_this_run": job.key in new_keys,
        "track": job.extra.get("track"),
        **tri.to_dict(),
        "notes": job.notes,
        "also_posted_as": job.extra.get("also", []),
    }


def build(
    *,
    now: datetime,
    window_hours: int,
    rows: list[dict[str, Any]],
    sources: dict[str, dict[str, Any]],
    stale_simplify: list[dict[str, Any]],
    bootstrap: bool,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "generated_at_et": now.astimezone(ET).strftime("%Y-%m-%d %I:%M %p ET"),
        "window_hours": window_hours,
        "bootstrap_run": bootstrap,
        "verdict_counts": counts,
        "sources": sources,
        "jobs": rows,
        "simplify_stale_after_board_check": stale_simplify,
    }


def _cell(s: str) -> str:
    return " ".join(str(s).split()).replace("|", "\\|")


def to_markdown(doc: dict[str, Any]) -> str:
    lines = [
        f"# Job sweep, {doc['generated_at_et']}",
        "",
        f"Postings from the last {doc['window_hours']}h that passed the title and US-location screens. "
        "Verdicts come from keyword rules; the quoted evidence is in candidates.json.",
        "",
        "| Source | Boards ok/checked | Scanned | Fresh | Relevant |",
        "|---|---|---|---|---|",
    ]
    for name, s in doc["sources"].items():
        lines.append(f"| {name} | {s['boards_ok']}/{s['boards_checked']} | {s['postings_scanned']} | {s['fresh_in_window']} | {s['relevant']} |")
    groups = ((True, "Posted in the last 24 hours"), (False, "Posted 24-72 hours ago (for weekend digests)"))
    for recent, group in groups:
        group_rows = [r for r in doc["jobs"] if r["within_24h"] is recent]
        lines += ["", f"## {group} ({len(group_rows)})"]
        for verdict, heading in SECTIONS:
            rows = [r for r in group_rows if r["verdict"] == verdict]
            if not rows:
                continue
            lines += ["", f"### {heading} ({len(rows)})", "", "| Posted | Company | Role | Track | Why |", "|---|---|---|---|---|"]
            for r in rows:
                why = "; ".join(r["reasons"]) or ("sponsorship mentioned" if r["sponsorship_positive"] else "")
                new = " **new**" if r["new_this_run"] else ""
                lines.append(
                    f"| {_cell(r['posted'])}{new} | {_cell(r['company'])} | [{_cell(r['title'])}]({r['url']}) | "
                    f"{_cell(r['track'] or '')} | {_cell(why)} |"
                )
    lines.append("")
    return "\n".join(lines)


def write(out_dir: Path, doc: dict[str, Any], discovery: dict[str, Any] | None) -> None:
    out_dir = Path(out_dir)
    write_json_atomic(out_dir / "candidates.json", doc)
    md = out_dir / "candidates.md"
    tmp = md.with_suffix(".md.tmp")
    tmp.write_text(to_markdown(doc), encoding="utf-8")
    tmp.replace(md)
    if discovery is not None:
        write_json_atomic(out_dir / "discovered_boards.json", discovery)
