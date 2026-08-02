"""§1 pick pricing, TWO LENSES since v7.

v7.4: CURRENT-YEAR picks carry ONE number and it is KTC's own — the calculator
publishes a price for the exact slot ("2026 Pick 1.01"), so `p == mv == p_me`
and there is nothing for a lens to disagree about. (v7.0 used the rookie board's
n-th-player value as a stand-in, on the mistaken belief that KTC published no
per-pick price; that proxy missed in both directions.) FUTURE picks keep the two
lenses, because that is where the slot is genuinely unknown: `mv` is the
`rank_L`-banded tranche the league sees, `p_me` the pessimistic one — Early for a
pick I own (I would be sending it), Late for one the counterparty owns."""

from __future__ import annotations

import pytest

from core.scoring import picks as pk

from .conftest import pick_of


def test_my_2026_picks_are_ktcs_own_numbered_prices(league, me):
    """§1 v7.4. KTC generates a price for every numbered current-year pick and
    `ktc_picks` reproduces it exactly, so a 1.01 is worth what the calculator
    says a 1.01 is worth — no proxy, no band, no lens.

    Note 1.01 is NOT an integer (7,994.86): KTC derives the top two picks off
    the rookie ladder rather than a tranche, and passes the unrounded figure
    into its own adjustment. We pass the same number for the same reason."""
    p101 = pick_of(me, 2026, 1)
    p209 = pick_of(me, 2026, 2)
    p303 = pick_of(me, 2026, 3)
    p401 = pick_of(me, 2026, 4)
    assert (p101.mv, p101.n) == (7994.860000000001, 1)
    assert (p209.mv, p209.n) == (3560.0, 21)
    assert (p303.mv, p303.n) == (2804.0, 27)
    assert (p401.mv, p401.n) == (2205.0, 37)
    # one number: the gate's, the ledger's and mine are the same figure
    for p in (p101, p209, p303, p401):
        assert p.p == p.mv == p.p_me
        assert p.band_me == f"KTC {p.year} Pick {p.round}.{p.slot:02d}"
    assert sum(p.mv for p in me.picks if p.year == 2026) == 16563.86
    # an opponent's current-year picks price identically — the slot is as
    # knowable for them as for me, and KTC quotes one price per slot
    for p in league.teams["ronakpatel32"].picks:
        if p.year == 2026:
            assert p.p == p.mv == p.p_me and not p.mine


def test_the_generic_2026_tranche_is_no_longer_a_price(league, me):
    """The 36 generic tranches are still scraped and still price FUTURE years,
    but no current-year pick is valued at one any more. Pinned as a negative,
    because reverting to the tranche is precisely the silent failure that made
    our gate disagree with the counterparty's screen."""
    tr_ = league.tranches
    assert tr_[(2026, "Early", 1)] == 6243  # still there, still scraped
    for p in me.picks:
        if p.year != 2026:
            continue
        assert p.mv != tr_[(2026, p.band, p.round)]
        # and the band survives only as a label on the slot
        assert p.band == pk.band_of_slot(p.slot)


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
    # my FUTURE inventory books above market and every opponent's below; the
    # current-year picks are identical on both lenses and so cancel out of the
    # comparison entirely (v7.4)
    me_t = league.teams["bengramling"]
    assert sum(p.p_me for p in me_t.picks) == 44688.86 > me_t.picks_mv == 41869.86
    for name, t in league.teams.items():
        cy = [p for p in t.picks if p.year == league.current_year]
        assert all(p.p_me == p.mv for p in cy)
        if name != league.me:
            assert sum(p.p_me for p in t.picks) < t.picks_mv, name


def test_future_assets(league):
    """F at market face: F(trdouglas) = 58,233 · F(me) = 49,303. The league tab
    ranks 12 teams against each other so it stays on the MARKET lens — but v7.4
    moved that lens for current-year picks (KTC's numbered price replaced the
    generic tranche), so these numbers moved with it."""
    assert round(league.teams["trdouglas"].f) == 58233
    assert round(league.teams["bengramling"].f) == 49303
    me_t = league.teams["bengramling"]
    assert round(me_t.f - sum(p.v for p in me_t.taxi)) == 41870  # picks at market


def test_all_96_plus_48_picks_price(league):
    """Every 2026/2027 pick (48 each) + all 48 own 2028 picks price cleanly."""
    counts = {2026: 0, 2027: 0, 2028: 0}
    fractional: list[str] = []
    for t in league.teams.values():
        for p in t.picks:
            assert p.p > 0 and p.mv > 0 and p.p_me > 0, p.label
            if p.p_me != int(p.p_me):
                fractional.append(p.label)
            counts[p.year] += 1
    assert counts == {2026: 48, 2027: 48, 2028: 48}
    # §11.13f / XTOL lean on integral coordinates. v7.4 admits exactly two
    # exceptions, and they are KTC's, not ours: the calculator derives 1.01 and
    # 1.02 off the rookie ladder and passes the unrounded figure into its own
    # adjustment, so matching it means carrying the fraction. XTOL (1e-6)
    # absorbs a hundredth; rounding would put us off KTC's number.
    assert sorted(set(fractional)) == ["2026 1.01", "2026 1.02"]


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
