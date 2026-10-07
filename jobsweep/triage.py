"""Rule-based first pass over a posting's text.

Advisory only. It labels each posting and quotes the sentence that triggered the label,
so whoever writes the digest can confirm it quickly. It never deletes anything.

Verdicts, best first:
  looks_ok     nothing disqualifying found
  stretch      asks for 1-2 years
  check        ambiguous wording (sponsorship question, export control)
  no_text      the source gives no description; read it on the site
  likely_drop  PhD required, 3+ years, citizenship/clearance, or no sponsorship
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

EXCERPT_CHARS = 1500
EVIDENCE_CHARS = 300

_APOS = r"(?:'|’)"
_REQ_HEAD = re.compile(
    r"(?:basic|minimum|required|must[- ]have)\s+(?:qualifications|requirements|skills)"
    r"|qualifications\s*:|requirements\s*:|who you are|what you" + _APOS + r"ll need|what you need"
    r"|what we" + _APOS + r"re looking for|what we need|you (?:will |should |must )?have\b|about you"
    r"|your background|you bring|ideal candidate",
    re.I,
)
_PREF_HEAD = re.compile(
    r"(?:preferred|bonus|desired|nice[- ]to[- ]have)\s+(?:qualifications|requirements|skills|experience|points)"
    r"|nice to have|bonus points|it" + _APOS + r"s a plus|would be a plus|preferred\s*:",
    re.I,
)
# Split on sentence ends, but not after one-letter abbreviations (U.S., Ph.D., e.g.).
_SENTENCE_SPLIT = re.compile(r"(?<![\s.][A-Za-z]\.)(?<=[.!?;])\s+|\n+")

_EEO = re.compile(
    r"regardless of|without regard|discriminat|equal (?:employment )?opportunit|protected (?:class|veteran|status)"
    r"|national origin|affirmative action|e-verify",
    re.I,
)
_NEGATED = re.compile(r"not required|isn" + _APOS + r"t required|is not a requirement|no clearance", re.I)
_PREF_WORD = re.compile(r"prefer|nice to have|bonus|ideally|\ba plus\b|desirable|is a plus", re.I)

_CITIZEN = re.compile(
    r"\bU\.?\s?S\.?\s+citizen(?:s|ship)?\b|\bUnited States citizen(?:s|ship)?\b"
    r"|\bU\.?\s?S\.?\s+persons?\b|\bITAR\b"
    r"|\b(?:top secret|ts/sci|secret clearance|security clearance|active clearance|clearance is required)\b"
    r"|\bobtain (?:and maintain )?(?:a |an )?(?:security |government |federal )?clearance\b",
    re.I,
)
_EXPORT = re.compile(r"\bexport[- ]control(?:led)?\b", re.I)

_NEG = (
    r"(?:not|unable to|cannot|can ?not|can" + _APOS + r"t|won" + _APOS + r"t|will not|do not|does not|"
    r"don" + _APOS + r"t|doesn" + _APOS + r"t|are not able to|is not able to|not able to)"
)
_NO_SPONSOR = re.compile(
    rf"\b{_NEG}\s+(?:currently\s+)?(?:be\s+)?(?:able\s+to\s+)?sponsor"
    rf"|\b{_NEG}\s+(?:currently\s+)?(?:be\s+)?(?:able\s+to\s+)?(?:offer|provide|support|consider)[^.\n]{{0,60}}?(?:sponsor|visa|h-?1b)"
    r"|without (?:the )?(?:need for |requiring |requirement of |need of )?(?:current or future |now or in the future |future )?"
    r"(?:employer[- ])?(?:visa |immigration |work )?sponsorship"
    r"|\bnot (?:be )?eligible for (?:visa |immigration |employer )?sponsorship|\bineligible for (?:visa )?sponsorship"
    r"|sponsorship (?:is |will )?not (?:be )?(?:available|offered|provided|considered|possible)"
    r"|\bno (?:visa |immigration |h-?1b )?sponsorship\b"
    r"|\b(?:must|will|would) not (?:currently |now )?(?:need|require)[^.\n]{0,40}sponsorship"
    rf"|\b{_NEG}\s+(?:accept|consider|hire)[^.\n]{{0,40}}\b(?:opt|cpt|f-?1|visa)\b",
    re.I,
)
_SPONSOR_QUESTION = re.compile(
    r"(?:now or in the future|currently or in the future|now or at any (?:point|time) in the future)[^.\n]{0,60}sponsorship"
    r"|sponsorship[^.\n]{0,60}now or in the future",
    re.I,
)
_SPONSOR_OK = re.compile(
    r"(?:visa|h-?1b|immigration|work) sponsorship (?:is |will be )?(?:available|offered|provided)"
    r"|\b(?:we|will|can|do|does|able to) (?:offer |provide |support )?(?:visa |h-?1b |immigration )sponsorship"
    r"|\bsponsorship (?:is )?available|\bwill sponsor\b|\bopen to sponsoring\b|\bsponsors? (?:h-?1b|visas)\b",
    re.I,
)

_PHD = re.compile(r"\bph\.?\s?d\b\.?|\bdoctora(?:l|te)\b", re.I)
_PHD_STRONG = re.compile(
    r"required|must have|must hold|or equivalent (?:research |industry |practical )?experience|is a must|minimum", re.I
)
_OTHER_DEGREE = re.compile(
    r"\b(?:master" + _APOS + r"?s?|m\.\s?s\.?|ms|msc|m\.?eng|meng|bachelor" + _APOS + r"?s?|b\.\s?s\.?|bs|bsc|"
    r"b\.?tech|undergraduate|graduate degree)\b",
    re.I,
)
_MS = re.compile(
    r"\b(?:master" + _APOS + r"?s?|m\.\s?s\.?|ms|msc|m\.?eng|meng|graduate degree|advanced degree)\b", re.I
)

_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_WORDNUM_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\b(?:\s*\(\d{1,2}\))?"
    r"(?=\s*\+?\s*(?:or more\s+|plus\s+)?(?:years?|yrs?)\b)",
    re.I,
)
_YEARS = re.compile(
    r"(?<![\d.$])(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|—|to)\s*\d{1,2}\s*\+?\s*)?(?:or more\s+)?(?:years?|yrs?)\b",
    re.I,
)
_EXP_WORD = re.compile(
    r"experience|industry|professional|working|hands-on|track record|post-?grad|work(?:ed)? (?:in|on|with)", re.I
)
_YEARS_IGNORE_BEFORE = re.compile(r"(?:within|past|last|next|first|every|over)\s*(?:the\s*)?$", re.I)
_YEARS_ZERO_BEFORE = re.compile(r"(?:less than|under|fewer than|up to|no more than|at most)\s*$", re.I)
_CLAUSE_SPLIT = re.compile(r",?\s+\bor\b\s+|;|/|\(|\)", re.I)


@dataclass
class Triage:
    verdict: str
    reasons: list[str] = field(default_factory=list)
    min_years: int | None = None
    sponsorship_positive: bool = False
    evidence: dict[str, str] = field(default_factory=dict)
    quals_excerpt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reasons": self.reasons,
            "min_years": self.min_years,
            "sponsorship_positive": self.sponsorship_positive,
            "evidence": self.evidence,
            "quals_excerpt": self.quals_excerpt,
        }


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s and s.strip()]


def _clip(s: str, n: int = EVIDENCE_CHARS) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def required_section(text: str) -> tuple[str, bool]:
    """(text of the required-qualifications part, whether a heading was found)."""
    head = _REQ_HEAD.search(text)
    if head:
        pref = _PREF_HEAD.search(text, head.end())
        return text[head.start() : pref.start() if pref else len(text)], True
    pref = _PREF_HEAD.search(text)
    return (text[: pref.start()] if pref else text), False


def quals_excerpt(text: str) -> str:
    head = _REQ_HEAD.search(text)
    if head:
        start = head.start()
    else:
        exp = re.search(r"experience|degree", text, re.I)
        start = max(0, exp.start() - 200) if exp else 0
    return _clip(text[start:], EXCERPT_CHARS)


def _normalize_numbers(s: str) -> str:
    return _WORDNUM_RE.sub(lambda m: str(_WORDNUM[m.group(1).lower()]), s)


def _years_in(fragment: str) -> list[int]:
    found = []
    for m in _YEARS.finditer(fragment):
        before = fragment[max(0, m.start() - 20) : m.start()]
        if _YEARS_IGNORE_BEFORE.search(before):
            continue
        n = 0 if _YEARS_ZERO_BEFORE.search(before) else int(m.group(1))
        if n <= 20:
            found.append(n)
    return found


def years_requirement(required: str) -> tuple[int | None, str]:
    """The years a Master's graduate needs, as best the wording allows.

    If a clause names a Master's degree with a number of years, that clause wins
    ("BS + 5 or MS + 3" -> 3). Otherwise the largest number in the required section.
    """
    ms_years: list[tuple[int, str]] = []
    all_years: list[tuple[int, str]] = []
    for sent in _sentences(_normalize_numbers(required)):
        if not _EXP_WORD.search(sent) or _PREF_WORD.search(sent) or _EEO.search(sent):
            continue
        nums = _years_in(sent)
        if not nums:
            continue
        all_years.extend((n, sent) for n in nums)
        for clause in _CLAUSE_SPLIT.split(sent):
            if clause and _MS.search(clause):
                ms_years.extend((n, sent) for n in _years_in(clause))
    if ms_years:
        n, sent = min(ms_years, key=lambda x: x[0])
        return n, _clip(sent)
    if all_years:
        n, sent = max(all_years, key=lambda x: x[0])
        return n, _clip(sent)
    return None, ""


def _first(pattern: re.Pattern[str], sentences: list[str], *, guard_eeo: bool = True) -> str:
    for s in sentences:
        if pattern.search(s) and not (guard_eeo and _EEO.search(s)) and not _NEGATED.search(s):
            return _clip(s)
    return ""


def triage(text: str, hints: dict[str, str] | None = None) -> Triage:
    """hints: extra signals from the source, e.g. {"citizenship": "Simplify: U.S. Citizenship is Required"}."""
    hints = hints or {}
    text = text or ""
    sentences = _sentences(text)
    evidence: dict[str, str] = {}
    hard: list[str] = []
    soft: list[str] = []

    if ev := (_first(_CITIZEN, sentences) or hints.get("citizenship", "")):
        hard.append("citizenship/clearance")
        evidence["citizenship/clearance"] = ev
    if ev := (_first(_NO_SPONSOR, sentences) or hints.get("no_sponsorship", "")):
        hard.append("no sponsorship")
        evidence["no sponsorship"] = ev
    elif ev := _first(_SPONSOR_QUESTION, sentences):
        soft.append("sponsorship wording")
        evidence["sponsorship wording"] = ev
    if "citizenship/clearance" not in hard and (ev := _first(_EXPORT, sentences)):
        soft.append("export control")
        evidence["export control"] = ev

    required, has_heading = required_section(text)
    for s in _sentences(required):
        if _PHD.search(s) and not _OTHER_DEGREE.search(s) and not _PREF_WORD.search(s):
            if has_heading or _PHD_STRONG.search(s):
                hard.append("PhD required")
                evidence["PhD required"] = _clip(s)
                break

    min_years, years_ev = years_requirement(required)
    if min_years is not None:
        evidence["years"] = years_ev
        if min_years >= 3:
            hard.append(f"{min_years}+ years")

    positive = bool(hints.get("sponsorship_positive")) or any(
        _SPONSOR_OK.search(s) and not _NO_SPONSOR.search(s) for s in sentences
    )

    if hard:
        verdict, reasons = "likely_drop", hard + soft
    elif soft:
        verdict, reasons = "check", soft
    elif min_years in (1, 2):
        verdict, reasons = "stretch", [f"{min_years} year{'s' if min_years > 1 else ''}"]
    elif not text.strip():
        verdict, reasons = "no_text", ["no description from this source"]
    else:
        verdict, reasons = "looks_ok", []

    return Triage(
        verdict=verdict,
        reasons=reasons,
        min_years=min_years,
        sponsorship_positive=positive,
        evidence=evidence,
        quals_excerpt=quals_excerpt(text) if text.strip() else "",
    )
