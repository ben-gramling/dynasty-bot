"""§11 implementation invariants (v4, amended v7): market-face conservation
(exact per leg) and the my-lens split that stops the two REPORTED ΔFs from
negating (§11.1b), the per-side two-coordinate score (ΔS, ΔF), independence
from the lineup model, import graph, bundles, exclusivity, legality,
determinism, runtime.

Pins computed from the COMMITTED fixtures (see test_trades docstring)."""

from __future__ import annotations

import ast
import json
import random
import time
from dataclasses import replace as dc_replace
from itertools import combinations
from pathlib import Path

import pytest

from core.scoring import Params, compute_all
from core.scoring import lineup as ln
from core.scoring import model as md
from core.scoring import trades as tr

from .conftest import board_legs

SCORING = Path(tr.__file__).resolve().parent


def _pv_inv(name: str, pos: str, v: float, i: int) -> ln.PlayerV:
    return ln.PlayerV(sid=f"synv:{i}", name=name, pos=pos, v=float(v), ktc_id=i)


# --------------------------- 1. face conservation + the per-side coordinates


def test_face_transfer_conserved_per_leg(board, league):
    """§11.1 as restored by v7.5: face transfers exactly on EVERY leg — each
    asset carries the same `v` on both rosters, there is only one price vector
    (`v_me == v` for every asset), so `ΔF(me) == −ΔF(them)` with no wedge and
    no lens split. The pick-bearing legs are the load-bearing witnesses: under
    v7 they were exactly where the two printed ΔFs did NOT negate."""
    canonical = {
        a.key: (a.v, a.v_me)
        for t in league.teams.values()
        for a in tr.team_assets(league, t).values()
    }
    saw_pick_leg = False
    for card in board_legs(board):
        for a in card["give"] + card["get"]:
            v, v_me = canonical[a["key"]]
            assert v == v_me, (card["id"], a["name"])  # v7.5: one price
            assert a["v"] == round(v), (card["id"], a["name"])
            assert "v_me" not in a, (card["id"], a["name"])  # tripwire silent
        # The card DISPLAYS integers; the coordinates use the real numbers, and
        # v7.4 made two of them fractional because KTC's own are (it derives
        # 2026 1.01/1.02 off the rookie ladder and passes the unrounded figure
        # into its adjustment). So the conservation identity is asserted against
        # the PACKAGES the engine priced, and the displayed ints are checked
        # separately as the rounding of those same numbers.
        give, get = tr.card_packages(league, card)
        c = card["coords"]
        assert c["them"]["dF"] == round(give.v_sum - get.v_sum, 1), card["id"]
        assert c["me"]["dF"] == round(get.v_me_sum - give.v_me_sum, 1), card["id"]
        # v7.5: one price vector — the two sides negate on EVERY leg
        assert (give.v_sum, get.v_sum) == (give.v_me_sum, get.v_me_sum), card["id"]
        assert c["me"]["dF"] == -c["them"]["dF"], card["id"]
        saw_pick_leg |= any(a.kind == "pick" for a in give.assets + get.assets)
        # and the display is exactly the rounding of what was priced
        assert sum(a["v"] for a in card["give"]) == sum(
            round(x.v) for x in give.assets
        )
        assert sum(a["v"] for a in card["get"]) == sum(round(x.v) for x in get.assets)
    # conservation is exercised on pick-bearing legs, not just player swaps
    assert saw_pick_leg


def test_coords_are_per_side_dF_zero_sum_dS_not(league):
    """§2/§11.1 pinned: each side's coordinates are computed against its OWN
    roster. Javonte Williams (5,460) ↔ ronakpatel32's Zay Flowers (5,651): my
    side is (ΔS +191, ΔF +191) — objectively GOOD with the gain pinned to
    exactly +191 at every rational preference (floor = ceiling). Ron's side is
    (ΔS +96, ΔF −191) — a preference trade, good for δ < δ* ≈ 0.3345 (the
    win-now read). ΔF negates exactly; ΔS does not — deployment differs by
    roster, which is the arbitrage.

    v7 note: this is a PLAYER-for-player trade, and after the two-lens split it
    is the surviving witness that ΔF negates across the parties — it does so
    precisely because no pick crosses, so my lens and the market lens coincide
    (`Asset.v_me == Asset.v` for every player)."""
    card = tr.propose_by_names(
        league, "ronakpatel32", ["Javonte Williams"], ["Zay Flowers"]
    )
    assert card["coords"] == {
        "me": {"dS": 191.0, "dF": 191.0},
        "them": {"dS": 96.0, "dF": -191.0},
    }
    assert card["coords"]["me"]["dF"] == -card["coords"]["them"]["dF"]
    assert card["coords"]["me"]["dS"] != -card["coords"]["them"]["dS"]
    assert card["verdict"] == {"me": True, "them": False}
    assert card["floor"]["me"] == 191.0  # floor == ceiling: gain exactly +191
    assert card["breakeven"] == {"me": None, "them": round(96.0 / 287.0, 4)}
    assert card["gate"]["verdict"] == "PASS"
    # face value still transfers exactly: 5,460 out, 5,651 in
    assert sum(a["v"] for a in card["give"]) == 5460
    assert sum(a["v"] for a in card["get"]) == 5651


