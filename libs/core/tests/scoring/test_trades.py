"""§2 the score, §3 the gate (v3.1 minimal-gap proposal policy), §5 enumeration
+ §10 worked examples.

§10 pins are computed from the COMMITTED fixtures (data/, 2026-07-26 KTC values,
2026-07-27 transactions). The spec's §10 prose quotes 2026-07-27 live values
(Evans 4,116; ΔW ≈ +1,624 etc.); the fixture-truth numbers pinned here differ
slightly — same trades, same verdicts, exact to this data.
"""

from __future__ import annotations

import pytest

from core.scoring import trades as tr

from .conftest import board_legs, by_name


def test_give_list_protects_cornerstones_and_skips_unvalued(league, me):
    """§5: all actives except the top-2 by v, plus all picks; taxi and unvalued
    players never enter enumeration."""
    assets = tr.give_list(league, me)
    players = [a.name for a in assets if a.kind == "player"]
    assert "Ashton Jeanty" not in players and "Omarion Hampton" not in players  # top-2
    assert "Darren Waller" not in players  # unvalued (§11.7)
    assert "Cam Ward" not in players and "Elijah Arroyo" not in players  # taxi
    valued_actives = [p for p in me.act if not p.unvalued]
    assert len(players) == len(valued_actives) - 2
    assert sum(1 for a in assets if a.kind == "pick") == len(me.picks) == 11


def test_team_assets_covers_everything(league, me):
    """The propose/CLI pool: every active, taxi player, and pick — cornerstones too."""
    assets = tr.team_assets(league, me)
    assert "Ashton Jeanty" in assets and "Cam Ward" in assets and "Darren Waller" in assets
    assert "2026 1.01" in assets and "2027 R1 (own)" in assets
    a101 = assets["2026 1.01"]
    assert a101.v == 6243  # tranche — the ΔW number
    assert a101.concrete == 7762  # rookie-board slot value — display only


def test_adj_value_consolidation():
    """§3.1: c = (1.00, 0.90, 0.80), sorted v desc; 4th+ asset keeps the last coeff."""
    assert tr.adj_value([4125, 3674], (1.0, 0.9, 0.8)) == 7431.6
    assert tr.adj_value([3674, 4125], (1.0, 0.9, 0.8)) == 7431.6  # order-insensitive
    assert tr.adj_value([1000, 2000, 3000, 4000], (1.0, 0.9, 0.8)) == pytest.approx(
        4000 + 0.9 * 3000 + 0.8 * 2000 + 0.8 * 1000
    )


def test_worked_example_1_sell_leg(league):
    """§10.1: Evans + Sutton → jaketoppen for vishan's 2027 1st + his 2028 4th."""
    card = tr.propose_by_names(
        league, "jaketoppen",
        ["Mike Evans", "Courtland Sutton"],
        ["2027 R1 (from vishan)", "2028 R4 (own)"],
    )
    give = {a["name"]: a["v"] for a in card["give"]}
    get = {a["name"]: a["v"] for a in card["get"]}
    assert give == {"Mike Evans": 4125, "Courtland Sutton": 3674}
    assert get == {"2027 R1 (from vishan)": 7398, "2028 R4 (own)": 1759}
    assert card["dW"] == {"me": 1358.0, "them": -1358.0}  # exact zero-sum
    g = card["gate"]
    assert (g["adj_give"], g["adj_get"]) == (7431.6, 8981.1)
    assert (g["gap"], g["gap_pct"], g["band"]) == (1549.5, 17.3, 1796.2)
    assert g["band_ok"] and g["raw_ratio"] == 1.17 and g["ratio_ok"]
    assert g["verdict"] == "PASS"
    assert card["leg_type"] == "sell"
    assert card["net_roster"] == {"me": -2, "them": 2}
    assert card["sequencing"] == "standalone sell-leg — no pairing needed"
    # aimed at a visible hole: jaketoppen's WR room ranks 10th of 12
    assert card["holes"] == [{"pos": "WR", "their_rank": 10}]
    # anchor-ask note: open 8% above the target package
    assert card["anchor_ask"]["pct"] == 8.0
    assert card["anchor_ask"]["ask"] == round(1.08 * (7398 + 1759))
    # posture annotation from the fixture log (spec prose had jaketoppen a BUYER
    # on live data; the committed window says NEUTRAL — annotation only)
    assert card["posture"]["shape"] == "players"
    assert card["posture"]["label"] in ("BUYER", "SELLER", "NEUTRAL")


def test_worked_example_2_buy_pair_shape(league):
    """§10.2: buy Jauan Jennings from millj for my 2028 3rd — picks → SELLER fit."""
    card = tr.propose_by_names(league, "millj", ["2028 R3 (own)"], ["Jauan Jennings"])
    assert card["dW"] == {"me": 533.0, "them": -533.0}
    g = card["gate"]
    assert (g["adj_give"], g["adj_get"]) == (2468.0, 3001.0)
    assert g["gap_pct"] == 17.8 and g["band_ok"]
    assert g["raw_ratio"] == 1.22 and g["verdict"] == "PASS"
    assert card["leg_type"] == "buy"
    assert card["posture"]["label"] == "SELLER"  # millj: 3 sells on record
    assert card["posture"]["shape"] == "picks" and card["posture"]["fit"] is True
    # buy at the cap: sequencing points at the paired sell (§5)
    assert "sell-leg first" in card["sequencing"]


