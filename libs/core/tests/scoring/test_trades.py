"""§2 the score, §3 the gate, §5 v3.3 enumerate-then-filter pairing behind the
target-return dial (posture as a hard pair-pool constraint) + §10 worked examples.

§10 pins are computed from the COMMITTED fixtures (data/, 2026-07-26 KTC values,
2026-07-27 transactions). The spec's §10 prose quotes 2026-07-27 live values
(Evans 4,116; ΔW ≈ +1,624 etc.); the fixture-truth numbers pinned here differ
slightly — same trades, same verdicts, exact to this data.
"""

from __future__ import annotations

import pytest

from core.scoring import Params
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
    # §5 v3.2 count deltas: 2 players out, 2 picks in — a building block, not
    # count-neutral alone
    assert card["net_players"] == {"me": -2, "them": 2}
    assert card["net_picks"] == {"me": 2, "them": -2}
    assert card["standalone"] is False
    assert card["sequencing"] == (
        "building block — nets -2 players / +2 picks for you; "
        "not count-neutral alone — pair before executing"
    )
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
    # §5 v3.2: +1 player / −1 pick — needs a −1 player / +1 pick exit to execute
    assert card["net_players"] == {"me": 1, "them": -1}
    assert card["net_picks"] == {"me": -1, "them": 1}
    assert card["standalone"] is False


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
    """§3/§11.3 (v3.3): every displayed leg is in-band, under the cap, and clears
    the return floor on its own Σv sent — W_min is retired as a gate."""
    legs = board_legs(result["trade_recs"])
    assert legs, "board should not be empty on the fixture snapshot"
    for card in legs:
        g = card["gate"]
        assert g["verdict"] == "PASS"
        assert g["gap"] <= g["band"] + 1e-9
        assert card["return_pct"] >= 100 * params.return_floor - 1e-9
        assert card["dW"]["me"] == -card["dW"]["them"]


def test_board_ranking_and_ids(result):
    """§5 v3.3: pairs rank by return on inventory deployed, descending; the
    secondary sell/neutral list by ΔW descending; ids are sequential."""
    doc = result["trade_recs"]
    rets = [p["return_pct"] for p in doc["pairs"]]
    assert rets == sorted(rets, reverse=True)
    assert [p["id"] for p in doc["pairs"]] == [f"P{i + 1}" for i in range(len(doc["pairs"]))]
    recs = doc["recommendations"]
    dws = [c["dW"]["me"] for c in recs]
    assert dws == sorted(dws, reverse=True)
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
    assert board["truncated"] is None
    assert [e["count"] for e in board["counts_by_threshold"]] == [0] * len(board["presets"])
    assert [(b["stored"], b["count"], b["saturated"]) for b in board["bands"]] == [
        (0, 0, False)
    ] * len(board["presets"])


def test_below_noise_floor_note(league):
    """propose() flags a positive ΔW inside the W_min noise band instead of
    hiding it — display note only, never a gate (v3.3)."""
    mine = tr.team_assets(league, league.teams[league.me])
    theirs = tr.team_assets(league, league.teams["jaketoppen"])
    # my 2026 2.09 at tranche 3,504 for their 2028 2nd at 3,579: ΔW +75 < 150
    card = tr.propose(league, "jaketoppen", [mine["2026 2.09"]], [theirs["2028 R2 (own)"]])
    assert card["dW"]["me"] == 75.0
    note = next(n for n in card.get("notes", []) if "noise" in n)
    assert "not a gate" in note



# --------------------------------------- §3 v3.3 ceiling annotation (band edge)


def test_ceiling_is_band_edge_info(result, league, params):
    """Each displayed card's ceiling ≥ the proposal's get value, and the ceiling
    package itself is in-band and fleece-clean (it is the maximum such Σv — pure
    negotiating-room information, never the proposal). v3.3: no W_min edge on
    the reconstruction window — W_min retired as a gate."""
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
            if not (
                give.v_sum / params.fleece_ratio
                <= t.v_sum
                <= params.fleece_ratio * give.v_sum
            ):
                continue
            g = tr.gate_info(league, give, t)
            if not g["band_ok"]:
                continue
            if best is None or t.v_sum > best[0]:
                best = (t.v_sum, g)
        assert best is not None, card["id"]
        assert round(best[0]) == card["ceiling"]["value"], card["id"]
        assert best[1]["band_ok"] and best[1]["ratio_ok"], card["id"]


