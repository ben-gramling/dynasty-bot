"""§7 trades tab + §11.2 worked example (exact to the decimal)."""

from __future__ import annotations

import pytest

from core.scoring import trades as tr
from core.scoring import transactions as tx

from .conftest import by_name, pick_of


@pytest.fixture(scope="module")
def jt_scored(league):
    return tr.scored_candidates(league, "jaketoppen")


def _find(scored, give: set, get: set):
    for tier, h, g, gt, rm, rt in scored:
        if {a.name for a in g.assets} == give and {a.name for a in gt.assets} == get:
            return tier, h, rm, rt
    return None


def test_give_list_matches_spec(league, me):
    """§7.1: the quoted give-list — deep-flex block + vet bench head, cuts, all picks;
    cornerstones (Jeanty/Hampton) never enter it."""
    assets = tr.give_list(league, me)
    players = [a.name for a in assets if a.kind == "player"]
    assert players[:8] == [
        "Kenneth Walker III", "Javonte Williams", "Alec Pierce", "Jordan Addison",
        "Mike Evans", "Travis Hunter", "Rico Dowdle", "Courtland Sutton",
    ]
    assert {"Darren Waller", "Joe Flacco", "Stefon Diggs"} <= set(players)  # scheduled cuts
    assert "Ashton Jeanty" not in players and "Omarion Hampton" not in players
    assert sum(1 for a in assets if a.kind == "pick") == len(me.picks)  # all 11 picks


def test_sigma0_values(league, me):
    """§7.1 quoted gross-surplus values. The spec's parenthetical integers mix
    floor and round display (Walker 2,486 = floor(2486.55), Pierce 2,379 =
    round(2378.59)), so these prose figures are pinned to ±1; the exact-contract
    quantities live in §11/§2.4/§2.5 tests."""
    want = {
        "Kenneth Walker III": 2486, "Javonte Williams": 2427, "Alec Pierce": 2379,
        "Jordan Addison": 2372, "Mike Evans": 2331, "Travis Hunter": 2327,
        "Rico Dowdle": 2216, "Courtland Sutton": 2204, "Chris Godwin": 2186,
        "Tyler Allgeier": 2006, "Stefon Diggs": 1585,
    }
    for name, val in want.items():
        p = by_name(league, name)
        assert abs((p.v - me.rv0[p.sid]) - val) <= 1.0, name


def test_headline_trade_exact(league):
    """§11.2: Sutton + Evans → jaketoppen's own 2027 1st — every quoted number."""
    card = tr.propose(
        league, "jaketoppen",
        give_names=["Courtland Sutton", "Mike Evans"],
        get_names=["2027 R1 (own)"],
    )
    m = card["sides"]["me"]
    assert m["score"] == 595.1
    assert m["dL"] == -250.0
    assert m["dNC"] == 27.7
    assert m["dA"] == -1681.0
    assert m["dC"] == -1400.9
    assert m["lineup_weighted"] == pytest.approx(-133.4, abs=0.05)
    assert m["wealth_weighted"] == -672.4
    assert m["crunch_term"] == 1400.9
    assert m["crunch"] == {"cuts_before": 3, "cuts_after": 1, "rescued": ["Joe Flacco", "Stefon Diggs"]}
    assert [(t["kind"], t["slot"], t["out"], t["in"], t["delta"]) for t in m["dL_terms"]] == [
        ("starter", "WR3", "Mike Evans 4125", "Travis Hunter 4061", -57.0),
        ("backup", "WR", "Travis Hunter 4061", "Chris Godwin 3644", -137.6),
        ("backup", "FLEX", "Travis Hunter 4061", "Rico Dowdle 3830", -55.4),
    ]
    t = card["sides"]["them"]
    assert t["omega"] == 0.70
    assert t["score"] == 1401.8
    assert t["dL"] == 1282.2
    assert t["dNC"] == 0.0
    assert t["dA"] == 1681.0
    assert t["dC"] == 0.0
    assert [(t_["slot"], t_["out"], t_["in"], t_["delta"]) for t_ in t["dL_terms"]] == [
        ("WR3", "Malik Washington 3203", "Mike Evans 4125", 820.6),
        ("WR", "Darnell Mooney 2489", "Courtland Sutton 3674", 391.1),
        ("FLEX", "Jordan Mason 3380", "Courtland Sutton 3674", 70.6),
    ]
    assert card["rank_score_H"] == 773.6
    f = card["fairness"]
    assert f["adj_give"] == 7431.6 and f["adj_get"] == 6118.0
    assert f["gap_pct"] == 17.7 and f["raw_ratio"] == 1.27 and f["cap"] == 1.35
    assert card["tier"] == "A" and card["posture_fit"] is True
    assert card["activity"] == "High"
    assert card["anchor_ask_pct"] == 8.0
    assert card["omega_sensitivity"] == {"0.5": 809.1, "0.6": 595.1, "0.7": 381.1}
    # the get-pick carries its pricing provenance (§12)
    get = card["get"][0]
    assert get == {
        "type": "pick", "name": "2027 R1 (own)", "v": 6118, "mv": 6118,
        "pricing": {"rule": "tranche", "band": "Mid", "band_reason": "jaketoppen rank_L 6"},
    }


def test_headline_trade_generated(jt_scored):
    """§7: the generator itself surfaces the §11.2 headline through all filters."""
    hit = _find(jt_scored, {"Courtland Sutton", "Mike Evans"}, {"2027 R1 (own)"})
    assert hit is not None
    tier, h, rm, rt = hit
    assert tier == "A"
    assert round(h, 1) == 773.6
    assert round(rm.score, 1) == 595.1
    assert round(rt.score, 1) == 1401.8


