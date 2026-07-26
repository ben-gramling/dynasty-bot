"""§2 lineup model + §13.1/§13.3/§13.4 invariants, pinned to committed fixtures."""

from __future__ import annotations

import pytest

from core.scoring import model as md
from core.scoring import transactions as tx
from core.scoring.lineup import PlayerV, solve
from core.scoring.params import Params

from .conftest import by_name

# §8 / §13.3: the full 12-row expected-lineup-strength table (2026-07-26 snapshot).
EXPECTED_L = {
    "DrewR87": 52418.8,
    "NoahMoell": 51546.0,
    "cmgaither43": 50970.9,
    "joeydavis299": 50491.1,
    "bengramling": 49598.8,
    "jaketoppen": 47214.1,
    "trdouglas": 46552.0,
    "ronakpatel32": 46217.9,
    "millj": 45926.6,
    "josbaski": 44975.3,
    "Jukinski": 42140.3,
    "vishan": 40315.7,
}


def test_solver_reproduces_sleeper_ppts_2025(ppts_fixture, params):
    """§13.1: greedy solver == Sleeper `ppts` for all 12 rosters, weeks 1–14."""
    pos = ppts_fixture["positions"]
    totals: dict[int, float] = {}
    repl = {g: 0.0 for g in ("QB", "RB", "WR", "TE", "FLEX")}
    zero_q = Params(q_qb=0, q_rb=0, q_wr=0, q_te=0, q_flex=0)
    for rows in ppts_fixture["weeks"].values():
        for r in rows:
            pool = [
                PlayerV(sid=pid, name=pid, pos=pos.get(pid, "UNK"), v=pts)
                for pid, pts in r["players_points"].items()
            ]
            lineup = solve(pool, repl, zero_q)
            week_opt = sum(sum(p.v for p in lineup.starters[g]) for g in lineup.starters)
            totals[r["roster_id"]] = totals.get(r["roster_id"], 0.0) + week_opt
    for rid, want in ppts_fixture["ppts_regular_season"].items():
        assert totals[int(rid)] == pytest.approx(want, abs=0.005), f"roster {rid}"


def test_replacement_constants(league):
    """§2.3: 3rd-best non-rookie FA per position."""
    assert league.replacement == {
        "QB": 1562,
        "RB": 2207,
        "WR": 2202,
        "TE": 2372,
        "FLEX": 2372,
    }


def test_my_lineup_and_backups(league, me):
    """§2.4: exact optimal lineup, backups, and L(me) = 49,598.8."""
    lu = me.lineup
    assert [p.name for p in lu.starters["QB"]] == ["Joe Burrow"]
    assert {p.name for p in lu.starters["RB"]} == {"Ashton Jeanty", "Omarion Hampton"}
    assert [p.name for p in lu.starters["WR"]] == ["Alec Pierce", "Jordan Addison", "Mike Evans"]
    assert [p.name for p in lu.starters["TE"]] == ["Sam LaPorta"]
    assert [p.name for p in lu.starters["FLEX"]] == ["Kenneth Walker III", "Javonte Williams"]
    assert {g: b[0] for g, b in lu.backups.items()} == {
        "QB": 919,
        "RB": 3830,
        "WR": 4061,
        "TE": 2673,
        "FLEX": 4061,
    }
    assert round(lu.L, 1) == 49598.8


def test_full_league_l_table(league):
    """§13.3: all 12 L values; offseason pool includes IR (Kittle/Jones counted)."""
    for name, want in EXPECTED_L.items():
        assert round(league.teams[name].L, 1) == want, name


def test_offseason_pool_includes_ir(league):
    jt = league.teams["jaketoppen"]
    pool_names = {p.name for p in jt.pool}
    assert "George Kittle" in pool_names and "Daniel Jones" in pool_names
    act_names = {p.name for p in jt.act}
    assert "George Kittle" not in act_names  # IR is active-cap-exempt


def test_l_monotone_in_additions(league, me):
    """§13.4: L(T ∪ a) ≥ L(T) for any added player."""
    for v in (1, 500, 2000, 4300, 6000, 9999):
        for pos in ("QB", "RB", "WR", "TE"):
            p = PlayerV(sid=f"syn:{pos}:{v}", name="syn", pos=pos, v=v)
            aug = solve(me.pool + [p], league.replacement, league.params)
            assert aug.L >= me.L - 1e-9, (pos, v)


