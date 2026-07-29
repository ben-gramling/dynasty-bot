"""§7 lineup-strength model (kept machinery: solver + replacement anchors),
pinned to committed fixtures. Lineup numbers feed the league tab and the
in-season FAAB formula only — never the trade path (§11.2)."""

from __future__ import annotations

import pytest

from core.scoring import model as md
from core.scoring.lineup import PlayerV, diff_terms, solve
from core.scoring.params import Params

from .conftest import by_name

# The full 12-row expected-lineup-strength table (2026-07-26 snapshot).
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
    """Greedy solver == Sleeper `ppts` for all 12 rosters, weeks 1–14."""
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
    """3rd-best non-rookie FA per position."""
    assert league.replacement == {
        "QB": 1562,
        "RB": 2207,
        "WR": 2202,
        "TE": 2372,
        "FLEX": 2372,
    }


def test_my_lineup_and_backups(league, me):
    """Exact optimal lineup, backups, and L(me) = 49,598.8."""
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
    """All 12 L values; offseason pool includes IR (Kittle/Jones counted)."""
    for name, want in EXPECTED_L.items():
        assert round(league.teams[name].L, 1) == want, name


def test_offseason_pool_includes_ir(league):
    jt = league.teams["jaketoppen"]
    pool_names = {p.name for p in jt.pool}
    assert "George Kittle" in pool_names and "Daniel Jones" in pool_names
    act_names = {p.name for p in jt.act}
    assert "George Kittle" not in act_names  # IR is active-cap-exempt


def test_taxi_not_lineup_eligible(league, me):
    """Taxi players are lineup-ineligible — Cam Ward is future stash, not QB insurance."""
    assert "Cam Ward" in {p.name for p in me.taxi}
    assert "Cam Ward" not in {p.name for p in me.pool}
    assert me.lineup.backups["QB"][0] == 919  # Flacco, not Ward


def test_l_monotone_in_additions(league, me):
    """L(T ∪ a) ≥ L(T) for any added player."""
    for v in (1, 500, 2000, 4300, 6000, 9999):
        for pos in ("QB", "RB", "WR", "TE"):
            p = PlayerV(sid=f"syn:{pos}:{v}", name="syn", pos=pos, v=v)
            aug = solve(me.pool + [p], league.replacement, league.params)
            assert aug.L >= me.L - 1e-9, (pos, v)


def test_flacco_worse_than_free_insurance(league, me):
    """Removing Flacco RAISES L (FA line 1,562 > his 919); streaming Richardson
    adds +75.5 — lineup facts for the league tab, not trade inputs."""
    flacco = by_name(league, "Joe Flacco")
    without = solve([p for p in me.pool if p.sid != flacco.sid], league.replacement, league.params)
    assert round(without.L - me.L, 1) == 38.6
    richardson = by_name(league, "Anthony Richardson")
    aug = solve(me.pool + [richardson], league.replacement, league.params)
    assert round(aug.L - me.L, 1) == 75.5


def test_positional_bars_differ(league, me):
    """A new WR enters over Evans 4,125; a new RB must clear Javonte to start —
    and the synthetic 5,555 pair quantifies it (WR +1,309.2 vs QB +278.2)."""
    wr = PlayerV(sid="s1", name="s", pos="WR", v=4500)
    rb = PlayerV(sid="s2", name="s", pos="RB", v=4500)
    aug_wr = solve(me.pool + [wr], league.replacement, league.params)
    aug_rb = solve(me.pool + [rb], league.replacement, league.params)
    assert "s1" in {p.sid for g in ("WR", "FLEX") for p in aug_wr.starters[g]}
    assert "s2" not in {p.sid for g in ("RB", "FLEX") for p in aug_rb.starters[g]}
    wr5 = PlayerV(sid="syn:wr5555", name="syn WR", pos="WR", v=5555)
    qb5 = PlayerV(sid="syn:qb5555", name="syn QB", pos="QB", v=5555)
    assert round(solve(me.pool + [wr5], league.replacement, league.params).L - me.L, 1) == 1309.2
    assert round(solve(me.pool + [qb5], league.replacement, league.params).L - me.L, 1) == 278.2


def test_real_same_k_pair(league, me):
    """Regression fixture: Jameson Williams vs Jaxson Dart, both 5,408 — the
    lineup lens separates them (league-tab context only)."""
    jw = by_name(league, "Jameson Williams")
    dart = by_name(league, "Jaxson Dart")
    assert jw.v == 5408 and dart.v == 5408
    dl_jw = solve(me.pool + [jw], league.replacement, league.params).L - me.L
    dl_dart = solve(me.pool + [dart], league.replacement, league.params).L - me.L
    assert round(dl_jw, 1) == 1178.3
    assert round(dl_dart, 1) == 269.3


def test_dl_terms_match_solver_diff(league, me):
    """diff_terms sums to ΔL exactly (same computation, not re-derived)."""
    for p in (by_name(league, "Puka Nacua"), by_name(league, "DK Metcalf")):
        aug = solve(me.pool + [p], league.replacement, league.params)
        terms = diff_terms(me.lineup, aug, league.params, league.replacement)
        assert sum(t["delta"] for t in terms) == pytest.approx(aug.L - me.L, abs=1e-6)


def test_availability_scales_lineup_never_wealth(league, me):
    """u scales the lineup solver only — the trade coordinates bank full v."""
    hurt = PlayerV(sid="syn:hurt", name="hurt", pos="WR", v=6000, u=0.25)
    t2 = md.apply_tx(league, me, add_players=[hurt])
    assert t2.players_v_sum - me.players_v_sum == 6000  # full v banked
    assert t2.L - me.L < 1000  # but the lineup sees 1,500 effective


def test_unvalued_player(league, me):
    """Waller v = 0, flagged, never imputed; exactly one such player."""
    waller = by_name(league, "Darren Waller")
    assert waller.v == 0 and waller.unvalued
    all_unvalued = [
        p for t in league.teams.values() for p in t.pool + t.taxi if p.unvalued
    ]
    assert len(all_unvalued) == 1


def test_solver_tiebreak_ktc_playerid_asc(params):
    """Equal-ṽ ties break by KTC playerID ascending — deterministic and
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
