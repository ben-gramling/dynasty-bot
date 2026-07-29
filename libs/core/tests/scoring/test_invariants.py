"""§11 implementation invariants (v4): face conservation (ΔF zero-sum per
leg), the per-side two-coordinate score (ΔS, ΔF), independence from the lineup
model, import graph, bundles, exclusivity, legality, determinism, runtime.

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


def test_face_transfer_conserved_per_leg(result, league):
    """§11.1: on every leg the FACE-KTC transfer is exact — each asset carries
    the same v on both rosters, so `ΔF(side A) = −ΔF(side B)` on every leg.
    This, not ΔS, is what v4 conserves; verified from the cards' own coords."""
    canonical = {
        a.key: a.v for t in league.teams.values() for a in tr.team_assets(league, t).values()
    }
    for card in board_legs(result["trade_recs"]):
        for a in card["give"] + card["get"]:
            assert a["v"] == round(canonical[a["key"]]), (card["id"], a["name"])
        out_me = sum(a["v"] for a in card["give"])
        in_me = sum(a["v"] for a in card["get"])
        # ΔF is exactly zero-sum across the leg's parties (§11.1)
        c = card["coords"]
        assert c["me"]["dF"] == -c["them"]["dF"], card["id"]
        assert c["me"]["dF"] == round(float(in_me - out_me), 1), card["id"]
        # and the packages the engine priced carry exactly those sums
        give, get = tr.card_packages(league, card)
        assert round(give.v_sum) == out_me and round(get.v_sum) == in_me


