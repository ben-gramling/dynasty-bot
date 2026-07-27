"""§1 pick pricing: tranche = the traded value; concrete board price survives as
a display annotation on current-year picks only."""

from __future__ import annotations

import pytest

from core.scoring import picks as pk

from .conftest import pick_of


def test_my_2026_concrete_prices(league, me):
    """Board-slot values (display annotation): 1.01 = 7,762 · 2.09 = 3,236 ·
    3.03 = 2,927 · 4.01 = 1,922."""
    p101 = pick_of(me, 2026, 1)
    p209 = pick_of(me, 2026, 2)
    p303 = pick_of(me, 2026, 3)
    p401 = pick_of(me, 2026, 4)
    assert (p101.p, p101.n) == (7762, 1)
    assert (p209.p, p209.n) == (3236, 21)
    assert (p303.p, p303.n) == (2927, 27)
    assert (p401.p, p401.n) == (1922, 37)


def test_my_2026_tranche_values(me):
    """The mv tranche numbers — what ΔW and the wealth ledgers actually use (§1)."""
    assert pick_of(me, 2026, 1).mv == 6243  # Early 1st (slot 1)
    assert pick_of(me, 2026, 2).mv == 3504  # Late 2nd (slot 9)
    assert pick_of(me, 2026, 3).mv == 2835  # Early 3rd (slot 3)
    assert pick_of(me, 2026, 4).mv == 2033  # Early 4th (slot 1)
    assert sum(p.mv for p in me.picks if p.year == 2026) == 14615


def test_2027_band_projection(league):
    """Band from ORIGIN owner's rank_L (9–12 E / 5–8 M / 1–4 L); p == mv here."""
    me_team = league.teams["bengramling"]
    assert league.rank_l["bengramling"] == 5  # → Mid
    assert pick_of(me_team, 2027, 1).mv == 6118
    assert pick_of(me_team, 2027, 2).mv == 4139
    assert pick_of(me_team, 2027, 4).mv == 2036
    jt = league.teams["jaketoppen"]
    own_r1 = pick_of(jt, 2027, 1, origin_rid=2)
    assert own_r1.mv == 6118 and own_r1.band == "Mid"  # jaketoppen rank_L 6
    juk_2nd = pick_of(jt, 2027, 2, origin_rid=3)
    assert juk_2nd.mv == 4524 and juk_2nd.band == "Early"  # Jukinski rank_L 11
    vis_r1 = pick_of(jt, 2027, 1, origin_rid=8)
    assert vis_r1.mv == 7398 and vis_r1.band == "Early"  # vishan rank_L 12
    for t in league.teams.values():
        for p in t.picks:
            if p.year != league.current_year:
                assert p.p == p.mv  # only current-year picks carry a separate board price


def test_2028_flat_mid(me):
    """Two years out prices flat Mid — never a monotonic year premium."""
    vals = sorted((p.round, p.mv) for p in me.picks if p.year == 2028)
    assert vals == [(1, 5207), (2, 3579), (3, 2468), (4, 1759)]
    assert sum(v for _, v in vals) == 13013


def test_future_assets(league):
    """F at face tranche: F(trdouglas) = 58,571 · F(me) = 47,354."""
    assert round(league.teams["trdouglas"].f) == 58571
    assert round(league.teams["bengramling"].f) == 47354
    me_t = league.teams["bengramling"]
    assert round(me_t.f - sum(p.v for p in me_t.taxi)) == 39921  # picks at tranche


def test_all_96_plus_48_picks_price(league):
    """Every 2026/2027 pick (48 each) + all 48 own 2028 picks price cleanly."""
    counts = {2026: 0, 2027: 0, 2028: 0}
    for t in league.teams.values():
        for p in t.picks:
            assert p.p > 0 and p.mv > 0, p.label
            counts[p.year] += 1
    assert counts == {2026: 48, 2027: 48, 2028: 48}


def test_board_interpolation(league):
    """Missing board ranks interpolate linearly between neighbors (display path)."""
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
