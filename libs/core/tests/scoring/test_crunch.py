"""§4 roster-crunch shadow cost + §13.6 fixtures."""

from __future__ import annotations

from dataclasses import replace as dc_replace

import pytest

from core.scoring import Params
from core.scoring import model as md
from core.scoring import transactions as tx

from .conftest import by_name

# §13.6 cuts vector and §4 C(T) table (2026-07-26, ω per §5.2).
EXPECTED_CRUNCH = {
    "cmgaither43": (3, 2137.6),
    "jaketoppen": (0, 0.0),
    "Jukinski": (4, 5072.6),
    "bengramling": (3, 1400.9),
    "trdouglas": (6, 6379.3),
    "millj": (6, 6570.9),
    "joeydavis299": (4, 3953.2),
    "vishan": (2, 3560.2),
    "josbaski": (2, 1033.5),
    "NoahMoell": (3, 2764.3),
    "DrewR87": (3, 2900.4),
    "ronakpatel32": (0, 0.0),
}


def test_cuts_vector_and_c(league):
    for name, (cuts, c) in EXPECTED_CRUNCH.items():
        t = league.teams[name]
        assert t.cuts == cuts, name
        assert round(t.c, 1) == c, name


def test_my_cut_set(me):
    """C(me) = 1,400.9 with cut set {Waller, Flacco, Diggs}."""
    assert [p.name for p in me.cut_players] == ["Darren Waller", "Joe Flacco", "Stefon Diggs"]
    assert round(me.c, 1) == 1400.9


def test_rv0_values(league, me):
    """§6.2 gross retention values behind the cut list."""
    assert round(me.rv0[by_name(league, "Darren Waller").sid], 1) == 0.0
    assert round(me.rv0[by_name(league, "Joe Flacco").sid], 1) == 344.5
    assert round(me.rv0[by_name(league, "Stefon Diggs").sid], 1) == 1056.4
    assert round(me.rv0[by_name(league, "Theo Johnson").sid], 1) == 1087.3
    assert round(me.rv0[by_name(league, "Tank Dell").sid], 1) == 1248.8


def test_free_option_invariant(league, me):
    """§13.6: Waller→Dulcich swap yields ΔC = +1,064.8 and NetClaim ≈ 0."""
    dulcich = by_name(league, "Greg Dulcich")
    waller = by_name(league, "Darren Waller")
    res = tx.score_transaction(league, me, add_players=[dulcich], remove_ids=[waller.sid])
    assert round(res.dc, 1) == 1064.8
    assert abs(res.score) < 0.05
    raw = tx.score_transaction(
        league, me, add_players=[dulcich], remove_ids=[waller.sid], include_crunch=False
    )
    assert round(raw.score, 1) == 1064.8


def test_c_recomputed_on_post_transaction_roster(league, me):
    """§4: a claimed player landing below the cut line becomes the new marginal cut."""
    richardson = by_name(league, "Anthony Richardson")
    waller = by_name(league, "Darren Waller")
    res = tx.score_transaction(league, me, add_players=[richardson], remove_ids=[waller.sid])
    # Richardson's own RV⁰ (916.5) enters the cut set and Flacco's RV⁰ re-prices
    # to pure wealth (367.6) because Richardson takes the insurance rung.
    assert round(res.score, 1) == -45.8
    assert round(res.dc, 1) == 939.7


def test_c_zero_after_draft_resolves(snapshot, params):
    """§13.6: draft complete ⇒ current-year picks cease to exist ⇒ C = 0 league-wide."""
    done = dc_replace(snapshot, draft={**dict(snapshot.draft), "status": "complete"})
    league2 = md.build_league(done, params)
    for name, t in league2.teams.items():
        assert t.cuts == 0 and t.c == 0.0, name
    assert all(not p.year == league2.current_year for t in league2.teams.values() for p in t.picks)
    assert league2.fa_rookies == []  # rookie inventory section dissolves


def test_crunch_is_omega_aware(league, me):
    """RV⁰ uses each team's own ω: C(me) re-prices when ω moves (§7.4 sensitivity)."""
    cuts5, c5, _ = md.crunch(league, me.pool, me.act, me.lineup, me.picks, me.free_taxi, 0.5)
    cuts7, c7, _ = md.crunch(league, me.pool, me.act, me.lineup, me.picks, me.free_taxi, 0.7)
    assert cuts5 == cuts7 == 3
    assert round(c5, 1) == pytest.approx(1760.7, abs=0.1)
    assert round(c7, 1) == pytest.approx(1041.0, abs=0.1)
