"""KTC parser tests against data/fixtures/ktc_sample.html — real page markup
recorded live on 2026-07-26, trimmed to 3 playersArray records — plus
validation against the full committed data/ktc_raw.json snapshot."""

import copy

import httpx
import pytest

from core import ktc


def test_extract_from_recorded_sample(ktc_sample_html):
    players = ktc.extract_players_array(ktc_sample_html)
    assert [p["playerName"] for p in players] == ["Josh Allen", "Ja'Marr Chase", "Bijan Robinson"]
    josh = players[0]
    assert josh["playerID"] == 365
    assert josh["position"] == "QB"
    assert 0 <= josh["oneQBValues"]["value"] <= 9999
    assert 0 <= josh["superflexValues"]["value"] <= 9999


def test_extract_ignores_other_embedded_arrays(ktc_sample_html):
    # the sample keeps the page's oneQBPlayers embed; the parser must not grab it
    assert "var oneQBPlayers" in ktc_sample_html
    assert len(ktc.extract_players_array(ktc_sample_html)) == 3


def test_extract_bracket_scan_fallback():
    # "];" inside a string defeats the non-greedy regex; the scanner must not
    html = '<script>var playersArray = [{"playerName":"A ]; B","playerID":1}];</script>'
    players = ktc.extract_players_array(html)
    assert players == [{"playerName": "A ]; B", "playerID": 1}]


def test_extract_missing_array_raises():
    with pytest.raises(ktc.KtcError):
        ktc.extract_players_array("<html>nothing here</html>")


def test_validate_accepts_committed_snapshot(ktc_raw):
    ktc.validate(ktc_raw["players"])  # 500 assets, 36 RDP, values in range


def test_validate_rejects_wrong_count(ktc_raw):
    with pytest.raises(ktc.KtcError, match="500"):
        ktc.validate(ktc_raw["players"][:499])


def test_validate_rejects_wrong_rdp_count(ktc_raw):
    assets = copy.deepcopy(ktc_raw["players"])
    next(a for a in assets if a["position"] == "RDP")["position"] = "WR"
    with pytest.raises(ktc.KtcError, match="RDP"):
        ktc.validate(assets)


def test_validate_rejects_out_of_range_value(ktc_raw):
    assets = copy.deepcopy(ktc_raw["players"])
    assets[0]["oneQBValues"]["value"] = 10000
    with pytest.raises(ktc.KtcError, match="oneQBValues"):
        ktc.validate(assets)


def test_fetch_sends_browser_user_agent(ktc_sample_html):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers["User-Agent"]
        seen["url"] = str(request.url)
        return httpx.Response(200, text=ktc_sample_html)

    html = ktc.fetch_html(transport=httpx.MockTransport(handler))
    assert seen["url"] == ktc.URL
    assert seen["ua"] == ktc.USER_AGENT
    assert "Chrome" in seen["ua"]
    assert ktc.extract_players_array(html)


def test_scrape_validates(ktc_sample_html):
    # the 3-record sample must fail the 500-asset guard end-to-end
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=ktc_sample_html))
    with pytest.raises(ktc.KtcError, match="500"):
        ktc.scrape(transport=transport)