def test_coords_are_per_side_dF_zero_sum_dS_not(league):
    """§2/§11.1 pinned: each side's coordinates are computed against its OWN
    roster. Javonte Williams (5,460) ↔ ronakpatel32's Zay Flowers (5,651): my
    side is (ΔS +191, ΔF +191) — objectively GOOD with the gain pinned to
    exactly +191 at every rational preference (floor = ceiling). Ron's side is
    (ΔS +96, ΔF −191) — a preference trade, good for δ < δ* ≈ 0.3345 (the
    win-now read). ΔF negates exactly; ΔS does not — deployment differs by
    roster, which is the arbitrage."""
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
    everything I own — players at face plus picks at tranche (IR in neither,
    §11.8). ΔS/ΔF on any trade are the changes in exactly these two numbers
    (asserted trade-by-trade in test_trades §11.8b(c))."""
    s = ln.starter_sum(tr.starter_pool(me))
    assert s == 51832.0
    assert me.picks_mv == 39921.0
    # everything the F coordinate sees: active + taxi at face plus the picks
    assert sum(p.v for p in tr.starter_pool(me)) == 87173.0
    assert tr.total_face(me) == 87173.0 + 39921.0 == 127094.0


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
        "me": {"dS": -64.0, "dF": 1358.0},
        "them": {"dS": 1216.0, "dF": -1358.0},
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
            assert tr.total_face(me) - tr.total_face(me2) == victim.v
    # …and trading him moves exactly one coordinate: ΔS stays 0 (he never
    # started), ΔF is the face delta itself
    jake = tr.team_assets(league, league.teams["jaketoppen"])
    mine = tr.team_assets(league, league.teams[league.me])
    card = tr.propose(
        league, "jaketoppen", [mine[my_bench.name]], [jake["2028 R4 (own)"]]
    )
    assert card["coords"]["me"]["dS"] == 0.0  # he never started
    assert card["coords"]["me"]["dF"] == pytest.approx(
        jake["2028 R4 (own)"].v - my_bench.v, abs=0.05
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
    """§11.2 AST-level: `trades.py` may import the RAW starter-sum solve and its
    incremental evaluator from `lineup` — and nothing else. `solve`,
    `removal_dl`, `diff_terms`, `Lineup` (the q / u / replacement machinery)
    must never appear. `posture.py` still imports nothing from the package."""
    tree = ast.parse((SCORING / "trades.py").read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any("lineup" in a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if "lineup" in (node.module or ""):
                imported.update(a.name for a in node.names)
            else:
                assert not any("lineup" in a.name for a in node.names)
    assert imported == RAW_STARTER_API, imported
    banned = {"solve", "removal_dl", "diff_terms", "Lineup", "GROUPS", "GROUP_N"}
    assert not (imported & banned)

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
        base_face = tr.total_face(t)
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


def test_pairs_v4_contract(result, params, league):
    """§11.5 / §5 v4: every stored pair embeds a gate-PASS buy and sell with
    DISTINCT counterparties sharing no assets, netting for my side EXACTLY
    0 players AND 0 picks (plus the carried Δ(active roster) ≤ 0). The pair's
    coordinates are the EXACT COMBINED ones — recomputed here from the
    embedded cards — its verdict/floor/ceiling derive from them, and its
    return_pct is the guaranteed floor over face Σv sent. Pairs are unique by
    their asset multisets."""
    pairs = result["trade_recs"]["pairs"]
    assert 0 < len(pairs) <= params.pairs_per_band * len(params.return_presets)
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
        assert got["return_pct"] == pair["return_pct"]
        assert got["sent"] == sum(
            a["v"] for leg in (pair["buy"], pair["sell"]) for a in leg["give"]
        )
        # §5 v3.4.1: the per-leg MARKET returns are pure face arithmetic on the
        # embedded cards — face ΔF(me) ÷ face Σv sent on that leg
        for tag in ("buy", "sell"):
            leg = pair[tag]
            sent = sum(a["v"] for a in leg["give"])
            face_df = sum(a["v"] for a in leg["get"]) - sent
            assert pair["leg_returns"][tag] == round(100.0 * face_df / sent, 2)
            assert leg["market_return_pct"] == pair["leg_returns"][tag]
        assert pair["max_leg_return_pct"] == max(pair["leg_returns"].values())


def test_pair_coords_are_combined_not_the_leg_sum(result, league):
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
    pairs = result["trade_recs"]["pairs"]
    assert all("coords" in p and "floor" in p and "ceiling" in p for p in pairs)
    buy = tr.propose_by_names(league, "NoahMoell", ["2027 R1 (own)"], ["Josh Jacobs"])
    sell = tr.propose_by_names(
        league, "jaketoppen", ["Kenneth Walker III"], ["2027 R1 (from vishan)"]
    )
    assert buy["coords"]["me"] == {"dS": 0.0, "dF": -1265.0}
    assert sell["coords"]["me"] == {"dS": -2220.0, "dF": 1117.0}
    pair = tr.pair_coords(league, buy, sell)
    assert pair["dS"] == -1428.0  # combined ≠ leg sum (−2,220)
    ds_sum = buy["coords"]["me"]["dS"] + sell["coords"]["me"]["dS"]
    assert pair["dS"] - ds_sum == 792.0  # the lineup interaction, raw
    # ΔF is exactly additive across legs — no interaction exists in face
    assert pair["dF"] == buy["coords"]["me"]["dF"] + sell["coords"]["me"]["dF"] == -148.0
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
    """§11.8b(d) at the storage layer: the bucket sink hard-rejects any pair
    whose guaranteed floor is not strictly positive — even if a walk offered
    it, it is neither stored nor counted. (Floor > 0 ⟺ both coordinates > 0
    ⟺ verdict with both strict; the stored universe's 1% floor preset would
    also exclude it, but the guard must not depend on the presets.)"""
    legs = [
        # minimal fake leg tuples: only L_SENT (2) and L_MKT (12) are read
        (0.0, 0.0, 100.0, 1, -1, 0, 0, None, None, None, None, 0.0, 0.01),
        (0.0, 0.0, 100.0, -1, 1, 1, 0, None, None, None, None, 0.0, 0.01),
    ]
    buckets = tr.leg_buckets((2.5, 5.0, 10.0, 20.0))
    tbands = tr.return_bands((1.0, 2.5, 5.0, 10.0, 20.0))
    sink = tr._BucketSink(buckets, tbands, quota=10, legs=legs)
    sink.append((-0.05, 10.0, -0.05, 0, 1))  # floor-negative: verdict false
    sink.append((0.0, 500.0, 0.0, 0, 1))  # floor exactly 0: not objectively good
    assert sum(sink.counts) == 0 and all(not h for h in sink.heaps)
    sink.append((0.05, 10.0, 0.05, 0, 1))  # floor-positive: stored and counted
    assert sum(sink.counts) == 1


def test_buy_legs_are_allowed_to_be_floor_negative_alone(result, pool, league):
    """§5 v4: the per-leg return floor stays retired — a leg whose ISOLATION
    floor is negative (every buy leg paying picks for a player is: its ΔF is
    the face it ships) stays in the pool and stays pairable, because its
    partner recoups. What must hold is only the PAIR's verdict (§11.8b(d)).
    Pinned where it lives — the candidate pool — plus the fact that
    floor-negative legs of BOTH directions are eligible to pair."""
    buys = [p["buy"] for p in result["trade_recs"]["pairs"]]
    assert buys
    # the stored board itself uses floor-negative legs: the fixture's top
    # pair carries a sell leg with negative market return (face recouped on
    # the buy side)
    assert any(
        min(p["buy"]["coords"]["me"]["dS"], p["buy"]["coords"]["me"]["dF"]) < 0
        or min(p["sell"]["coords"]["me"]["dS"], p["sell"]["coords"]["me"]["dF"]) < 0
        for p in result["trade_recs"]["pairs"]
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


def test_no_standalone_buy_anywhere(result):
    """§5 v3.1 invariant 2: buy legs exist ONLY inside pairs — never in the
    secondary list, and the watch list carries blockers, not proposal cards."""
    doc = result["trade_recs"]
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


def test_exclusive_with_and_pair_overlaps(result):
    """§11.5 (v3.3 scope): the secondary list carries exact leg-level
    exclusive_with among itself; the stored board carries the honest pair-level
    `overlaps` tally instead (leg-level id lists across a full stored board
    would be O(pairs²) payload) — verified by reconstruction on a sample. Pair
    legs carry an empty exclusive_with by design."""
    doc = result["trade_recs"]
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


def test_legality_on_both_rosters(result, league):
    """§11.8: every emitted leg leaves both rosters legal (minima, size, taxi
    routing per §8) — recomputed from scratch here, not trusted from the card."""
    by_key: dict[str, tr.Asset] = {}
    for t in league.teams.values():
        for a in tr.team_assets(league, t).values():
            by_key[a.key] = a
    me_t = league.teams[league.me]
    for card in board_legs(result["trade_recs"]):
        give = tr.package_of(league, [by_key[a["key"]] for a in card["give"]])
        get = tr.package_of(league, [by_key[a["key"]] for a in card["get"]])
        verdicts = tr.legality(league, me_t, league.teams[card["counterparty"]], give, get)
        assert verdicts["legal"], card["id"]
        for side in ("me", "them"):
            assert verdicts[side]["minima_ok"] and verdicts[side]["size_ok"]
        assert verdicts["me"]["net_roster"] == card["net_roster"]["me"]
        assert verdicts["them"]["net_roster"] == card["net_roster"]["them"]


# --------------------------------------------------------- 9. determinism, 10. cost


def test_determinism_byte_for_byte(snapshot, params, result):
    """§11.9: identical snapshot ⇒ identical board, byte-for-byte."""
    again = compute_all(snapshot, params)
    assert json.dumps(again, sort_keys=True) == json.dumps(result, sort_keys=True)


def test_runtime_within_budget(snapshot, params):
    """§11.10: v3.4 put the exact KTC-calculator gate and a raw starter-sum
    re-solve inside the enumeration, and the exact combined pricing inside the
    pair walk. Measured ≈ 29s on the dev box (v3.3 was ≈ 7s) — bought with an
    incremental exact evaluator, a necessary-condition screen ahead of the
    gate, and bounded walks. v4 costs NOTHING here: the two coordinates are
    the same one starter re-solve plus a face delta the leg already carries —
    a min() replaced the δ multiply-add (measured ≈ 30s on this box, the same
    band as v3.5's 28.9s) — so the bound stays where it was rather than
    tightening onto measurement noise. The collector Lambda's budget is 600s
    for the whole run (scrape included), so the 90s bound here keeps real
    headroom while still catching the regression that matters: any unbounded
    walk blows straight past it."""
    t0 = time.perf_counter()
    compute_all(snapshot, params)
    elapsed = time.perf_counter() - t0
    assert elapsed < 90.0, elapsed


# ------------------------------------------------------------------ output shape


def test_unvalued_never_in_board_recs(result):
    """§11.7: enumeration never floats a zero-value asset into a package."""
    for card in board_legs(result["trade_recs"]):
        for a in card["give"] + card["get"]:
            assert not a.get("unvalued"), card["id"]
        assert card["unvalued"] == []
