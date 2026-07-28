"""§2 the wealth ledger, §3 the exact-KTC gate, §5 v3.3 enumerate-then-filter
pairing behind the target-return dial (posture as a hard pair-pool constraint)
+ §10 worked examples.

§10 pins are computed from the COMMITTED fixtures (data/, 2026-07-26 KTC values,
2026-07-27 transactions) and are exact to this data; the spec's §10 prose quotes
the same trades.
"""

from __future__ import annotations

from core.scoring import Params
from core.scoring import ktc_adjust as ka
from core.scoring import trades as tr

from .conftest import board_legs


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
    assert a101.v == 6243  # tranche — the ledger and gate number
    assert a101.concrete == 7762  # rookie-board slot value — display only


def test_gate_is_the_exact_ktc_calculator(league):
    """§3.1 v3.4: the band compares the two totals KTC's OWN trade calculator
    displays — `gate_info` is a thin wrapper over the pinned port, and the top
    overall KTC value in the snapshot supplies the cap C."""
    assert league.top_ktc_value == 9998.0  # fixture: Bijan Robinson
    mine = tr.team_assets(league, league.teams[league.me])
    theirs = tr.team_assets(league, league.teams["jaketoppen"])
    give = tr.package_of(league, [mine["Mike Evans"], mine["Courtland Sutton"]])
    get = tr.package_of(
        league, [theirs["2027 R1 (from vishan)"], theirs["2028 R4 (own)"]]
    )
    g = tr.gate_info(league, give, get)
    direct = ka.ktc_adjustment(
        [4125.0, 3674.0], [7398.0, 1759.0], top_value=league.top_ktc_value
    )
    assert (g["adj_give"], g["adj_get"]) == (
        float(direct["adj_total1"]),
        float(direct["adj_total2"]),
    )
    # the concentrated pick side is topped up — the adjustment does not cancel
    assert direct["side"] == 2 and direct["value"] > 0
    assert g["gap"] == round(abs(g["adj_give"] - g["adj_get"]), 1)


def test_worked_example_1_sell_leg(league):
    """§10.1: Evans + Sutton → jaketoppen for vishan's 2027 1st + his 2028 4th.
    v3.4 flips this one: the LEDGER loves it (+9,093 — two players who barely
    reach my max-Σv lineup become 9,157 of pick wealth), but the exact KTC
    calculator prices the concentrated 7,398 pick far above two mid WRs, so the
    gap lands at 36.8% against a 20% band and the gate REJECTS it. Under v3.3's
    fitted consolidation curve the same trade read 17.3% and passed."""
    card = tr.propose_by_names(
        league, "jaketoppen",
        ["Mike Evans", "Courtland Sutton"],
        ["2027 R1 (from vishan)", "2028 R4 (own)"],
    )
    give = {a["name"]: a["v"] for a in card["give"]}
    get = {a["name"]: a["v"] for a in card["get"]}
    assert give == {"Mike Evans": 4125, "Courtland Sutton": 3674}
    assert get == {"2027 R1 (from vishan)": 7398, "2028 R4 (own)": 1759}
    # §2 v3.4 per-side ledger — NOT a negation
    assert card["dW"] == {"me": 9093.0, "them": -7941.0}
    assert card["dW_parts"] == {
        "me": {"dS": -64.0, "dP": 9157.0},
        "them": {"dS": 1216.0, "dP": -9157.0},
    }
    assert card["dW_basis"] == "isolation"
    g = card["gate"]
    assert (g["adj_give"], g["adj_get"]) == (7799.0, 12339.0)
    assert (g["gap"], g["gap_pct"], g["band"]) == (4540.0, 36.8, 2467.8)
    assert g["band_ok"] is False
    assert g["raw_ratio"] == 1.17 and g["ratio_ok"]
    assert g["verdict"] == "FAIL: outside fairness band (gap 36.8% > band)"
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
    assert card["anchor_ask"]["pct"] == 8.0
    assert card["anchor_ask"]["ask"] == round(1.08 * (7398 + 1759))
    assert card["posture"]["shape"] == "players"
    assert card["posture"]["label"] in ("BUYER", "SELLER", "NEUTRAL")