def test_diggs_runner_up_generated(jt_scored):
    """§11.2 runner-up: Diggs → jaketoppen 2027 4th, pure crunch arbitrage."""
    hit = _find(jt_scored, {"Stefon Diggs"}, {"2027 R4 (own)"})
    assert hit is not None
    tier, h, rm, rt = hit
    assert round(rm.score, 1) == 814.4
    assert round(rt.score, 1) == 216.6
    assert round(h, 1) == 879.4


def test_adj_value_consolidation():
    """§7.2: c = (1.00, 0.90, 0.80), sorted mv desc; 4th+ asset keeps the last coeff."""
    assert tr.adj_value([4125, 3674], (1.0, 0.9, 0.8)) == 7431.6
    assert tr.adj_value([3674, 4125], (1.0, 0.9, 0.8)) == 7431.6  # order-insensitive
    assert tr.adj_value([1000, 2000, 3000, 4000], (1.0, 0.9, 0.8)) == pytest.approx(
        4000 + 0.9 * 3000 + 0.8 * 2000 + 0.8 * 1000
    )


def test_fairness_band_and_fleece(league, jt_scored):
    """§7.2 filters hold for every generated candidate (cuts-only gives exempt from
    the band — documented crunch-arbitrage carve-out)."""
    params = league.params
    for tier, h, g, gt, rm, rt in jt_scored:
        assert rm.score >= params.g_min - 1e-9
        assert rt.score >= params.their_floor - 1e-9
        assert g.mv_sum <= params.fleece_ratio * gt.mv_sum + 1e-9
        assert gt.mv_sum <= params.fleece_ratio * g.mv_sum + 1e-9
        if not (g.all_cuts or gt.all_cuts):
            gap = abs(g.adjv - gt.adjv)
            assert gap <= max(params.fairness_abs, params.fairness_rel * max(g.adjv, gt.adjv)) + 1e-9


def test_no_pure_pick_shuffles(jt_scored, league):
    """§7.1: pick-for-pick swaps only when a current-year pick COUNT changes —
    an equal-count 2026-for-2026 swap moves no crunch and never surfaces."""
    for tier, h, g, gt, rm, rt in jt_scored:
        if g.n_players == 0 and gt.n_players == 0:
            assert g.n_2026 != gt.n_2026


def test_enumeration_bounds_and_eval_budget(league):
    """§13.10 (erratum 8): give-lists stay 8+cuts+picks, packages stay ≤3 a side,
    every enumerated package passes through the cheap §7.2 pre-filters, and the
    per-bucket proxy-best-first budget keeps joint evaluations league-wide in the
    low 10⁴ (the pinned §11.2 candidates surviving the budget is asserted by
    test_headline_trade_generated / test_diggs_runner_up_generated)."""
    params = league.params
    for t in league.teams.values():
        assets = tr.give_list(league, t)
        n_players = sum(1 for a in assets if a.kind == "player")
        assert n_players <= params.give_list_size + len(t.cut_players)
        assert sum(1 for a in assets if a.kind == "pick") == len(t.picks)
    total = evaluated = 0
    for opp in league.opponents:
        for (n_g, n_t), bucket in tr.candidate_buckets(league, opp).items():
            assert 1 <= n_g <= params.max_package and 1 <= n_t <= params.max_package
            total += len(bucket)
            evaluated += min(len(bucket), params.trade_eval_cap_per_bucket)
    assert 0 < total < 5_000_000
    assert 0 < evaluated < 25_000


def test_trade_zone(league):
    """§7.5: the full quoted diagnostic — including honest empty zones."""
    rows = {r["target"]: r for r in tr.trade_zone(league)}
    want = {
        "Puka Nacua": (8772, "Jukinski", 11511, 15030, 3519),
        "Malik Nabers": (7534, "vishan", 8831, 12140, 3309),
        "Emeka Egbuka": (6826, "ronakpatel32", 8034, 10487, 2453),
        "Chris Olave": (6183, "ronakpatel32", 7083, 8985, 1902),
        "Tetairoa McMillan": (6951, "josbaski", 9654, 10778, 1125),
        "Marvin Harrison Jr.": (5632, "Jukinski", 6867, 7699, 832),
        "Ladd McConkey": (6245, "millj", 9711, 9130, None),
        "DK Metcalf": (4308, "Jukinski", 4908, 4607, None),
    }
    for name, (v, owner, floor, ceiling, zone) in want.items():
        r = rows[name]
        assert (r["v"], r["owner"], r["their_floor"], r["my_ceiling"], r["zone"]) == (
            v, owner, floor, ceiling, zone,
        ), name


def test_trade_tab_disabled_after_deadline(snapshot, params):
    from dataclasses import replace as dc_replace

    from core.scoring import model as md

    late = dc_replace(snapshot, state={**dict(snapshot.state), "season_type": "regular", "week": 12})
    league2 = md.build_league(late, params)
    assert tr.trade_candidates(league2) == []


def test_omega_sensitivity_reprices_crunch(league):
    """§7.4: the sensitivity line re-scores everything, crunch included (validated
    by the exact 809.1 / 595.1 / 381.1 triple in the headline card)."""
    me = league.teams[league.me]
    sutton, evans = by_name(league, "Courtland Sutton"), by_name(league, "Mike Evans")
    r1 = pick_of(league.teams["jaketoppen"], 2027, 1, origin_rid=2)
    naive_05 = 0.5 * (-250.01 + 27.72) + 0.5 * (-1681) + 1400.9  # crunch NOT repriced
    full_05 = tx.score_transaction(
        league, me, remove_ids=[sutton.sid, evans.sid], add_picks=[r1], omega=0.5
    ).score
    assert round(full_05, 1) == 809.1
    assert abs(naive_05 - full_05) > 300  # repricing the crunch is load-bearing
