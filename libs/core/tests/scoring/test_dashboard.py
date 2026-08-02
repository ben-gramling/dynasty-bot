"""The v7.1 per-counterparty hedge dashboard: payload shape and the standalone
HTML render. Fixtures only — the payload is built from the committed snapshot
through the same `find_spreads` the CLI calls.

`core.dashboard` lives outside `core.scoring` (it is presentation, not spec),
but its test lives here because it needs the session-scoped `league` fixture
and the leg-table cache that the scoring conftest already provides."""

from __future__ import annotations

import re

import pytest

from core import dashboard as dash


@pytest.fixture(scope="module")
def payload(league, tmp_path_factory) -> dict:
    """One counterparty search per opponent. `workers=1` keeps it in-process:
    the parallel path is a wall-clock optimisation, not a behaviour change, and
    forking under pytest buys nothing but flakiness."""
    return dash.hedge_payload(
        league,
        # the fair window with a HIGH return bar and a tiny top: the sound k5
        # break bites hard at 6%, which keeps eleven exhaustive searches inside
        # a sane test budget while still leaving every team something to rank
        sliders={"min_return": 6.0, "favor_min": -5.0, "favor_max": 5.0, "top": 2},
        cache_dir=tmp_path_factory.mktemp("finder-cache"),
        workers=1,
        generated_at="2026-08-02 12:00 UTC",
        data_age="0.2h old",
    )


def test_every_counterparty_gets_a_section(payload, league):
    """One entry per opponent, in a deterministic order, me excluded — a team
    with nothing to show still appears, because "nothing here" is the answer
    the desk needs about that team."""
    names = [t["name"] for t in payload["teams"]]
    assert names == sorted(league.opponents)
    assert league.me not in names
    assert payload["totals"]["teams"] == len(league.opponents) == 11


def test_the_named_team_is_actually_on_one_of_the_legs(payload):
    """A hedge has TWO counterparties. `their_side` says which leg belongs to
    the team the section is filed under, and `partner` names the other — get
    this wrong and the page attributes trades to the wrong manager."""
    seen_buy = seen_sell = False
    for team in payload["teams"]:
        for sp in team["spreads"]:
            side = sp["their_side"]
            assert side in ("buy", "sell")
            assert sp[side]["counterparty"] == team["name"]
            other = "sell" if side == "buy" else "buy"
            assert sp[other]["counterparty"] == sp["partner"] != team["name"]
            seen_buy |= side == "buy"
            seen_sell |= side == "sell"
    assert seen_buy and seen_sell  # both orientations really occur


def test_hedges_are_count_neutral_verdict_true_and_maximin_ordered(payload):
    """The §5 unit and the §2 ranking, straight from the finder — the dashboard
    re-derives nothing, so these hold by construction and this pins that."""
    for team in payload["teams"]:
        for sp in team["spreads"]:
            assert sp["net_players"] == 0 and sp["net_picks"] == 0
            assert sp["verdict"] is True
            assert sp["floor"] == min(sp["coords"]["dS"], sp["coords"]["dF"])
            assert sp["ceiling"] == max(sp["coords"]["dS"], sp["coords"]["dF"])
            assert sp["return_robust"] >= payload["sliders"]["min_return"]
            # the favor window is the fair band on BOTH legs (v5.0.1 push-down)
            for leg in ("buy", "sell"):
                assert -5.0 <= sp["favor"][leg] <= 5.0
        # maximin is on the floor-based RETURN (floor ÷ Σ face sent), not the
        # raw floor — a smaller floor on a much smaller package outranks a
        # bigger one, which is the whole point of ranking on inventory deployed
        rets = [s["return_robust"] for s in team["spreads"]]
        assert rets == sorted(rets, reverse=True)