def test_worked_example_2_buy_leg_negative_alone(league):
    """§10.2: buy Jauan Jennings from millj for my 2028 3rd. v3.4 makes the
    isolation ledger honest — Jennings does not crack my max-Σv lineup, so the
    buy is a pure 2,468 pick spend for 0 starter value; and the exact gate
    rejects it besides (a 3,026 player outweighs a 2,468 pick by 1,430
    adjusted, a 36.7% gap). The shape (picks → SELLER) is still right."""
    card = tr.propose_by_names(league, "millj", ["2028 R3 (own)"], ["Jauan Jennings"])
    assert card["dW"] == {"me": -2468.0, "them": 2468.0}
    assert card["dW_parts"]["me"] == {"dS": 0.0, "dP": -2468.0}
    g = card["gate"]
    assert (g["adj_give"], g["adj_get"]) == (2468.0, 3898.0)
    assert (g["gap"], g["gap_pct"], g["band"]) == (1430.0, 36.7, 779.6)
    assert g["band_ok"] is False
    assert g["raw_ratio"] == 1.22 and g["ratio_ok"] is True
    assert g["verdict"].startswith("FAIL")
    assert card["leg_type"] == "buy"
    assert card["posture"]["label"] == "SELLER"  # millj: 3 sells on record
    assert card["posture"]["shape"] == "picks" and card["posture"]["fit"] is True
    assert "sell-leg first" in card["sequencing"]
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


def test_board_gate_recomputes_exactly(result, league):
    """§3/§11.3 (v3.4): every displayed leg is inside the EXACT KTC-calculator
    band and under the fleece cap, and the card's gate figures reproduce from a
    fresh gate_info call (no stale or approximated adjusted totals). The screen
    the pool scan runs ahead of the gate never lets a violator through."""
    legs = board_legs(result["trade_recs"])
    assert legs, "board should not be empty on the fixture snapshot"
    for card in legs:
        g = card["gate"]
        assert g["verdict"] == "PASS"
        assert g["gap"] <= g["band"] + 1e-9
    for card in legs[:25]:  # full recomputation on a sample
        give, get = tr.card_packages(league, card)
        fresh = tr.gate_info(league, give, get)
        for k in ("adj_give", "adj_get", "gap", "band", "band_ok", "raw_ratio", "ratio_ok"):
            assert fresh[k] == card["gate"][k], (card["id"], k)


def test_pool_screen_never_rejects_a_gate_passer(league):
    """§11.3: the pool scan short-circuits on a cheap necessary condition before
    paying for the exact KTC adjustment. The screen must be one-sided — it may
    let a failure through (the gate catches it) but must NEVER reject a trade
    the gate would pass. Checked exhaustively over the fleece bracket of a
    sample of my give-packages against a full opponent give-list."""
    params = league.params
    cap = league.top_ktc_value + 80.0
    me_t = league.teams[league.me]
    my_pkgs = tr._packages(league, tr.give_list(league, me_t))[::37]
    opp_pkgs = tr._packages(league, tr.give_list(league, league.teams["jaketoppen"]))[::11]
    assert my_pkgs and opp_pkgs
    screened_out = passers = 0
    for g in my_pkgs:
        for t in opp_pkgs:
            if not (
                g.v_sum / params.fleece_ratio <= t.v_sum <= params.fleece_ratio * g.v_sum
            ):
                continue
            r_max = max(g.max_v, t.max_v)
            raw_gap = abs(
                tr._raw_adj_total(g.vals, r_max, cap)
                - tr._raw_adj_total(t.vals, r_max, cap)
            )
            b_star = max(500.0, 0.25 * max(g.v_sum, t.v_sum))
            rejected = raw_gap > 1.15 * tr._process_v0(b_star, r_max, cap)
            band_ok = tr.gate_info(league, g, t)["band_ok"]
            if band_ok:
                passers += 1
                assert not rejected, (g.keys, t.keys)  # one-sided: never a miss
            screened_out += int(rejected)
    assert passers > 0 and screened_out > 0  # both branches exercised


