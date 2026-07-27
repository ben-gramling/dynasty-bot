"""§6 waiver tab: claim score = v(add) − v(drop), drop list ascending v, and the
v1 §6.4 bid mechanics verbatim (Waller/Kyler backtests must never move)."""

from __future__ import annotations

import pytest

from core.scoring import waivers as wv
from core.scoring.params import Params


@pytest.fixture(scope="module")
def board(league, me):
    return wv.waiver_board(league, me)


def test_rookie_inventory_split(board, league):
    """59 rookies read-only; 155 true waiver targets."""
    assert len(board["rookie_inventory"]) == 59
    assert len(board["targets"]) == 155
    top = board["rookie_inventory"][0]
    assert top["player"] == "Jeremiyah Love" and top["v"] == 7762
    names = {r["player"] for r in board["targets"]}
    assert "Jeremiyah Love" not in names


def test_board_top_rows(board):
    """§6: claim = v(add) − v(drop); my standing drop is Darren Waller (v = 0),
    so the head of the board is simply the best-valued FAs."""
    rows = {r["player"]: r for r in board["targets"]}
    for name, v in [
        ("Greg Dulcich", 2662),
        ("Ja'Tavion Sanders", 2496),
        ("Jaylin Lane", 2432),
        ("Emanuel Wilson", 2410),
    ]:
        r = rows[name]
        assert r["v"] == v
        assert r["claim"] == v  # drop v = 0
        assert r["drop"] == "Darren Waller"
        assert r["recommended"] is True
        assert r["bid"]["bid"] == 0 and r["bid"]["D"] == 0  # uncontested daily waivers
    assert [r["player"] for r in board["targets"][:4]] == [
        "Greg Dulcich", "Ja'Tavion Sanders", "Jaylin Lane", "Emanuel Wilson",
    ]


def test_claims_sorted_and_positive_recommended(board):
    claims = [r["claim"] for r in board["targets"]]
    assert claims == sorted(claims, reverse=True)
    for r in board["targets"]:
        assert r["recommended"] == (r["claim"] > 0)
        assert r["rank"] >= 1


def test_offseason_board_all_zero_bids(board):
    """Today's board — uncontested daily waivers, every bid $0."""
    assert all(r["bid"]["bid"] == 0 for r in board["targets"])
    assert all(r["bid"]["D"] == 0 for r in board["targets"][:20])


def test_drop_queue(board):
    """§6: actives ascending by v — informational housekeeping."""
    rows = board["drops"]
    head = [(r["player"], r["v"]) for r in rows[:5]]
    assert head == [
        ("Darren Waller", 0.0),
        ("Joe Flacco", 919.0),
        ("Stefon Diggs", 2641.0),
        ("Theo Johnson", 2673.0),
        ("Tank Dell", 3122.0),
    ]
    assert rows[0]["unvalued"] is True
    vs = [r["v"] for r in rows]
    assert vs == sorted(vs)


def test_bid_backtests():
    """§6.4 in-season calibration (verbatim from v1 §13.7):
    Waller wk4 → $63 ($60 actual); Kyler wk11 → $117 ($115)."""
    p = Params()
    assert wv.bid_in_season(p, b_rem=190, dl=2000, d=1, netclaim_raw=99999) == 63
    assert wv.bid_in_season(p, b_rem=200, dl=3500, d=1, netclaim_raw=99999) == 117
    # the 0.65 bankroll clamp binds on desperation bids
    assert wv.bid_in_season(p, b_rem=100, dl=6000, d=2, netclaim_raw=99999) == 65
    # the κ ceiling binds when the claim is not worth the cash
    assert wv.bid_in_season(p, b_rem=200, dl=3500, d=1, netclaim_raw=500) == 20
    # stash-only claims: $0
    assert wv.bid_in_season(p, b_rem=200, dl=0.0, d=2, netclaim_raw=2000) == 0


def test_g_contest_multipliers_load_bearing():
    """§6.4 g(D) = 0.5 / 1.0 / 1.15 must visibly scale the need term when neither
    the κ ceiling nor the bankroll clamp binds (mutating g must fail this)."""
    p = Params()
    # b_rem·dL/k_need = 200·2000/6000 = 66.7 before g
    assert wv.bid_in_season(p, b_rem=200, dl=2000, d=0, netclaim_raw=99999) == 33
    assert wv.bid_in_season(p, b_rem=200, dl=2000, d=1, netclaim_raw=99999) == 67
    assert wv.bid_in_season(p, b_rem=200, dl=2000, d=2, netclaim_raw=99999) == 77
    assert wv.bid_in_season(p, b_rem=200, dl=2000, d=5, netclaim_raw=99999) == 77  # D≥2 bucket


def test_offseason_bid_ladder():
    """§6.4: $0 modal / $1 beats the $0 crowd / min($3, 6%) when contested."""
    p = Params()
    assert wv.bid_offseason(p, budget=50, d=0, netclaim_raw=2500) == 0
    assert wv.bid_offseason(p, budget=50, d=1, netclaim_raw=2500) == 1
    assert wv.bid_offseason(p, budget=50, d=2, netclaim_raw=2500) == 3
    assert wv.bid_offseason(p, budget=50, d=2, netclaim_raw=1000) == 1
    assert wv.bid_offseason(p, budget=100, d=2, netclaim_raw=2500) == 3  # cap $3


def test_rival_demand_uses_live_budgets(league):
    """§6.4 D(a): three rivals are at $0 until the reset; josbaski $44, ronakpatel32 $45."""
    faab = {n: t.faab for n, t in league.teams.items()}
    assert faab["cmgaither43"] == 0 and faab["jaketoppen"] == 0 and faab["millj"] == 0
    assert faab["josbaski"] == 44 and faab["ronakpatel32"] == 45
    assert faab["bengramling"] == 50
