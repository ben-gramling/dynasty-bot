"""§2 the v4 two-coordinate score (ΔS, ΔF — verdict, interval, maximin), §3 the
exact-KTC gate, §5 enumerate-then-filter pairing behind the two dials (posture
as a hard pair-pool constraint, verdict as a hard storage constraint) + §10
worked examples.

§10/§11.8b pins are computed from the COMMITTED fixtures (data/, 2026-07-26 KTC
values, 2026-07-27 transactions) and are exact to this data; the spec's §10
prose quotes the same trades.
"""

from __future__ import annotations

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
    assert a101.v == 6243  # tranche — the MARKET/gate number (v7: gate only)
    assert a101.v_me == a101.concrete == 7762  # exact board slot — what ΔF books


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
    v4 reports the two coordinates and no blend; **v7 re-prices the two picks I
    would RECEIVE at the cheap end of their rounds** (7,398 → 5,562 Late,
    1,759 → 1,451 Late), which turns my side from (−64, +1,358) into
    (ΔS −64, ΔF −786): no longer a preference trade at all, but bad at EVERY
    rational preference — no breakeven exists. This is the headline case for
    the v7 rule: buying future picks off a counterparty at a market-fair price
    is not a gain once you stop assuming the picks land early. Their side is
    unchanged at (ΔS +1,216, ΔF −1,358) because the counterparty is reported at
    market face, so the two ΔFs no longer negate (§11.1b). The gate is untouched
    and still REJECTS (the exact KTC calculator prices the concentrated 7,398
    pick far above two mid WRs: 36.8% against a 20% band; under v3.3's fitted
    curve it read 17.3% and passed)."""
    card = tr.propose_by_names(
        league, "jaketoppen",
        ["Mike Evans", "Courtland Sutton"],
        ["2027 R1 (from vishan)", "2028 R4 (own)"],
    )
    give = {a["name"]: a["v"] for a in card["give"]}
    get = {a["name"]: a["v"] for a in card["get"]}
    assert give == {"Mike Evans": 4125, "Courtland Sutton": 3674}
    assert get == {"2027 R1 (from vishan)": 7398, "2028 R4 (own)": 1759}
    # v7: the picks I receive carry my own cheaper price alongside the market one
    assert [(a["name"], a.get("v_me")) for a in card["get"]] == [
        ("2027 R1 (from vishan)", 5562),
        ("2028 R4 (own)", 1451),
    ]
    assert all("v_me" not in a for a in card["give"])  # players are lens-neutral
    # §2 v4 per-side coordinates, v7 lenses — mine on v_me, theirs at market,
    # so ΔF no longer negates (§11.1b); ΔS was never a negation either
    assert card["coords"] == {
        "me": {"dS": -64.0, "dF": -786.0},
        "them": {"dS": 1216.0, "dF": -1358.0},
    }
    assert card["coords"]["me"]["dF"] == round(
        (5562 + 1451) - (4125 + 3674) - 0.0, 1
    )  # v7 ΔF is exactly the v_me delta
    assert card["verdict"] == {"me": False, "them": False}
    assert card["floor"] == {"me": -786.0, "them": -1358.0}
    # both my coordinates are negative ⇒ bad at every δ, so NO breakeven exists
    assert card["breakeven"]["me"] is None
    assert card["breakeven"]["them"] == round(1216.0 / (1216.0 + 1358.0), 4) == 0.4724
    assert card["coords_basis"] == "isolation"
    # §5 v4 leg return is floor-based: −786 ÷ 7,799 sent (denominator stays MARKET)
    assert card["return_pct"] == -10.08
    # the market skim is untouched — it reads face on both sides
    assert card["market_return_pct"] == 17.41
    g = card["gate"]
    assert (g["adj_give"], g["adj_get"]) == (7799.0, 12339.0)
    assert (g["gap"], g["gap_pct"], g["band"]) == (4540.0, 36.8, 2467.8)
    assert g["band_ok"] is False
    assert g["raw_ratio"] == 1.17 and g["ratio_ok"]
    assert g["verdict"] == "FAIL: outside fairness band (gap 36.8% > band)"
    # §4a v5 favor from the SAME adjusted totals: 100·(7,799−12,339)/20,138 =
    # −22.54 → −22.5 in the calculator's own 1-decimal quantization; negative
    # = skewed to ME (they'd never take it, which is also why the band fails)
    assert card["favor"] == g["favor"] == -22.5
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


def test_worked_example_2_buy_leg_face_for_face(league):
    """§10.2: buy Jauan Jennings (3,001) from millj for my 2028 3rd (2,468).
    Jennings never cracks my max-Σv lineup, so the whole move is in the face
    coordinate. **v7 charges me the dear end of the round for the pick I send**
    (2,468 → 2,618 Early, because I own it), so the trade reads
    (ΔS 0, ΔF +383) rather than (0, +533) — still objectively GOOD (one strict
    coordinate), guaranteed floor still 0, gain now the interval 0 to +383.
    millj's side is unchanged at (0, −533) — reported at market face — so the
    two ΔFs differ by exactly the 150-point lens wedge (§11.1b). The exact gate
    still rejects it (a 3,001 player outweighs a 2,468 pick by 1,430 adjusted,
    a 36.7% gap); the shape (picks → SELLER) is still right."""
    card = tr.propose_by_names(league, "millj", ["2028 R3 (own)"], ["Jauan Jennings"])
    assert sum(a["v"] for a in card["give"]) == 2468
    assert sum(a["v"] for a in card["get"]) == 3001
    assert card["coords"] == {
        "me": {"dS": 0.0, "dF": 383.0},
        "them": {"dS": 0.0, "dF": -533.0},
    }
    # the wedge is exactly the tranche step the lens charged me: Early − Mid
    assert card["coords"]["me"]["dF"] - -card["coords"]["them"]["dF"] == -(2618 - 2468)
    assert card["verdict"] == {"me": True, "them": False}
    assert card["floor"] == {"me": 0.0, "them": -533.0}
    # verdict-true ⇒ no breakeven; both-coordinates-≤0 ⇒ no breakeven either
    assert card["breakeven"] == {"me": None, "them": None}
    assert card["return_pct"] == 0.0  # floor-based: guaranteed nothing
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


# ---------------------- §2/§11.8b v4 coordinate pins (verdict, interval, δ*)


def _pv(name: str, pos: str, v: float, i: int) -> ln.PlayerV:
    return ln.PlayerV(sid=f"syn:{i}", name=name, pos=pos, v=float(v), ktc_id=i)


def _synth_pick(v: float, v_me: float | None = None, name: str = "synthetic 2027 R2") -> tr.Asset:
    """A pick asset with no lineup role — face value, nothing else. `v_me`
    defaults to `v` so a synthetic pick is lens-neutral unless a test is
    specifically about the v7 two-lens split."""
    return tr.Asset(
        kind="pick", key=f"syn:{name}", name=name, v=float(v),
        v_me=float(v if v_me is None else v_me), pos=None,
        unvalued=False, concrete=None,
    )


def _synth_coords(league, roster, give, get) -> tuple[float, float]:
    """(ΔS, ΔF) for a synthetic roster and an explicit swap. `give`/`get` are
    Assets (players or `_synth_pick`s)."""
    return tr.coords_delta(
        ln.StarterIndex(roster),
        [tr.package_of(league, give)],
        [tr.package_of(league, get)],
    )


def _blend(d_s: float, d_f: float, delta: float) -> float:
    """The single-number ledger v4 refuses to pick: ΔW(δ) = ΔS + δ·(ΔF − ΔS).
    Computed LOCALLY in the tests — no δ exists anywhere in the engine."""
    return d_s + delta * (d_f - d_s)


def test_v4_qb_case_a_is_a_preference_trade_with_breakeven_half(league):
    """§2/§11.8b(a), the user's FIRST worked QB case: "my total KTC has gone up
    but I can only start one QB". An 8,000 starter + a 4,000 backup swapped for
    a 7,000 + a 6,000 is (ΔS −1,000, ΔF +1,000): NOT objectively good — a
    preference trade with breakeven δ* = 0.5 exactly. A rebuilder (δ > 0.5)
    should take it; the user (win-now on this roster) correctly refuses. No
    verdict says "bad"; the verdict says "not good for every preference"."""
    starter, backup = _pv("QB8000", "QB", 8000, 1), _pv("QB4000", "QB", 4000, 2)
    roster = [starter, backup]
    assert ln.starter_sum(roster) == 8000.0  # only one QB slot exists
    d_s, d_f = _synth_coords(
        league,
        roster,
        [tr.player_asset(starter), tr.player_asset(backup)],
        [tr.player_asset(_pv("QB7000", "QB", 7000, 3)),
         tr.player_asset(_pv("QB6000", "QB", 6000, 4))],
    )
    assert (d_s, d_f) == (-1000.0, 1000.0)
    assert tr.verdict_of(d_s, d_f) is False
    assert tr.breakeven_of(d_s, d_f) == 0.5  # exactly
    assert (min(d_s, d_f), max(d_s, d_f)) == (-1000.0, 1000.0)  # the interval
    # the breakeven really is where the blend crosses zero (blend local to the
    # test — the engine owns no δ)
    assert _blend(d_s, d_f, 0.5) == 0.0
    assert _blend(d_s, d_f, 0.49) < 0.0 < _blend(d_s, d_f, 0.51)


def test_v4_qb_case_b_bench_upgrade_is_objectively_good_floor_zero(league):
    """§2/§11.8b(a), the user's SECOND worked QB case: "a trade that upgrades my
    bench without decreasing my starters or my picks can still be a good
    trade". The 8,000 starter is untouched and the 5,000 backup becomes a
    6,000 backup: (ΔS 0, ΔF +1,000) — objectively GOOD (ΔF strict), gain
    between 0 and +1,000. The floor of 0 ranks it honestly low: nothing is
    guaranteed, but no rational preference loses."""
    starter, backup = _pv("QB8000", "QB", 8000, 1), _pv("QB5000", "QB", 5000, 2)
    roster = [starter, backup]
    d_s, d_f = _synth_coords(
        league,
        roster,
        [tr.player_asset(backup)],
        [tr.player_asset(_pv("QB6000", "QB", 6000, 3))],
    )
    assert (d_s, d_f) == (0.0, 1000.0)
    assert tr.verdict_of(d_s, d_f) is True
    assert min(d_s, d_f) == 0.0  # the guaranteed floor
    assert max(d_s, d_f) == 1000.0  # the ceiling
    assert tr.breakeven_of(d_s, d_f) is None  # verdicts don't carry breakevens


def test_verdict_and_breakeven_semantics():
    """§2 v4 the derived figures, exhaustively by sign case: verdict requires
    both coordinates ≥ 0 with one strict; the breakeven exists exactly for
    preference trades (one coordinate > 0, verdict false) and is always in
    (0, 1); both-≤-0 spreads are bad for every rational preference and carry
    neither."""
    assert tr.verdict_of(10.0, 0.0) and tr.verdict_of(0.0, 10.0) and tr.verdict_of(3.0, 4.0)
    assert not tr.verdict_of(0.0, 0.0)  # nothing strict: not "better"
    assert not tr.verdict_of(-1.0, 5.0) and not tr.verdict_of(5.0, -1.0)
    assert not tr.verdict_of(-2.0, -3.0)
    for d_s, d_f in [(-1000.0, 1000.0), (512.0, -125.0), (-64.0, 1358.0), (96.0, -191.0)]:
        b = tr.breakeven_of(d_s, d_f)
        assert b is not None and 0.0 < b < 1.0, (d_s, d_f)
        assert abs(_blend(d_s, d_f, b)) < 1e-9  # the zero crossing
    # no breakeven without a sign split, and never when ΔS == ΔF (no crossing)
    for d_s, d_f in [(3.0, 4.0), (0.0, 10.0), (0.0, 0.0), (-2.0, -3.0), (0.0, -5.0), (-4.0, -4.0)]:
        assert tr.breakeven_of(d_s, d_f) is None, (d_s, d_f)


def test_stored_conversion_floor_zero(league):
    """§11.8b(b): a non-starter sold for a pick of the SAME face is (0, 0) —
    not objectively good (nothing strict), floor 0, no breakeven. The v3.4
    reclassification exploit stays dead with no parameter needed: there is
    simply nothing to bank."""
    wrs = [_pv(f"WR{v}", "WR", v, i) for i, v in enumerate([9000, 8000, 7000, 6000, 5000, 4000])]
    bench = wrs[-1]  # 3 WR + 2 FLEX slots: the 6th WR cannot start
    assert ln.starter_sum(wrs) == ln.starter_sum(wrs[:-1]) == 35000.0
    d_s, d_f = _synth_coords(league, wrs, [tr.player_asset(bench)], [_synth_pick(4000)])
    assert (d_s, d_f) == (0.0, 0.0)
    assert tr.verdict_of(d_s, d_f) is False and tr.breakeven_of(d_s, d_f) is None
    # unequal faces move ONLY the face coordinate: ΔS stays 0, ΔF is the
    # face delta itself, and the floor is min(0, ΔF)
    for pick_v in (3000, 3900, 4100, 5000):
        d_s, d_f = _synth_coords(
            league, wrs, [tr.player_asset(bench)], [_synth_pick(pick_v)]
        )
        assert (d_s, d_f) == (0.0, pick_v - bench.v)
        assert min(d_s, d_f) == min(0.0, pick_v - bench.v)


def test_hunter_for_a_2027_second_conversion_earns_no_floor(league, board):
    """§11.8b(b) pinned on the COMMITTED fixtures. Travis Hunter (4,061) is on
    my bench; selling him for ronakpatel32's 2027 2nd (market 4,139) used to be
    (ΔS 0, ΔF +78) — verdict true, floor 0, return 0.00%, below the 1% stored
    universe. **v7 books the pick I receive at Late 3,855**, so the naked
    conversion is now (ΔS 0, ΔF −206): verdict FALSE, a strict loss at every
    preference. The reclassification exploit v3.4 killed (it paid the pick's
    entire +4,139 face) is not merely dead but negative — turning a bench body
    into an unknown-slot future pick costs you, parameter-free.

    v5's per-bucket dF-top union may still store a PAIR carrying this leg, and
    the floor arithmetic is now strictly friendlier: combined ΔS ≤ the
    partner's ΔS (Hunter only back-fills) and combined ΔF = partner ΔF − 206,
    so the pair's floor can never EXCEED the partner's own."""
    mine = tr.team_assets(league, league.teams[league.me])
    ron = tr.team_assets(league, league.teams["ronakpatel32"])
    hunter, second = mine["Travis Hunter"], ron["2027 R2 (own)"]
    assert (hunter.v, second.v) == (4061.0, 4139.0)
    starters = {p.sid for grp in ln.starters(tr.starter_pool(league.teams[league.me])).values() for p in grp}
    assert hunter.player.sid not in starters  # bench: ΔS = 0 either way

    card = tr.propose(league, "ronakpatel32", [hunter], [second])
    assert card["gate"]["verdict"] == "PASS"  # it was always gate-clean
    assert second.v_me == 3855.0  # Late: theirs, so I would be receiving it
    assert card["coords"]["me"] == {"dS": 0.0, "dF": -206.0}
    assert card["verdict"]["me"] is False and card["floor"]["me"] == -206.0
    assert card["return_pct"] == -5.07  # floor-based, on the MARKET 4,061 sent
    # the market still calls it a small gain — the lens is the whole difference
    assert card["market_return_pct"] == 1.92
    # what v3.4 would have paid for the same trade: ΔS + the pick's full face
    assert card["coords"]["me"]["dS"] + second.v == 4139.0
    # any stored pair carrying the conversion leg owes its floor to the partner
    conv = ({hunter.key}, {second.key})
    for pair in board["pairs"]:
        for tag, other in (("buy", "sell"), ("sell", "buy")):
            leg = pair[tag]
            legk = ({a["key"] for a in leg["give"]}, {a["key"] for a in leg["get"]})
            if legk != conv:
                continue
            assert pair["verdict"] is True and pair["return_pct"] >= 1.0
            # v7: the conversion's own ΔF edge is NEGATIVE (−206), so it can
            # only drag the pair's floor down — never lift it above the partner's
            assert pair["floor"] <= pair[other]["floor"]["me"] + 1e-6, pair["id"]


def test_interval_endpoints_are_the_delta_extremes(league):
    """§11.8b(c): for arbitrary fixture trades, the card's coordinates equal
    the old blended ledger evaluated at its endpoints — ΔW(0) = ΔS (pure
    deployability) and ΔW(1) = ΔF (the face ledger) — with the blend computed
    LOCALLY against a full direct recompute of S and total_face on the
    post-trade roster. No δ exists in the engine.

    v7: the recompute runs in the SAME lens the card used (`lens="me"`), and it
    stays an identity because `Pick.p_me` is minted at snapshot pricing and
    `apply_tx` carries it across unchanged — a pick I receive keeps its Late
    price on arrival instead of re-pricing to Early."""
    me_t = league.teams[league.me]
    cases = [
        ("jaketoppen", ["Mike Evans", "Courtland Sutton"],
         ["2027 R1 (from vishan)", "2028 R4 (own)"]),
        ("millj", ["2028 R3 (own)"], ["Jauan Jennings"]),
        ("ronakpatel32", ["Javonte Williams"], ["Zay Flowers"]),
        ("Jukinski", ["Joe Burrow", "2026 4.01"], ["2026 1.12", "2028 R1 (own)"]),
    ]
    s_before = ln.starter_sum(tr.starter_pool(me_t))
    f_before = tr.total_face(me_t, lens="me")
    for opp, give_names, get_names in cases:
        card = tr.propose_by_names(league, opp, give_names, get_names)
        give, get = tr.card_packages(league, card)
        after = tr._apply(league, me_t, get=get, give=give)
        d_s_direct = ln.starter_sum(tr.starter_pool(after)) - s_before
        d_f_direct = tr.total_face(after, lens="me") - f_before
        # ΔW(0) = ΔS and ΔW(1) = ΔF, both against the direct recompute
        assert card["coords"]["me"]["dS"] == round(d_s_direct, 1), (opp, give_names)
        assert card["coords"]["me"]["dF"] == round(d_f_direct, 1), (opp, give_names)
        # and every blend in between stays inside the card's interval
        lo = min(d_s_direct, d_f_direct)
        hi = max(d_s_direct, d_f_direct)
        for delta in (0.0, 0.25, 0.5, 0.75, 1.0):
            assert lo - 1e-9 <= _blend(d_s_direct, d_f_direct, delta) <= hi + 1e-9


def test_favor_is_the_gates_own_metric_11_12a(board, league):
    """§11.12(a): `favor` derives from the SAME adjusted totals as the gate —
    one source of truth — and `|f| ≤ 5 ⟺ check_equality(adjT1, adjT2, 5)`,
    the port's own FAIR test at the calculator's default variance. Verified
    over every displayed board leg (fresh recompute, no stored figures) and a
    systematic sample of raw package crossings including |f| near the 5.0
    boundary."""
    for card in board_legs(board)[:25]:
        give, get = tr.card_packages(league, card)
        a1, a2 = tr.adjusted_gap(league, give, get)
        f = tr.favor_of(a1, a2)
        assert card["favor"] == round(f, 2), card["id"]
        assert (abs(f) <= 5.0) == ka.check_equality(a1, a2, 5), card["id"]
        # sign convention: + = counterparty wins = they RECEIVE more adjusted
        assert (f > 0) == (a1 > a2) or f == 0.0
    # raw-crossing sample: the iff must hold everywhere, not just on winners
    me_t = league.teams[league.me]
    my_pkgs = tr._packages(league, tr.give_list(league, me_t))[::151]
    opp_pkgs = tr._packages(league, tr.give_list(league, league.teams["jaketoppen"]))[::67]
    assert my_pkgs and opp_pkgs
    near_boundary = 0
    for g in my_pkgs:
        for t in opp_pkgs:
            a1, a2 = tr.adjusted_gap(league, g, t)
            f = tr.favor_of(a1, a2)
            assert (abs(f) <= 5.0) == ka.check_equality(a1, a2, 5), (g.keys, t.keys)
            if 4.0 <= abs(f) <= 6.0:
                near_boundary += 1
    assert near_boundary > 0  # the boundary region is genuinely exercised


def test_fleece_never_on_board(board):
    """§11.3: the §10.3 shape never surfaces, and no emitted card violates the cap."""
    for card in board_legs(board):
        names = ({a["name"] for a in card["give"]}, {a["name"] for a in card["get"]})
        assert names != ({"Cam Ward"}, {"Shedeur Sanders"})
        assert card["gate"]["raw_ratio"] <= 1.35
        assert card["gate"]["ratio_ok"] and card["gate"]["band_ok"]


def test_board_gate_recomputes_exactly(board, league):
    """§3/§11.3 (v3.4): every displayed leg is inside the EXACT KTC-calculator
    band and under the fleece cap, and the card's gate figures reproduce from a
    fresh gate_info call (no stale or approximated adjusted totals). The screen
    the pool scan runs ahead of the gate never lets a violator through."""
    legs = board_legs(board)
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


def test_board_ranking_and_ids(board):
    """§5 v4/§11.8b(e): stored pairs sort MAXIMIN — floor-based return desc,
    ceiling desc as tie-break, ids last — ALWAYS, whatever the cap filter later
    selects; the secondary sell/neutral list by isolation floor descending;
    ids are sequential."""
    doc = board
    keys = [(p["return_pct"], p["ceiling"]) for p in doc["pairs"]]
    assert keys == sorted(keys, key=lambda t: (-t[0], -t[1]))
    assert [p["id"] for p in doc["pairs"]] == [f"P{i + 1}" for i in range(len(doc["pairs"]))]
    # the ceiling tie-break is exercised for real on this fixture: display
    # returns tie in dozens of places
    assert sum(
        1 for i in range(1, len(keys)) if keys[i][0] == keys[i - 1][0]
    ) > 0
    recs = doc["recommendations"]
    floors = [c["floor"]["me"] for c in recs]
    assert floors == sorted(floors, reverse=True)
    assert [c["id"] for c in recs] == [f"S{i + 1}" for i in range(len(recs))]
    assert [c["rank"] for c in recs] == list(range(1, len(recs) + 1))


def test_pick_cards_carry_both_lenses(board, league):
    """§1 v7: every pick on a card ships the MARKET tranche as `v` (what their
    calculator charges) and MY price as `v_me` (what ΔF booked), with a note
    naming both bands. Players never carry `v_me`. The old display-only
    `concrete` annotation is gone — `v_me` supersedes it and would have been
    the identical number on current-year picks."""
    canonical = {
        a.key: a
        for t in league.teams.values()
        for a in tr.team_assets(league, t).values()
    }
    picks = players = 0
    for card in board_legs(board):
        for a in card["give"] + card["get"]:
            assert "concrete" not in a, a["name"]  # superseded by v_me
            if a["type"] != "pick":
                players += 1
                assert "v_me" not in a
                continue
            picks += 1
            src = canonical[a["key"]]
            if src.v_me == src.v:
                assert "v_me" not in a
                continue
            assert a["v_me"] == round(src.v_me) != a["v"]
            assert "on my side" in a["note"] and "the gate uses theirs" in a["note"]
    assert picks > 0 and players > 0  # the fixture board moves both kinds


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
    assert board["favor_presets"] == [-10.0, -5.0, 0.0, 2.5, 5.0]
    assert board["delta_presets"] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert [e["count"] for e in board["counts_by_threshold"]] == [0] * len(board["presets"])
    assert [(b["stored"], b["count"], b["saturated"]) for b in board["bands"]] == [
        (0, 0, False)
    ] * 5  # the five favor buckets (v5)


def test_below_noise_floor_note(league, params):
    """propose() flags a positive guaranteed floor inside the W_min noise band
    instead of hiding it — display note only, never a gate (v3.3); applied to
    the FLOOR (v4). A floor of exactly 0 carries no note (nothing is
    guaranteed, and 0 is not 'noise')."""
    mine = tr.team_assets(league, league.teams[league.me])
    ron = tr.team_assets(league, league.teams["ronakpatel32"])
    # Mike Evans for ronakpatel32's Wan'Dale Robinson: (ΔS +132, ΔF +132) —
    # objectively good, floor == ceiling == +132, entirely inside KTC's error
    # bars. Players only, so v7's pick lens cannot touch it.
    card = tr.propose(league, "ronakpatel32", [mine["Mike Evans"]], [ron["Wan'Dale Robinson"]])
    assert card["coords"]["me"] == {"dS": 132.0, "dF": 132.0}
    assert card["verdict"]["me"] is True and card["floor"]["me"] == 132.0
    assert 0.0 < card["floor"]["me"] < params.w_min
    note = next(n for n in card.get("notes", []) if "noise" in n)
    assert "not a gate" in note and "floor" in note
    # a pick-for-pick swap with floor exactly 0 gets no noise note. v7 moves the
    # face edge (75 → 153: my 2.09 books at its exact board slot 3,236 while
    # their 2028 2nd comes in Late at 3,389) but not the floor, which is ΔS.
    theirs = tr.team_assets(league, league.teams["jaketoppen"])
    card2 = tr.propose(league, "jaketoppen", [mine["2026 2.09"]], [theirs["2028 R2 (own)"]])
    assert card2["coords"]["me"] == {"dS": 0.0, "dF": 153.0}
    assert card2["floor"]["me"] == 0.0
    assert not any("noise" in n for n in card2.get("notes", []))


# --------------------------------------- §3 v3.4 ceiling annotation (band edge)


def test_ceiling_is_band_edge_info(board, league, params):
    """Each displayed card's ceiling ≥ the proposal's get value, and the ceiling
    package itself clears the exact gate and the fleece cap (it is the maximum
    such Σv — pure negotiating-room information, never the proposal). v3.4: the
    exact band is not monotone in Σv, so the reconstruction scans the whole
    fleece bracket instead of stopping at the first miss."""
    legs = board_legs(board)
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


def test_pair_coords_math_pinned(league):
    """§5 v4 coordinate arithmetic pinned to the fixtures, re-pinned for the v7
    lens. The buy leg swaps my own 2028 4th (market 1,759, but I send it, so it
    books Early 1,916) for a 1,876 non-starter: (0, −40) — verdict now FALSE,
    floor −40. The sell leg ships Joe Burrow plus my 2026 4.01 (board 1,922)
    for Jukinski's 2026 1.12 (board 3,874) and his 2028 1st (received ⇒ Late
    4,768): (−1,312, +976). The PAIR combines: ΔS one re-solve (−1,312 —
    Burrow's slot dent survives, and it is untouched by the lens), ΔF additive
    (+936); verdict FALSE, floor −1,312, breakeven δ* = 0.5836. Floor-based
    return −13.76% on 9,536 MARKET sent — the return is unchanged because this
    pair's floor is the ΔS coordinate, which no lens can move."""
    buy, sell = _fixture_pair_legs(league)
    assert buy["coords"]["me"] == {"dS": 0.0, "dF": -40.0}
    assert (buy["floor"]["me"], sum(a["v"] for a in buy["give"])) == (-40.0, 1759)
    assert buy["verdict"]["me"] is False and buy["return_pct"] == -2.27
    assert sell["coords"]["me"] == {"dS": -1312.0, "dF": 976.0}
    assert (sell["floor"]["me"], sum(a["v"] for a in sell["give"])) == (-1312.0, 7777)
    assert sell["verdict"]["me"] is False
    assert sell["breakeven"]["me"] == round(-1312.0 / (-1312.0 - 976.0), 4) == 0.5734
    pair = tr.pair_coords(league, buy, sell)
    assert pair == {
        "dS": -1312.0,
        "dF": 936.0,
        "verdict": False,
        "floor": -1312.0,
        "ceiling": 936.0,
        "breakeven": 0.5836,
        "sent": 9536.0,
        "return_pct": -13.76,
    }
    # ΔF is additive across legs; ΔS is NOT assembled from the legs
    assert pair["dF"] == buy["coords"]["me"]["dF"] + sell["coords"]["me"]["dF"]


def test_exhaustiveness_spot_check(league, pool):
    """v3.3 anti-starvation, v4 pricing: a known-legal complementary leg pair
    built by hand from the fixtures IS present in the engine's pool and
    validates as a member of the computed pair space at exactly its EXACT
    combined floor-based return."""
    buy, sell = _fixture_pair_legs(league)
    bi = tr.find_pool_leg(
        pool, "cmgaither43",
        [a["key"] for a in buy["give"]], [a["key"] for a in buy["get"]],
    )
    si = tr.find_pool_leg(
        pool, "Jukinski",
        [a["key"] for a in sell["give"]], [a["key"] for a in sell["get"]],
    )
    assert bi is not None and si is not None, "legs missing from the v4 pool"
    ret = tr.pair_in_space(league, pool, bi, si)
    assert ret is not None
    assert round(100 * ret, 2) == -13.76 == tr.pair_coords(league, buy, sell)["return_pct"]


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


def test_posture_is_a_hard_pair_pool_constraint(league, pool, board):
    """§5 v3.3 pinned negative: ronakpatel32 is the fixture's BUYER — a
    picks-majority package at him passes the §3 gate (my 2026 2.09 for Tony
    Pollard: coords (0, +286), objectively good, gap 1.7%) yet appears
    NOWHERE in the pair pool or on the board; millj (SELLER) likewise never
    receives players-majority. The pin is the ABSENCE, not the verdict: a
    gate-clean, objectively-good trade is still refused because the shape
    contradicts the counterparty's posture."""
    mine = tr.team_assets(league, league.teams[league.me])
    ron = tr.team_assets(league, league.teams["ronakpatel32"])
    candidate = tr.propose(league, "ronakpatel32", [mine["2026 2.09"]], [ron["Tony Pollard"]])
    assert candidate["gate"]["verdict"] == "PASS"
    assert candidate["coords"]["me"] == {"dS": 0.0, "dF": 286.0}
    assert candidate["verdict"]["me"] is True and candidate["gate"]["gap_pct"] == 1.7
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
    assert tr.find_pool_leg(
        pool, "ronakpatel32", [mine["2026 2.09"].key], [ron["Tony Pollard"].key]
    ) is None
    for card in board_legs(board):
        label = card["posture"]["label"]
        assert tr.posture_allows(label, card["posture"]["shape"]), card["id"]


def test_board_pairs_verdict_true_and_honest_on_fixture(board, params):
    """§5 v7 / §11.12(g) on the committed fixture. Storage is stratified by
    FAVOR bucket (pair favor = min(f_buy, f_sell)): 925 pairs survive as the
    per-bucket unions of tops by robust return / dS / dF.

    v5 recorded here that the two HIGH-favor buckets were EMPTY, and reasoned
    that a pair both counterparties' calculators like while I keep a ≥1%
    guaranteed floor essentially could not exist. That reasoning was wrong, and
    it was wrong because of a SEARCH defect rather than the market: the walks
    skipped every Δplayers == 0 crossing family outright, and a fixed collection
    budget then starved what remained. With both fixed, v6 pulled [0,+5) from
    0 to 282 of its 300 quota.

    **v7 gives 193 of those back, and that is the lens, not a defect.** Pricing
    my own picks at the dear end of their round and theirs at the cheap end
    costs the modal leg roughly a thousand points of ΔF — 78.9% of my give
    packages carry a pick and 73.9% of opponent get packages re-price — and a
    canonical buy+sell pair takes the hit on BOTH legs. Board 1,178 → 925 and
    [0,+5) 282 → 89. The favor axis is untouched (it reads market face), so what
    shrank is the set of pairs that still clear a positive guaranteed floor once
    the picks are priced my way. [+5,∞) remains empty: giving away MORE than the
    fair window while keeping a positive floor is now harder still.

    The headline pair also moved — v6's top was displaced rather than re-scored
    — which is the honest signal that the lens re-orders the book rather than
    shifting it. Its ΔS is unchanged at +1,783 (no lens can touch the starter
    coordinate; picks never enter the lineup).

    Every count remains a saturated verified floor: the walk orders legs by a
    per-leg key while pairs are priced by exact combined coordinates, so no
    cutoff can certify completeness."""
    doc = board
    bands = doc["bands"]
    assert doc["presets"] == [1.0, 2.5, 5.0, 10.0, 20.0]
    assert doc["favor_presets"] == [-10.0, -5.0, 0.0, 2.5, 5.0]
    # fixture pin: the global top pair is a genuine both-coordinates gain —
    # guaranteed +1,783, at best +1,895 — and both legs sit outside their
    # counterparties' FAIR window in MY favor (the geometry above)
    top = doc["pairs"][0]
    assert top["return_pct"] == 15.23
    assert top["coords"] == {"dS": 1783.0, "dF": 1933.0}
    assert (top["floor"], top["ceiling"]) == (1783.0, 1933.0)
    assert top["verdict"] is True
    assert top["favor"] == {"buy": -9.9, "sell": -8.9, "min": -9.9}
    assert top["sent"] == 11711.0
    # v7 re-pin, 1,178 → 925 (v6 had taken it 886 → 1,178). Unlike v6's two
    # ADDITIVE fixes, this is a genuine contraction: the same search now has to
    # clear a positive floor at MY pick prices.
    assert len(doc["pairs"]) == sum(b["stored"] for b in bands) == 925
    # the counterparty-favorable end, which is the whole point of the stratified
    # storage: [0,+5) — trades their OWN calculator scores as even-or-better for
    # them — went 0 (v5.1) → 282 (v6) → 89 (v7). It is now the binding cost of
    # the lens, and the number to watch if the rule is ever softened.
    assert [b["stored"] for b in bands] == [300, 300, 236, 89, 0]
    for b in bands:
        # v5 union storage: at most 3 top-quota heaps' worth per bucket
        assert b["stored"] <= 3 * params.pairs_per_band
        assert b["count"] >= b["stored"]
        assert b["saturated"] is True  # verified floors throughout (v3.4)
        assert sum(b["by_total"]) == b["count"]  # the grid partitions the bucket
    # §11.8b(d)/§11.12(g): EVERY stored pair is verdict-true, both coordinates
    # strictly positive, interval consistent, favor consistent with its cards
    for pair in doc["pairs"]:
        assert pair["verdict"] is True
        assert pair["coords"]["dS"] > 0 and pair["coords"]["dF"] > 0
        assert pair["floor"] == min(pair["coords"]["dS"], pair["coords"]["dF"])
        assert pair["ceiling"] == max(pair["coords"]["dS"], pair["coords"]["dF"])
        assert pair["favor"]["buy"] == pair["buy"]["favor"]
        assert pair["favor"]["sell"] == pair["sell"]["favor"]
        assert pair["favor"]["min"] == min(pair["favor"]["buy"], pair["favor"]["sell"])
        assert tr.pair_count_deltas(pair["buy"], pair["sell"]) == (0, 0)
        assert pair["return_pct"] >= doc["presets"][0]
    t = doc["truncated"]
    assert t is not None and t["stored"] == 925
    assert t["total"] >= 925 and t["total_saturated"] is True
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


def test_return_bands_and_favor_bucket_math():
    """v5 filter math pinned: total-return bands derive from the floor presets
    as half-open [lo, hi) intervals (open top); FAVOR buckets derive from the
    §5 band edges as half-open intervals open at BOTH ends — a leg can skew
    arbitrarily far toward me (favor → −∞) or toward them. The favor dial is
    a FLOOR: a floor at a bucket edge selects exactly the buckets with
    lo ≥ that edge."""
    bands = tr.return_bands((1.0, 2.5, 5.0, 10.0, 20.0))
    assert bands == [(1.0, 2.5), (2.5, 5.0), (5.0, 10.0), (10.0, 20.0), (20.0, None)]
    assert tr.band_index(bands, 19.39) == 3  # pinned fixture pair total (v4 top)
    assert tr.band_index(bands, 22.98) == 4
    assert tr.band_index(bands, 5.0) == 2 and tr.band_index(bands, 4.99) == 1
    assert tr.band_index(bands, 2.5) == 1 and tr.band_index(bands, 10.0) == 3
    assert tr.band_index(bands, 1.0) == 0
    assert tr.band_index(bands, 0.99) is None  # below the lowest preset: no band

    buckets = tr.favor_buckets((-10.0, -5.0, 0.0, 5.0))
    assert buckets == [
        (None, -10.0), (-10.0, -5.0), (-5.0, 0.0), (0.0, 5.0), (5.0, None),
    ]
    assert tr.bucket_index(buckets, -22.5) == 0  # §10.1's leg, my way entirely
    assert tr.bucket_index(buckets, -10.8) == 0  # pinned fixture top-pair min
    assert tr.bucket_index(buckets, -10.0) == 1  # half-open at the edge
    assert tr.bucket_index(buckets, -5.01) == 1
    assert tr.bucket_index(buckets, -5.0) == 2
    assert tr.bucket_index(buckets, -0.1) == 2
    assert tr.bucket_index(buckets, 0.0) == 3  # their calculator says FAIR
    assert tr.bucket_index(buckets, 4.99) == 3
    assert tr.bucket_index(buckets, 5.0) == 4  # skewed to them beyond FAIR
    assert tr.bucket_index(buckets, 22.5) == 4
    # floor-selection identity: favor_min ≥ e ⟺ bucket.lo ≥ e, at every edge
    for e in (-10.0, -5.0, 0.0, 5.0):
        selected = {i for i, (lo, _hi) in enumerate(buckets) if lo is not None and lo >= e}
        for m in (-22.5, -10.01, -10.0, -5.01, -5.0, -0.1, 0.0, 2.5, 4.99, 5.0, 22.5):
            assert (tr.bucket_index(buckets, m) in selected) == (m >= e), (e, m)


def test_bucket_storage_invariant(board, params):
    """v5 stratification (§11.12(g)): every stored pair's FAVOR MIN sits
    inside its bucket, per-bucket storage is capped at the 3-heap union bound,
    each bucket's stored pairs read robust-return-desc, and the flat list is
    sorted by robust return desc globally (the favor dial filters, the δ dial
    re-sorts client-side — neither re-orders the stored doc)."""
    doc = board
    bands = doc["bands"]
    edges = [(b["lo"], b["hi"]) for b in bands]
    by_bucket: dict[int, list[float]] = {i: [] for i in range(len(bands))}
    for p in doc["pairs"]:
        m = p["favor"]["min"]
        assert m == min(p["favor"]["buy"], p["favor"]["sell"])
        i = tr.bucket_index(edges, m)
        lo, hi = edges[i]
        assert lo is None or m >= lo
        assert hi is None or m < hi
        by_bucket[i].append(p["return_pct"])
    for i, b in enumerate(bands):
        got = by_bucket[i]
        assert len(got) == b["stored"] <= 3 * params.pairs_per_band
        assert got == sorted(got, reverse=True)  # robust-desc within the bucket
        assert b["count"] >= b["stored"]
        if not b["saturated"] and b["count"] <= params.pairs_per_band:
            # a complete walk over a small bucket keeps everything: each heap
            # holds the whole bucket, so the union is the exact tally
            assert b["stored"] == b["count"]
    rets = [p["return_pct"] for p in doc["pairs"]]
    assert rets == sorted(rets, reverse=True)  # global sort: robust return desc
    assert len(doc["pairs"]) == sum(b["stored"] for b in bands)


def test_counts_by_threshold_consistency(board):
    """§5 floor-dial counts (compat, TOTAL return): thresholds ascend with the
    presets, counts are non-increasing in the threshold, saturation is
    downward-closed, and every count covers the stored pairs clearing that
    threshold."""
    doc = board
    entries = doc["counts_by_threshold"]
    assert [e["threshold"] for e in entries] == doc["presets"]
    counts = [e["count"] for e in entries]
    assert counts == sorted(counts, reverse=True)
    sat = [e["saturated"] for e in entries]
    assert sat == sorted(sat, reverse=True)  # True-prefix on ascending thresholds
    for e in entries:
        n_stored = sum(1 for p in doc["pairs"] if p["return_pct"] >= e["threshold"])
        assert e["count"] >= n_stored


def test_grid_consistent_with_buckets_and_thresholds(board):
    """v5 grid honesty: each favor bucket's `by_total` row partitions its
    count exactly; the grid's columns at or above a floor preset sum (across
    every bucket) to that threshold's count; and every (return floor, favor
    floor) cell read is a floor for the stored pairs matching both dials."""
    doc = board
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
    # any (return floor, favor floor) inventory read dominates the stored
    # pairs behind it — favor floors at the bucket edges select whole buckets
    for fmin in (-10.0, -5.0, 0.0, 5.0, None):
        for k, floor_p in enumerate(presets):
            inv = sum(
                sum(b["by_total"][k:])
                for b in bands
                if fmin is None or (b["lo"] is not None and b["lo"] >= fmin)
            )
            n_stored = sum(
                1
                for p in doc["pairs"]
                if p["return_pct"] >= floor_p
                and (fmin is None or p["favor"]["min"] >= fmin)
            )
            assert inv >= n_stored, (fmin, floor_p)


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
        assert b["stored"] <= 3 * 2  # union of three 2-deep heaps (v5)
        assert b["count"] >= b["stored"]
        assert sum(b["by_total"]) == b["count"]
        if not b["saturated"] and b["count"] <= 2:
            assert b["stored"] == b["count"]
    assert len(board["pairs"]) == sum(b["stored"] for b in bands) > 0
    assert [p["id"] for p in board["pairs"]] == [
        f"P{i + 1}" for i in range(len(board["pairs"]))
    ]
    rets = [p["return_pct"] for p in board["pairs"]]
    assert rets == sorted(rets, reverse=True)
    edges = [(b["lo"], b["hi"]) for b in bands]
    for p in board["pairs"]:
        i = tr.bucket_index(edges, p["favor"]["min"])
        assert bands[i]["stored"] > 0
    t = board["truncated"]
    assert t is not None and t["stored"] == len(board["pairs"])
    assert t["total"] > t["stored"]
    assert any("storage cap" in n for n in board["notes"])
    assert any("stratified storage" in n for n in board["notes"])


def test_count_deltas_track_taxi_and_negate_exactly(board, league):
    """§5 v3.2: net_players/net_picks are asset-count arithmetic on the card
    itself (players wherever they land — taxi-routed arrivals included; picks
    regardless of year) and exactly negate across sides."""
    for card in board_legs(board):
        np_me = sum(1 for a in card["get"] if a["type"] == "player") - sum(
            1 for a in card["give"] if a["type"] == "player"
        )
        nk_me = sum(1 for a in card["get"] if a["type"] == "pick") - sum(
            1 for a in card["give"] if a["type"] == "pick"
        )
        assert card["net_players"] == {"me": np_me, "them": -np_me}
        assert card["net_picks"] == {"me": nk_me, "them": -nk_me}
        assert card["standalone"] == (np_me == 0 and nk_me == 0)
        # v6: leg_type follows the CROSSING family, not the player count alone.
        # "neutral" means executable alone — 0 players AND 0 picks. A leg that
        # nets 0 players but ±k picks is NOT standalone and is now pairable, so
        # `canonical_sig` decides which side of the spread it is (through v5.1
        # it was mislabelled "neutral" and no walk could reach it at all).
        expect = (
            "neutral"
            if (np_me == 0 and nk_me == 0)
            else "buy"
            if tr.canonical_sig((np_me, nk_me))
            else "sell"
        )
        assert card["leg_type"] == expect
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
    """§11.7: an unvalued asset contributes 0 to BOTH coordinates (it can never
    start and has no tranche) and is loudly flagged."""
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
    assert with_waller["coords"] == base["coords"]  # v=0 never moves the score silently
    assert with_waller["floor"] == base["floor"]
    assert with_waller["verdict"] == base["verdict"]
    assert with_waller["unvalued"] == ["Darren Waller"]
    waller = next(a for a in with_waller["give"] if a["name"] == "Darren Waller")
    assert waller.get("unvalued") is True
    assert any("unvalued" in n.lower() for n in with_waller["notes"])