def test_board_ranking_and_ids(result):
    """§5 v3.4.1: pairs sort by TOTAL return desc — ALWAYS, whatever the cap
    filter later selects; the secondary sell/neutral list by isolation ΔW
    descending; ids are sequential."""
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
    assert card["dW_parts"]["me"] == {"dS": 0.0, "dP": 75.0}
    note = next(n for n in card.get("notes", []) if "noise" in n)
    assert "not a gate" in note


# --------------------------------------- §3 v3.4 ceiling annotation (band edge)


def test_ceiling_is_band_edge_info(result, league, params):
    """Each displayed card's ceiling ≥ the proposal's get value, and the ceiling
    package itself clears the exact gate and the fleece cap (it is the maximum
    such Σv — pure negotiating-room information, never the proposal). v3.4: the
    exact band is not monotone in Σv, so the reconstruction scans the whole
    fleece bracket instead of stopping at the first miss."""
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


# ------------------------- §5 v3.4 pair space: count-neutrality, posture, dial


def _fixture_pair_legs(league):
    """A gate-PASS complementary pair from the fixture board: the buy (my 2028
    4th → cmgaither43's George Holani, +1P/−1pk) and the sell (Joe Burrow + my
    2026 4.01 → Jukinski's 2026 1.12 + 2028 1st, −1P/+1pk). Distinct
    counterparties, no shared assets."""
    buy = tr.propose_by_names(league, "cmgaither43", ["2028 R4 (own)"], ["George Holani"])
    sell = tr.propose_by_names(
        league, "Jukinski", ["Joe Burrow", "2026 4.01"], ["2026 1.12", "2028 R1 (own)"]
    )
    return buy, sell


def test_pair_count_deltas_both_currencies(league):
    buy, sell = _fixture_pair_legs(league)
    assert buy["gate"]["verdict"] == "PASS" and sell["gate"]["verdict"] == "PASS"
    assert (buy["net_players"]["me"], buy["net_picks"]["me"]) == (1, -1)
    assert (sell["net_players"]["me"], sell["net_picks"]["me"]) == (-1, 1)
    assert tr.pair_count_deltas(buy, sell) == (0, 0)


def test_pair_ledger_math_pinned(league):
    """§5 v3.4 return-on-inventory arithmetic, pinned to the fixtures. The buy
    leg is NEGATIVE alone (−1,759: a pick out, a player who never starts in) —
    exactly the shape v3.3's per-leg return floor used to delete. The sell leg
    recoups (+6,516 = starters −1,312, picks +7,828), and the PAIR is the
    combined ledger over the face Σv sent across both legs:
    4,757 ÷ 9,536 = 49.88%."""
    buy, sell = _fixture_pair_legs(league)
    assert (buy["dW"]["me"], sum(a["v"] for a in buy["give"])) == (-1759.0, 1759)
    assert buy["return_pct"] == -100.0
    assert (sell["dW"]["me"], sum(a["v"] for a in sell["give"])) == (6516.0, 7777)
    assert sell["dW_parts"]["me"] == {"dS": -1312.0, "dP": 7828.0}
    pair = tr.pair_ledger(league, buy, sell)
    assert pair == {
        "dS": -1312.0,
        "dP": 6069.0,
        "dW": 4757.0,
        "sent": 9536.0,
        "return_pct": 49.88,
    }


def test_exhaustiveness_spot_check(league, pool):
    """v3.3 anti-starvation, v3.4 pricing: a known-legal complementary leg pair
    built by hand from the fixtures IS present in the engine's pool and
    validates as a member of the computed pair space at exactly its EXACT
    combined return."""
    buy, sell = _fixture_pair_legs(league)
    bi = tr.find_pool_leg(
        pool, "cmgaither43",
        [a["key"] for a in buy["give"]], [a["key"] for a in buy["get"]],
    )
    si = tr.find_pool_leg(
        pool, "Jukinski",
        [a["key"] for a in sell["give"]], [a["key"] for a in sell["get"]],
    )
    assert bi is not None and si is not None, "legs missing from the v3.4 pool"
    ret = tr.pair_in_space(league, pool, bi, si)
    assert ret is not None
    assert round(100 * ret, 2) == 49.88 == tr.pair_ledger(league, buy, sell)["return_pct"]