# ------------------------- §5 v3.3 pair space: count-neutrality, posture, dial


def _fixture_pair_legs(league):
    """The §10.2 buy (millj: my 2028 R3 → Jauan Jennings, +1P/−1pk) and its
    fixture complement (cmgaither43: Sam LaPorta → 2026 1.04, −1P/+1pk) — both
    gate-PASS, distinct counterparties, no shared assets."""
    buy = tr.propose_by_names(league, "millj", ["2028 R3 (own)"], ["Jauan Jennings"])
    sell = tr.propose_by_names(league, "cmgaither43", ["Sam LaPorta"], ["2026 1.04"])
    return buy, sell


def test_pair_count_deltas_both_currencies(league):
    buy, sell = _fixture_pair_legs(league)
    assert buy["gate"]["verdict"] == "PASS" and sell["gate"]["verdict"] == "PASS"
    assert (buy["net_players"]["me"], buy["net_picks"]["me"]) == (1, -1)
    assert (sell["net_players"]["me"], sell["net_picks"]["me"]) == (-1, 1)
    assert tr.pair_count_deltas(buy, sell) == (0, 0)


def test_return_pct_math_pinned(league):
    """§5 v3.3 return-on-inventory arithmetic, pinned to the fixtures:
    buy ΔW +533 on 2,468 sent (21.6%), sell ΔW +1,048 on 5,195 sent (20.17%),
    pair (533+1048)/(2468+5195) = 20.63% — the sent-weighted mediant, strictly
    between the leg returns."""
    buy, sell = _fixture_pair_legs(league)
    assert (buy["dW"]["me"], sum(a["v"] for a in buy["give"])) == (533.0, 2468)
    assert buy["return_pct"] == 21.6
    assert (sell["dW"]["me"], sum(a["v"] for a in sell["give"])) == (1048.0, 5195)
    assert sell["return_pct"] == 20.17
    assert tr.pair_return_pct(buy, sell) == 20.63
    assert sell["return_pct"] < 20.63 < buy["return_pct"]


def test_exhaustiveness_spot_check(league):
    """v3.3 anti-starvation: a known-legal complementary leg pair built by hand
    from the fixtures IS present in the engine's pool and validates as a member
    of the computed pair space at exactly its return — the enumerate-then-filter
    inversion this version exists for."""
    pool = tr.build_pair_pool(league)
    buy, sell = _fixture_pair_legs(league)
    bi = tr.find_pool_leg(
        pool, "millj",
        [a["key"] for a in buy["give"]], [a["key"] for a in buy["get"]],
    )
    si = tr.find_pool_leg(
        pool, "cmgaither43",
        [a["key"] for a in sell["give"]], [a["key"] for a in sell["get"]],
    )
    assert bi is not None and si is not None, "legs missing from the v3.3 pool"
    ret = tr.pair_in_space(league, pool, bi, si)
    assert ret is not None
    assert round(100 * ret, 2) == 20.63 == tr.pair_return_pct(buy, sell)


def test_pinned_negative_count_signature_mismatch(league):
    """v3.2 pinned must-never-pair, restated on the v3.3 machinery: a sell of
    1 player for 2 picks (−1P/+2pk) is player-neutral against the +1P/−1pk buy
    but nets +1 pick — the signatures do not complement, so the pair is never
    in the space (picks count as picks regardless of year)."""
    buy, _ = _fixture_pair_legs(league)
    sell_inflating = tr.propose_by_names(
        league, "cmgaither43", ["Kenneth Walker III"], ["2026 1.04", "2028 R4 (own)"]
    )
    assert sell_inflating["gate"]["verdict"] == "PASS"  # the leg itself is clean
    assert (sell_inflating["net_players"]["me"], sell_inflating["net_picks"]["me"]) == (-1, 2)
    assert tr.pair_count_deltas(buy, sell_inflating) == (0, 1)
    pool = tr.build_pair_pool(league)
    bi = tr.find_pool_leg(
        pool, "millj", [a["key"] for a in buy["give"]], [a["key"] for a in buy["get"]]
    )
    assert bi is not None
    # every pool leg with the (−1, +2) signature refuses to pair with the buy
    for si in pool.buckets.get((-1, 2), [])[:50]:
        assert tr.pair_in_space(league, pool, bi, si) is None


