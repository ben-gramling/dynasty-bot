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

SCORING = Path(tr.__file__).resolve().parent


# ------------------------------------------------------------------ 1. zero-sum


def test_zero_sum_every_card(result, league):
    """§11.1: ΔW(me) + ΔW(them) = 0 exactly, on every emitted and proposed trade."""
    for card in result["trade_recs"]["recommendations"]:
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
    base_board = {key(c): c["dW"]["me"] for c in tr.trade_board(league)["recommendations"]}
    overlap = 0
    for c in board2["recommendations"]:
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


def test_pairs_are_roster_neutral(result):
    """§11.5: two-leg bundles net Δ(roster count) ≤ 0; every referenced id exists."""
    recs = {c["id"]: c for c in result["trade_recs"]["recommendations"]}
    pairs = result["trade_recs"]["pairs"]
    assert pairs
    complete = 0
    for pair in pairs:
        assert all(leg in recs for leg in pair["legs"])
        if len(pair["legs"]) == 2:
            complete += 1
            buy, sell = (recs[leg] for leg in pair["legs"])
            assert buy["leg_type"] == "buy" and sell["leg_type"] == "sell"
            assert pair["net_roster"] <= 0
            assert pair["net_roster"] == (
                buy["net_roster"]["me"] + sell["net_roster"]["me"]
            )
            assert pair["dW"] == round(buy["dW"]["me"] + sell["dW"]["me"], 1)
            # a bundle never shares an asset between its legs
            keys = lambda c: {a["key"] for a in c["give"] + c["get"]}
            assert not keys(buy) & keys(sell)
        else:
            assert "no hedge" in pair["note"]
    assert complete > 0  # the fixture board does produce whole bundles
    # every buy-leg on the board appears in exactly one pair entry
    buy_ids = {c["id"] for c in recs.values() if c["leg_type"] == "buy"}
    assert sorted(leg for p in pairs for leg in p["legs"][:1]) == sorted(buy_ids)


def test_exclusive_with_fires_on_shared_assets(result):
    """§11.5: any two legs sharing a concrete asset name each other."""
    recs = result["trade_recs"]["recommendations"]
    keys = {c["id"]: {a["key"] for a in c["give"] + c["get"]} for c in recs}
    for a in recs:
        for b in recs:
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
    for card in result["trade_recs"]["recommendations"]:
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
    for card in result["trade_recs"]["recommendations"]:
        for a in card["give"] + card["get"]:
            assert not a.get("unvalued"), card["id"]
        assert card["unvalued"] == []
