"""§11 implementation invariants: zero-sum, independence from the lineup model,
import graph, bundles, exclusivity, legality, determinism, runtime.

Pins computed from the COMMITTED fixtures (see test_trades docstring)."""

from __future__ import annotations

import ast
import json
import time
from dataclasses import replace as dc_replace
from pathlib import Path

import pytest

from core.scoring import Params, compute_all
from core.scoring import model as md
from core.scoring import trades as tr

from .conftest import board_legs

SCORING = Path(tr.__file__).resolve().parent


# ------------------------------------------------------------------ 1. zero-sum


def test_zero_sum_every_card(result, league):
    """§11.1: ΔW(me) + ΔW(them) = 0 exactly, on every emitted and proposed trade."""
    for card in board_legs(result["trade_recs"]):
        assert card["dW"]["me"] + card["dW"]["them"] == 0.0
    for give, get in (
        (["Mike Evans", "Courtland Sutton"], ["2027 R1 (from vishan)", "2028 R4 (own)"]),
        (["2026 1.01"], ["Nico Collins"]),
    ):
        card = tr.propose_by_names(league, "jaketoppen", give, get)
        assert card["dW"]["me"] + card["dW"]["them"] == 0.0


# ------------------------------------------------ 2. independence + import graph


PERTURBED = [
    Params(q_qb=0.5, q_rb=0.01, q_wr=0.4, q_te=0.02, q_flex=0.3),
    Params(replacement_fa_rank=8),
    Params(u_out_long=0.9, u_out_short=0.95),
    Params(taxi_insurance_mult=0.75),
]


def _dw_101(league):
    card = tr.propose_by_names(
        league, "jaketoppen",
        ["Mike Evans", "Courtland Sutton"],
        ["2027 R1 (from vishan)", "2028 R4 (own)"],
    )
    return card["dW"]["me"]


def test_lineup_perturbations_never_move_dw(snapshot, league):
    """§11.2: perturb every lineup parameter — trade ΔW is unchanged."""
    base = _dw_101(league)
    assert base == 1358.0
    for params in PERTURBED:
        league2 = md.build_league(snapshot, params)
        assert _dw_101(league2) == base, params


def test_roster_tweaks_never_move_dw(snapshot, params, league):
    """§11.2: remove a bench player from any uninvolved roster — ΔW unchanged."""
    base = _dw_101(league)
    # knock a bench player off Jukinski (uninvolved third party)
    juk = league.teams["Jukinski"]
    bench = sorted(
        (p for p in juk.act if p.sid not in juk.lineup.starter_ids), key=lambda p: p.sid
    )[0]
    rosters = []
    for r in snapshot.rosters:
        r = dict(r)
        if r["roster_id"] == juk.rid:
            r["players"] = [sid for sid in r["players"] if sid != bench.sid]
        rosters.append(r)
    league2 = md.build_league(dc_replace(snapshot, rosters=rosters), params)
    assert _dw_101(league2) == base
    # and a board-level cross-check: same (opp, give, get) legs price identically
    board2 = tr.trade_board(league2)
    key = lambda c: (
        c["counterparty"],
        tuple(sorted(a["key"] for a in c["give"])),
        tuple(sorted(a["key"] for a in c["get"])),
    )
    base_board = {key(c): c["dW"]["me"] for c in board_legs(tr.trade_board(league))}
    overlap = 0
    for c in board_legs(board2):
        if key(c) in base_board:
            overlap += 1
            assert c["dW"]["me"] == base_board[key(c)]
    assert overlap > 0