def test_posture_is_a_hard_pair_pool_constraint(league, result):
    """§5 v3.3 pinned negative: ronakpatel32 is the fixture's BUYER — a
    picks-majority package at him passes the §3 gate (my 2026 1.01 for Emeka
    Egbuka, ΔW +583, leg return 9.34%) yet appears NOWHERE in the pair pool or
    on the board; millj (SELLER) likewise never receives players-majority."""
    mine = tr.team_assets(league, league.teams[league.me])
    ron = tr.team_assets(league, league.teams["ronakpatel32"])
    candidate = tr.propose(league, "ronakpatel32", [mine["2026 1.01"]], [ron["Emeka Egbuka"]])
    assert candidate["gate"]["verdict"] == "PASS"
    assert candidate["dW"]["me"] == 583.0 and candidate["return_pct"] == 9.34
    assert candidate["posture"]["label"] == "BUYER"
    assert candidate["posture"]["shape"] == "picks"  # count-majority: 1 pick out

    pool = tr.build_pair_pool(league)
    assert league.postures["ronakpatel32"]["label"] == "BUYER"
    assert league.postures["millj"]["label"] == "SELLER"
    ron_i = pool.opp_names.index("ronakpatel32")
    mil_i = pool.opp_names.index("millj")
    for leg in pool.legs:
        if leg[tr.L_OPP] == ron_i:
            assert tr.offer_shape(leg[tr.L_GIVE]) == "players"
        elif leg[tr.L_OPP] == mil_i:
            assert tr.offer_shape(leg[tr.L_GIVE]) == "picks"
    assert tr.find_pool_leg(pool, "ronakpatel32", ["2026-1.01"], [ron["Emeka Egbuka"].key]) is None
    for card in board_legs(result["trade_recs"]):
        label = card["posture"]["label"]
        assert tr.posture_allows(label, card["posture"]["shape"]), card["id"]


def test_board_pairs_dense_and_honest_on_fixture(result, params):
    """§5 v3.3.1 on the committed fixture: the pair space is deep — EVERY band
    fills to its quota (the v3.3 top-500-overall storage put all 500 pairs at
    ~31%, unable to serve a range query — the pinned regression this replaces),
    the cap is reported via `truncated`, and unfinished bands carry saturated
    verified floors. The [1,2.5) band is fully enumerated (exact) because the
    low end of the space is owned outright by the below-walk."""
    doc = result["trade_recs"]
    bands = doc["bands"]
    assert doc["presets"] == [1.0, 2.5, 5.0, 10.0, 20.0]
    assert doc["pairs"][0]["return_pct"] == 31.72  # fixture pin: global top
    assert len(doc["pairs"]) == sum(b["stored"] for b in bands) == 500
    for b in bands:
        assert b["stored"] == params.pairs_per_band == 100  # every band at quota
        assert b["count"] >= b["stored"]
    assert bands[0]["saturated"] is False  # [1,2.5) fully enumerated
    assert bands[-1]["saturated"] is True  # [20,∞) runs deeper than any budget
    # the flagship range query has real inventory: the [5,10) stored top sits
    # near the band's top edge, not at its floor
    b510 = next(b for b in bands if b["lo"] == 5.0)
    in_range = [p for p in doc["pairs"] if 5.0 <= p["return_pct"] < 10.0]
    assert len(in_range) == b510["stored"] == 100
    assert in_range[0]["return_pct"] > 9.0
    t = doc["truncated"]
    assert t is not None and t["stored"] == 500
    assert t["total"] >= 500 and t["total_saturated"] is True
    for pair in doc["pairs"]:
        assert tr.pair_count_deltas(pair["buy"], pair["sell"]) == (0, 0)
        assert pair["return_pct"] >= 100 * params.return_floor
    for card in doc["recommendations"]:
        assert card["leg_type"] in ("sell", "neutral")
        if card["standalone"]:
            assert (card["net_players"]["me"], card["net_picks"]["me"]) == (0, 0)
            assert "count-neutral" in card["sequencing"]
        else:
            assert "pair before executing" in card["sequencing"]
    for w in doc["watch"]:
        assert "no clean exit" in w["blocker"]
        assert "players" in w["blocker"] and "picks" in w["blocker"]


