"""§3 pick pricing + §13.5 pick fixtures."""

from __future__ import annotations

import pytest

from core.scoring import picks as pk

from .conftest import pick_of


def test_my_2026_concrete_prices(league, me):
    """§3.2: 1.01 = 7,762 · 2.09 = 3,236 · 3.03 = 2,927 · 4.01 = 1,922."""
    p101 = pick_of(me, 2026, 1)
    p209 = pick_of(me, 2026, 2)
    p303 = pick_of(me, 2026, 3)
    p401 = pick_of(me, 2026, 4)
    assert (p101.p, p101.n) == (7762, 1)
    assert (p209.p, p209.n) == (3236, 21)
    assert (p303.p, p303.n) == (2927, 27)
    assert (p401.p, p401.n) == (1922, 37)
    assert sum(p.p for p in me.picks if p.year == 2026) == 15847


def test_sell_floors(me):
    """§13.5: SellFloor = max(board, tranche)."""
    assert pick_of(me, 2026, 1).sell_floor == 7762  # concrete above Early-1st tranche 6,243
    assert pick_of(me, 2026, 1).mv == 6243
    assert pick_of(me, 2026, 2).sell_floor == 3504  # Late-2nd tranche above rank-21 board
    assert pick_of(me, 2026, 3).sell_floor == 2927
    assert pick_of(me, 2026, 4).sell_floor == 2033


def test_2027_band_projection(league):
    """§3.2: band from ORIGIN owner's rank_L (9–12 E / 5–8 M / 1–4 L)."""
    me_team = league.teams["bengramling"]
    assert league.rank_l["bengramling"] == 5  # → Mid
    assert pick_of(me_team, 2027, 1).p == 6118
    assert pick_of(me_team, 2027, 2).p == 4139
    assert pick_of(me_team, 2027, 4).p == 2036
    jt = league.teams["jaketoppen"]
    own_r1 = pick_of(jt, 2027, 1, origin_rid=2)
    assert own_r1.p == 6118 and own_r1.band == "Mid"  # jaketoppen rank_L 6
    juk_2nd = pick_of(jt, 2027, 2, origin_rid=3)
    assert juk_2nd.p == 4524 and juk_2nd.band == "Early"  # Jukinski rank_L 11
    vis_r1 = pick_of(jt, 2027, 1, origin_rid=8)
    assert vis_r1.p == 7398 and vis_r1.band == "Early"  # vishan rank_L 12


def test_2028_flat_mid(me):
    """§3.2: two years out prices flat Mid — never a monotonic year premium."""
    vals = sorted((p.round, p.p) for p in me.picks if p.year == 2028)
    assert vals == [(1, 5207), (2, 3579), (3, 2468), (4, 1759)]
    assert sum(v for _, v in vals) == 13013


def test_future_assets(league):
    """§13.5: F(trdouglas) = 55,814 · F(me) = 48,586."""
    assert round(league.teams["trdouglas"].f) == 55814
    assert round(league.teams["bengramling"].f) == 48586
    assert round(league.teams["bengramling"].f - sum(p.v for p in league.teams["bengramling"].taxi)) == 41153


def test_all_96_plus_48_picks_price(league):
    """§13.5: every 2026/2027 pick (48 each) + all 48 own 2028 picks price cleanly."""
    counts = {2026: 0, 2027: 0, 2028: 0}
    for t in league.teams.values():
        for p in t.picks:
            assert p.p > 0 and p.mv > 0, p.label
            counts[p.year] += 1
    assert counts == {2026: 48, 2027: 48, 2028: 48}


def test_board_interpolation(league):
    """§13.5: missing board ranks interpolate linearly between neighbors."""
    b54 = pk.board_value(league.board, 54).value
    b55 = pk.board_value(league.board, 55)
    b56 = pk.board_value(league.board, 56).value
    assert b55.interpolated
    assert b55.value == pytest.approx((b54 + b56) / 2)
    b57 = pk.board_value(league.board, 57)
    b61 = pk.board_value(league.board, 61).value
    assert b57.value == pytest.approx(b56 + (b61 - b56) * 1 / 5)
    # no slot ≤ 48 missing today
    assert all(n in league.board for n in range(1, 49))


def test_now_credit(league, me):
    """§3.3: NC(me) = 1,475.9; marginal decomposition 1,406.4 + 69.5 + 0 + 0."""
    assert round(me.nc, 1) == 1475.9
    import core.scoring.model as md

    # leave-one-out marginals
    def nc_without(year, rnd):
        picks = [p for p in me.picks if not (p.year == year and p.round == rnd)]
        return md.now_credit(league, me.pool, me.lineup, picks)

    assert round(me.nc - nc_without(2026, 1), 1) == 1406.4
    assert round(me.nc - nc_without(2026, 2), 1) == 69.5
    assert round(me.nc - nc_without(2026, 3), 1) == 0.0
    assert round(me.nc - nc_without(2026, 4), 1) == 0.0
