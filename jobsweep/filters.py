"""Title screening, role-track labels, and US location detection."""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------- location

US_STATE_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM "
    "NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)
_STATE_NAMES = (
    "alabama alaska arizona arkansas california colorado connecticut delaware florida georgia hawaii "
    "idaho illinois indiana iowa kansas kentucky louisiana maine maryland massachusetts michigan "
    "minnesota mississippi missouri montana nebraska nevada ohio oklahoma oregon pennsylvania "
    "tennessee texas utah vermont virginia washington wisconsin wyoming"
).split() + [
    "new hampshire", "new jersey", "new mexico", "new york", "north carolina", "north dakota",
    "rhode island", "south carolina", "south dakota", "west virginia", "district of columbia",
]
_US_CITIES = [
    "san francisco", "sf bay area", "bay area", "silicon valley", "nyc", "manhattan", "brooklyn",
    "seattle", "bellevue", "redmond", "kirkland", "boston", "austin", "mountain view", "palo alto",
    "menlo park", "redwood city", "san mateo", "foster city", "sunnyvale", "santa clara", "san jose",
    "cupertino", "milpitas", "fremont", "oakland", "emeryville", "berkeley", "san diego",
    "los angeles", "santa monica", "culver city", "el segundo", "irvine", "pasadena", "chicago",
    "pittsburgh", "atlanta", "denver", "boulder", "philadelphia", "princeton", "ann arbor", "detroit",
    "houston", "dallas", "plano", "phoenix", "salt lake city", "miami", "raleigh", "durham",
    "minneapolis", "portland", "hillsboro", "folsom", "sacramento", "nashville", "baltimore",
    "arlington", "mclean", "reston", "herndon", "columbus", "madison", "jersey city", "hoboken",
    "somerville", "cambridge, ma",
]
_NON_US = [
    "canada", "toronto", "vancouver", "montreal", "ottawa", "waterloo", "calgary", "united kingdom",
    "england", "london", "cambridge, uk", "oxford", "edinburgh", "uk", "ireland", "dublin", "india",
    "bangalore", "bengaluru", "hyderabad", "chennai", "pune", "mumbai", "noida", "gurgaon", "gurugram",
    "delhi", "germany", "berlin", "munich", "hamburg", "france", "paris", "netherlands", "amsterdam",
    "spain", "madrid", "barcelona", "portugal", "lisbon", "switzerland", "zurich", "zürich", "geneva",
    "poland", "warsaw", "krakow", "kraków", "israel", "tel aviv", "singapore", "japan", "tokyo",
    "korea", "seoul", "china", "beijing", "shanghai", "shenzhen", "hong kong", "taiwan", "taipei",
    "australia", "sydney", "melbourne", "new zealand", "mexico", "brazil", "são paulo", "sao paulo",
    "argentina", "colombia", "bogota", "bogotá", "chile", "emea", "apac", "latam", "europe", "sweden",
    "stockholm", "denmark", "copenhagen", "finland", "norway", "italy", "milan", "romania", "czech",
    "prague", "hungary", "budapest", "ukraine", "serbia", "estonia", "philippines", "vietnam",
    "indonesia", "malaysia", "thailand", "uae", "dubai", "saudi", "egypt", "nigeria", "kenya",
    "south africa", "turkey", "istanbul", "pakistan", "bangladesh", "costa rica",
]


def _words(phrases: list[str]) -> re.Pattern[str]:
    alts = "|".join(re.escape(p) for p in sorted(phrases, key=len, reverse=True))
    return re.compile(rf"(?<![\w]){'(?:' + alts + ')'}(?![\w])", re.I)


_US_EXPLICIT = re.compile(r"\bUS\b|\bU\.S\.|\bUSA\b")
_US_EXPLICIT_I = re.compile(r"united states|north america|\bus[- ](?:remote|based|only)\b", re.I)
_STATE_NAME_RE = _words(_STATE_NAMES)
_CITY_RE = _words(_US_CITIES)
_NON_US_RE = _words(_NON_US)
_CODE_RE = re.compile(r"\b[A-Z]{2}\b")
_REMOTE_RE = re.compile(r"\b(?:remote|anywhere|hybrid|distributed)\b", re.I)