def test_both_sides_objectively_good_pinned(league):
    """§11.1 pinned: a leg where BOTH sides' verdicts are good. Because ΔF is
    zero-sum, that requires a face-equal swap improving BOTH lineups — the
    same two faces deploy differently on the two rosters. Synthetic (the
    fixture snapshot has no exact-face 1-for-1 of this shape): team A benches
    a 6,000 WR behind five better ones and starts a 5,000 QB; team B benches
    a 6,000 QB behind a 9,000 one and fields a thin WR room. Swapping the two
    6,000s is (+1,000, 0) for A and (+4,000, 0) for B — objectively good on
    BOTH sides."""
    wr_out = _pv_inv("WR-A", "WR", 6000, 10)
    qb_in = _pv_inv("QB-B", "QB", 6000, 11)
    roster_a = [
        _pv_inv("QB-A", "QB", 5000, 1),
        _pv_inv("WR1", "WR", 9000, 2), _pv_inv("WR2", "WR", 8000, 3),
        _pv_inv("WR3", "WR", 7000, 4), _pv_inv("WR4", "WR", 6500, 5),
        _pv_inv("WR5", "WR", 6200, 6),
        wr_out,  # 6th WR: 3 WR + 2 FLEX slots, he cannot start
    ]
    roster_b = [
        _pv_inv("QB-B9", "QB", 9000, 20), qb_in,  # one QB slot: 6,000 benched
        _pv_inv("WRb1", "WR", 4000, 21), _pv_inv("WRb2", "WR", 3500, 22),
        _pv_inv("WRb3", "WR", 3000, 23), _pv_inv("WRb4", "WR", 2500, 24),
        _pv_inv("WRb5", "WR", 2000, 25),
    ]
    d_s_a, d_f_a = tr.coords_delta(
        ln.StarterIndex(roster_a),
        [tr.package_of(league, [tr.player_asset(wr_out)])],
        [tr.package_of(league, [tr.player_asset(qb_in)])],
    )
    d_s_b, d_f_b = tr.coords_delta(
        ln.StarterIndex(roster_b),
        [tr.package_of(league, [tr.player_asset(qb_in)])],
        [tr.package_of(league, [tr.player_asset(wr_out)])],
    )
    assert (d_s_a, d_f_a) == (1000.0, 0.0)
    assert (d_s_b, d_f_b) == (4000.0, 0.0)
    assert d_f_a == -d_f_b == 0.0  # face conservation, degenerate case
    assert tr.verdict_of(d_s_a, d_f_a) and tr.verdict_of(d_s_b, d_f_b)


def test_coordinate_levels_pinned(league, me):
    """§2 v4 the two coordinates' LEVELS on my fixture roster: `S` is the
    max-Σv legal lineup over ACTIVE + TAXI at raw KTC; `total_face` is
    everything I own — players at face plus picks (IR in neither, §11.8).
    ΔS/ΔF on any trade are the changes in exactly these two numbers (asserted
    trade-by-trade in test_trades §11.8b(c)).

    v7 gave the F level a LENS, still a required argument; v7.5 made the two
    lenses one price and v7.6 made that price flat Mid for future picks (the
    slot is never estimated, whoever owns it), so `market` and `me` agree at
    129,042.86. ΔF is computed in the `me` lens, so that is the one the
    identity is asserted against."""
    s = ln.starter_sum(tr.starter_pool(me))
    assert s == 51832.0
    assert me.picks_mv == 41869.86
    assert sum(p.p_me for p in me.picks) == 41869.86
    # everything the F coordinate sees: active + taxi at face plus the picks
    assert sum(p.v for p in tr.starter_pool(me)) == 87173.0
    assert tr.total_face(me, lens="market") == 87173.0 + 41869.86 == 129042.86
    assert tr.total_face(me, lens="me") == 87173.0 + 41869.86 == 129042.86


# ------------------------------------------------ 2. independence + import graph


PERTURBED = [
    Params(q_qb=0.5, q_rb=0.01, q_wr=0.4, q_te=0.02, q_flex=0.3),
    Params(replacement_fa_rank=8),
    Params(u_out_long=0.9, u_out_short=0.95),
    Params(taxi_insurance_mult=0.75),
]


def _coords_ex1(league):
    card = tr.propose_by_names(
        league, "jaketoppen",
        ["Mike Evans", "Courtland Sutton"],
        ["2027 R1 (from vishan)", "2028 R4 (own)"],
    )
    return card["coords"]


def test_lineup_perturbations_never_move_coords(snapshot, league):
    """§11.2: perturb every lineup parameter — the trade coordinates are
    unchanged on BOTH sides (the S-solve uses raw v only: no q, no u, no
    replacement; and no other parameter exists in the score at all, v4)."""
    base = _coords_ex1(league)
    assert base == {
        "me": {"dS": -64.0, "dF": 78.0},
        "them": {"dS": 1216.0, "dF": -78.0},
    }
    for params in PERTURBED:
        league2 = md.build_league(snapshot, params)
        assert _coords_ex1(league2) == base, params


