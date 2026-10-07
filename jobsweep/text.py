"""HTML-to-text, name normalization, and small string helpers."""

from __future__ import annotations

import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_BLOCK_TAGS = re.compile(r"<\s*/?\s*(?:p|div|li|ul|ol|br|h[1-6]|tr|table|section)\b[^>]*>", re.I)
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t\u00a0]+")
_LINEBREAKS = re.compile(r"\s*\n\s*")
_LEGAL = re.compile(r"\b(?:inc|llc|ltd|corp|corporation|co|plc|gmbh|the)\b\.?")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def html_to_text(raw: str | None) -> str:
    if not raw:
        return ""
    s = html.unescape(raw)  # Greenhouse returns entity-escaped HTML (&lt;p&gt;)
    s = _BLOCK_TAGS.sub("\n", s)
    s = _TAGS.sub(" ", s)
    s = html.unescape(s)
    s = _SPACES.sub(" ", s)
    s = _LINEBREAKS.sub("\n", s)
    return s.strip()


def norm(s: str) -> str:
    s = _LEGAL.sub(" ", s.lower())
    return _NON_ALNUM.sub(" ", s).strip()


def dedupe_key(company: str, title: str) -> str:
    """Same company + same title across sources or locations collapses to one row."""
    return f"{norm(company)}|{norm(title)}"


def strip_tracking(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not (k.lower().startswith("utm_") or k.lower() == "ref")
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def split_locations(raw: str) -> list[str]:
    parts = re.split(r"\s*(?:;|\||\n)\s*", raw or "")
    return [p.strip() for p in parts if p.strip()]


def text(value: object) -> str:
    """A stripped string, or '' for anything that is not a string (untrusted JSON)."""
    return value.strip() if isinstance(value, str) else ""


def pretty_name(token: str) -> str:
    return " ".join(w.capitalize() for w in re.split(r"[-_]+", token) if w)
