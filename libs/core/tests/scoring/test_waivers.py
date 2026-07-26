"""§6 waiver tab + §11.1 worked example + §13.7 bid backtests."""

from __future__ import annotations

import pytest

from core.scoring import waivers as wv
from core.scoring.params import Params


@pytest.fixture(scope="module")
def board(league, me):
    return wv.waiver_board(league, me)


def test_rookie_inventory_split(board, league):
    """§6.1: 59 rookies read-only; 155 true waiver targets."""
    assert len(board["rookie_inventory"]) == 59
    assert len(board["targets"]) == 155
    top = board["rookie_inventory"][0]
    assert top["player"] == "Jeremiyah Love" and top["v"] == 7762
    names = {r["player"] for r in board["targets"]}
    assert "Jeremiyah Love" not in names


def test_board_top_rows(board):
    """§6.1 current top of the board: free-option TE/WR/RB rows at NetClaim 0."""
    rows = {r["player"]: r for r in board["targets"]}
    for name, v, raw in [
        ("Greg Dulcich", 2662, 1064.8),
        ("Ja'Tavion Sanders", 2496, 998.4),
        ("Jaylin Lane", 2432, 972.8),
        ("Emanuel Wilson", 2410, 964.0),
    ]:
        r = rows[name]
        assert r["v"] == v
        assert abs(r["netclaim"]) < 0.05
        assert r["netclaim_raw"] == raw
        assert r["drop"] == "Darren Waller"
        assert r["free_option"] and r["recommended"]
        assert r["bid"]["bid"] == 0 and r["bid"]["D"] == 0
    assert [r["player"] for r in board["targets"][:4]] == [
        "Greg Dulcich", "Ja'Tavion Sanders", "Jaylin Lane", "Emanuel Wilson",
    ]


def test_richardson_row_and_queue(board):
    """§6.1: Richardson is the ΔL > 0 QB2 row — NetClaim −45.8 today, queued
    post-draft at ≈ +549 (swap for Flacco once the crunch clears)."""
    r = next(x for x in board["targets"] if x["player"] == "Anthony Richardson")
    assert r["dL"] == 75.5
    assert r["netclaim"] == -45.8
    assert r["netclaim_raw"] == 893.9
    assert not r["recommended"]
    q = next(x for x in board["queued"] if x["player"] == "Anthony Richardson")
    assert q["drop"] == "Joe Flacco"
    assert q["score_post_draft"] == 548.9


def test_dulcich_claim_decomposition(board):
    """§11.1: the three labeled components of the free-option claim."""
    r = next(x for x in board["targets"] if x["player"] == "Greg Dulcich")
    side = r["sides"]["me"]
    assert side["lineup_weighted"] == 0.0
    assert side["wealth_weighted"] == 1064.8
    assert side["crunch_term"] == -1064.8
    assert side["crunch"]["cuts_before"] == 3 and side["crunch"]["cuts_after"] == 3
    assert r["bid"] == {
        "mode": "offseason", "D": 0, "netclaim": 0.0, "netclaim_raw": 1064.8,
        "ceiling": 42.6, "clamp": None, "bid": 0,
    }
    # audit trail: the two 9-row lineup tables ship with the card
    tables = r["audit"]["lineup_tables"]
    assert len(tables["before"]) == 9 and len(tables["after"]) == 9


def test_offseason_board_all_zero_bids(board):
    """§13.7: today's board — uncontested daily waivers, every bid $0."""
    assert all(r["bid"]["bid"] == 0 for r in board["targets"])
    assert all(r["bid"]["D"] == 0 for r in board["targets"][:20])


def test_drop_queue(board):
    """§6.2: actives ascending by crunch-aware RV with gross RV⁰ alongside."""
    rows = board["drops"]
    head = [(r["player"], r["rv"], r["rv0"]) for r in rows[:5]]
    assert head == [
        ("Darren Waller", 0.0, 0.0),
        ("Stefon Diggs", 0.0, 1056.4),
        ("Joe Flacco", 11.6, 344.5),
        ("Theo Johnson", 30.9, 1087.3),
        ("Tank Dell", 192.4, 1248.8),
    ]
    waller = rows[0]
    assert waller["scheduled_cut"] and waller["unvalued"]
    diggs = rows[1]
    assert diggs["scheduled_cut"]
    # DROP_FLOOR: anything with RV⁰ > 2,500 requires explicit confirm
    assert all(r["require_confirm"] == (r["rv0"] > 2500) for r in rows)
    # §12: DROP rows share the decomposition schema (sides/dL_terms/audit)
    for r in rows:
        side = r["sides"]["me"]
        assert {"omega", "dL", "dNC", "dA", "dC", "score", "dL_terms", "crunch"} <= set(side)
        assert r["rv"] == -side["score"]
        tables = r["audit"]["lineup_tables"]
        assert len(tables["before"]) == 9 and len(tables["after"]) == 9


def test_bid_backtests():
    """§13.7 in-season calibration: Waller wk4 → $63 ($60 actual); Kyler wk11 → $117 ($115)."""
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
    """§6.3: three rivals are at $0 until the reset; josbaski $44, ronakpatel32 $45."""
    faab = {n: t.faab for n, t in league.teams.items()}
    assert faab["cmgaither43"] == 0 and faab["jaketoppen"] == 0 and faab["millj"] == 0
    assert faab["josbaski"] == 44 and faab["ronakpatel32"] == 45
    assert faab["bengramling"] == 50
