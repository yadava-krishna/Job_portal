"""Locations without AI: one display form per place, the country, and who a remote role is open to.

    "bangalore, , India"    -> Bengaluru, India                 country IN
    "Mountain View, CA"     -> Mountain View, CA, United States country US
    "Remote - USA"          -> Remote (United States)            remote, open to ["US"]
    "India (Remote)"        -> Remote (India)                    remote, open to ["IN"]
    "Worldwide Remote"      -> Remote (worldwide)                remote, open to ["*"]
    "Remote"                -> Remote                            remote, open to None (not stated)

Only places this module recognises are folded or assigned a country; anything else is kept as written (tidied), and
an unrecognised place never gets a guessed country.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

COUNTRY_NAMES: dict[str, str] = {
    "IN": "India", "US": "United States", "GB": "United Kingdom", "CA": "Canada", "DE": "Germany", "NL": "Netherlands",
    "IE": "Ireland", "AU": "Australia", "NZ": "New Zealand", "SG": "Singapore", "AE": "United Arab Emirates", "SA": "Saudi Arabia",
    "QA": "Qatar", "FR": "France", "ES": "Spain", "PT": "Portugal", "IT": "Italy", "PL": "Poland", "SE": "Sweden", "DK": "Denmark",
    "NO": "Norway", "FI": "Finland", "CH": "Switzerland", "AT": "Austria", "BE": "Belgium", "CZ": "Czechia", "RO": "Romania",
    "JP": "Japan", "KR": "South Korea", "CN": "China", "HK": "Hong Kong", "TW": "Taiwan", "PH": "Philippines", "TH": "Thailand",
    "MY": "Malaysia", "ID": "Indonesia", "VN": "Vietnam", "IL": "Israel", "BR": "Brazil", "MX": "Mexico", "AR": "Argentina",
    "CO": "Colombia", "BG": "Bulgaria", "SK": "Slovakia", "LU": "Luxembourg", "HU": "Hungary",
    "GR": "Greece", "TR": "Türkiye", "UA": "Ukraine", "CR": "Costa Rica", "CL": "Chile", "ZA": "South Africa", "NG": "Nigeria", "KE": "Kenya", "EG": "Egypt", "PK": "Pakistan",
    "BD": "Bangladesh", "LK": "Sri Lanka", "NP": "Nepal",
}

# Words that name a country unambiguously (country names, demonyms used in postings, and well-known cities).
_COUNTRY_WORDS: dict[str, tuple[str, ...]] = {
    "IN": ("india", "bengaluru", "bangalore", "mumbai", "bombay", "pune", "hyderabad", "secunderabad", "chennai", "madras",
           "gurugram", "gurgaon", "noida", "new delhi", "delhi", "kolkata", "calcutta", "ahmedabad", "kochi", "cochin",
           "coimbatore", "jaipur", "chandigarh", "thiruvananthapuram", "trivandrum", "mysuru", "mysore", "indore", "nagpur",
           "lucknow", "vadodara", "surat", "visakhapatnam", "bhubaneswar", "mangaluru", "mangalore", "navi mumbai", "thane",
           "karnataka", "maharashtra", "telangana", "tamil nadu", "haryana", "kerala", "gujarat", "west bengal", "uttar pradesh",
           "andhra pradesh", "rajasthan", "punjab", "bihar", "odisha", "madhya pradesh", "mohali", "vizag", "guntur", "patna",
           "ludhiana", "jalandhar", "vellore", "noida", "greater noida", "ghaziabad", "faridabad", "bhopal", "kanpur"),
    "US": ("united states", "usa", "u.s.", "new york", "nyc", "san francisco", "seattle", "austin", "boston", "chicago",
           "los angeles", "denver", "atlanta", "miami", "dallas", "houston", "mountain view", "palo alto", "san jose",
           "sunnyvale", "menlo park", "washington, dc", "washington dc", "philadelphia", "phoenix", "portland", "san diego",
           "salt lake city", "pittsburgh", "minneapolis", "detroit", "nashville", "raleigh", "charlotte", "california", "texas",
           "ohio", "utah", "virginia", "pennsylvania", "illinois", "massachusetts", "colorado", "florida", "oregon", "michigan",
           "minnesota", "arizona", "north carolina", "new jersey", "maryland", "kentucky", "tennessee", "wisconsin", "indiana",
           "connecticut", "missouri", "nevada", "reston", "mclean"),
    "GB": ("united kingdom", "uk", "england", "scotland", "wales", "london", "manchester", "edinburgh", "glasgow", "birmingham",
           "bristol", "cambridge, uk", "leeds", "belfast"),
    "CA": ("canada", "toronto", "vancouver", "montreal", "ottawa", "calgary", "waterloo"),
    "DE": ("germany", "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne", "köln", "stuttgart"),
    "NL": ("netherlands", "amsterdam", "rotterdam", "utrecht", "the hague", "eindhoven"),
    "IE": ("ireland", "dublin", "cork"),
    "AU": ("australia", "sydney", "melbourne", "brisbane", "perth", "adelaide"),
    "NZ": ("new zealand", "auckland", "wellington"),
    "SG": ("singapore",),
    "AE": ("united arab emirates", "uae", "dubai", "abu dhabi"),
    "SA": ("saudi arabia", "riyadh", "jeddah"),
    "QA": ("qatar", "doha"),
    "FR": ("france", "paris", "lyon"),
    "ES": ("spain", "madrid", "barcelona"),
    "PT": ("portugal", "lisbon", "porto"),
    "IT": ("italy", "milan", "rome"),
    "PL": ("poland", "warsaw", "krakow", "kraków", "wroclaw"),
    "SE": ("sweden", "stockholm"), "DK": ("denmark", "copenhagen"), "NO": ("norway", "oslo"), "FI": ("finland", "helsinki"),
    "CH": ("switzerland", "zurich", "zürich", "geneva"), "AT": ("austria", "vienna"), "BE": ("belgium", "brussels"),
    "CZ": ("czechia", "czech republic", "prague"), "RO": ("romania", "bucharest"), "BG": ("bulgaria", "sofia"),
    "SK": ("slovakia", "bratislava"), "LU": ("luxembourg",), "HU": ("hungary", "budapest"), "GR": ("greece", "athens"),
    "TR": ("turkey", "türkiye", "istanbul"), "UA": ("ukraine", "kyiv"), "CR": ("costa rica", "san josé, costa rica"),
    "JP": ("japan", "tokyo", "osaka"), "KR": ("south korea", "korea", "seoul"), "CN": ("china", "shanghai", "beijing", "shenzhen"),
    "HK": ("hong kong",), "TW": ("taiwan", "taipei"), "PH": ("philippines", "manila", "makati", "cebu", "taguig"),
    "TH": ("thailand", "bangkok"), "MY": ("malaysia", "kuala lumpur"), "ID": ("indonesia", "jakarta"),
    "VN": ("vietnam", "ho chi minh", "hanoi"), "IL": ("israel", "tel aviv"),
    "BR": ("brazil", "são paulo", "sao paulo", "rio de janeiro"), "MX": ("mexico", "mexico city", "guadalajara", "monterrey"),
    "AR": ("argentina", "buenos aires"), "CO": ("colombia", "bogota", "bogotá", "medellin", "medellín"), "CL": ("chile", "santiago"),
    "ZA": ("south africa", "cape town", "johannesburg"), "NG": ("nigeria", "lagos"), "KE": ("kenya", "nairobi"),
    "EG": ("egypt", "cairo"), "PK": ("pakistan", "karachi", "lahore"), "BD": ("bangladesh", "dhaka"),
    "LK": ("sri lanka", "colombo"), "NP": ("nepal", "kathmandu"),
}
_COUNTRY_ABBREV = {"IN": ("ind",), "US": ("usa", "u.s.", "u.s.a.", "united states of america"), "GB": ("uk", "u.k.", "great britain"),
                   "AE": ("uae",), "CZ": ("czech republic",), "KR": ("korea",)}
# Region words a remote posting may use. "*" means anywhere.
_REGIONS: dict[str, tuple[str, ...]] = {
    "*": ("worldwide", "anywhere", "global", "globally", "any location", "international"),
    "APAC": ("apac", "asia pacific", "asia-pacific", "asia"),
    "EMEA": ("emea",), "EU": ("europe", "eu", "european union"), "LATAM": ("latam", "latin america", "south america"),
    "NA": ("north america", "americas"),
}
REGION_MEMBERS: dict[str, set[str]] = {
    "APAC": {"IN", "SG", "AU", "NZ", "JP", "KR", "CN", "HK", "TW", "PH", "TH", "MY", "ID", "VN", "PK", "BD", "LK", "NP"},
    "EMEA": {"GB", "DE", "NL", "IE", "FR", "ES", "PT", "IT", "PL", "SE", "DK", "NO", "FI", "CH", "AT", "BE", "CZ", "RO", "AE",
             "SA", "QA", "IL", "ZA", "NG", "KE", "EG"},
    "EU": {"DE", "NL", "IE", "FR", "ES", "PT", "IT", "PL", "SE", "DK", "FI", "AT", "BE", "CZ", "RO", "BG", "SK", "LU", "HU", "GR"},
    "LATAM": {"BR", "MX", "AR", "CO", "CL"},
    "NA": {"US", "CA", "MX"},
}
REGION_NAMES = {"*": "worldwide", "APAC": "Asia-Pacific", "EMEA": "Europe, Middle East and Africa", "EU": "Europe",
                "LATAM": "Latin America", "NA": "North America"}
_US_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK "
                 "OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())
_CA_PROVINCES = {"ON", "BC", "QC", "AB", "MB", "SK", "NS", "NB", "NL", "PE"}

# Cities written several ways. Keys are lower case; values are the display name.
CITY_CANON: dict[str, str] = {
    "bangalore": "Bengaluru", "bengaluru": "Bengaluru", "bengalūru": "Bengaluru", "gurgaon": "Gurugram", "gurugram": "Gurugram",
    "bombay": "Mumbai", "mumbai": "Mumbai", "new delhi": "New Delhi", "delhi": "Delhi", "delhi ncr": "Delhi NCR", "ncr": "Delhi NCR",
    "noida": "Noida", "madras": "Chennai", "chennai": "Chennai", "calcutta": "Kolkata", "kolkata": "Kolkata",
    "hyderabad": "Hyderabad", "secunderabad": "Hyderabad", "pune": "Pune", "ahmedabad": "Ahmedabad", "kochi": "Kochi",
    "cochin": "Kochi", "trivandrum": "Thiruvananthapuram", "thiruvananthapuram": "Thiruvananthapuram", "mysore": "Mysuru",
    "mysuru": "Mysuru", "mangalore": "Mangaluru", "mangaluru": "Mangaluru", "jaipur": "Jaipur", "chandigarh": "Chandigarh",
    "coimbatore": "Coimbatore", "indore": "Indore", "nagpur": "Nagpur", "navi mumbai": "Navi Mumbai", "thane": "Thane",
    "nyc": "New York", "new york city": "New York", "new york": "New York", "sf": "San Francisco", "bay area": "San Francisco Bay Area",
}
_INDIAN_STATES = {"karnataka", "maharashtra", "telangana", "tamil nadu", "haryana", "kerala", "gujarat", "west bengal",
                  "uttar pradesh", "andhra pradesh", "delhi", "rajasthan", "punjab", "odisha", "madhya pradesh"}

_REMOTE = re.compile(r"\b(remote|work from home|wfh|anywhere|worldwide|distributed|telecommute)\b", re.I)
_PART_SPLIT = re.compile(r"\s*(?:;|\||/|·|•|\bor\b|\band\b|&)\s*", re.I)
_BRACKETS = re.compile(r"\s*[()\[\]]\s*")
_DASH = re.compile(r"\s+[-–]\s+|(?<=[a-z])-\s+|\s+-(?=[A-Z])")
_MODE_WORDS = re.compile(r"\b(hybrid|on[- ]?site|in[- ]office|office|onsite)\b", re.I)
_CODE_PREFIX = re.compile(r"^([A-Z]{2})(?:-([A-Z]{2}))?\s*-\s*(.+)$")
_IN_STATE_CODES = {"KA", "MH", "TN", "TS", "DL", "HR", "UP", "GJ", "KL", "AP", "WB", "RJ", "PB"}


def _contains(text: str, word: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None


def countries_in(text: str | None) -> list[str]:
    """Every country the text names, in order of appearance. Region words are not countries.

    A country written out ("India", "USA", "UK") wins over a city that exists in two countries; a US state or Canadian
    province code ("Dublin, CA") wins over the city, except where the code is also an Indian state abbreviation next to
    an Indian city ("Bangalore, IN", "Chennai, TN")."""
    t = (text or "").lower()
    if not t:
        return []
    explicit: list[tuple[int, str]] = []
    implicit: list[tuple[int, str]] = []
    for code, words in _COUNTRY_WORDS.items():
        named = {COUNTRY_NAMES[code].lower(), *_COUNTRY_ABBREV.get(code, ())}
        for w in words:
            m = re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", t)
            if m:
                (explicit if w in named else implicit).append((m.start(), code))
    for m in re.finditer(r"(?<![A-Za-z])(US|U\.S\.|UK|IND)(?![A-Za-z])", text or ""):  # upper-case only: "us" is a word
        explicit.append((m.start(), {"UK": "GB", "IND": "IN"}.get(m.group(1), "US")))
    if explicit:
        return list(dict.fromkeys(c for _, c in sorted(explicit)))
    codes: list[tuple[int, str]] = []
    for m in re.finditer(r"(?:,|\s-)\s*([A-Z]{2})\b(?!\s*-)", text or ""):  # "Mountain View, CA" / "Toronto, ON"
        st = m.group(1)
        if any(c == "IN" for _, c in implicit) and (st == "IN" or st in _IN_STATE_CODES):
            continue
        code = "US" if st in _US_STATES else "CA" if st in _CA_PROVINCES else None
        if code:
            codes.append((m.start(), code))
    if codes:
        return list(dict.fromkeys(c for _, c in sorted(codes)))
    return list(dict.fromkeys(c for _, c in sorted(implicit)))


def regions_in(text: str | None) -> list[str]:
    t = (text or "").lower()
    return [code for code, words in _REGIONS.items() if any(_contains(t, w) for w in words)]


def infer_country(location: str | None) -> str | None:
    """The single country a location names, or None (unknown, remote-anywhere or several countries)."""
    hits = countries_in(location)
    return hits[0] if len(set(hits)) == 1 else None


@dataclass
class Place:
    display: str | None                     # tidy, consistent text for the UI
    cities: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    remote: bool = False
    # Remote roles only: who may apply. ["*"] anywhere, country/region codes, or None when the posting doesn't say.
    remote_scope: list[str] | None = None
    mode: str | None = None                 # Hybrid / On-site when the location text says so ("Hybrid - Bengaluru")

    @property
    def country(self) -> str | None:
        return self.countries[0] if len(self.countries) == 1 else None


def _tidy(part: str) -> str:
    bits = [b.strip(" .-–") for b in part.split(",")]
    out: list[str] = []
    for b in bits:
        if not b:
            continue
        canon = CITY_CANON.get(b.lower())
        word = canon or (b.title() if b.islower() else b)
        if word.lower() not in (o.lower() for o in out):
            out.append(word)
    return ", ".join(out)


def _with_country(part: str) -> str:
    """"Bengaluru, Karnataka" -> "Bengaluru, India"; "Austin, TX, USA" -> "Austin, TX, United States". A part that names
    no single country is returned as written."""
    pc = set(countries_in(part))
    if len(pc) != 1:
        return part
    code = pc.pop()
    name = COUNTRY_NAMES[code]
    country_words = {name.lower(), code.lower(), *_COUNTRY_ABBREV.get(code, ())}
    bits = [b for b in part.split(", ") if b.lower() not in country_words]
    if code == "IN":
        bits = [b for b in bits if b.lower() not in _INDIAN_STATES and b not in _IN_STATE_CODES] or bits
    return ", ".join([*bits, name]) if bits else name


def _scope_text(scope: list[str]) -> str:
    if scope == ["*"]:
        return "worldwide"
    names = [COUNTRY_NAMES.get(c) or REGION_NAMES.get(c, c) for c in scope]
    return ", ".join(names[:4]) + (f" +{len(names) - 4} more" if len(names) > 4 else "")


def normalize_location(raw: str | None, *, remote_hint: bool = False, restrictions: list[str] | None = None) -> Place:
    """One consistent form of a posting's location. `restrictions` is a source's explicit list of allowed countries."""
    text = " ".join(str(raw or "").split())
    remote = remote_hint or bool(_REMOTE.search(text))
    restricted = [c for r in (restrictions or []) for c in (countries_in(r) or regions_in(r))]
    if not text and not restricted:
        return Place(display="Remote" if remote else None, remote=remote, remote_scope=None)
    countries = list(dict.fromkeys(countries_in(text)))
    regions = [r for r in regions_in(text) if r != "*" or remote]
    cities: list[str] = []
    low = text.lower()
    for alias, canon in CITY_CANON.items():
        if _contains(low, alias) and canon not in cities:
            cities.append(canon)
    if remote:
        scope = list(dict.fromkeys(restricted or countries + [r for r in regions if r != "*"])) or (["*"] if "*" in regions else None)
        display = "Remote" + (f" ({_scope_text(scope)})" if scope else "")
        return Place(display=display, cities=cities, countries=[c for c in (scope or []) if c in COUNTRY_NAMES],
                     remote=True, remote_scope=scope, mode="Remote")
    mode = "Hybrid" if re.search(r"\bhybrid\b", text, re.I) else "On-site" if re.search(r"\b(on[- ]?site|in[- ]office)\b", text, re.I) else None
    parts: list[str] = []
    for piece in _PART_SPLIT.split(_MODE_WORDS.sub(" ", text)):
        piece = _BRACKETS.sub(", ", piece).strip(" ,")
        m = _CODE_PREFIX.match(piece)
        if m and (m.group(1) in COUNTRY_NAMES or m.group(1) == "UK"):  # "IN-Pune", "US-CA-Dublin", "ES - Barcelona"
            name = COUNTRY_NAMES.get(m.group(1), "United Kingdom")
            piece = ", ".join(x for x in (m.group(3), m.group(2), name) if x)
        tidy = _tidy(re.sub(r"^(?:based\s+)?(?:in|at)\s+", "", _DASH.sub(", ", piece), flags=re.I))
        if tidy:
            parts.append(_with_country(tidy))
    display = " · ".join(dict.fromkeys(parts)) or None
    return Place(display=display, cities=cities, countries=countries, remote=False, remote_scope=None, mode=mode)


def remote_open_to(scope: list[str] | None, countries: list[str]) -> bool | None:
    """True/False whether a remote role's scope admits a candidate who may work in `countries`; None when not stated."""
    if not scope:
        return None
    if "*" in scope:
        return True
    want = {c.upper() for c in countries}
    for s in scope:
        if s in want or (s in REGION_MEMBERS and REGION_MEMBERS[s] & want):
            return True
    return False


def describe_scope(scope: list[str] | None) -> str:
    return _scope_text(scope) if scope else "not stated"