def classify_location(loc: str) -> bool | None:
    """True = US, False = clearly not US, None = can't tell (keep it and say so)."""
    s = (loc or "").strip()
    if not s:
        return None
    strong = bool(_US_EXPLICIT.search(s) or _US_EXPLICIT_I.search(s) or _STATE_NAME_RE.search(s))
    weak = bool(set(_CODE_RE.findall(s)) & US_STATE_CODES) or bool(_CITY_RE.search(s))
    non_us = bool(_NON_US_RE.search(s))
    if strong:
        return True  # "New Mexico", "Remote - US or Canada"
    if non_us:
        return False  # "Chennai, TN", "Berlin, DE": a two-letter code alone is not enough
    if weak:
        return True
    return None


def job_us_status(locations: list[str]) -> bool | None:
    verdicts = [classify_location(loc) for loc in locations]
    if any(v is True for v in verdicts):
        return True
    if verdicts and all(v is False for v in verdicts):
        return False
    return None


# ---------------------------------------------------------------- titles

TRACKS: list[tuple[str, re.Pattern[str]]] = [
    ("GenAI/LLM", re.compile(
        r"\bllms?\b|large language|language model|gen(?:erative)?[ -]?ai|\bgenai\b|\bagents?\b|"
        r"\bagentic\b|\brag\b|\bnlp\b|natural language|foundation model|multimodal|conversational", re.I)),
    ("Computer vision", re.compile(
        r"computer vision|\bvision\b|\bcv\b|perception|imaging|\bimage|\bvideo|\b3d\b|camera|graphics", re.I)),
    ("Edge/inference", re.compile(
        r"on-device|\bedge\b|inference|embedded|compiler|\bkernels?\b|accelerat|\bgpu|cuda|silicon|"
        r"performance|efficien", re.I)),
    ("Signal/wireless/audio", re.compile(
        r"signal|\bdsp\b|wireless|\b[56]g\b|\brf\b|radar|lidar|sensor|audio|speech|acoustic|"
        r"communication|\bradio\b", re.I)),
    ("RL/robotics", re.compile(
        r"robot|reinforcement|\brl\b|autonom|embodied|manipulation|locomotion", re.I)),
    ("Research", re.compile(r"research", re.I)),
    ("Data science", re.compile(r"data scien|analytics|statistic", re.I)),
    ("ML/AI general", re.compile(
        r"machine learning|\bml\b|\bai\b|artificial intelligence|deep learning|applied scien|mlops", re.I)),
]
EARLY_TRACK = "Early-career (general)"
# Ranking follows the candidate profile's track order; it is separate from which label wins above.
_TRACK_RANK = {
    "GenAI/LLM": 0, "ML/AI general": 1, "Computer vision": 2, "Edge/inference": 3,
    "Signal/wireless/audio": 4, "Research": 5, "RL/robotics": 6, "Data science": 7, EARLY_TRACK: 8,
}


def track_for(title: str) -> str:
    for name, pattern in TRACKS:
        if pattern.search(title):
            return name
    return "ML/AI general"


def track_rank(track: str) -> int:
    return _TRACK_RANK.get(track, len(_TRACK_RANK))


@dataclass(frozen=True)
class TitleRules:
    exclude: re.Pattern[str]
    include: re.Pattern[str]
    early: re.Pattern[str]
    role_noun: re.Pattern[str]
    include_noun: re.Pattern[str]

    @classmethod
    def from_strings(cls, exclude: str, include: str, early: str, role_noun: str, include_noun: str | None = None) -> "TitleRules":
        return cls(*(re.compile(p, re.I) for p in (exclude, include, early, role_noun, include_noun or role_noun)))

    def screen(self, title: str) -> tuple[bool, str]:
        """(keep?, track or reason)."""
        t = " ".join((title or "").split())
        if not t:
            return False, "empty title"
        hit = self.exclude.search(t)
        if hit:
            return False, f"excluded word: {hit.group(0)}"
        if self.include.search(t) and self.include_noun.search(t):
            return True, track_for(t)  # "Front Desk Agent" or "Speech Language Pathologist" fail the noun check
        if self.early.search(t) and self.role_noun.search(t):
            return True, EARLY_TRACK
        return False, "not an ML/AI or early-career title"