def test_return_bands_and_membership_math():
    """v3.3.1 range-filter math pinned: bands derive from the presets as
    half-open [lo, hi) intervals with an open top; membership at the edges is
    exact. The fixture pair at 20.63% (§10.2 buy + its complement) lives in
    [20, ∞); the 9.34% ronak leg return lives in [5, 10)."""
    bands = tr.return_bands((1.0, 2.5, 5.0, 10.0, 20.0))
    assert bands == [(1.0, 2.5), (2.5, 5.0), (5.0, 10.0), (10.0, 20.0), (20.0, None)]
    assert tr.band_index(bands, 20.63) == 4  # pinned fixture pair return
    assert tr.band_index(bands, 9.34) == 2  # pinned fixture leg return
    assert tr.band_index(bands, 5.0) == 2 and tr.band_index(bands, 4.99) == 1
    assert tr.band_index(bands, 2.5) == 1 and tr.band_index(bands, 10.0) == 3
    assert tr.band_index(bands, 20.0) == 4 and tr.band_index(bands, 31.72) == 4
    assert tr.band_index(bands, 1.0) == 0
    assert tr.band_index(bands, 0.99) is None  # below the lowest preset: no band


def test_stratified_band_storage_invariant(result, params):
    """v3.3.1 stratification: every stored pair's return sits inside its band,
    per-band storage is capped at the quota and return-desc within the band,
    bands concatenate descending (so the whole list reads return-desc), and an
    unsaturated band stores exactly min(quota, count)."""
    doc = result["trade_recs"]
    bands = doc["bands"]
    edges = [(b["lo"], b["hi"]) for b in bands]
    by_band: dict[int, list[float]] = {i: [] for i in range(len(bands))}
    for p in doc["pairs"]:
        i = tr.band_index(edges, p["return_pct"])
        assert i is not None
        by_band[i].append(p["return_pct"])
    for i, b in enumerate(bands):
        got = by_band[i]
        assert len(got) == b["stored"] <= params.pairs_per_band
        assert got == sorted(got, reverse=True)  # return-desc within band
        for r in got:
            assert r >= b["lo"] and (b["hi"] is None or r < b["hi"])
        assert b["count"] >= b["stored"]
        if not b["saturated"]:
            assert b["stored"] == min(params.pairs_per_band, b["count"])
    rets = [p["return_pct"] for p in doc["pairs"]]
    assert rets == sorted(rets, reverse=True)  # bands concatenated desc
    assert len(doc["pairs"]) == sum(b["stored"] for b in bands)


def test_counts_by_threshold_consistency(result):
    """§5 v3.3 dial counts: thresholds ascend with the presets, counts are
    non-increasing in the threshold, saturation is downward-closed (a saturated
    floor at r saturates every threshold below r), and every count covers the
    stored pairs clearing that threshold."""
    doc = result["trade_recs"]
    entries = doc["counts_by_threshold"]
    assert [e["threshold"] for e in entries] == doc["presets"]
    counts = [e["count"] for e in entries]
    assert counts == sorted(counts, reverse=True)
    sat = [e["saturated"] for e in entries]
    assert sat == sorted(sat, reverse=True)  # True-prefix on ascending thresholds
    for e in entries:
        n_stored = sum(1 for p in doc["pairs"] if p["return_pct"] >= e["threshold"])
        assert e["count"] >= n_stored