def test_worked_example_3_fleece_rejected(league):
    """§10.3 pinned must-never-emit: Cam Ward for Shedeur Sanders, ratio 1.87 > 1.35."""
    card = tr.propose_by_names(league, "vishan", ["Cam Ward"], ["Shedeur Sanders"])
    assert card["gate"]["raw_ratio"] == 1.87
    assert card["gate"]["ratio_ok"] is False and card["gate"]["band_ok"] is False
    assert card["gate"]["verdict"].startswith("FAIL")
    # reversed direction is the same fleece for the other side
    rev = tr.propose(
        league, "vishan",
        [tr.team_assets(league, league.teams[league.me])["Cam Ward"]],
        [tr.team_assets(league, league.teams["vishan"])["Shedeur Sanders"]],
    )
    assert rev["gate"]["raw_ratio"] == 1.87


def test_fleece_never_on_board(result):
    """§11.3: the §10.3 shape never surfaces, and no emitted card violates the cap."""
    for card in board_legs(result["trade_recs"]):
        names = ({a["name"] for a in card["give"]}, {a["name"] for a in card["get"]})
        assert names != ({"Cam Ward"}, {"Shedeur Sanders"})
        assert card["gate"]["raw_ratio"] <= 1.35
        assert card["gate"]["ratio_ok"] and card["gate"]["band_ok"]


def test_board_gate_and_floor(result, params):
    """§3/§11.3: every displayed leg is in-band, under the cap, above W_min."""
    legs = board_legs(result["trade_recs"])
    assert legs, "board should not be empty on the fixture snapshot"
    for card in legs:
        g = card["gate"]
        assert g["verdict"] == "PASS"
        assert g["gap"] <= g["band"] + 1e-9
        assert card["dW"]["me"] >= params.w_min
        assert card["dW"]["me"] == -card["dW"]["them"]


def test_board_ranking_and_shape_ordering(result):
    """§5 v3.1: pairs rank fit-first then combined ΔW; the secondary sell list
    likewise (posture-shape rank, then ΔW desc); ids are sequential."""
    doc = result["trade_recs"]
    pair_keys = [
        (
            -(int(p["buy"]["posture"]["fit"]) + int(p["sell"]["posture"]["fit"])),
            -p["dW_combined"],
        )
        for p in doc["pairs"]
    ]
    assert pair_keys == sorted(pair_keys)
    assert [p["id"] for p in doc["pairs"]] == [f"P{i + 1}" for i in range(len(doc["pairs"]))]
    recs = doc["recommendations"]
    rec_keys = [
        (tr._shape_rank(c["posture"]["shape"], c["posture"]["label"]), -c["dW"]["me"])
        for c in recs
    ]
    assert rec_keys == sorted(rec_keys)
    assert [c["id"] for c in recs] == [f"S{i + 1}" for i in range(len(recs))]
    assert [c["rank"] for c in recs] == list(range(1, len(recs) + 1))


def test_concrete_pick_annotation_display_only(result):
    """§1: current-year picks trade at tranche; the board slot value is a note."""
    seen = 0
    for card in board_legs(result["trade_recs"]):
        for a in card["give"] + card["get"]:
            if a["type"] == "pick" and "concrete" in a:
                seen += 1
                assert a["v"] != a["concrete"]
                assert "tranche" in a["note"]
    assert seen > 0  # the fixture board does move 2026 picks


def test_enumeration_bounds(league, params):
    """§5: give-lists bounded by roster arithmetic, packages ≤ 3 a side."""
    for t in league.teams.values():
        assets = tr.give_list(league, t)
        n_players = sum(1 for a in assets if a.kind == "player")
        assert n_players <= len(t.act) - params.give_list_protect_top
        assert sum(1 for a in assets if a.kind == "pick") == len(t.picks)
        pkgs = tr._packages(league, assets)
        assert all(1 <= len(p.assets) <= params.max_package for p in pkgs)


def test_trade_board_disabled_after_deadline(snapshot, params):
    from dataclasses import replace as dc_replace

    from core.scoring import model as md

    late = dc_replace(
        snapshot, state={**dict(snapshot.state), "season_type": "regular", "week": 12}
    )
    league2 = md.build_league(late, params)
    board = tr.trade_board(league2)
    assert board["disabled"] is True
    assert board["recommendations"] == [] and board["pairs"] == [] and board["watch"] == []


