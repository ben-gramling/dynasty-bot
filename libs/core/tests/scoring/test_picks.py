"""§1/§3.2 pick pricing: ONE price per pick since v7.5, and never a forecast.

v7.4: CURRENT-YEAR picks price at KTC's own number — the calculator publishes a
price for the exact slot ("2026 Pick 1.01"), so `p == mv == p_me` and there is
nothing to estimate. (v7.0 used the rookie board's n-th-player value as a
stand-in, on the mistaken belief that KTC published no per-pick price; that
proxy missed in both directions.)

v7.6: FUTURE picks price FLAT MID. The no-estimates ruling (v7.5) killed the
projection — `mv` carried a forecast band through v7.4, next-year from the
origin team's `rank_L` and two years out flat Mid — and v7.5 first replaced it
with directional pessimism (Early when I send, Late when I receive). The user
then chose the neutral midpoint instead: every future pick prices at its
round's Mid tranche, whoever owns it, for EVERY consumer — the gate, ΔF, the
deep links, the league tab and the hedge board — so `p == mv == p_me` for
every pick and the price vector is symmetric between seats."""

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


def test_rank_l_no_longer_prices_any_pick(league):
    """§3.2 v7.5, pinned as a negative: the `rank_L` finish projection is
    retired from pricing. Vishan's 2027 1st — the projected 1.01 off rank_L
    12, Early 7,398 on the old market lens — prices Mid 6,118 like every other
    2027 1st, and DrewR87's (rank_L 1, the old Late 5,562) prices the same
    6,118. `band_of_rank_l` itself is gone; `league.rank_l` survives for
    standings only."""
    assert league.rank_l["vishan"] == 12 and league.rank_l["DrewR87"] == 1
    assert not hasattr(pk, "band_of_rank_l")
    jt = league.teams["jaketoppen"]
    vis_r1 = pick_of(jt, 2027, 1, origin_rid=8)
    assert vis_r1.mv == 6118 and vis_r1.band == "Mid"  # not Early 7,398
    drew_r1 = pick_of(league.teams["DrewR87"], 2027, 1)
    assert drew_r1.mv == 6118 and drew_r1.band == "Mid"  # not Late 5,562
    for t in league.teams.values():
        for p in t.picks:
            if p.year != league.current_year:
                assert p.p == p.mv == p.p_me  # one price, every consumer


def test_future_picks_price_flat_mid_for_everyone(league, me):
    """§3.2 v7.6: every future pick prices at its round's Mid tranche —
    whoever owns it, wherever its origin team is projected to finish. The
    price vector is SYMMETRIC: my 2028 2nd and any opponent's are the same
    number, so a same-year same-round pick swap is exactly ΔF 0. (v7.5's
    directional pessimism — Early out / Late in — made that swap a certified
    loss, e.g. −463 on a 2028 2nd; the user chose the midpoint instead.)"""
    tr_ = league.tranches
    for t in league.teams.values():
        for p in t.picks:
            if p.year == league.current_year:
                continue
            assert p.band == p.band_me == "Mid"
            assert p.p == p.mv == p.p_me == tr_[(p.year, "Mid", p.round)]
    vals = sorted((p.round, p.mv) for p in me.picks if p.year == 2028)
    assert vals == [(1, 5207), (2, 3579), (3, 2468), (4, 1759)]
    assert sum(v for _, v in vals) == 13013
    assert sum(p.mv for p in me.picks if p.year == 2027) == 6118 + 4139 + 2036 == 12293
    assert me.picks_mv == sum(p.p_me for p in me.picks) == 41869.86


def test_band_ends_are_carried_but_never_a_price(league, me):
    """§2 v8.2: every future pick carries the ends of KTC's PUBLISHED band —
    `mv_lo` the Late tranche, `mv_hi` the Early — for the reported interval
    ONLY: `p == mv == p_me` stays the flat Mid for every consumer (§11.16).
    Current-year picks have a known slot: both ends equal the price, so
    `mv_hi == mv_lo` ⟺ no swing, by construction."""
    tr_ = league.tranches
    for t in league.teams.values():
        for p in t.picks:
            if p.year == league.current_year:
                assert p.mv_lo == p.mv_hi == p.mv
                continue
            assert p.mv_lo == tr_[(p.year, "Late", p.round)]
            assert p.mv_hi == tr_[(p.year, "Early", p.round)]
            assert p.mv_lo < p.mv < p.mv_hi  # KTC's band brackets its Mid
            assert p.p == p.mv == p.p_me == tr_[(p.year, "Mid", p.round)]
    # pinned widths on the committed snapshot: a 2027 1st swings −556/+1280
    # around Mid 6,118 (the asymmetry is KTC's convexity, not a choice)
    p27 = pick_of(me, 2027, 1)
    assert (p27.mv_lo, p27.mv, p27.mv_hi) == (5562.0, 6118.0, 7398.0)


def test_future_assets(league):
    """F: players at KTC face + picks at the §3.2 one price. v7.6 moved every
    future pick onto the flat Mid tranche, so the league tab's F column is a
    neutral survey again (v7.5 briefly made it my seat's read).
    F(trdouglas) = 58,964 · F(me) = 49,303."""
    assert round(league.teams["trdouglas"].f) == 58964
    assert round(league.teams["bengramling"].f) == 49303
    me_t = league.teams["bengramling"]
    assert round(me_t.f - sum(p.v for p in me_t.taxi)) == 41870


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