def test_counts_by_band_consistent_with_thresholds(result):
    """v3.3.1: presets coincide with band los, so bands ≥ a threshold tile its
    ≥-space exactly. Every threshold count dominates the sum of its bands'
    (floor) counts, equality holds when nothing involved is saturated, a
    saturated threshold implies a saturated band above it, and an exact
    threshold with exact bands is exactly their sum."""
    doc = result["trade_recs"]
    bands = doc["bands"]
    for e in doc["counts_by_threshold"]:
        above = [b for b in bands if b["lo"] >= e["threshold"]]
        assert e["count"] >= sum(b["count"] for b in above)
        assert e["count"] >= sum(b["stored"] for b in above)
        if e["saturated"]:
            assert any(b["saturated"] for b in above)
        if all(not b["saturated"] for b in above):
            assert e["saturated"] is False
            assert e["count"] == sum(b["count"] for b in above)


def test_forced_per_band_truncation_honesty(snapshot):
    """Force per-band truncation with a tiny quota and tiny budgets: every
    non-empty band stores up to the quota, counts stay verified floors at or
    above stored, unsaturated bands store exactly min(quota, count), ids stay
    sequential, ordering stays return-desc, and the compat `truncated` block
    plus the storage-cap note disclose the depth honestly."""
    from core.scoring import model as md

    small = Params(pairs_per_band=2, pair_scan_budget=2000, pair_collect_budget=60_000)
    board = tr.trade_board(md.build_league(snapshot, small))
    bands = board["bands"]
    assert any(b["saturated"] for b in bands)  # the fixture space is deep
    for b in bands:
        assert b["stored"] <= 2
        assert b["count"] >= b["stored"]
        if not b["saturated"]:
            assert b["stored"] == min(2, b["count"])
    assert len(board["pairs"]) == sum(b["stored"] for b in bands) > 0
    assert [p["id"] for p in board["pairs"]] == [
        f"P{i + 1}" for i in range(len(board["pairs"]))
    ]
    rets = [p["return_pct"] for p in board["pairs"]]
    assert rets == sorted(rets, reverse=True)
    edges = [(b["lo"], b["hi"]) for b in bands]
    for p in board["pairs"]:
        i = tr.band_index(edges, p["return_pct"])
        assert i is not None and bands[i]["stored"] > 0
    t = board["truncated"]
    assert t is not None and t["stored"] == len(board["pairs"])
    assert t["total"] > t["stored"]
    assert any("storage cap" in n for n in board["notes"])
    assert any("stratified storage" in n for n in board["notes"])


def test_count_deltas_track_taxi_and_negate_exactly(result, league):
    """§5 v3.2: net_players/net_picks are asset-count arithmetic on the card
    itself (players wherever they land — taxi-routed arrivals included; picks
    regardless of year) and exactly negate across sides."""
    from .conftest import board_legs

    for card in board_legs(result["trade_recs"]):
        np_me = sum(1 for a in card["get"] if a["type"] == "player") - sum(
            1 for a in card["give"] if a["type"] == "player"
        )
        nk_me = sum(1 for a in card["get"] if a["type"] == "pick") - sum(
            1 for a in card["give"] if a["type"] == "pick"
        )
        assert card["net_players"] == {"me": np_me, "them": -np_me}
        assert card["net_picks"] == {"me": nk_me, "them": -nk_me}
        assert card["standalone"] == (np_me == 0 and nk_me == 0)
        assert card["leg_type"] == (
            "buy" if np_me > 0 else "sell" if np_me < 0 else "neutral"
        )
    # taxi routing never hides a count: sending my taxi-stashed Arroyo is −1
    # player for me / +1 for them even though neither active roster changes
    my_assets = tr.team_assets(league, league.teams[league.me])
    jake_assets = tr.team_assets(league, league.teams["jaketoppen"])
    card = tr.propose(
        league, "jaketoppen", [my_assets["Elijah Arroyo"]], [jake_assets["2028 R4 (own)"]]
    )
    assert card["taxi_stashed"]["them"] == ["Elijah Arroyo"]
    assert card["net_roster"] == {"me": 0, "them": 0}
    assert card["net_players"] == {"me": -1, "them": 1}
    assert card["net_picks"] == {"me": 1, "them": -1}
    assert card["leg_type"] == "sell"


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
