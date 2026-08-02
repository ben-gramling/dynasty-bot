"""KeepTradeCut dynasty-rankings scraper (docs/keeptradecut.md).

One page fetch with a browser User-Agent returns the full 500-asset dataset
embedded as `var playersArray = [...];` in an inline <script>.
"""

import json
import re

import httpx

URL = "https://keeptradecut.com/dynasty-rankings"
# The two page globals `core.scoring.ktc_picks` needs live on the CALCULATOR
# page, not the rankings page (verified: the rankings HTML carries neither).
TC_URL = "https://keeptradecut.com/trade-calculator"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

EXPECTED_ASSETS = 500
EXPECTED_RDP = 36
VALUE_MIN, VALUE_MAX = 0, 9999

_ARRAY_RE = re.compile(r"var playersArray\s*=\s*(\[.*?\]);", re.DOTALL)

# `LEAGUEYEARPHASE` selects which generator the calculator runs (2 = rookie
# season, the only one we port); `DRAFTYEAR` names the year those picks belong
# to. Cheap insurance against exactly the silent-wrong-number failure the
# numbered-pick work exists to remove.
_PHASE_RE = re.compile(r"\bLEAGUEYEARPHASE\s*=\s*(\d+)")
_DRAFTYEAR_RE = re.compile(r"\bDRAFTYEAR\s*=\s*(\d{4})")


_SITE_JS_RE = re.compile(r'src="(/js/site\.min\.js\?v=[^"]+)"')


def fetch_calculator_globals(
    *, timeout: float = 60.0, transport: httpx.BaseTransport | None = None
) -> dict[str, int]:
    """`{league_year_phase, draft_year}`, or {} if either is unreadable.

    Two GETs, no browser. The constants are NOT in the calculator page's HTML —
    verified — they are top-level assignments in `site.min.js`, whose URL
    carries a cache-busting hash that only the page knows. So: fetch the page,
    read the script src off it, fetch that. ~2 MB, once per collect, and it
    turns "we assume KTC is in rookie-draft phase" into a scraped fact."""
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
        transport=transport,
    ) as client:
        page = client.get(TC_URL)
        page.raise_for_status()
        m = _SITE_JS_RE.search(page.text)
        if not m:
            return {}
        js = client.get(f"https://keeptradecut.com{m.group(1)}")
        js.raise_for_status()
        return extract_calculator_globals(js.text)


def extract_calculator_globals(html: str) -> dict[str, int]:
    """`{league_year_phase, draft_year}` out of `site.min.js`'s text, or {}
    when absent.

    Absent is not an error here — the rankings page is the contract for VALUES
    and these two are a bonus. The caller decides what a missing phase means;
    `ktc_picks` refuses to price without one rather than assuming."""
    out: dict[str, int] = {}
    m = _PHASE_RE.search(html)
    if m:
        out["league_year_phase"] = int(m.group(1))
    m = _DRAFTYEAR_RE.search(html)
    if m:
        out["draft_year"] = int(m.group(1))
    return out


class KtcError(Exception):
    """KTC page fetch/parse/validation failure."""


def fetch_html(*, timeout: float = 60.0, transport: httpx.BaseTransport | None = None) -> str:
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
        transport=transport,
    ) as client:
        resp = client.get(URL)
        resp.raise_for_status()
        return resp.text


def extract_players_array(html: str) -> list[dict]:
    """Parse the embedded playersArray. Non-greedy regex first, bracket-depth
    scanner as fallback in case `];` ever appears inside a string."""
    m = _ARRAY_RE.search(html)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return json.loads(_scan_array(html))


def _scan_array(html: str) -> str:
    start = html.find("var playersArray")
    if start == -1:
        raise KtcError("playersArray not found in page — KTC layout changed?")
    i = html.index("[", start)
    depth, in_str, esc = 0, False, False
    for j in range(i, len(html)):
        c = html[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return html[i : j + 1]
    raise KtcError("unterminated playersArray")


def validate(assets: list[dict]) -> None:
    if len(assets) != EXPECTED_ASSETS:
        raise KtcError(f"expected {EXPECTED_ASSETS} assets, got {len(assets)}")
    rdp = sum(1 for a in assets if a.get("position") == "RDP")
    if rdp != EXPECTED_RDP:
        raise KtcError(f"expected {EXPECTED_RDP} RDP records, got {rdp}")
    for a in assets:
        for fmt in ("oneQBValues", "superflexValues"):
            v = (a.get(fmt) or {}).get("value")
            if not isinstance(v, int) or not VALUE_MIN <= v <= VALUE_MAX:
                raise KtcError(
                    f"bad {fmt}.value {v!r} on playerID {a.get('playerID')!r}"
                )


def scrape(*, transport: httpx.BaseTransport | None = None) -> list[dict]:
    """Fetch, parse and validate; returns the 500-asset list."""
    assets = extract_players_array(fetch_html(transport=transport))
    validate(assets)
    return assets