def test_scoping_to_one_counterparty_is_exhaustive(payload):
    """§4a v6: `with_team` pushes down into the crossing, so a per-counterparty
    run completes rather than saturating. If this ever flips to False the
    tallies become floors and the page must say so — which it does, but the
    point of the per-counterparty split is that it should not have to."""
    assert payload["totals"]["all_exact"] is True
    assert all(t["exact"] for t in payload["teams"])
    assert payload["totals"]["matched"] > 0


def test_render_is_standalone_and_escapes(payload):
    """The artifact CSP blocks every external request, so the page must carry
    no src/href to anywhere and no script at all."""
    page = dash.render_html(payload)
    assert "<script" not in page.lower()
    assert not re.search(r'\b(src|href)\s*=\s*"(?!#)', page)
    assert "http://" not in page and "https://" not in page
    # no <html>/<head>/<body> — the artifact harness supplies the skeleton.
    # Matched as complete tags: `<header>` is ours and must not trip this.
    assert not re.search(r"<\s*(!doctype|html|head|body)\b", page, re.I)
    # every team is a section, and the disclosure works without JS
    for team in payload["teams"]:
        assert f">{team['name']}</h2>" in page
    assert page.count("<details class=\"hedge\">") == sum(
        len(t["spreads"]) for t in payload["teams"]
    )


def test_render_uses_the_ledger_conventions(payload):
    """docs/web-design.md: red is ONLY a negative number (or the star), the
    minus is a true U+2212, and both themes are defined at token level."""
    page = dash.render_html(payload)
    assert "--star:#C8102E" in page and "--sky:#A8D8F0" in page  # flag palette
    assert "prefers-color-scheme:dark" in page
    assert ':root[data-theme="dark"]' in page and ':root[data-theme="light"]' in page
    assert "green" not in page.lower()  # positives are ink, never a traffic light
    assert 'class="chip-k">' in page
    # Every hedge on this page is verdict-true (both coordinates >= 0), so a
    # real board is almost all positives — which is exactly why the negative
    # styling has to be exercised deliberately rather than assumed present.
    assert dash._num(-1234) == "\u22121,234"  # true minus U+2212, not a hyphen
    assert dash._num(1234, signed=True) == "+1,234"
    assert 'class="chip-v neg">\u2212250</span>' in dash._chip("face", -250)
    assert "neg" not in dash._chip("face", 250)  # positives never wear it
    # and favor is deliberately NOT a ledger number: negative favor is GOOD for
    # us, so it never takes the red, it says the direction in words instead
    assert dash._favor_chip(-4.6) == dash._favor_chip(-4.6).replace("neg", "")
    assert "4.6 to you" in dash._favor_chip(-4.6)
    assert "4.6 to them" in dash._favor_chip(4.6)
    assert "even" in dash._favor_chip(0.0)


def test_slider_echo_survives_into_the_page(payload):
    page = dash.render_html(payload)
    assert "guaranteed floor" in page
    assert "0.2h old" in page and "2026-08-02 12:00 UTC" in page
    assert "min return" in page and "favor" in page


def test_html_escaping_of_asset_names():
    """Names come from KTC and Sleeper; a stray angle bracket must not become
    markup. Built by hand so the case exists regardless of the fixture."""
    nasty = '<script>alert("x")</script> & Co.'
    payload = {
        "me": "bengramling",
        "generated_at": None,
        "data_age": None,
        "sliders": dict(dash._SLIDER_DEFAULTS),
        "totals": {"teams": 1, "with_hedges": 1, "matched": 1, "all_exact": True},
        "teams": [
            {
                "name": nasty,
                "market": {
                    "posture": "BUYER",
                    "holes": [{"pos": "WR", "rank": 10}],
                    "pick_inventory": {"count": 3, "value": 9000},
                    "faab": 50,
                },
                "counts": {"matched": 1},
                "exact": True,
                "constraints": [],
                "spreads": [],
            }
        ],
    }
    page = dash.render_html(payload)
    assert "<script>" not in page
    assert "&lt;script&gt;" in page and "&amp; Co." in page
