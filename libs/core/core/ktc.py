"""KeepTradeCut dynasty-rankings scraper (docs/keeptradecut.md).

One page fetch with a browser User-Agent returns the full 500-asset dataset
embedded as `var playersArray = [...];` in an inline <script>.
"""

import json
import re

import httpx

URL = "https://keeptradecut.com/dynasty-rankings"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

EXPECTED_ASSETS = 500
EXPECTED_RDP = 36
VALUE_MIN, VALUE_MAX = 0, 9999

_ARRAY_RE = re.compile(r"var playersArray\s*=\s*(\[.*?\]);", re.DOTALL)


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