def test_vtt_rv_monotone_in_v(league, me):
    """§13.4: VTT and RV weakly monotone in v, roster held fixed."""
    prev_vtt = None
    for v in (500, 1500, 2500, 3500, 4500, 5500, 7000, 9000):
        p = PlayerV(sid="syn:wr", name="syn", pos="WR", v=v)
        val = tx.vtt(league, me, p)
        if prev_vtt is not None:
            assert val >= prev_vtt - 1e-6, v
        prev_vtt = val
    prev_rv = None
    for target_v in (0, 919, 2641, 2673, 3122, 4061, 4125):
        # synthetic clone of increasing value inserted then removed
        p = PlayerV(sid="syn:rv", name="syn", pos="WR", v=target_v)
        t2 = md.apply_tx(league, me, add_players=[p])
        val = -tx.score_transaction(league, t2, remove_ids=[p.sid]).score
        if prev_rv is not None:
            assert val >= prev_rv - 1e-6, target_v
        prev_rv = val


def test_synthetic_5555_pair(league, me):
    """§2.5: identical 5,555 market price — WR beats QB on this roster."""
    wr = PlayerV(sid="syn:wr5555", name="syn WR", pos="WR", v=5555)
    qb = PlayerV(sid="syn:qb5555", name="syn QB", pos="QB", v=5555)
    res_wr = tx.score_transaction(league, me, add_players=[wr], include_nc=False, include_crunch=False)
    res_qb = tx.score_transaction(league, me, add_players=[qb], include_nc=False, include_crunch=False)
    assert round(res_wr.dl, 1) == 1309.2
    assert round(res_qb.dl, 1) == 278.2
    assert round(res_wr.score, 1) == 3007.5
    assert round(res_qb.score, 1) == 2388.9


def test_real_same_k_pair(league, me):
    """§2.5 regression fixture: Jameson Williams vs Jaxson Dart, both 5,408."""
    jw = by_name(league, "Jameson Williams")
    dart = by_name(league, "Jaxson Dart")
    assert jw.v == 5408 and dart.v == 5408
    res_jw = tx.score_transaction(league, me, add_players=[jw], include_nc=False, include_crunch=False)
    res_dart = tx.score_transaction(league, me, add_players=[dart], include_nc=False, include_crunch=False)
    assert round(res_jw.dl, 1) == 1178.3
    assert round(res_jw.score, 1) == 2870.2
    assert round(res_dart.dl, 1) == 269.3
    assert round(res_dart.score, 1) == 2324.8
    assert res_jw.score > res_dart.score


def test_dl_terms_match_solver_diff(league, me):
    """§12/§13.8: dL_terms sum to ΔL exactly (same computation, not re-derived)."""
    for p in (by_name(league, "Puka Nacua"), by_name(league, "DK Metcalf"), by_name(league, "Anthony Richardson")):
        res = tx.score_transaction(league, me, add_players=[p])
        assert sum(t["delta"] for t in res.terms) == pytest.approx(res.dl, abs=1e-6)


def test_solver_tiebreak_ktc_playerid_asc(params):
    """§2.1: equal-ṽ ties break by KTC playerID ascending — deterministic and
    load-bearing (mutating the tie-break must fail this test)."""
    repl = {g: 0.0 for g in ("QB", "RB", "WR", "TE", "FLEX")}
    hi = PlayerV(sid="s9", name="high id", pos="QB", v=5000, ktc_id=900)
    lo = PlayerV(sid="s1", name="low id", pos="QB", v=5000, ktc_id=7)
    for pool in ([hi, lo], [lo, hi]):  # input order must not matter
        lineup = solve(pool, repl, params)
        assert lineup.starters["QB"][0].name == "low id"
        assert lineup.backups["QB"][1].name == "high id"
    # same rule orders the FLEX competition
    wr_hi = PlayerV(sid="w9", name="wr high", pos="WR", v=4000, ktc_id=500)
    wr_lo = PlayerV(sid="w1", name="wr low", pos="WR", v=4000, ktc_id=3)
    lineup = solve([wr_hi, wr_lo], repl, params)
    assert [p.name for p in lineup.starters["WR"]] == ["wr low", "wr high"]