def test_pinned_negative_count_signature_mismatch(league, pool):
    """v3.2 pinned must-never-pair, restated on the v3.4 machinery: a sell of
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
    bi = tr.find_pool_leg(
        pool, "cmgaither43", [a["key"] for a in buy["give"]], [a["key"] for a in buy["get"]]
    )
    assert bi is not None
    # every pool leg with the (−1, +2) signature refuses to pair with the buy
    for si in pool.buckets.get((-1, 2), [])[:50]:
        assert tr.pair_in_space(league, pool, bi, si) is None


def test_posture_is_a_hard_pair_pool_constraint(league, pool, result):
    """§5 v3.3 pinned negative: ronakpatel32 is the fixture's BUYER — a
    picks-majority package at him passes the §3 gate (my 2026 1.01 for Lamar
    Jackson: ledger ΔW −5,731 in isolation, gap 0.8%) yet appears NOWHERE in
    the pair pool or on the board; millj (SELLER) likewise never receives
    players-majority."""
    mine = tr.team_assets(league, league.teams[league.me])
    ron = tr.team_assets(league, league.teams["ronakpatel32"])
    candidate = tr.propose(league, "ronakpatel32", [mine["2026 1.01"]], [ron["Lamar Jackson"]])
    assert candidate["gate"]["verdict"] == "PASS"
    assert candidate["dW"]["me"] == -5731.0 and candidate["gate"]["gap_pct"] == 0.8
    assert candidate["posture"]["label"] == "BUYER"
    assert candidate["posture"]["shape"] == "picks"  # count-majority: 1 pick out

    assert league.postures["ronakpatel32"]["label"] == "BUYER"
    assert league.postures["millj"]["label"] == "SELLER"
    ron_i = pool.opp_names.index("ronakpatel32")
    mil_i = pool.opp_names.index("millj")
    for leg in pool.legs:
        if leg[tr.L_OPP] == ron_i:
            assert tr.offer_shape(leg[tr.L_GIVE]) == "players"
        elif leg[tr.L_OPP] == mil_i:
            assert tr.offer_shape(leg[tr.L_GIVE]) == "picks"
    assert tr.find_pool_leg(pool, "ronakpatel32", ["2026-1.01"], [ron["Lamar Jackson"].key]) is None
    for card in board_legs(result["trade_recs"]):
        label = card["posture"]["label"]
        assert tr.posture_allows(label, card["posture"]["shape"]), card["id"]


def test_board_pairs_dense_and_honest_on_fixture(result, params):
    """§5 v3.4.1 on the committed fixture: the pair space is deep — EVERY
    max-leg bucket fills to its quota, the cap is reported via `truncated`,
    and every count is a saturated verified floor (v3.4: the walk orders legs
    by their ISOLATION ΔWs while pairs are priced by the EXACT combined
    ledger, so no cutoff can certify completeness)."""
    doc = result["trade_recs"]
    bands = doc["bands"]
    assert doc["presets"] == [1.0, 2.5, 5.0, 10.0, 20.0]
    assert doc["leg_cap_presets"] == [2.5, 5.0, 10.0, 20.0]
    assert doc["pairs"][0]["return_pct"] == 49.88  # fixture pin: global top
    # the top pair is lopsided in market terms — its sell leg skims 26.8% face
    assert doc["pairs"][0]["leg_returns"] == {"buy": 6.65, "sell": 26.8}
    assert doc["pairs"][0]["max_leg_return_pct"] == 26.8
    assert len(doc["pairs"]) == sum(b["stored"] for b in bands) == 500
    for b in bands:
        assert b["stored"] == params.pairs_per_band == 100  # every bucket at quota
        assert b["count"] >= b["stored"]
        assert b["saturated"] is True  # verified floors throughout (v3.4)
        assert sum(b["by_total"]) == b["count"]  # the grid partitions the bucket
    # the flagship v3.4.1 query — high total floor UNDER a tight leg cap —
    # has real inventory: cap 2.5% selects the (−∞,2.5) bucket, whose stored
    # top-by-total all clear a 5% total floor with balanced legs
    flagship = [
        p for p in doc["pairs"]
        if p["return_pct"] >= 5.0 and p["max_leg_return_pct"] < 2.5
    ]
    assert len(flagship) == 100
    assert flagship[0]["return_pct"] == 49.76  # fixture pin: even legs, huge total
    assert flagship[0]["max_leg_return_pct"] < 2.5
    t = doc["truncated"]
    assert t is not None and t["stored"] == 500
    assert t["total"] >= 500 and t["total_saturated"] is True
    for pair in doc["pairs"]:
        assert tr.pair_count_deltas(pair["buy"], pair["sell"]) == (0, 0)
        assert pair["return_pct"] >= doc["presets"][0]
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


def test_return_bands_and_bucket_math():
    """v3.4.1 filter math pinned: total-return bands derive from the floor
    presets as half-open [lo, hi) intervals (open top); max-leg BUCKETS derive
    from the cap presets as half-open intervals open at BOTH ends — buy legs
    are normally negative in market return, so the bottom bucket must reach
    −∞. A cap preset `c` selects exactly the buckets with hi ≤ c."""
    bands = tr.return_bands((1.0, 2.5, 5.0, 10.0, 20.0))
    assert bands == [(1.0, 2.5), (2.5, 5.0), (5.0, 10.0), (10.0, 20.0), (20.0, None)]
    assert tr.band_index(bands, 49.88) == 4  # pinned fixture pair total
    assert tr.band_index(bands, 5.0) == 2 and tr.band_index(bands, 4.99) == 1
    assert tr.band_index(bands, 2.5) == 1 and tr.band_index(bands, 10.0) == 3
    assert tr.band_index(bands, 1.0) == 0
    assert tr.band_index(bands, 0.99) is None  # below the lowest preset: no band

    buckets = tr.leg_buckets((2.5, 5.0, 10.0, 20.0))
    assert buckets == [
        (None, 2.5), (2.5, 5.0), (5.0, 10.0), (10.0, 20.0), (20.0, None),
    ]
    assert tr.bucket_index(buckets, -100.0) == 0  # a pure-spend buy leg
    assert tr.bucket_index(buckets, 0.0) == 0
    assert tr.bucket_index(buckets, 2.49) == 0
    assert tr.bucket_index(buckets, 2.5) == 1  # the cap is exclusive at c
    assert tr.bucket_index(buckets, 4.99) == 1
    assert tr.bucket_index(buckets, 26.8) == 4  # pinned fixture max leg
    # cap-selection identity: max_leg < c ⟺ bucket.hi ≤ c, for every preset
    for c in (2.5, 5.0, 10.0, 20.0):
        selected = {i for i, (_lo, hi) in enumerate(buckets) if hi is not None and hi <= c}
        for m in (-3.0, 0.0, 2.49, 2.5, 4.99, 5.0, 9.99, 10.0, 19.99, 20.0, 26.8):
            assert (tr.bucket_index(buckets, m) in selected) == (m < c), (c, m)


def test_bucket_storage_invariant(result, params):
    """v3.4.1 stratification: every stored pair's MAX LEG market return sits
    inside its bucket, per-bucket storage is capped at the quota, each
    bucket's stored pairs read TOTAL-return-desc, and the flat list is sorted
    by total return desc globally (the cap dial filters, never re-orders)."""
    doc = result["trade_recs"]
    bands = doc["bands"]
    edges = [(b["lo"], b["hi"]) for b in bands]
    by_bucket: dict[int, list[float]] = {i: [] for i in range(len(bands))}
    for p in doc["pairs"]:
        m = p["max_leg_return_pct"]
        assert m == max(p["leg_returns"]["buy"], p["leg_returns"]["sell"])
        i = tr.bucket_index(edges, m)
        lo, hi = edges[i]
        assert lo is None or m >= lo
        assert hi is None or m < hi
        by_bucket[i].append(p["return_pct"])
    for i, b in enumerate(bands):
        got = by_bucket[i]
        assert len(got) == b["stored"] <= params.pairs_per_band
        assert got == sorted(got, reverse=True)  # total-desc within the bucket
        assert b["count"] >= b["stored"]
        if not b["saturated"]:
            assert b["stored"] == min(params.pairs_per_band, b["count"])
    rets = [p["return_pct"] for p in doc["pairs"]]
    assert rets == sorted(rets, reverse=True)  # global sort: total return desc
    assert len(doc["pairs"]) == sum(b["stored"] for b in bands)


def test_counts_by_threshold_consistency(result):
    """§5 floor-dial counts (compat, TOTAL return): thresholds ascend with the
    presets, counts are non-increasing in the threshold, saturation is
    downward-closed, and every count covers the stored pairs clearing that
    threshold."""
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


def test_grid_consistent_with_buckets_and_thresholds(result):
    """v3.4.1 grid honesty: each bucket's `by_total` row partitions its count
    exactly; the grid's columns at or above a floor preset sum (across every
    bucket) to that threshold's count; and every (floor, cap) cell read is a
    floor for the stored pairs matching both dials."""
    doc = result["trade_recs"]
    bands = doc["bands"]
    presets = doc["presets"]
    for b in bands:
        assert len(b["by_total"]) == len(presets)
        assert all(n >= 0 for n in b["by_total"])
        assert sum(b["by_total"]) == b["count"]  # rows partition the bucket
    for k, e in enumerate(doc["counts_by_threshold"]):
        col_sum = sum(sum(b["by_total"][k:]) for b in bands)
        assert e["count"] >= col_sum
        n_stored = sum(1 for p in doc["pairs"] if p["return_pct"] >= e["threshold"])
        assert e["count"] == max(col_sum, n_stored)
    # any (floor, cap) inventory read dominates the stored pairs behind it
    for cap in (2.5, 5.0, 10.0, 20.0, None):
        for k, floor_p in enumerate(presets):
            inv = sum(
                sum(b["by_total"][k:])
                for b in bands
                if cap is None or (b["hi"] is not None and b["hi"] <= cap)
            )
            n_stored = sum(
                1
                for p in doc["pairs"]
                if p["return_pct"] >= floor_p
                and (cap is None or p["max_leg_return_pct"] < cap)
            )
            assert inv >= n_stored, (cap, floor_p)


def test_forced_per_bucket_truncation_honesty(snapshot):
    """Force truncation with a tiny quota and tiny budgets: every non-empty
    bucket stores up to the quota, counts stay verified floors at or above
    stored, ids stay sequential, ordering stays total-return-desc, and the
    compat `truncated` block plus the storage-cap note disclose the depth."""
    from core.scoring import model as md

    small = Params(pairs_per_band=2, pair_scan_budget=2000, pair_collect_budget=60_000)
    board = tr.trade_board(md.build_league(snapshot, small))
    bands = board["bands"]
    assert any(b["saturated"] for b in bands)  # the fixture space is deep
    for b in bands:
        assert b["stored"] <= 2
        assert b["count"] >= b["stored"]
        assert sum(b["by_total"]) == b["count"]
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
        i = tr.bucket_index(edges, p["max_leg_return_pct"])
        assert bands[i]["stored"] > 0
    t = board["truncated"]
    assert t is not None and t["stored"] == len(board["pairs"])
    assert t["total"] > t["stored"]
    assert any("storage cap" in n for n in board["notes"])
    assert any("stratified storage" in n for n in board["notes"])


def test_count_deltas_track_taxi_and_negate_exactly(result, league):
    """§5 v3.2: net_players/net_picks are asset-count arithmetic on the card
    itself (players wherever they land — taxi-routed arrivals included; picks
    regardless of year) and exactly negate across sides."""
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
    """§11.7: an unvalued asset contributes 0 to ΔW (it can never start and has
    no tranche) and is loudly flagged."""
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
    assert with_waller["dW_parts"] == base["dW_parts"]
    assert with_waller["unvalued"] == ["Darren Waller"]
    waller = next(a for a in with_waller["give"] if a["name"] == "Darren Waller")
    assert waller.get("unvalued") is True
    assert any("unvalued" in n.lower() for n in with_waller["notes"])
