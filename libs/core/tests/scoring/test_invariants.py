"""§11 implementation invariants (v3.4): face conservation, the per-side wealth
ledger, independence from the lineup model, import graph, bundles, exclusivity,
legality, determinism, runtime.

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


# ------------------------------------- 1. face conservation + the per-side ledger


def test_face_transfer_conserved_per_leg(result, league):
    """§11.1: on every leg the FACE-KTC transfer is exact — each asset carries
    the same v on both rosters, so my face flow and theirs negate to the point.
    This, not ΔW, is what v3.4 conserves."""
    canonical = {
        a.key: a.v for t in league.teams.values() for a in tr.team_assets(league, t).values()
    }
    for card in board_legs(result["trade_recs"]):
        for a in card["give"] + card["get"]:
            assert a["v"] == round(canonical[a["key"]]), (card["id"], a["name"])
        out_me = sum(a["v"] for a in card["give"])
        in_me = sum(a["v"] for a in card["get"])
        # my face delta and the counterparty's are exact negations
        assert (in_me - out_me) + (out_me - in_me) == 0
        # and the packages the engine priced carry exactly those sums
        give, get = tr.card_packages(league, card)
        assert round(give.v_sum) == out_me and round(get.v_sum) == in_me


def test_ledger_is_per_side_not_zero_sum(league):
    """§2/§11.1 v3.4 pinned: ΔW is each side's OWN ledger. Javonte Williams
    (5,460) ↔ ronakpatel32's Zay Flowers (5,651) is the fixture's arbitrage
    shape — the ONLY gate-clean 1-for-1 in the whole snapshot where BOTH
    ledgers gain: my starters +191, theirs +96, no picks either way."""
    card = tr.propose_by_names(
        league, "ronakpatel32", ["Javonte Williams"], ["Zay Flowers"]
    )
    assert card["dW"] == {"me": 191.0, "them": 96.0}
    assert card["dW"]["me"] + card["dW"]["them"] != 0.0  # emphatically not zero-sum
    assert card["dW_parts"] == {
        "me": {"dS": 191.0, "dP": 0.0},
        "them": {"dS": 96.0, "dP": 0.0},
    }
    assert card["gate"]["verdict"] == "PASS"
    # face value still transfers exactly: 5,460 out, 5,651 in
    assert sum(a["v"] for a in card["give"]) == 5460
    assert sum(a["v"] for a in card["get"]) == 5651


def test_wealth_ledger_components(league, me):
    """§2: W = S + P, with S the max-Σv legal lineup over ACTIVE + TAXI at raw
    KTC and P the picks at tranche. Pinned to the committed fixture."""
    s = ln.starter_sum(tr.starter_pool(me))
    assert s == 51832.0
    assert me.picks_mv == 39921.0
    assert tr.wealth(me) == s + me.picks_mv == 91753.0


# ------------------------------------------------ 2. independence + import graph


PERTURBED = [
    Params(q_qb=0.5, q_rb=0.01, q_wr=0.4, q_te=0.02, q_flex=0.3),
    Params(replacement_fa_rank=8),
    Params(u_out_long=0.9, u_out_short=0.95),
    Params(taxi_insurance_mult=0.75),
]


def _dw_ex1(league):
    card = tr.propose_by_names(
        league, "jaketoppen",
        ["Mike Evans", "Courtland Sutton"],
        ["2027 R1 (from vishan)", "2028 R4 (own)"],
    )
    return card["dW"]


def test_lineup_perturbations_never_move_dw(snapshot, league):
    """§11.2: perturb every lineup parameter — the trade ledger is unchanged on
    BOTH sides (the S-solve uses raw v only: no q, no u, no replacement)."""
    base = _dw_ex1(league)
    assert base == {"me": 9093.0, "them": -7941.0}
    for params in PERTURBED:
        league2 = md.build_league(snapshot, params)
        assert _dw_ex1(league2) == base, params


def test_bench_player_never_moves_dw(snapshot, params, league, me):
    """§11.2: add or remove a bench player who cannot crack the max-Σv lineup —
    no ΔW moves. Verified both on an uninvolved third party's roster and on MY
    OWN (the strongest form: my ledger's S is blind to my own bench)."""
    base = _dw_ex1(league)
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
        assert _dw_ex1(league2) == base, (team.name, victim.name)


def test_roster_tweaks_never_move_recommended_pair_dw(snapshot, params, league):
    """§11.2 at board level: knocking an uninvolved third party's bench player
    off the roster leaves every surviving (opponent, give, get) leg priced
    identically on both ledgers."""
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
        key(c): c["dW"]["me"]
        for c in board_legs(tr.trade_board(league))
        if c["counterparty"] != "Jukinski"
    }
    overlap = 0
    for c in board_legs(tr.trade_board(league2)):
        if c["counterparty"] == "Jukinski":
            continue
        if key(c) in base_board:
            overlap += 1
            assert c["dW"]["me"] == base_board[key(c)]
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