def test_roster_counts_never_move_coords_but_face_is_a_coordinate(snapshot, params, league, me):
    """§11.2 RESTATED FOR v4 — the honest form of the old "bench players never
    move the score" regression.

    (a) ROSTER COUNTS are housekeeping — removing an uninvolved non-startable
        bench player (mine or a third party's) leaves a given trade's
        coordinates bit-identical on both sides, because they read only ΔS and
        the traded assets' face; and
    (b) owned FACE is a COORDINATE by design — that same body carries v of the
        F coordinate while he sits there, and shipping him in a trade moves ΔF
        by exactly his face. v4 reports it raw instead of discounting it.
    """
    base = _coords_ex1(league)
    starters = {
        p.sid for grp in ln.starters(tr.starter_pool(me)).values() for p in grp
    }
    my_bench = sorted(
        (p for p in me.act if p.sid not in starters and not p.unvalued),
        key=lambda p: (p.v, p.sid),
    )[0]
    juk = league.teams["Jukinski"]
    juk_starters = {
        p.sid for grp in ln.starters(tr.starter_pool(juk)).values() for p in grp
    }
    juk_bench = sorted(
        (p for p in juk.act if p.sid not in juk_starters), key=lambda p: (p.v, p.sid)
    )[0]
    for team, victim in ((me, my_bench), (juk, juk_bench)):
        rosters = []
        for r in snapshot.rosters:
            r = dict(r)
            if r["roster_id"] == team.rid:
                r["players"] = [sid for sid in r["players"] if sid != victim.sid]
            rosters.append(r)
        league2 = md.build_league(dc_replace(snapshot, rosters=rosters), params)
        # (a) an uninvolved bench body never moves an unrelated trade's coords
        assert _coords_ex1(league2) == base, (team.name, victim.name)
        me2 = league2.teams[league2.me]
        if team is me:
            # (b) but he was carrying his face on MY F coordinate the whole time
            assert ln.starter_sum(tr.starter_pool(me2)) == ln.starter_sum(
                tr.starter_pool(me)
            )  # he never started
            assert tr.total_face(me, lens="me") - tr.total_face(
                me2, lens="me"
            ) == pytest.approx(victim.v)  # v7.4: two pick prices carry a fraction
    # …and trading him moves exactly one coordinate: ΔS stays 0 (he never
    # started), ΔF is the face delta itself
    jake = tr.team_assets(league, league.teams["jaketoppen"])
    mine = tr.team_assets(league, league.teams[league.me])
    card = tr.propose(
        league, "jaketoppen", [mine[my_bench.name]], [jake["2028 R4 (own)"]]
    )
    assert card["coords"]["me"]["dS"] == 0.0  # he never started
    # v7.6: the pick's ONE price is the flat Mid tranche 1,759, whoever owns
    # it — the slot is never estimated
    assert jake["2028 R4 (own)"].v == jake["2028 R4 (own)"].v_me == 1759.0
    assert card["coords"]["me"]["dF"] == pytest.approx(
        jake["2028 R4 (own)"].v_me - my_bench.v, abs=0.05
    )


def test_roster_tweaks_never_move_recommended_pair_coords(snapshot, params, league):
    """§11.2 at board level: knocking an uninvolved third party's bench player
    off the roster leaves every surviving (opponent, give, get) leg priced
    identically on both sides' coordinates."""
    juk = league.teams["Jukinski"]
    juk_starters = {
        p.sid for grp in ln.starters(tr.starter_pool(juk)).values() for p in grp
    }
    bench = sorted(
        (p for p in juk.act if p.sid not in juk_starters), key=lambda p: (p.v, p.sid)
    )[0]
    rosters = []
    for r in snapshot.rosters:
        r = dict(r)
        if r["roster_id"] == juk.rid:
            r["players"] = [sid for sid in r["players"] if sid != bench.sid]
        rosters.append(r)
    league2 = md.build_league(dc_replace(snapshot, rosters=rosters), params)
    key = lambda c: (
        c["counterparty"],
        tuple(sorted(a["key"] for a in c["give"])),
        tuple(sorted(a["key"] for a in c["get"])),
    )
    base_board = {
        key(c): c["coords"]
        for c in board_legs(tr.trade_board(league))
        if c["counterparty"] != "Jukinski"
    }
    overlap = 0
    for c in board_legs(tr.trade_board(league2)):
        if c["counterparty"] == "Jukinski":
            continue
        if key(c) in base_board:
            overlap += 1
            assert c["coords"] == base_board[key(c)]
    assert overlap > 0


RAW_STARTER_API = {"EMPTY4", "StarterIndex", "pos_columns", "starter_sum"}


