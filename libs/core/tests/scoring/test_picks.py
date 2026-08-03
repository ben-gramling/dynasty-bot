"""§1/§3.2 pick pricing: ONE price per pick since v7.5, and never a forecast.

v7.4: CURRENT-YEAR picks price at KTC's own number — the calculator publishes a
price for the exact slot ("2026 Pick 1.01"), so `p == mv == p_me` and there is
nothing to estimate. (v7.0 used the rookie board's n-th-player value as a
stand-in, on the mistaken belief that KTC published no per-pick price; that
proxy missed in both directions.)

v7.5: FUTURE picks lose the projection entirely. Through v7.4 `mv` carried a
forecast band — next-year from the origin team's `rank_L`, two years out flat
Mid — and only my lens (`p_me`) was pessimistic. The user's ruling: NEVER
estimate where a future pick lands within its round; ALWAYS assume the bad end
in the direction the asset would travel — Early for a pick I own (I would be
sending it), Late for one anyone else owns (I would be receiving it). That
pessimistic tranche is now the ONLY price: the gate, the deep links, the board
and ΔF all read the same number, and `p == mv == p_me` for every pick."""

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
    retired from pricing. My 2027 picks price Early although my rank_L is 5
    (the old projection said Mid), and vishan's 2027 1st — the projected 1.01
    off rank_L 12, Early 7,398 on the old market lens — prices Late 5,562 in
    the hands of the team I would buy it from. `band_of_rank_l` itself is gone;
    `league.rank_l` survives for standings only."""
    assert league.rank_l["bengramling"] == 5  # the forecast still exists...
    me_team = league.teams["bengramling"]
    assert pick_of(me_team, 2027, 1).mv == 7398  # ...and prices nothing
    assert pick_of(me_team, 2027, 2).mv == 4524
    assert pick_of(me_team, 2027, 4).mv == 2163
    assert not hasattr(pk, "band_of_rank_l")
    jt = league.teams["jaketoppen"]
    vis_r1 = pick_of(jt, 2027, 1, origin_rid=8)
    assert vis_r1.mv == 5562 and vis_r1.band == "Late"  # vishan rank_L 12
    for t in league.teams.values():
        for p in t.picks:
            if p.year != league.current_year:
                assert p.p == p.mv == p.p_me  # one price, every consumer


def test_2028_prices_by_direction_not_flat_mid(me):
    """Two years out used to price flat Mid on the market lens; v7.5 prices it
    like every future year — mine Early, because mine is what I would send."""
    vals = sorted((p.round, p.mv) for p in me.picks if p.year == 2028)
    assert vals == [(1, 5654), (2, 3852), (3, 2618), (4, 1916)]
    assert sum(v for _, v in vals) == 14040


def test_future_picks_price_by_trade_direction(league):
    """§1 the v7.5 rule: future picks price Early when I own them and Late when
    anyone else does — regardless of what the origin team's finish suggests,
    and for EVERY consumer (the band and the price are one field now)."""
    tr_ = league.tranches
    for name, t in league.teams.items():
        mine = name == league.me
        for p in t.picks:
            if p.year == league.current_year:
                continue
            assert p.band == p.band_me == ("Early" if mine else "Late")
            assert p.p == p.mv == p.p_me == tr_[(p.year, p.band, p.round)]
    # my own 2027 1st books Early although rank_L 5 projected Mid (6,118)
    own27 = pick_of(league.teams["bengramling"], 2027, 1)
    assert (own27.band, own27.mv) == ("Early", 7398)
    # the league's best pick — vishan's 2027 1st, held by jaketoppen: the old
    # market lens called it Early 7,398 off vishan's rank_L 12; if I acquire it
    # I pay Late. This is the deliberate cost of the rule: real signal is
    # discarded in the direction that would flatter me.
    best = pick_of(league.teams["jaketoppen"], 2027, 1, origin_rid=8)
    assert (best.band, best.mv) == ("Late", 5562)
    # my FUTURE inventory prices above everyone's identical inventory: same
    # (year, round) multiset as any full set, dearer band on every future pick
    me_t = league.teams["bengramling"]
    assert me_t.picks_mv == sum(p.p_me for p in me_t.picks) == 44688.86
    for name, t in league.teams.items():
        cy = [p for p in t.picks if p.year == league.current_year]
        assert all(p.p_me == p.mv for p in cy)
        if name != league.me:
            future = [p for p in t.picks if p.year != league.current_year]
            assert all(p.band == "Late" for p in future), name


def test_future_assets(league):
    """F: players at KTC face + picks at the §3.2 price. v7.5 moved every
    future pick onto the pessimistic tranche, so the league tab's F column
    moved with it: my picks read Early (dear), everyone else's Late (cheap).
    F(trdouglas) = 56,322 · F(me) = 52,122."""
    assert round(league.teams["trdouglas"].f) == 56322
    assert round(league.teams["bengramling"].f) == 52122
    me_t = league.teams["bengramling"]
    assert round(me_t.f - sum(p.v for p in me_t.taxi)) == 44689


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