def test_pairs_v34_contract(result, params, league):
    """§11.5 / §5 v3.4: every stored pair embeds a gate-PASS buy and sell with
    DISTINCT counterparties sharing no assets, netting for my side EXACTLY
    0 players AND 0 picks (plus the carried Δ(active roster) ≤ 0). The pair's
    ΔW is the EXACT COMBINED ledger — recomputed here from the embedded cards —
    and its return_pct recomputes from that, on face Σv sent. Pairs are unique
    by their asset multisets."""
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
        assert buy["dW_basis"] == sell["dW_basis"] == "isolation"
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
    for pair in pairs[:15]:  # exact-ledger reconstruction on a sample
        got = tr.pair_ledger(league, pair["buy"], pair["sell"])
        assert got["dW"] == pair["dW_combined"]
        assert got["return_pct"] == pair["return_pct"]
        assert {"dS": got["dS"], "dP": got["dP"]} == pair["dW_combined_parts"]
        assert got["sent"] == sum(
            a["v"] for leg in (pair["buy"], pair["sell"]) for a in leg["give"]
        )
        # §5 v3.4.1: the per-leg MARKET returns are pure face arithmetic on the
        # embedded cards — face ΔW(me) ÷ face Σv sent on that leg
        for tag in ("buy", "sell"):
            leg = pair[tag]
            sent = sum(a["v"] for a in leg["give"])
            face_dw = sum(a["v"] for a in leg["get"]) - sent
            assert pair["leg_returns"][tag] == round(100.0 * face_dw / sent, 2)
            assert leg["market_return_pct"] == pair["leg_returns"][tag]
        assert pair["max_leg_return_pct"] == max(pair["leg_returns"].values())


def test_pair_dw_is_combined_not_the_leg_sum(result, league):
    """§2/§5 v3.4: pair ΔW is the two legs applied TOGETHER, never the leg
    sum. The board reports both fields on every pair, and a pinned fixture
    pair shows them DIFFER: buy Josh Jacobs (4,853) from NoahMoell while
    selling Kenneth Walker III (my flex starter) — Jacobs starts ONLY once
    Walker's slot opens, so the buy is worthless alone (ΔS = 0) but worth
    +792 more inside the pair (Jacobs replaces the 4,061 bench fill-in, not
    nothing). Sum −940, combined −148. (Whether such a pair is STORED depends
    on the walk — the arithmetic is the invariant.)"""
    pairs = result["trade_recs"]["pairs"]
    assert all("dW_legs_isolated" in p and "dW_combined" in p for p in pairs)
    buy = tr.propose_by_names(league, "NoahMoell", ["2027 R1 (own)"], ["Josh Jacobs"])
    sell = tr.propose_by_names(
        league, "jaketoppen", ["Kenneth Walker III"], ["2027 R1 (from vishan)"]
    )
    assert buy["dW"]["me"] == -6118.0 and buy["dW_parts"]["me"]["dS"] == 0.0
    assert sell["dW"]["me"] == 5178.0
    pair = tr.pair_ledger(league, buy, sell)
    leg_sum = buy["dW"]["me"] + sell["dW"]["me"]
    assert leg_sum == -940.0
    assert pair["dW"] == -148.0  # combined ≠ sum: the lineup interaction
    assert pair["dW"] - leg_sum == 792.0  # Jacobs (4,853) − the 4,061 fill-in
    # submodularity guarantee (§2): combined is never BELOW the leg sum
    assert pair["dW"] >= leg_sum


def test_buy_legs_are_allowed_to_be_negative_alone(result):
    """§5 v3.4: the per-leg return floor is retired. Buy legs (picks out, a
    player in) are normally negative in isolation and must still reach the
    board inside a pair — the v3.3 floor would have deleted them all."""
    buys = [p["buy"] for p in result["trade_recs"]["pairs"]]
    assert buys
    assert any(b["dW"]["me"] < 0 for b in buys)


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
        assert set(w) == {"counterparty", "give", "get", "dW", "blocker"}
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
    """§11.10: v3.4 puts the exact KTC-calculator gate and a raw starter-sum
    re-solve inside the enumeration, and the exact combined ledger inside the
    pair walk. Measured ≈ 27s on the dev box (v3.3 was ≈ 7s) — bought with an
    incremental exact evaluator, a necessary-condition screen ahead of the
    gate, and bounded walks. The collector Lambda's budget is 600s for the
    whole run (scrape included), so the 90s bound here keeps real headroom
    while still catching the regression that matters: any unbounded walk blows
    straight past it."""
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