def test_trade_and_posture_import_no_lineup():
    """§11.2 grep-level: the trade scoring path imports nothing from lineup.py.
    (Roster-legality mechanics live in model.apply_tx; no ΔW input flows from them —
    the perturbation regressions above enforce that.)"""
    for mod in ("trades.py", "posture.py"):
        tree = ast.parse((SCORING / mod).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
                assert not any("lineup" in n for n in names), (mod, names)
            elif isinstance(node, ast.ImportFrom):
                assert "lineup" not in (node.module or ""), (mod, node.module)
                assert not any("lineup" in a.name for a in node.names), mod
    # posture additionally imports nothing from the scoring package at all
    tree = ast.parse((SCORING / "posture.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("core."), node.module


# ------------------------------------------------------- 5. bundles + exclusivity


def test_pairs_v32_contract(result, params, league):
    """§11.5 / §5 v3.2 strict: every pair embeds a gate-PASS buy and sell sharing
    no assets, netting for my side EXACTLY 0 players AND 0 picks (plus the carried
    Δ(active roster) ≤ 0), with honest combined ΔW; each buy/sell core appears at
    most once. The committed fixture yields zero pairs under strict count
    neutrality (pinned in test_trades) — the per-pair contract is exercised on a
    fixture-built pair through the same selection code."""
    pairs = result["trade_recs"]["pairs"]
    assert 0 <= len(pairs) <= params.max_pairs
    keys = lambda c: {a["key"] for a in c["give"] + c["get"]}
    # exercise the contract even when the board is honestly empty: run a real
    # gate-PASS complementary buy/sell through _select_pairs and wrap like the board
    from .test_trades import _v32_buy, _with_build_fields

    if not pairs:
        buy = _v32_buy(league)
        sell = _with_build_fields(
            tr.propose_by_names(league, "cmgaither43", ["Sam LaPorta"], ["2026 1.04"]),
            "sell",
        )
        kept, _ = tr._select_pairs([buy], [sell], params.max_pairs)
        assert kept
        pairs = [
            {
                "buy": b,
                "sell": s,
                "dW_combined": round(b["dW"]["me"] + s["dW"]["me"], 1),
                "net_roster": b["net_roster"]["me"] + s["net_roster"]["me"],
                "net_players": tr.pair_count_deltas(b, s)[0],
                "net_picks": tr.pair_count_deltas(b, s)[1],
                "fit_summary": "buy leg fits posture",
                "sequencing": "roster space available: the buy may execute first",
            }
            for b, s in kept
        ]
    for pair in pairs:
        buy, sell = pair["buy"], pair["sell"]
        assert buy["leg_type"] == "buy" and sell["leg_type"] == "sell"
        assert buy["gate"]["verdict"] == "PASS" and sell["gate"]["verdict"] == "PASS"
        assert not keys(buy) & keys(sell)  # invariant 3: no shared assets
        # §5 v3.2: both currencies zero, exactly — players wherever they land,
        # picks regardless of year
        assert tr.pair_count_deltas(buy, sell) == (0, 0)
        assert pair["net_players"] == 0 and pair["net_picks"] == 0
        assert pair["net_roster"] <= 0
        assert pair["net_roster"] == buy["net_roster"]["me"] + sell["net_roster"]["me"]
        assert pair["dW_combined"] == round(buy["dW"]["me"] + sell["dW"]["me"], 1)
        # different counterparties (required unless a buy has no other exit)
        assert buy["counterparty"] != sell["counterparty"]
        assert pair["fit_summary"] in (
            "both legs fit posture",
            "buy leg fits posture",
            "sell leg fits posture",
            "neither leg fits posture",
        )
        assert "sell" in pair["sequencing"] or "buy may execute first" in pair["sequencing"]


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


def test_exclusive_with_fires_on_shared_assets(result):
    """§11.5: any two DISPLAYED legs sharing a concrete asset name each other."""
    legs = board_legs(result["trade_recs"])
    keys = {c["id"]: {a["key"] for a in c["give"] + c["get"]} for c in legs}
    for a in legs:
        for b in legs:
            if a["id"] == b["id"]:
                continue
            if keys[a["id"]] & keys[b["id"]]:
                assert b["id"] in a["exclusive_with"], (a["id"], b["id"])
            else:
                assert b["id"] not in a["exclusive_with"], (a["id"], b["id"])


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
    """§11.10: v3 has no solver in the trade path — strictly cheaper than v1
    (v1 measured 8.2s on the dev box; v3 ≈ 1.2s). Generous absolute bound."""
    t0 = time.perf_counter()
    compute_all(snapshot, params)
    assert time.perf_counter() - t0 < 30.0


# ------------------------------------------------------------------ output shape


def test_unvalued_never_in_board_recs(result):
    """§11.7: enumeration never floats a zero-value asset into a package."""
    for card in board_legs(result["trade_recs"]):
        for a in card["give"] + card["get"]:
            assert not a.get("unvalued"), card["id"]
        assert card["unvalued"] == []