def test_trade_path_imports_only_the_raw_starter_solve():
    """§11.2 AST-level: the whole v5 trade path — `trades.py` plus the finder
    and the constraint compiler — may import the RAW starter-sum solve and its
    incremental evaluator from `lineup`, and nothing else. `solve`,
    `removal_dl`, `diff_terms`, `Lineup` (the q / u / replacement machinery)
    must never appear. `posture.py` still imports nothing from the package."""
    banned = {"solve", "removal_dl", "diff_terms", "Lineup", "GROUPS", "GROUP_N"}
    for fname in ("trades.py", "finder.py", "constraints.py"):
        tree = ast.parse((SCORING / fname).read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any("lineup" in a.name for a in node.names), fname
            elif isinstance(node, ast.ImportFrom):
                if "lineup" in (node.module or ""):
                    imported.update(a.name for a in node.names)
                else:
                    assert not any("lineup" in a.name for a in node.names), fname
        assert imported <= RAW_STARTER_API, (fname, imported)
        if fname == "trades.py":
            assert imported == RAW_STARTER_API, imported
        assert not (imported & banned), fname

    tree = ast.parse((SCORING / "posture.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("core."), node.module
        elif isinstance(node, ast.Import):
            assert not any("lineup" in a.name for a in node.names)


# ------------------------------------------------- the raw starter-sum solve §2


def _brute_force_starter_sum(players) -> float:
    """Exhaustive max over every legal 9-slot assignment — the reference the
    greedy fill is checked against."""
    by_pos: dict[str, list] = {"QB": [], "RB": [], "WR": [], "TE": []}
    for p in players:
        if p.pos in by_pos:
            by_pos[p.pos].append(p.v)
    best = 0.0
    need = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
    for qb in combinations(by_pos["QB"], min(need["QB"], len(by_pos["QB"]))):
        for rb in combinations(by_pos["RB"], min(need["RB"], len(by_pos["RB"]))):
            for wr in combinations(by_pos["WR"], min(need["WR"], len(by_pos["WR"]))):
                for te in combinations(by_pos["TE"], min(need["TE"], len(by_pos["TE"]))):
                    used: dict[str, list] = {"RB": list(rb), "WR": list(wr), "TE": list(te)}
                    rest: list[float] = []
                    for pos in ("RB", "WR", "TE"):
                        pool = list(by_pos[pos])
                        for v in used[pos]:
                            pool.remove(v)
                        rest += pool
                    for flex in combinations(rest, min(2, len(rest))):
                        best = max(best, sum(qb) + sum(rb) + sum(wr) + sum(te) + sum(flex))
    return best


def _synthetic(rng, n):
    return [
        ln.PlayerV(
            sid=f"s{i}",
            name=f"P{i}",
            pos=rng.choice(["QB", "RB", "WR", "TE"]),
            v=float(rng.randrange(0, 9999)),
            ktc_id=i,
        )
        for i in range(n)
    ]


def test_starter_sum_greedy_is_exact():
    """§2 v3.4: the greedy per-slot fill (positional tops, then the best two
    survivors in FLEX) equals brute-force enumeration of every legal lineup, on
    small synthetic rosters including thin ones with unfillable slots. Seeded
    RNG only — determinism (§11.9) forbids wall-clock randomness."""
    rng = random.Random(20260727)
    for n in (3, 5, 7, 9, 11, 13):
        for _ in range(25):
            roster = _synthetic(rng, n)
            assert ln.starter_sum(roster) == pytest.approx(
                _brute_force_starter_sum(roster)
            ), [(p.pos, p.v) for p in roster]


def test_starter_index_matches_full_resolve(league):
    """§11.10: the incremental evaluator inside the pair walk is EXACT — over
    every fixture roster and 300 seeded random deltas of up to 6 players out and
    6 in, `StarterIndex.delta` equals a full re-solve. Seeded RNG only."""
    rng = random.Random(20260727)
    all_players = [p for t in league.teams.values() for p in tr.starter_pool(t)]
    for t in league.teams.values():
        base = tr.starter_pool(t)
        index = ln.StarterIndex(base)
        assert index.base_sum == ln.starter_sum(base)
        for _ in range(300 // len(league.teams) + 1):
            k_out = rng.randrange(0, min(7, len(base) + 1))
            k_in = rng.randrange(0, 7)
            out = rng.sample(base, k_out)
            incoming = rng.sample(all_players, k_in)
            got = index.delta(ln.pos_columns(out), ln.pos_columns(incoming))
            out_ids = [p.sid for p in out]
            rest = list(base)
            for sid in out_ids:
                for i, p in enumerate(rest):
                    if p.sid == sid:
                        del rest[i]
                        break
            want = ln.starter_sum(rest + incoming) - index.base_sum
            assert got == pytest.approx(want), (t.name, out_ids)


def test_coords_delta_matches_direct_recompute(league):
    """§2/§11.10 v4: the evaluator returns `(ΔS, ΔF)` from one incremental
    starter re-solve and the face delta passed through. This asserts both
    coordinates against a DIRECT recomputation — full re-solve of `S`, `F`
    counted as everything owned — over every fixture roster and seeded random
    deltas, and (§11.8b(c)) that any blend `ΔW(δ) = ΔS + δ·(ΔF − ΔS)` formed
    LOCALLY equals the direct `W = S + δ·(F − S)` delta at that δ: the two
    coordinates ARE the endpoints of every rational single-number ledger.
    Picks carry no lineup role, so they enter only through `ΔF`; that
    asymmetry is exercised explicitly."""
    rng = random.Random(20260728)
    deltas = [0.0, 0.25, 1.0] + [round(rng.uniform(0.01, 0.99), 4) for _ in range(4)]
    all_players = [p for t in league.teams.values() for p in tr.starter_pool(t)]
    for t in league.teams.values():
        base = tr.starter_pool(t)
        base_s = ln.starter_sum(base)
        base_face = tr.total_face(t, lens="me")
        index = ln.StarterIndex(base)
        for _ in range(60 // len(league.teams) + 1):
            out = rng.sample(base, rng.randrange(0, min(5, len(base) + 1)))
            incoming = rng.sample(all_players, rng.randrange(0, 5))
            d_picks = float(rng.randrange(-6000, 6000))  # no lineup role at all
            d_face = (
                sum(p.v for p in incoming) - sum(p.v for p in out) + d_picks
            )
            rest = list(base)
            for sid in [p.sid for p in out]:
                for i, p in enumerate(rest):
                    if p.sid == sid:
                        del rest[i]
                        break
            after_s = ln.starter_sum(rest + incoming)
            after_face = base_face + d_face
            d_s, d_f = index.coords_delta(
                ln.pos_columns(out), ln.pos_columns(incoming), d_face
            )
            assert d_s == pytest.approx(after_s - base_s), t.name
            assert d_f == d_face
            for delta in deltas:
                # the blend is the TEST'S, not the engine's (§11.8b(c)):
                # direct W = S + δ·(F − S) at every δ
                w_before = base_s + delta * (base_face - base_s)
                w_after = after_s + delta * (after_face - after_s)
                blend = d_s + delta * (d_f - d_s)
                assert blend == pytest.approx(w_after - w_before), (t.name, delta)
            # and the coordinates through the trade-path entry point
            got = tr.coords_delta(
                index,
                [tr.package_of(league, [tr.player_asset(p) for p in out])],
                [tr.package_of(league, [tr.player_asset(p) for p in incoming])],
            )
            assert got[0] == pytest.approx(d_s)
            # (the package path has no d_picks input: its ΔF is players-only)
            assert got[1] == pytest.approx(d_face - d_picks)


def test_taxi_counts_in_S_and_ir_does_not(league, snapshot, params):
    """§11.8: a taxi player is startable (promote-anytime) and COUNTS in S; an
    IR player never does. Pinned on my own fixture roster."""
    me = league.teams[league.me]
    assert me.taxi, "fixture roster should carry taxi players"
    pool_ids = {p.sid for p in tr.starter_pool(me)}
    assert {p.sid for p in me.taxi} <= pool_ids
    assert not (me.reserve_ids & pool_ids) or league.offseason

    # a taxi STUD lifts S by exactly the value he displaces
    stud = ln.PlayerV(sid="taxi-stud", name="Taxi Stud", pos="WR", v=9999.0, ktc_id=1)
    base = ln.starter_sum(tr.starter_pool(me))
    assert ln.starter_sum(tr.starter_pool(me) + [stud]) > base

    # and an IR body does not enter the pool at all (in-season, where reserve
    # tags are live rather than stale July artifacts)
    in_season = dc_replace(
        snapshot, state={**dict(snapshot.state), "season_type": "regular", "week": 5}
    )
    league2 = md.build_league(in_season, params)
    me2 = league2.teams[league2.me]
    for sid in me2.reserve_ids:
        assert sid not in {p.sid for p in tr.starter_pool(me2)}


# ------------------------------------------------------- 5. bundles + exclusivity


def test_pairs_v4_contract(board, params, league):
    """§11.5 / §5 v4: every stored pair embeds a gate-PASS buy and sell with
    DISTINCT counterparties sharing no assets, netting for my side EXACTLY
    0 players AND 0 picks (plus the carried Δ(active roster) ≤ 0). The pair's
    coordinates are the EXACT COMBINED ones — recomputed here from the
    embedded cards — its verdict/floor/ceiling derive from them (floor and
    ceiling folding the §2 v8.2 pick-band swing), and its return_pct is the
    NEUTRAL flat-Mid floor over face Σv sent (the walk's ranking key —
    §11.17). Pairs are unique by their asset multisets."""
    pairs = board["pairs"]
    # v5 union storage: ≤ 3 heaps × quota × the five favor buckets
    assert 0 < len(pairs) <= 3 * params.pairs_per_band * (len(params.favor_band_edges) + 1)
    keys = lambda c: {a["key"] for a in c["give"] + c["get"]}
    seen_multisets = set()
    for pair in pairs:
        buy, sell = pair["buy"], pair["sell"]
        assert buy["leg_type"] == "buy" and sell["leg_type"] == "sell"
        assert buy["gate"]["verdict"] == "PASS" and sell["gate"]["verdict"] == "PASS"
        assert not keys(buy) & keys(sell)  # invariant 3: no shared assets
        assert tr.pair_count_deltas(buy, sell) == (0, 0)
        assert pair["net_players"] == 0 and pair["net_picks"] == 0
        assert pair["net_roster"] <= 0
        assert pair["net_roster"] == buy["net_roster"]["me"] + sell["net_roster"]["me"]
        assert buy["coords_basis"] == sell["coords_basis"] == "isolation"
        assert buy["counterparty"] != sell["counterparty"]  # v3.3: strict
        assert tr.posture_allows(buy["posture"]["label"], buy["posture"]["shape"])
        assert tr.posture_allows(sell["posture"]["label"], sell["posture"]["shape"])
        ms = (
            tuple(sorted(a["key"] for a in buy["give"] + buy["get"])),
            tuple(sorted(a["key"] for a in sell["give"] + sell["get"])),
        )
        assert ms not in seen_multisets  # deduped by exact asset-multiset pair
        seen_multisets.add(ms)
        assert pair["fit_summary"] in (
            "both legs fit posture",
            "buy leg fits posture",
            "sell leg fits posture",
            "neither leg fits posture",
        )
        assert "sell" in pair["sequencing"] or "buy may execute first" in pair["sequencing"]
    for pair in pairs[:15]:  # exact-coordinate reconstruction on a sample
        got = tr.pair_coords(league, pair["buy"], pair["sell"])
        assert {"dS": got["dS"], "dF": got["dF"]} == pair["coords"]
        assert got["verdict"] == pair["verdict"] is True
        assert got["floor"] == pair["floor"]
        assert got["ceiling"] == pair["ceiling"]
        assert got["swing"] == pair["swing"]
        # §11.17: the stored return_pct is the NEUTRAL flat-Mid maximin key
        # the walk ranked on; the band-extended guarantee lives in floor/swing
        assert got["return_mid_pct"] == pair["return_pct"]
        # `sent` is Σ MARKET face actually sent, unrounded; the cards display
        # rounded ints, so compare against the packages rather than the display
        # (v7.4: KTC's 2026 1.01/1.02 carry a fraction and we keep it).
        assert got["sent"] == pair["sent"] == round(
            sum(
                tr.card_packages(league, leg)[0].v_sum
                for leg in (pair["buy"], pair["sell"])
            ),
            1,
        )
        # §4a v5: the pair's favor figures are exactly its legs' card favors
        # (each derived from the gate's own adjusted totals, §11.12(a)) and
        # min() of them; the informational market_return_pct stays pure face
        # arithmetic on the embedded cards
        for tag in ("buy", "sell"):
            leg = pair[tag]
            sent = sum(a["v"] for a in leg["give"])
            face_df = sum(a["v"] for a in leg["get"]) - sent
            assert leg["market_return_pct"] == round(100.0 * face_df / sent, 2)
            assert pair["favor"][tag] == leg["favor"] == leg["gate"]["favor"]
        assert pair["favor"]["min"] == min(pair["favor"]["buy"], pair["favor"]["sell"])


def test_pair_coords_are_combined_not_the_leg_sum(board, league):
    """§2/§5 v4: pair ΔS is the two legs applied TOGETHER, never the leg sum
    (ΔF IS additive — face has no interactions). A pinned fixture pair shows
    the ΔS interaction: buy Josh Jacobs (4,853) from NoahMoell while selling
    Kenneth Walker III (my flex starter) — Jacobs starts ONLY once Walker's
    slot opens, so the buy moves no starter value alone (ΔS = 0) but is worth
    792 more of STARTER value inside the pair (Jacobs replaces the 4,061
    bench fill-in, not nothing). v4 reports the interaction raw, in the ΔS
    coordinate itself. This pair is verdict-FALSE (both coordinates negative)
    — §11.8b(d) says it is a must-never-emit, checked against the stored
    board."""
    pairs = board["pairs"]
    assert all("coords" in p and "floor" in p and "ceiling" in p for p in pairs)
    buy = tr.propose_by_names(league, "NoahMoell", ["2027 R1 (own)"], ["Josh Jacobs"])
    sell = tr.propose_by_names(
        league, "jaketoppen", ["Kenneth Walker III"], ["2027 R1 (from vishan)"]
    )
    # v7.6 moves both ΔFs (my own 2027 1st and vishan's both price at the flat
    # Mid 6,118 — the swap of the two 1sts nets exactly 0 face, a symmetry
    # pin) and leaves every ΔS untouched — picks never enter the lineup,
    # which is exactly what this test is about
    assert buy["coords"]["me"] == {"dS": 0.0, "dF": -1265.0}
    assert sell["coords"]["me"] == {"dS": -2220.0, "dF": -163.0}
    pair = tr.pair_coords(league, buy, sell)
    assert pair["dS"] == -1428.0  # combined ≠ leg sum (−2,220)
    ds_sum = buy["coords"]["me"]["dS"] + sell["coords"]["me"]["dS"]
    assert pair["dS"] - ds_sum == 792.0  # the lineup interaction, raw
    # ΔF is exactly additive across legs — no interaction exists in face, and
    # the one price is a static per-asset scalar so additivity is untouched
    assert pair["dF"] == buy["coords"]["me"]["dF"] + sell["coords"]["me"]["dF"] == -1428.0
    # superadditivity guarantee (§2): combined ΔS is never BELOW the leg sum
    assert pair["dS"] >= ds_sum
    # §11.8b(d): verdict-false — and absent from the stored board
    assert pair["verdict"] is False and pair["floor"] < 0
    mk = (
        tuple(sorted(a["key"] for a in buy["give"] + buy["get"])),
        tuple(sorted(a["key"] for a in sell["give"] + sell["get"])),
    )
    for p in pairs:
        stored_mk = (
            tuple(sorted(a["key"] for a in p["buy"]["give"] + p["buy"]["get"])),
            tuple(sorted(a["key"] for a in p["sell"]["give"] + p["sell"]["get"])),
        )
        assert stored_mk != mk


def test_verdict_false_pair_never_stored_even_if_offered():
    """§11.8b(d)/§11.12(g) at the storage layer: the bucket sink hard-rejects
    any pair whose guaranteed floor is not strictly positive — even if a walk
    offered it, it is neither stored nor counted. (Floor > 0 ⟺ both
    coordinates > 0 ⟺ verdict with both strict; the stored universe's 1% floor
    preset would also exclude it, but the guard must not depend on the
    presets.)"""
    legs = [
        # minimal fake leg tuples: only L_SENT (2) and L_FAVOR (12) are read
        (0.0, 0.0, 100.0, 1, -1, 0, 0, None, None, None, None, 0.0, -2.5),
        (0.0, 0.0, 100.0, -1, 1, 1, 0, None, None, None, None, 0.0, 1.5),
    ]
    buckets = tr.favor_buckets((-10.0, -5.0, 0.0, 5.0))
    tbands = tr.return_bands((1.0, 2.5, 5.0, 10.0, 20.0))
    sink = tr._BucketSink(buckets, tbands, quota=10, legs=legs)
    sink.append((-0.05, 10.0, -0.05, 0, 1, -5.0, 10.0))  # floor-negative: verdict false
    sink.append((0.0, 500.0, 0.0, 0, 1, 0.0, 500.0))  # floor exactly 0: not objectively good
    assert sum(sink.counts) == 0
    assert all(not h for hs in (sink.h_ret, sink.h_ds, sink.h_df) for h in hs)
    sink.append((0.05, 10.0, 0.05, 0, 1, 5.0, 10.0))  # floor-positive: stored and counted
    assert sum(sink.counts) == 1
    # bucketed on favor min = min(−2.5, 1.5) = −2.5 → the [−5, 0) bucket
    assert sink.counts[2] == 1
    # …and the stored union carries it once, despite living in three heaps
    assert sink.bucket_pairs(2) == [(0.05, 10.0, 0, 1)]


def test_buy_legs_are_allowed_to_be_floor_negative_alone(board, pool, league):
    """§5 v4: the per-leg return floor stays retired — a leg whose ISOLATION
    floor is negative (every buy leg paying picks for a player is: its ΔF is
    the face it ships) stays in the pool and stays pairable, because its
    partner recoups. What must hold is only the PAIR's verdict (§11.8b(d)).
    Pinned where it lives — the candidate pool — plus the fact that
    floor-negative legs of BOTH directions are eligible to pair."""
    buys = [p["buy"] for p in board["pairs"]]
    assert buys
    # the stored board itself uses floor-negative legs: the fixture's top
    # pair carries a sell leg with negative market return (face recouped on
    # the buy side)
    assert any(
        min(p["buy"]["coords"]["me"]["dS"], p["buy"]["coords"]["me"]["dF"]) < 0
        or min(p["sell"]["coords"]["me"]["dS"], p["sell"]["coords"]["me"]["dF"]) < 0
        for p in board["pairs"]
    )
    neg_buys: dict[tuple[int, int], list[int]] = {}
    neg_sells: dict[tuple[int, int], list[int]] = {}
    for i, leg in enumerate(pool.legs):
        if leg[tr.L_FLOOR] >= 0 or leg[tr.L_NP] == 0:
            continue
        sink = neg_buys if leg[tr.L_NP] > 0 else neg_sells
        sink.setdefault((leg[tr.L_NP], leg[tr.L_NK]), []).append(i)
    assert neg_buys and neg_sells  # the v3.3 per-leg floor would have deleted both
    # and they are genuinely pairable, not just parked: a floor-negative buy
    # leg is a member of the computed count-neutral pair space, priced by the
    # exact combined coordinates like any other
    paired = None
    for sig, bis in sorted(neg_buys.items()):
        comp = neg_sells.get((-sig[0], -sig[1]))
        if not comp:
            continue
        for bi in bis[:40]:
            for si in comp[:300]:
                if tr.pair_in_space(league, pool, bi, si) is not None:
                    paired = (bi, si)
                    break
            if paired:
                break
        if paired:
            break
    assert paired is not None
    bi, si = paired
    assert pool.legs[bi][tr.L_FLOOR] < 0 and pool.legs[si][tr.L_FLOOR] < 0


def test_no_standalone_buy_anywhere(board):
    """§5 v3.1 invariant 2: buy legs exist ONLY inside pairs — never in the
    secondary list, and the watch list carries blockers, not proposal cards."""
    doc = board
    pair_buys = {id(p["buy"]) for p in doc["pairs"]}

    def walk(node):
        if isinstance(node, dict):
            if node.get("leg_type") == "buy":
                assert id(node) in pair_buys, "standalone buy leg emitted"
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(doc)
    for card in doc["recommendations"]:
        assert card["leg_type"] in ("sell", "neutral")
    for w in doc["watch"]:
        assert set(w) == {"counterparty", "give", "get", "floor", "blocker"}
        assert "no clean exit" in w["blocker"]


def test_exclusive_with_and_pair_overlaps(board):
    """§11.5 (v3.3 scope): the secondary list carries exact leg-level
    exclusive_with among itself; the stored board carries the honest pair-level
    `overlaps` tally instead (leg-level id lists across a full stored board
    would be O(pairs²) payload) — verified by reconstruction on a sample. Pair
    legs carry an empty exclusive_with by design."""
    doc = board
    recs = doc["recommendations"]
    keys = {c["id"]: {a["key"] for a in c["give"] + c["get"]} for c in recs}
    for a in recs:
        for b in recs:
            if a["id"] == b["id"]:
                continue
            if keys[a["id"]] & keys[b["id"]]:
                assert b["id"] in a["exclusive_with"], (a["id"], b["id"])
            else:
                assert b["id"] not in a["exclusive_with"], (a["id"], b["id"])
    pair_keys = [
        {a["key"] for leg in (p["buy"], p["sell"]) for a in leg["give"] + leg["get"]}
        for p in doc["pairs"]
    ]
    for i, p in enumerate(doc["pairs"][:20]):  # reconstruction sample
        expect = sum(1 for j, k in enumerate(pair_keys) if j != i and pair_keys[i] & k)
        assert p["overlaps"] == expect, p["id"]
        assert p["buy"]["exclusive_with"] == [] and p["sell"]["exclusive_with"] == []


# ------------------------------------------------------------------- 8. legality


def test_legality_on_both_rosters(board, league):
    """§11.8: every emitted leg leaves both rosters legal (minima, size, taxi
    routing per §8) — recomputed from scratch here, not trusted from the card."""
    by_key: dict[str, tr.Asset] = {}
    for t in league.teams.values():
        for a in tr.team_assets(league, t).values():
            by_key[a.key] = a
    me_t = league.teams[league.me]
    for card in board_legs(board):
        give = tr.package_of(league, [by_key[a["key"]] for a in card["give"]])
        get = tr.package_of(league, [by_key[a["key"]] for a in card["get"]])
        verdicts = tr.legality(league, me_t, league.teams[card["counterparty"]], give, get)
        assert verdicts["legal"], card["id"]
        for side in ("me", "them"):
            assert verdicts[side]["minima_ok"] and verdicts[side]["size_ok"]
        assert verdicts["me"]["net_roster"] == card["net_roster"]["me"]
        assert verdicts["them"]["net_roster"] == card["net_roster"]["them"]


# --------------------------------------------------------- 9. determinism, 10. cost


def test_determinism_byte_for_byte(snapshot, params, result, league, board):
    """§11.9: identical snapshot ⇒ identical output, byte-for-byte — for the
    stored payloads AND for the pair board, which v7.1 moved out of
    `compute_all` but which is the half where determinism is hardest (heaps,
    walk order, tie-breaks)."""
    again = compute_all(snapshot, params)
    assert json.dumps(again, sort_keys=True) == json.dumps(result, sort_keys=True)
    again_board = tr.trade_board(md.build_league(snapshot, params))
    assert json.dumps(again_board, sort_keys=True) == json.dumps(board, sort_keys=True)


def test_runtime_within_budget(snapshot, params):
    """§11.10: v3.4 put the exact KTC-calculator gate and a raw starter-sum
    re-solve inside the enumeration, and the exact combined pricing inside the
    pair walk. Measured ≈ 29s on the dev box (v3.3 was ≈ 7s) — bought with an
    incremental exact evaluator, a necessary-condition screen ahead of the
    gate, and bounded walks. v4 costs NOTHING here: the two coordinates are
    the same one starter re-solve plus a face delta the leg already carries —
    a min() replaced the δ multiply-add (measured ≈ 30s on this box, the same
    band as v3.5's 28.9s) — so the bound stays where it was rather than
    tightening onto measurement noise.

    v7.1 SPLIT this. `compute_all` no longer builds the pair board, so what the
    collector actually runs nightly is now the cheap half and gets a tight
    bound; the board is measured separately, because it is still the expensive
    pass — it just runs in the CLI now. Both bounds exist to catch ONE thing:
    an unbounded walk, which blows past them by orders of magnitude. They are
    deliberately loose against wall-clock drift — the board measured 91 s here
    under a full-suite run against ~30 s standalone, and chasing that spread
    would turn a regression guard into a flaky benchmark."""
    t0 = time.perf_counter()
    compute_all(snapshot, params)
    nightly = time.perf_counter() - t0
    assert nightly < 20.0, nightly  # what the Lambda runs
    t0 = time.perf_counter()
    tr.trade_board(md.build_league(snapshot, params))
    board_cost = time.perf_counter() - t0
    assert board_cost < 180.0, board_cost  # what the CLI runs on demand


# ------------------------------------------------------------------ output shape


def test_unvalued_never_in_board_recs(board):
    """§11.7: enumeration never floats a zero-value asset into a package."""
    for card in board_legs(board):
        for a in card["give"] + card["get"]:
            assert not a.get("unvalued"), card["id"]
        assert card["unvalued"] == []
