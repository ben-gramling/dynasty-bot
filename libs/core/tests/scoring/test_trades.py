"""§2 the v3.5 wealth ledger (`W = S + δ·T`), §3 the exact-KTC gate, §5 v3.3
enumerate-then-filter pairing behind the target-return dial (posture as a hard
pair-pool constraint) + §10 worked examples.

§10 pins are computed from the COMMITTED fixtures (data/, 2026-07-26 KTC values,
2026-07-27 transactions) and are exact to this data; the spec's §10 prose quotes
the same trades.
"""

from __future__ import annotations

import pytest

from core.scoring import Params
from core.scoring import ktc_adjust as ka
from core.scoring import lineup as ln
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
    v3.5 deflates the ledger from v3.4's +9,093 to +291.5: the picks arriving are
    stored value at δ, not wealth at face, and the WRs leaving were already
    mostly stored too — what is left is δ of the 1,358 face gained minus the 64
    of starter value shipped. The gate is untouched and still REJECTS (the exact
    KTC calculator prices the concentrated 7,398 pick far above two mid WRs:
    36.8% against a 20% band; under v3.3's fitted curve it read 17.3% and
    passed)."""
    card = tr.propose_by_names(
        league, "jaketoppen",
        ["Mike Evans", "Courtland Sutton"],
        ["2027 R1 (from vishan)", "2028 R4 (own)"],
    )
    give = {a["name"]: a["v"] for a in card["give"]}
    get = {a["name"]: a["v"] for a in card["get"]}
    assert give == {"Mike Evans": 4125, "Courtland Sutton": 3674}
    assert get == {"2027 R1 (from vishan)": 7398, "2028 R4 (own)": 1759}
    # §2 v3.5 per-side ledger — NOT a negation. Both sides gain here: I bank
    # δ of a 1,358 face pickup, they bank 1,216 of real starter value.
    assert card["dW"] == {"me": 291.5, "them": 572.5}
    assert card["dW_parts"] == {
        "me": {"dS": -64.0, "dT": 355.5},
        "them": {"dS": 1216.0, "dT": -643.5},
    }
    # the two terms sum to ΔW exactly, on both sides (§2 v3.5)
    for side in ("me", "them"):
        p = card["dW_parts"][side]
        assert card["dW"][side] == round(p["dS"] + p["dT"], 1)
    # δ·Δface arithmetic, spelled out: 0.25·(9,157 − 7,799 + 64) = 355.5
    assert card["dW_parts"]["me"]["dT"] == 0.25 * ((9157 - 7799) - (-64))
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


def test_worked_example_2_buy_leg_stored_for_stored(league):
    """§10.2: buy Jauan Jennings (3,001) from millj for my 2028 3rd (2,468).
    Under v3.4 this was a pure −2,468 pick spend (Jennings never cracks my
    max-Σv lineup, so ΔS = 0 and the pick was 100% wealth). v3.5 prices it as
    what it is — a swap INSIDE the stored class — so it is worth δ of the 533
    face picked up, +133.2, not −2,468: the sign flip that killed the
    reclassification loop. The exact gate still rejects it (a 3,001 player
    outweighs a 2,468 pick by 1,430 adjusted, a 36.7% gap); the shape
    (picks → SELLER) is still right."""
    card = tr.propose_by_names(league, "millj", ["2028 R3 (own)"], ["Jauan Jennings"])
    assert sum(a["v"] for a in card["give"]) == 2468
    assert sum(a["v"] for a in card["get"]) == 3001
    assert card["dW"] == {"me": 133.2, "them": -133.2}
    assert card["dW_parts"]["me"] == {"dS": 0.0, "dT": 133.2}
    assert card["dW_parts"]["me"]["dT"] == round(0.25 * (3001 - 2468), 1)
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


# --------------------------------------- §2/§11.8b v3.5 stored value at δ = 0.25


def _pv(name: str, pos: str, v: float, i: int) -> ln.PlayerV:
    return ln.PlayerV(sid=f"syn:{i}", name=name, pos=pos, v=float(v), ktc_id=i)


def _synth_pick(v: float, name: str = "synthetic 2027 R2") -> tr.Asset:
    """A pick asset with no lineup role — stored value, nothing else."""
    return tr.Asset(
        kind="pick", key=f"syn:{name}", name=name, v=float(v), pos=None,
        unvalued=False, concrete=None,
    )


def _synth_ledger(league, roster, give, get, delta) -> tuple[float, float, float]:
    """(ΔS, δ·ΔT, ΔW) for a synthetic roster and an explicit swap. `give`/`get`
    are Assets (players or `_synth_pick`s)."""
    return tr.ledger_delta(
        ln.StarterIndex(roster),
        [tr.package_of(league, give)],
        [tr.package_of(league, get)],
        delta,
    )


def test_v35_qb_case_a_two_qbs_one_slot_scores_negative(league, params):
    """§2/§11.8b(a), the user's FIRST worked QB case: "my total KTC has gone up
    but I can only start one QB". An 8,000 starter + a 4,000 backup swapped for
    a 7,000 + a 6,000 raises face by 1,000 and must still score NEGATIVE —
    −1,000 of starter value against +2,000 of stored value at δ = 0.25 is
    −500. This case is what puts the CEILING on δ (δ < 0.5)."""
    assert params.stored_delta == 0.25
    starter, backup = _pv("QB8000", "QB", 8000, 1), _pv("QB4000", "QB", 4000, 2)
    roster = [starter, backup]
    assert ln.starter_sum(roster) == 8000.0  # only one QB slot exists
    d_s, d_t, d_w = _synth_ledger(
        league,
        roster,
        [tr.player_asset(starter), tr.player_asset(backup)],
        [tr.player_asset(_pv("QB7000", "QB", 7000, 3)),
         tr.player_asset(_pv("QB6000", "QB", 6000, 4))],
        params.stored_delta,
    )
    assert (d_s, d_t, d_w) == (-1000.0, 500.0, -500.0)
    assert d_w < 0.0  # the invariant the user stated
    assert d_s + d_t == d_w


def test_v35_qb_case_b_bench_upgrade_scores_positive(league, params):
    """§2/§11.8b(a), the user's SECOND worked QB case: "a trade that upgrades my
    bench without decreasing my starters or my picks can still be a good
    trade". The 8,000 starter is untouched and the 5,000 backup becomes a
    6,000 backup: ΔS = 0, +1,000 of stored value ⇒ +250. This case is what
    puts the FLOOR on δ (δ > 0) and is why pure deployability was rejected."""
    starter, backup = _pv("QB8000", "QB", 8000, 1), _pv("QB5000", "QB", 5000, 2)
    roster = [starter, backup]
    d_s, d_t, d_w = _synth_ledger(
        league,
        roster,
        [tr.player_asset(backup)],
        [tr.player_asset(_pv("QB6000", "QB", 6000, 3))],
        params.stored_delta,
    )
    assert (d_s, d_t, d_w) == (0.0, 250.0, 250.0)
    assert d_w > 0.0  # the invariant the user stated


@pytest.mark.parametrize("delta", [0.0, 0.1, 0.25, 0.4, 0.49, 0.5, 0.75, 1.0])
def test_the_two_qb_cases_bracket_delta_to_0_0p5(league, delta):
    """§2/§9: the two cases above are not just pins, they are the DERIVATION of
    δ ∈ (0, 0.5). Case A scores negative iff δ < 0.5; case B scores positive
    iff δ > 0. The shipped 0.25 is the midpoint of exactly that interval."""
    qb8 = _pv("QB8000", "QB", 8000, 1)
    a = _synth_ledger(
        league, [qb8, _pv("QB4000", "QB", 4000, 2)],
        [tr.player_asset(qb8), tr.player_asset(_pv("QB4000", "QB", 4000, 2))],
        [tr.player_asset(_pv("QB7000", "QB", 7000, 3)),
         tr.player_asset(_pv("QB6000", "QB", 6000, 4))],
        delta,
    )[2]
    b = _synth_ledger(
        league, [qb8, _pv("QB5000", "QB", 5000, 5)],
        [tr.player_asset(_pv("QB5000", "QB", 5000, 5))],
        [tr.player_asset(_pv("QB6000", "QB", 6000, 6))],
        delta,
    )[2]
    assert (a < 0) == (delta < 0.5), (delta, a)
    assert (b > 0) == (delta > 0.0), (delta, b)


def test_stored_class_conversion_scores_zero(league, params):
    """§11.8b(b): a pure conversion BETWEEN stored classes pays nothing. A
    non-starting player for a pick of equal face is exactly 0 — the death of
    v3.4's reclassification loop, where the same trade banked the pick's whole
    face because the bench player was priced at 0."""
    wrs = [_pv(f"WR{v}", "WR", v, i) for i, v in enumerate([9000, 8000, 7000, 6000, 5000, 4000])]
    bench = wrs[-1]  # 3 WR + 2 FLEX slots: the 6th WR cannot start
    assert ln.starter_sum(wrs) == ln.starter_sum(wrs[:-1]) == 35000.0
    d_s, d_t, d_w = _synth_ledger(
        league, wrs, [tr.player_asset(bench)], [_synth_pick(4000)], params.stored_delta
    )
    assert (d_s, d_t, d_w) == (0.0, 0.0, 0.0)
    # and the v3.5 bound holds for unequal face too: |ΔW| ≤ δ·|Δface|
    for pick_v in (3000, 3900, 4100, 5000):
        _, _, dw = _synth_ledger(
            league, wrs, [tr.player_asset(bench)], [_synth_pick(pick_v)],
            params.stored_delta,
        )
        assert abs(dw) <= params.stored_delta * abs(pick_v - bench.v) + 1e-9
        assert dw == params.stored_delta * (pick_v - bench.v)


def test_hunter_for_a_2027_second_no_longer_pays(league, params):
    """§11.8b(b) pinned on the COMMITTED fixtures — the regression v3.5 exists
    to kill. Travis Hunter (4,061) is on my bench: he cannot crack the max-Σv
    lineup, so under v3.4 shipping him for ronakpatel32's 2027 2nd (4,139)
    scored the pick's ENTIRE face, +4,139, for a roster that got no better.
    Under v3.5 both sides of the swap are stored value and the trade is worth
    δ·78 = +19.5 — noise, correctly. The gate passed then and passes now, so
    the seam really was reachable."""
    mine = tr.team_assets(league, league.teams[league.me])
    ron = tr.team_assets(league, league.teams["ronakpatel32"])
    hunter, second = mine["Travis Hunter"], ron["2027 R2 (own)"]
    assert (hunter.v, second.v) == (4061.0, 4139.0)
    starters = {p.sid for grp in ln.starters(tr.starter_pool(league.teams[league.me])).values() for p in grp}
    assert hunter.player.sid not in starters  # bench: ΔS = 0 either way

    card = tr.propose(league, "ronakpatel32", [hunter], [second])
    assert card["gate"]["verdict"] == "PASS"  # it was always gate-clean
    assert card["dW_parts"]["me"] == {"dS": 0.0, "dT": 19.5}
    assert card["dW"]["me"] == 19.5
    assert abs(card["dW"]["me"]) <= params.stored_delta * abs(second.v - hunter.v) + 1e-9
    # what v3.4 would have paid for the same trade: ΔS + the pick's full face
    v34 = card["dW_parts"]["me"]["dS"] + second.v
    assert v34 == 4139.0 and card["dW"]["me"] < 0.005 * v34


@pytest.mark.parametrize("delta", [0.0, 1.0])
def test_delta_endpoints_reproduce_the_older_ledgers(snapshot, delta):
    """§11.8b(c): the parameter's endpoints are the two ledgers v3.5 sits
    between. δ = 0 is pure deployability — ΔW collapses onto ΔS, v3.4's starter
    term with its pick column zeroed (the option §2 rejects, because it scores
    the second QB case at exactly 0). δ = 1 is v3.3's face ledger — ΔW is the
    face transfer itself, which is why the market, not the ledger, prices the
    gate."""
    from core.scoring import model as md

    league2 = md.build_league(snapshot, Params(stored_delta=delta))
    cases = [
        ("jaketoppen", ["Mike Evans", "Courtland Sutton"],
         ["2027 R1 (from vishan)", "2028 R4 (own)"]),
        ("millj", ["2028 R3 (own)"], ["Jauan Jennings"]),
        ("ronakpatel32", ["Javonte Williams"], ["Zay Flowers"]),
        ("Jukinski", ["Joe Burrow", "2026 4.01"], ["2026 1.12", "2028 R1 (own)"]),
    ]
    for opp, give, get in cases:
        card = tr.propose_by_names(league2, opp, give, get)
        parts = card["dW_parts"]["me"]
        face = sum(a["v"] for a in card["get"]) - sum(a["v"] for a in card["give"])
        if delta == 0.0:
            assert parts["dT"] == 0.0, (opp, give)
            assert card["dW"]["me"] == parts["dS"], (opp, give)
        else:
            assert card["dW"]["me"] == float(face), (opp, give)
            assert round(parts["dS"] + parts["dT"], 1) == float(face), (opp, give)


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
    # my 2026 2.09 at tranche 3,504 for their 2028 2nd at 3,579: a pick-for-pick
    # swap inside the stored class, so ΔW is δ·75 = +18.8, well under W_min
    card = tr.propose(league, "jaketoppen", [mine["2026 2.09"]], [theirs["2028 R2 (own)"]])
    assert card["dW"]["me"] == 18.8
    assert card["dW_parts"]["me"] == {"dS": 0.0, "dT": 18.8}
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
    """§5 v3.4 return-on-inventory arithmetic on the v3.5 ledger, pinned to the
    fixtures. The buy leg swaps a 1,759 pick for a 1,876 non-starter — stored
    for stored, +29.2. The sell leg ships Joe Burrow, my starting QB, for picks:
    v3.4 read it +6,516 (7,828 of pick face at 100% against a 1,312 starter
    dent), v3.5 reads it −463.0, because the picks arrive as stored value at δ.
    The PAIR is the combined ledger over the face Σv sent across both legs:
    −433.8 ÷ 9,536 = −4.55% — the 49.88% that used to top the board was
    reclassification, not wealth."""
    buy, sell = _fixture_pair_legs(league)
    assert (buy["dW"]["me"], sum(a["v"] for a in buy["give"])) == (29.2, 1759)
    assert buy["dW_parts"]["me"] == {"dS": 0.0, "dT": 29.2}
    assert buy["return_pct"] == 1.66
    assert (sell["dW"]["me"], sum(a["v"] for a in sell["give"])) == (-463.0, 7777)
    assert sell["dW_parts"]["me"] == {"dS": -1312.0, "dT": 849.0}
    pair = tr.pair_ledger(league, buy, sell)
    assert pair == {
        "dS": -1312.0,
        "dT": 878.2,
        "dW": -433.8,
        "sent": 9536.0,
        "return_pct": -4.55,
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
    assert bi is not None and si is not None, "legs missing from the v3.5 pool"
    ret = tr.pair_in_space(league, pool, bi, si)
    assert ret is not None
    assert round(100 * ret, 2) == -4.55 == tr.pair_ledger(league, buy, sell)["return_pct"]


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
    Jackson: ledger ΔW +387.2 in isolation under v3.5 — he displaces Burrow for
    a 512 starter gain, gap 0.8%) yet appears NOWHERE in the pair pool or on the
    board; millj (SELLER) likewise never receives players-majority. The pin is
    the ABSENCE, not the sign: a gate-clean, ledger-positive trade is still
    refused because the shape contradicts the counterparty's posture."""
    mine = tr.team_assets(league, league.teams[league.me])
    ron = tr.team_assets(league, league.teams["ronakpatel32"])
    candidate = tr.propose(league, "ronakpatel32", [mine["2026 1.01"]], [ron["Lamar Jackson"]])
    assert candidate["gate"]["verdict"] == "PASS"
    assert candidate["dW"]["me"] == 387.2 and candidate["gate"]["gap_pct"] == 0.8
    assert candidate["dW_parts"]["me"] == {"dS": 512.0, "dT": -124.8}
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
    assert doc["pairs"][0]["return_pct"] == 22.98  # fixture pin: global top
    # v3.5 re-sorts the whole board: the top pair is a STARTER upgrade
    # (dS +2,468) paid for with stored value (dT −354.8), where v3.4's 49.88%
    # top pair was a bench-to-picks reclassification
    assert doc["pairs"][0]["dW_combined_parts"] == {"dS": 2468.0, "dT": -354.8}
    # it is still lopsided in market terms — its sell leg skims 23.68% face
    assert doc["pairs"][0]["leg_returns"] == {"buy": 5.61, "sell": 23.68}
    assert doc["pairs"][0]["max_leg_return_pct"] == 23.68
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
    assert flagship[0]["return_pct"] == 18.38  # fixture pin: even legs, big total
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
    assert tr.band_index(bands, 22.98) == 4  # pinned fixture pair total
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
    assert tr.bucket_index(buckets, 23.68) == 4  # pinned fixture max leg
    # cap-selection identity: max_leg < c ⟺ bucket.hi ≤ c, for every preset
    for c in (2.5, 5.0, 10.0, 20.0):
        selected = {i for i, (_lo, hi) in enumerate(buckets) if hi is not None and hi <= c}
        for m in (-3.0, 0.0, 2.49, 2.5, 4.99, 5.0, 9.99, 10.0, 19.99, 20.0, 23.68):
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