def test_below_noise_floor_note(league):
    """propose() flags a positive ΔW under W_min instead of hiding it."""
    mine = tr.team_assets(league, league.teams[league.me])
    theirs = tr.team_assets(league, league.teams["jaketoppen"])
    # my 2026 2.09 at tranche 3,504 for their 2028 2nd at 3,579: ΔW +75 < 150
    card = tr.propose(league, "jaketoppen", [mine["2026 2.09"]], [theirs["2028 R2 (own)"]])
    assert card["dW"]["me"] == 75.0
    assert any("noise floor" in n for n in card.get("notes", []))


# ------------------------------------------------------ §3 v3.1 minimal-gap policy


def _reconstruct_min_gap(league, card):
    """Brute-force the §3 v3.1 selection for a displayed card's give package:
    the smallest in-band gap clearing W_min over the opponent's give-list, with
    the engine's own filters (fleece range, cheap positional legality on both
    sides, per_give_keep window, full §3.3 legality)."""
    params = league.params
    me_t = league.teams[league.me]
    opp_t = league.teams[card["counterparty"]]
    by_key = {a.key: a for a in tr.team_assets(league, me_t).values()}
    give = tr.package_of(league, [by_key[a["key"]] for a in card["give"]])
    alts = []
    for t in tr._packages(league, tr.give_list(league, opp_t)):
        if not (give.v_sum + params.w_min <= t.v_sum <= params.fleece_ratio * give.v_sum):
            continue
        gap = abs(t.adjv - give.adjv)
        band = max(params.fairness_abs, params.fairness_rel * max(t.adjv, give.adjv))
        if gap > band:
            continue
        if not tr._pos_legal_cheap(me_t, give.pos_out, t.pos_out, t.n_players - give.n_players):
            continue
        if not tr._pos_legal_cheap(opp_t, t.pos_out, give.pos_out, give.n_players - t.n_players):
            continue
        alts.append((gap, t.keys, t))
    alts.sort(key=lambda x: x[0])
    for gap, _keys, t in alts[: params.per_give_keep]:
        if tr.legality(league, me_t, opp_t, give, t)["legal"]:
            return gap
    return None


def test_board_proposals_sit_at_the_minimal_gap(result, league):
    """v3.1 invariant 1: every board proposal's gap is the MINIMUM among in-band
    alternatives for its give package clearing W_min — verified by reconstruction
    for a sample of displayed legs (the band is a tolerance, not a target)."""
    legs = board_legs(result["trade_recs"])
    sample = legs[:3] + legs[-2:]
    assert sample
    for card in sample:
        min_gap = _reconstruct_min_gap(league, card)
        assert min_gap is not None, card["id"]
        assert round(min_gap, 1) == card["gate"]["gap"], card["id"]


def test_ceiling_is_band_edge_info(result, league, params):
    """v3.1 invariant 4: each displayed card's ceiling ≥ the proposal's get value,
    and the ceiling package itself is in-band and fleece-clean (it is the maximum
    such Σv — pure negotiating-room information, never the proposal)."""
    legs = board_legs(result["trade_recs"])
    assert legs
    me_t = league.teams[league.me]
    by_key = {a.key: a for a in tr.team_assets(league, me_t).values()}
    for card in legs:
        get_sum = sum(a["v"] for a in card["get"])
        assert card["ceiling"]["value"] + 0.5 >= get_sum, card["id"]
    for card in legs[:3]:  # full reconstruction on a sample
        give = tr.package_of(league, [by_key[a["key"]] for a in card["give"]])
        opp_t = league.teams[card["counterparty"]]
        best = None
        for t in tr._packages(league, tr.give_list(league, opp_t)):
            if not (give.v_sum + params.w_min <= t.v_sum <= params.fleece_ratio * give.v_sum):
                continue
            g = tr.gate_info(league, give, t)
            if not g["band_ok"]:
                continue
            if best is None or t.v_sum > best[0]:
                best = (t.v_sum, g)
        assert best is not None, card["id"]
        assert round(best[0]) == card["ceiling"]["value"], card["id"]
        assert best[1]["band_ok"] and best[1]["ratio_ok"], card["id"]


def test_unvalued_flagged_in_propose(league):
    """§11.7: an unvalued asset contributes 0 to ΔW and is loudly flagged."""
    mine = tr.team_assets(league, league.teams[league.me])
    theirs = tr.team_assets(league, league.teams["jaketoppen"])
    base = tr.propose(
        league, "jaketoppen",
        [mine["Mike Evans"], mine["Courtland Sutton"]],
        [theirs["2027 R1 (from vishan)"], theirs["2028 R4 (own)"]],
    )
    with_waller = tr.propose(
        league, "jaketoppen",
        [mine["Mike Evans"], mine["Courtland Sutton"], mine["Darren Waller"]],
        [theirs["2027 R1 (from vishan)"], theirs["2028 R4 (own)"]],
    )
    assert with_waller["dW"] == base["dW"]  # v=0 never moves the score silently
    assert with_waller["unvalued"] == ["Darren Waller"]
    waller = next(a for a in with_waller["give"] if a["name"] == "Darren Waller")
    assert waller.get("unvalued") is True
    assert any("unvalued" in n.lower() for n in with_waller["notes"])
