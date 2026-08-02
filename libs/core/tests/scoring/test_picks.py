"""§1 pick pricing, TWO LENSES since v7.

`mv` is the MARKET tranche — the number every league-mate sees and the only pick
price the §3 gate may use. `p_me` is MY lens and is what ΔF books: the exact
rookie-board slot price in the current year (the order is known, so no pessimism
is warranted), and a deliberately conservative tranche beyond it — Early for a
pick I own (I would be sending it), Late for one the counterparty owns (I would
be receiving it). The `rank_L` projection survives on `mv` only."""

from __future__ import annotations

import pytest

from core.scoring import picks as pk

from .conftest import pick_of


def test_my_2026_concrete_prices(league, me):
    """Board-slot values: 1.01 = 7,762 · 2.09 = 3,236 · 3.03 = 2,927 ·
    4.01 = 1,922. v7 promoted these from display annotation to MY lens — the
    draft order is known, so the current-year branch prices the slot exactly
    and `p_me == p` in both directions (an opponent's current-year pick is just
    as knowable as mine)."""
    p101 = pick_of(me, 2026, 1)
    p209 = pick_of(me, 2026, 2)
    p303 = pick_of(me, 2026, 3)
    p401 = pick_of(me, 2026, 4)
    assert (p101.p, p101.n) == (7762, 1)
    assert (p209.p, p209.n) == (3236, 21)
    assert (p303.p, p303.n) == (2927, 27)
    assert (p401.p, p401.n) == (1922, 37)
    # v7: the same numbers ARE the my-lens price, and they cut both ways —
    # 1.01 books ABOVE its tranche (7,762 > 6,243) while 2.09 books below
    # (3,236 < 3,504). Exactness, not pessimism, is the current-year rule.
    for p in (p101, p209, p303, p401):
        assert p.p_me == p.p and p.band_me == f"exact slot {p.slot}"
    assert sum(p.p_me for p in me.picks if p.year == 2026) == 15847
    # and an opponent's current-year picks price exactly too
    opp = league.teams["ronakpatel32"]
    for p in opp.picks:
        if p.year == 2026:
            assert p.p_me == p.p and not p.mine


def test_my_2026_tranche_values(me):
    """The mv tranche numbers — the MARKET lens: what the §3 fairness gate,
    favorability and the return denominator use, and the only pick price KTC's
    calculator actually holds. v7 left every one of them untouched."""
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
    """Two years out prices flat Mid on the MARKET lens — never a monotonic
    year premium. My lens takes Early on all four, because they are mine and
    mine is what I would be sending."""
    vals = sorted((p.round, p.mv) for p in me.picks if p.year == 2028)
    assert vals == [(1, 5207), (2, 3579), (3, 2468), (4, 1759)]
    assert sum(v for _, v in vals) == 13013
    mine = sorted((p.round, p.p_me) for p in me.picks if p.year == 2028)
    assert mine == [(1, 5654), (2, 3852), (3, 2618), (4, 1916)]
    assert sum(v for _, v in mine) == 14040


def test_future_picks_price_by_trade_direction_not_by_rank_l(league):
    """§1 v7, the rule the user asked for: future picks book Early when I own
    them and Late when the counterparty does — regardless of what the origin
    team's `rank_L` says the slot will be. The market band still tracks rank_L,
    so the two lenses genuinely disagree in both directions."""
    tr_ = league.tranches
    for name, t in league.teams.items():
        mine = name == league.me
        for p in t.picks:
            if p.year == league.current_year:
                continue
            assert p.band_me == ("Early" if mine else "Late")
            assert p.p_me == tr_[(p.year, p.band_me, p.round)]
    # my own 2027 1st: market calls it Mid (rank_L 5); I book it Early
    own27 = pick_of(league.teams["bengramling"], 2027, 1)
    assert (own27.band, own27.mv) == ("Mid", 6118)
    assert (own27.band_me, own27.p_me) == ("Early", 7398)
    # the league's best pick — vishan's 2027 1st, held by jaketoppen. The market
    # calls it Early off vishan's rank_L 12; if I acquire it I still book Late.
    # This is the deliberate cost of the rule: real signal is discarded in the
    # direction that would flatter me.
    best = pick_of(league.teams["jaketoppen"], 2027, 1, origin_rid=8)
    assert (best.band, best.mv) == ("Early", 7398)
    assert (best.band_me, best.p_me) == ("Late", 5562)
    # my whole future inventory books ABOVE market; every opponent's below
    me_t = league.teams["bengramling"]
    assert sum(p.p_me for p in me_t.picks) == 43972 > round(me_t.picks_mv) == 39921
    for name, t in league.teams.items():
        if name != league.me:
            assert sum(p.p_me for p in t.picks) < t.picks_mv, name


def test_future_assets(league):
    """F at MARKET face tranche: F(trdouglas) = 58,571 · F(me) = 47,354. The
    league tab ranks 12 teams against each other, so it stays on the market
    lens — v7 must not move these (`v_me` has no meaning for a pick moving
    between two teams that aren't me)."""
    assert round(league.teams["trdouglas"].f) == 58571
    assert round(league.teams["bengramling"].f) == 47354
    me_t = league.teams["bengramling"]
    assert round(me_t.f - sum(p.v for p in me_t.taxi)) == 39921  # picks at tranche


def test_all_96_plus_48_picks_price(league):
    """Every 2026/2027 pick (48 each) + all 48 own 2028 picks price cleanly."""
    counts = {2026: 0, 2027: 0, 2028: 0}
    for t in league.teams.values():
        for p in t.picks:
            assert p.p > 0 and p.mv > 0 and p.p_me > 0, p.label
            # every coordinate input stays integral (§11.13f / XTOL rest on it)
            assert p.p_me == int(p.p_me), p.label
            counts[p.year] += 1
    assert counts == {2026: 48, 2027: 48, 2028: 48}


def test_board_interpolation(league):
    """Missing board ranks interpolate linearly between neighbors. v7 promoted
    this from a display path to a SCORED one — board values now enter ΔF — so
    `price_pick` rounds what it takes from here. The final assertion is the
    load-bearing one: nothing in 1..48 interpolates today, so no fractional
    coordinate exists on this snapshot."""
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
