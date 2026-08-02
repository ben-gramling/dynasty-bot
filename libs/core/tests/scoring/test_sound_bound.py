"""§11.13 — the v5.1 SOUND crossing bound.

Through v5.0.1 the floor-objective walks ordered and pruned on each leg's
ISOLATION floor, `min(ΔS, ΔF) − r·Σsent`, which implicitly treats the pair
floor as additive. It is not: ΔS is jointly determined by BOTH legs through the
starting lineup, so pairs whose legs are individually weak but complementary
were pruned unseen. v5.1 keys the walk on

    u(leg) = ΔF(leg) − r · Σsent(leg)        [prune when u_buy + u_sell < 0]

which is sound: ΔF is exactly additive across legs (§11.1 face conservation)
and `floor = min(ΔS, ΔF) ≤ ΔF`, so

    u_buy + u_sell < 0  ⟹  ΔF_pair < r·sent_pair
                        ⟹  floor_pair < r·sent_pair  ⟹  return < r.

The prune can only discard pairs that genuinely fail the return bar.

The four pins, all against the committed 2026-07-26 fixtures:
  (a) a scoped finder query's matched set EQUALS an in-test brute-force
      crossing, element for element, and reports exact=True;
  (b) the two facts the bound rests on, asserted directly: floor ≤ ΔF, and
      ΔF_pair = ΔF_buy + ΔF_sell exactly;
  (c) THE MOTIVATING REGRESSION — a pair whose legs are each below the return
      bar alone but whose COMBINED floor clears it twice over; pre-fix pruned,
      post-fix found;
  (d) nothing v5.0.1 reached is lost: at any cutoff the v5.0.1-keyed walk's
      output is a SUBSET of the v5.1-keyed walk's.

`libs/core/core/scoring/trades.py::_walk_pairs` still accepts `key=L_FLOOR` —
that IS the v5.0.1 walk, kept as the board's coverage phase — so (c) and (d)
compare the two behaviours directly rather than against a stashed checkout.
"""

from __future__ import annotations

import pytest

from core.scoring import Params
from core.scoring import constraints as cn
from core.scoring import finder as fd
from core.scoring import model as md
from core.scoring import trades as tr
from core.scoring.lineup import EMPTY4

# The scoped query every pin runs against: the fixture-pinned Holani-buy /
# Burrow-sell shape, asset-required on all four package sides so the crossing
# finishes exhaustively inside `finder_cross_budget` (constraint push-down at
# work) while still holding ~744k crossings — a real search, not a toy.
SCOPED_CONSTRAINTS = [
    {"who": "Jukinski", "side": "receives", "what": {"asset": "Joe Burrow"}, "mode": "require"},
    {"who": "Jukinski", "side": "sends", "what": {"asset": "2026 1.12"}, "mode": "require"},
    {"who": "cmgaither43", "side": "sends", "what": {"asset": "George Holani"}, "mode": "require"},
    {"who": "cmgaither43", "side": "receives", "what": {"asset": "2028 R4 (own)"}, "mode": "require"},
]
BUY_WITH, SELL_WITH = "cmgaither43", "Jukinski"
SCOPED_QUERY = {
    "legs": {"buy_with": [BUY_WITH], "sell_with": [SELL_WITH]},
    "constraints": SCOPED_CONSTRAINTS,
}


@pytest.fixture(scope="module")
def cache_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("sound-bound-cache")


@pytest.fixture(scope="module")
def scoped_pool(league, cache_dir):
    """The candidate-leg pool `find_spreads` builds for SCOPED_QUERY — same
    constraint push-down, same gate work, so a brute force over it is an
    independent recount of exactly the space the finder searched."""
    compiled, _ = cn.compile_constraints(league, query=SCOPED_CONSTRAINTS)
    tables = fd.load_leg_tables(league, cache_dir)
    return tr.build_pair_pool(
        league,
        enforce_posture=False,
        opponents=[n for n in league.opponents if n in (BUY_WITH, SELL_WITH)],
        my_pkgs_for=lambda opp: [
            p for p in tables[league.me] if cn.package_allowed(compiled, opp, "give", p)
        ],
        opp_pkgs_for=lambda opp: [
            p for p in tables[opp] if cn.package_allowed(compiled, opp, "get", p)
        ],
    )


def _brute_force(league, pool, min_return: float) -> dict:
    """Every VALID count-neutral pair of `pool` clearing the robust bar, keyed
    by asset multisets. No walk, no ordering, no cutoff — the whole crossing,
    with each pair priced by its exact combined coordinates."""
    legs = pool.legs
    me_t = league.teams[league.me]
    buy_oi = pool.opp_names.index(BUY_WITH)
    sell_oi = pool.opp_names.index(SELL_WITH)
    legal: dict = {}
    out: dict[tuple, dict] = {}
    for sig in sorted(pool.buckets):
        if not tr.canonical_sig(sig):
            continue
        comp = pool.buckets.get((-sig[0], -sig[1]))
        if not comp:
            continue
        for bi in pool.buckets[sig]:
            b = legs[bi]
            if b[tr.L_OPP] != buy_oi:
                continue
            for si in comp:
                s = legs[si]
                if s[tr.L_OPP] != sell_oi:
                    continue
                if s[tr.L_OPP] == b[tr.L_OPP] or (s[tr.L_MASK] & b[tr.L_MASK]):
                    continue
                if tr._leg_legal(league, me_t, pool, bi, legal) is False:
                    continue
                if tr._leg_legal(league, me_t, pool, si, legal) is False:
                    continue
                ret, floor, ceil, d_s, d_f = pool.pair_eval(bi, si)
                if not tr.verdict_of(d_s, d_f):  # robust = good at every δ
                    continue
                if ret < min_return / 100.0 - 1e-12:
                    continue
                out[_ident_legs(legs, bi, si)] = {
                    "ret": ret, "floor": floor, "dS": d_s, "dF": d_f,
                }
    return out


def _ident_legs(legs, bi: int, si: int) -> tuple:
    return (
        legs[bi][tr.L_GIVE].keys, legs[bi][tr.L_GET].keys,
        legs[si][tr.L_GIVE].keys, legs[si][tr.L_GET].keys,
    )


def _ident_spread(spread: dict) -> tuple:
    def keys(card, side):
        return tuple(sorted(a["key"] for a in card[side]))

    return (
        keys(spread["buy"], "give"), keys(spread["buy"], "get"),
        keys(spread["sell"], "give"), keys(spread["sell"], "get"),
    )


# ------------------------------------------------------- (b) the two facts


def test_bound_rests_on_floor_le_df_and_df_additivity_11_13b(league, scoped_pool):
    """§11.13(b): the two facts the sound bound is built from, asserted
    directly over fixture pairs rather than argued.

    1. `floor = min(ΔS, ΔF) ≤ ΔF` — trivially true by definition, but it is
       the half that makes ΔF an UPPER bound on the guaranteed floor, so it is
       pinned at leg level (every pool leg) and at pair level (exact combined
       coordinates).
    2. `ΔF_pair = ΔF_buy + ΔF_sell` EXACTLY — face has no lineup interaction
       (§11.1), which is what makes the key additive and the two-pointer prune
       legitimate. ΔS is NOT additive, and the sample below shows pairs where
       it genuinely differs from the leg sum — that difference is the whole
       reason the isolation-floor key was unsound."""
    legs = scoped_pool.legs
    assert legs
    for leg in legs:
        # fact 1 at leg level: the leg's isolation floor never exceeds its ΔF
        assert leg[tr.L_FLOOR] <= leg[tr.L_DFACE] + 1e-9
    me_t = league.teams[league.me]
    legal: dict = {}
    checked = ds_non_additive = 0
    for sig in sorted(scoped_pool.buckets):
        if not tr.canonical_sig(sig):
            continue
        comp = scoped_pool.buckets.get((-sig[0], -sig[1]))
        if not comp:
            continue
        for bi in scoped_pool.buckets[sig][:60]:
            for si in comp[:60]:
                b, s = legs[bi], legs[si]
                if s[tr.L_OPP] == b[tr.L_OPP] or (s[tr.L_MASK] & b[tr.L_MASK]):
                    continue
                if tr._leg_legal(league, me_t, scoped_pool, bi, legal) is False:
                    continue
                if tr._leg_legal(league, me_t, scoped_pool, si, legal) is False:
                    continue
                _ret, floor, _ceil, d_s, d_f = scoped_pool.pair_eval(bi, si)
                # fact 2: ΔF is EXACTLY additive across the legs
                assert d_f == pytest.approx(b[tr.L_DFACE] + s[tr.L_DFACE], abs=1e-9)
                # fact 1: the guaranteed floor never exceeds ΔF
                assert floor <= d_f + 1e-9
                assert floor == min(d_s, d_f)
                # ΔS is not additive — this is what the old key assumed
                iso_ds_b = scoped_pool.index.delta(b[tr.L_OUT4], b[tr.L_IN4])
                iso_ds_s = scoped_pool.index.delta(s[tr.L_OUT4], s[tr.L_IN4])
                if abs(d_s - (iso_ds_b + iso_ds_s)) > 1e-9:
                    ds_non_additive += 1
                checked += 1
    assert checked > 100, checked
    assert ds_non_additive > 0, "the fixture must exhibit real lineup coupling"


def test_add_only_gain_bounds_the_pairs_joint_ds_11_13f(league, scoped_pool):
    """§11.13(f) v6: `ΔS_pair ≤ A_buy + A_sell`, the second half of the
    separable floor bound.

    `A` is the add-only starter gain of a leg's RECEIVED package: what it would
    add to the current lineup with nothing sent away. Starter sum is the
    max-weight basis of a transversal matroid, hence monotone submodular, so
    removals can only lower it and the two additions are subadditive — see
    `tr.pair_ds_bound`.

    The contrast matters as much as the bound: the sum of the legs' ISOLATION
    ΔS values is NOT a bound, and this test asserts the fixture actually
    exhibits that (v5.1's coverage bug was exactly this confusion). A bound
    that were merely 'usually right' would reintroduce it."""
    legs = scoped_pool.legs
    assert legs
    me_t = league.teams[league.me]
    legal: dict = {}
    checked = iso_sum_violations = 0
    for sig in sorted(scoped_pool.buckets):
        if not tr.canonical_sig(sig):
            continue
        comp = scoped_pool.buckets.get((-sig[0], -sig[1]))
        if not comp:
            continue
        for bi in scoped_pool.buckets[sig][:60]:
            for si in comp[:60]:
                b, s = legs[bi], legs[si]
                if s[tr.L_OPP] == b[tr.L_OPP] or (s[tr.L_MASK] & b[tr.L_MASK]):
                    continue
                if tr._leg_legal(league, me_t, scoped_pool, bi, legal) is False:
                    continue
                if tr._leg_legal(league, me_t, scoped_pool, si, legal) is False:
                    continue
                _ret, floor, _ceil, d_s, d_f = scoped_pool.pair_eval(bi, si)
                bound = tr.pair_ds_bound(b[tr.L_A], s[tr.L_A])
                # NO tolerance: every input is integral, so a sound bound holds
                # exactly. Slack is allowed; a violation is not.
                assert d_s <= bound, (d_s, bound, bi, si)
                # and therefore the floor is bounded by the separable minimum
                assert floor <= min(bound, b[tr.L_DFACE] + s[tr.L_DFACE])
                iso_b = scoped_pool.index.delta(b[tr.L_OUT4], b[tr.L_IN4])
                iso_s = scoped_pool.index.delta(s[tr.L_OUT4], s[tr.L_IN4])
                if d_s > iso_b + iso_s + 1e-9:
                    iso_sum_violations += 1
                checked += 1
    assert checked > 100, checked
    assert iso_sum_violations > 0, (
        "the fixture must contain pairs whose joint ΔS exceeds the isolation "
        "sum — otherwise this test cannot distinguish the sound bound from the "
        "unsound one it replaces"
    )


def test_add_only_gain_depends_only_on_the_received_package(league, scoped_pool):
    """§11.13(f) v6: `A` is a function of the GET package alone.

    That is what lets it be solved once per distinct package instead of once
    per leg, and it holds because `pos_columns` drops picks — a leg's received
    STARTABLE set is exactly its received players. If this ever fails, the
    per-package cache in `build_pair_pool` is silently wrong."""
    by_get: dict[tuple[str, ...], float] = {}
    for leg in scoped_pool.legs:
        keys = leg[tr.L_GET].keys
        prev = by_get.setdefault(keys, leg[tr.L_A])
        assert prev == leg[tr.L_A], keys
        # and it IS the add-only solve, not something else
        assert leg[tr.L_A] == scoped_pool.index.delta(EMPTY4, leg[tr.L_IN4])
    assert len(by_get) > 1


# ------------------------------------------ (a) matched set == brute force


def test_finder_matched_set_equals_brute_force_crossing_11_13a(
    league, scoped_pool, cache_dir
):
    """§11.13(a): on a scoped fixture query the finder's matched set EQUALS an
    in-test brute-force crossing of the same constrained pool, ELEMENT FOR
    ELEMENT (asset multisets, not just counts), and the run reports
    `exact=True` — so "no spread matched" from a completed walk is a real
    answer about the space, not about where the walk happened to look.

    Measured on the committed fixtures under the v7 lens: 1,047,492 crossings,
    599,345 valid count-neutral pairs, 115 clearing the 6% robust bar. The bar
    moved 12% → 6% because the lens caps this scoped pool's best pair at 7.30%
    (pre-v7 the same query cleared 12% forty times) — a 12% pin would now be
    vacuously true, which is exactly what this test must not be."""
    query = {**SCOPED_QUERY, "min_return": 6.0, "top": 2000}
    r = fd.find_spreads(league, query, cache_dir=cache_dir)
    assert r["exact"] is True
    brute = _brute_force(league, scoped_pool, 6.0)
    assert len(brute) > 0, "the pin must not be vacuous"
    assert r["counts"]["matched"] == len(brute)
    assert r["counts"]["returned"] == len(r["spreads"]) == len(brute)  # top ≫ matched
    assert {_ident_spread(s) for s in r["spreads"]} == set(brute)
    # …and every returned spread carries the brute force's own exact figures
    for s in r["spreads"]:
        got = brute[_ident_spread(s)]
        assert s["coords"] == {"dS": round(got["dS"], 1), "dF": round(got["dF"], 1)}
        assert s["floor"] == round(got["floor"], 1)
        assert s["return_robust"] == round(100.0 * got["ret"], 2)
    # the exactness claim discriminates: starve the budget and it flips
    starved = md.build_league(league.snapshot, Params(finder_cross_budget=50))
    r2 = fd.find_spreads(starved, query, cache_dir=cache_dir)
    assert r2["exact"] is False
    assert r2["counts"]["matched"] <= r["counts"]["matched"]


# --------------------------------------------- (c) the motivating regression


def test_complementary_pair_the_old_prune_dropped_11_13c(
    league, scoped_pool, cache_dir
):
    """§11.13(c) — THE REGRESSION THAT MOTIVATED v5.1, re-pinned for the v7 lens.

    The pinned pair (committed fixtures, 5% robust return bar):

      buy  from cmgaither43 — I send Jordan Addison + my 2027 1st + my 2028 4th
           (Σ 12,623 market; both picks book at the DEAR end because I am the
           sender, §1 v7) for Jayden Daniels + Rome Odunze + George Holani.
           Isolation floor −95: BELOW the bar, and negative.
      sell to Jukinski     — I send Joe Burrow + Tank Dell + Theo Johnson
           (Σ 11,539) for DK Metcalf + 2026 1.06 + 2026 1.12, the two picks at
           their exact board slots. Isolation floor −1,129: far below the bar.
      pair — ΔS +1,782, ΔF +1,681, guaranteed floor +1,681 on 24,162 sent:
           6.96% return, well clear of the bar. The legs are complementary
           through the starting lineup: each ships starters and reads as a loss
           alone, while together the incoming players rebuild the lineup around
           the holes the other opened.

    Pre-fix vs post-fix, measured, at r = 5% on this pool:
      v5.0.1 key: floor_buy + floor_sell = −95 + −1,129 = −1,224 < 0.05 ×
                  24,162 = 1,208.1 ⟹ σ_buy + σ_sell < 0 ⟹ PRUNED, never priced.
      v5.1 key:   ΔF_buy + ΔF_sell = 1,681 ≥ 1,208.1 ⟹ kept, priced exactly.

    Both walks are run below — `_walk_pairs(key=L_FLOOR)` IS the v5.0.1 walk
    (it survives as the board's coverage phase), so this is the old behaviour
    itself, not a reconstruction of it. On this pool at the 5% bar the sound
    walk keeps 159,510 crossings against the v5.0.1 walk's 230, and 26,089 of
    the 159,280 it uniquely reaches have this exact shape — both legs under the
    bar alone, the pair verdict-true above it.

    v7 note: the old pinned pair (Javonte + 2026 1.01 + 2028 R4 for Daniels +
    Chase Brown + Holani, against Burrow + Godwin + Diggs for MHJ + 1.12 +
    2.04) is no longer an example of anything — buying two current-year picks
    while paying with my own 1.01 collapses its ΔF from +2,975 to −12 under the
    lens. The theorem is untouched; only the fixture example had to move."""
    mine = tr.team_assets(league, league.teams[league.me])
    colin = tr.team_assets(league, league.teams[BUY_WITH])
    josh = tr.team_assets(league, league.teams[SELL_WITH])
    buy_i = tr.find_pool_leg(
        scoped_pool,
        BUY_WITH,
        [mine[n].key for n in ("Jordan Addison", "2027 R1 (own)", "2028 R4 (own)")],
        [colin[n].key for n in ("Jayden Daniels", "Rome Odunze", "George Holani")],
    )
    sell_i = tr.find_pool_leg(
        scoped_pool,
        SELL_WITH,
        [mine[n].key for n in ("Joe Burrow", "Tank Dell", "Theo Johnson")],
        [josh[n].key for n in ("DK Metcalf", "2026 1.06", "2026 1.12")],
    )
    assert buy_i is not None and sell_i is not None
    legs = scoped_pool.legs
    b, s = legs[buy_i], legs[sell_i]
    r = 0.05
    sent = b[tr.L_SENT] + s[tr.L_SENT]

    # --- each leg is individually below the bar (and both are negative alone)
    assert (b[tr.L_FLOOR], b[tr.L_SENT]) == (-95.0, 12623.0)
    assert (s[tr.L_FLOOR], s[tr.L_SENT]) == (-1129.0, 11539.0)
    assert b[tr.L_FLOOR] < r * b[tr.L_SENT] and s[tr.L_FLOOR] < r * s[tr.L_SENT]

    # --- the combined floor clears it
    ret, floor, _ceil, d_s, d_f = scoped_pool.pair_eval(buy_i, sell_i)
    assert (round(d_s, 1), round(d_f, 1)) == (1782.0, 1681.0)
    assert round(floor, 1) == 1681.0 and round(sent, 1) == 24162.0
    assert round(100.0 * ret, 2) == 6.96 and ret >= r
    assert tr.verdict_of(d_s, d_f)
    assert tr.pair_in_space(league, scoped_pool, buy_i, sell_i) is not None

    # --- the keys, side by side, at the bar
    assert b[tr.L_FLOOR] + s[tr.L_FLOOR] == -1224.0 < r * sent  # v5.0.1: pruned
    assert b[tr.L_DFACE] + s[tr.L_DFACE] == 1681.0 >= r * sent  # v5.1: kept

    # --- and that is exactly what the two walks do
    legal: dict = {}
    sound: list = []
    _, done = tr._walk_pairs(league, scoped_pool, r, 10_000_000, legal, sound)
    assert done
    iso: list = []
    _, done_iso = tr._walk_pairs(
        league, scoped_pool, r, 10_000_000, legal, iso, tr.L_FLOOR
    )
    assert done_iso  # the v5.0.1 walk ran to ITS completion and still missed it
    sound_pairs = {(t[3], t[4]) for t in sound}
    iso_pairs = {(t[3], t[4]) for t in iso}
    assert (buy_i, sell_i) in sound_pairs
    assert (buy_i, sell_i) not in iso_pairs

    # --- the consumer sees it: a robust 5% query returns the pair
    found = fd.find_spreads(
        league, {**SCOPED_QUERY, "min_return": 5.0, "top": 400}, cache_dir=cache_dir
    )
    assert found["exact"] is True
    want = _ident_legs(legs, buy_i, sell_i)
    hit = next((sp for sp in found["spreads"] if _ident_spread(sp) == want), None)
    assert hit is not None
    assert hit["return_robust"] == 6.96
    assert hit["coords"] == {"dS": 1782.0, "dF": 1681.0}
    assert hit["floor"] == 1681.0 and hit["verdict"] is True


# ------------------------------------------------- (d) nothing may vanish


def test_v5_0_1_walk_output_is_a_subset_11_13d(league, scoped_pool):
    """§11.13(d): results may change by ADDITION only — no pair the v5.0.1
    prune kept can be lost, because the v5.1 key dominates it pointwise.
    `floor(leg) = min(ΔS, ΔF) ≤ ΔF(leg)`, so at the SAME cutoff

        σ_buy + σ_sell ≥ 0  ⟹  u_buy + u_sell ≥ 0,

    i.e. {v5.0.1 crossings} ⊆ {v5.1 crossings}, pair for pair. Asserted here
    over complete walks at three cutoffs (both keys run to completion, so
    neither set is a budget artefact). Measured on the scoped fixture pool
    under the v7 lens: at r = 3% v5.0.1 keeps 4,004 pairs against v5.1's
    230,841; at 4%, 1,032 against 195,025; at 5%, 230 against 159,510 — the
    additions are the complementary pairs (c) is about, not noise: every one of
    them is priced by its exact combined coordinates. The cutoffs moved down
    from (5%, 8%, 10%) because the v5.0.1 key finds NOTHING at 8% or above
    here, which would make the subset claim vacuous on that side."""
    legal: dict = {}
    for r in (0.03, 0.04, 0.05):
        sound: list = []
        _, d1 = tr._walk_pairs(league, scoped_pool, r, 10_000_000, legal, sound)
        iso: list = []
        _, d2 = tr._walk_pairs(
            league, scoped_pool, r, 10_000_000, legal, iso, tr.L_FLOOR
        )
        assert d1 and d2, r  # neither walk was truncated: sets, not floors
        sound_pairs = {(t[3], t[4]) for t in sound}
        iso_pairs = {(t[3], t[4]) for t in iso}
        assert iso_pairs, r  # non-vacuous on both sides
        assert iso_pairs <= sound_pairs, r
        assert len(sound_pairs) > len(iso_pairs), r  # strict: real additions
        # every addition that clears the bar is genuine inventory the old walk
        # could never have priced
        added_clearing = [
            t for t in sound if (t[3], t[4]) not in iso_pairs and t[0] >= r
        ]
        assert added_clearing, r


def test_board_headline_pair_survives_v5_1(board):
    """§11.13(d) at board level. The nightly collection is budget-truncated on
    the committed fixtures under EITHER key, so the honest statement is about
    the inventory it keeps: v5.1 runs the sound walk first (it is the pass that
    can certify) and then the v5.0.1 collection verbatim as a coverage phase,
    handing back only what the sound walk already owns — so the board is a
    superset of v5.0.1's reach minus per-bucket quota displacement.

    Measured when v5.1 landed: 886 stored either way, 865 identical, 21
    displaced out of the per-bucket top-100-by-ΔF heap by a tie cluster, 21
    admitted in their place; the ≥1% tally rose 609,084 → 609,153.

    v7 re-pin. The headline pair is now a DIFFERENT pair — v6's was displaced,
    not re-scored — because pricing picks my way re-orders the book. What this
    test still guards is that the board's top is a genuine both-coordinates
    gain and that the list is return-sorted. Note ΔS is unchanged at +1,783:
    the lens cannot reach the starter coordinate, since picks never enter the
    lineup."""
    doc = board
    top = doc["pairs"][0]
    assert top["return_pct"] == 15.23
    assert top["coords"] == {"dS": 1783.0, "dF": 1933.0}
    assert (top["floor"], top["ceiling"], top["sent"]) == (1783.0, 1933.0, 11711.0)
    assert doc["counts_by_threshold"][0]["count"] >= 600_000
    rets = [p["return_pct"] for p in doc["pairs"]]
    assert rets == sorted(rets, reverse=True)


# ------------------------------------- exactness plumbing: board + finder


def test_completed_board_walk_reports_exact_counts(snapshot):
    """§5 v5.1 / §11.13(a) at the board: `saturated` now MEANS something on the
    collection path. When the sound top walk runs to completion at a cutoff at
    or below the stored floor, every storable pair was provably visited (the
    key bounds the floor from above), so the tallies are EXACT and `saturated`
    is False.

    Measured pre-fix vs post-fix on this exact configuration:
      v5.0.1: saturated True on every band, ≥1% tally 1,310, 444 pairs stored
      v5.1:   saturated False, ≥1% tally 1,870, 536 pairs stored
    The old tally was disclosed as a floor and it genuinely was one — it
    missed 30% of the space, because the isolation-floor key both prunes
    unsoundly and certifies nothing. The new tally is verified below against a
    full brute force of the same pool.

    The configuration keeps the whole-space branch OUT of reach (25,239
    crossings > the 9,300 collection budget — unchanged by v7, since pool
    membership is decided on market face), so it is the v5.1 path under test
    and not v3.4's.

    v7: this shrinks to 32 pairs / a ≥1% tally of 32, and `truncated` becomes
    None — which is the STRONGER form of the same claim. Nothing was truncated
    because the walk was complete and every storable pair fit."""
    exact_params = Params(
        max_package=1, pair_collect_budget=9_300, pair_scan_budget=1_000
    )
    league = md.build_league(snapshot, exact_params)
    pool = tr.build_pair_pool(league)
    assert _tp_all(pool) > exact_params.pair_collect_budget  # not branch 0
    # the certifying cutoff is half a DISPLAY step under the 1% preset, because
    # that is where the sink's admission boundary really sits
    assert tr._tp_estimate(pool, 0.01 - 5e-5) <= exact_params.pair_collect_budget

    board = tr.trade_board(league)
    assert all(b["saturated"] is False for b in board["bands"])
    assert all(e["saturated"] is False for e in board["counts_by_threshold"])
    # nothing to disclose: the tally is exact AND every counted pair is stored
    assert board["truncated"] is None
    assert board["counts_by_threshold"][0]["count"] == len(board["pairs"]) == 32

    # independent brute force of the SAME pool: the tallies are real counts
    me_t = league.teams[league.me]
    legal: dict = {}
    tally = [0] * len(board["presets"])
    for sig in sorted(pool.buckets):
        if not tr.canonical_sig(sig):
            continue
        comp = pool.buckets.get((-sig[0], -sig[1]))
        if not comp:
            continue
        for bi in pool.buckets[sig]:
            b = pool.legs[bi]
            for si in comp:
                s = pool.legs[si]
                if s[tr.L_OPP] == b[tr.L_OPP] or (s[tr.L_MASK] & b[tr.L_MASK]):
                    continue
                if tr._leg_legal(league, me_t, pool, bi, legal) is False:
                    continue
                if tr._leg_legal(league, me_t, pool, si, legal) is False:
                    continue
                ret, _floor, _ceil, _d_s, _d_f = pool.pair_eval(bi, si)
                if ret <= 0.0:
                    continue
                idx = tr.band_index(
                    tr.return_bands(board["presets"]), round(100.0 * ret, 2)
                )
                if idx is not None:
                    tally[idx] += 1
    for k, e in enumerate(board["counts_by_threshold"]):
        assert e["count"] == sum(tally[k:]), (k, e)
    # …and the flag discriminates: starve the collection and it saturates
    starved = md.build_league(
        snapshot,
        Params(max_package=1, pair_collect_budget=200, pair_scan_budget=200),
    )
    board2 = tr.trade_board(starved)
    assert any(b["saturated"] for b in board2["bands"])
    assert board2["counts_by_threshold"][0]["count"] <= board["counts_by_threshold"][0]["count"]


def _tp_all(pool) -> int:
    return tr._tp_estimate(pool, -1e9)


# ------------------------------------------- (e) boundary and phase integrity


def _mini_pool(pool, bi: int, si: int) -> tr.PairPool:
    """A two-leg pool holding exactly one crossing (buy leg 0, sell leg 1) —
    real legs, real starter index, so `pair_eval` prices it exactly."""
    b, s = pool.legs[bi], pool.legs[si]
    return tr.PairPool(
        opp_names=pool.opp_names,
        legs=[b, s],
        buckets={
            (b[tr.L_NP], b[tr.L_NK]): [0],
            (s[tr.L_NP], s[tr.L_NK]): [1],
        },
        opp_pkgs=pool.opp_pkgs,
        enforce_posture=False,
        index=pool.index,
    )


def test_exact_tie_on_the_bar_is_kept_11_13e(league, scoped_pool):
    """§11.13(e): a crossing sitting EXACTLY on the bar must survive the prune.

    The walks test the bound in SPLIT form — `(r·sent_b − ΔF_b) + (r·sent_s −
    ΔF_s) ≤ 0` — because that is what makes the two-pointer early exit
    possible. The bound itself is the PAIR form `ΔF_pair ≥ r·sent_pair`. The
    two are the same identity in ℝ and NOT the same in float64: ΔF and Σsent
    are integral, so `r·sent` is exact often enough that the split sum lands on
    +2.3e-13 where the pair form reads a dead heat. Such a pair qualifies
    whenever `floor == ΔF` (i.e. ΔS ≥ ΔF) — its exact return IS r — so a
    zero-tolerance split test discards a pair the bound promises to keep. That
    is a one-ULP hole in "the prune can only discard pairs that genuinely fail
    the bar", and `tr.XTOL` closes it.

    The fixture pair the search lands on is the one the soundness audit found:
    ΔS +437 / ΔF +433 on 15,316 sent, return 2.827…%, split sum +2.27e-13."""
    legs = scoped_pool.legs
    me_t = league.teams[league.me]
    legal: dict = {}
    tie = None
    for sig in sorted(scoped_pool.buckets):
        if not tr.canonical_sig(sig) or tie is not None:
            continue
        comp = scoped_pool.buckets.get((-sig[0], -sig[1]))
        if not comp:
            continue
        for bi in scoped_pool.buckets[sig][:120]:
            for si in comp[:120]:
                b, s = legs[bi], legs[si]
                if s[tr.L_OPP] == b[tr.L_OPP] or (s[tr.L_MASK] & b[tr.L_MASK]):
                    continue
                if tr._leg_legal(league, me_t, scoped_pool, bi, legal) is False:
                    continue
                if tr._leg_legal(league, me_t, scoped_pool, si, legal) is False:
                    continue
                ret, floor, _c, d_s, d_f = scoped_pool.pair_eval(bi, si)
                if d_s < d_f or d_f <= 0:
                    continue  # need floor == ΔF > 0: return sits ON the key
                nb = ret * b[tr.L_SENT] - b[tr.L_DFACE]
                ns = ret * s[tr.L_SENT] - s[tr.L_DFACE]
                if nb + ns > 0.0:  # a zero-tolerance split test prunes it
                    tie = (bi, si, ret, floor, nb + ns)
                    break
            if tie is not None:
                break
    assert tie is not None, "the fixture must exhibit an on-the-bar crossing"
    bi, si, r, floor, split = tie
    b, s = legs[bi], legs[si]
    sent = b[tr.L_SENT] + s[tr.L_SENT]
    # the pair form says it qualifies (its exact return IS the bar)…
    assert floor == b[tr.L_DFACE] + s[tr.L_DFACE]
    assert b[tr.L_DFACE] + s[tr.L_DFACE] >= r * sent
    # …while the split form the walk actually evaluates rounds the wrong way
    assert split > 0.0
    assert split < tr.XTOL  # and by less than one KTC micro-point

    mini = _mini_pool(scoped_pool, bi, si)
    out: list = []
    _, done = tr._walk_pairs(league, mini, r, 10, {0: True, 1: True}, out)
    assert done
    assert [(t[3], t[4]) for t in out] == [(0, 1)], "the tie must be KEPT at r"
    # and the complement still owns nothing here: the two walks partition
    below: list = []
    _, done_b = tr._walk_pairs_below(league, mini, r, 10, {0: True, 1: True}, below)
    assert done_b and below == []
    # a bar one micro-point above the pair's return really does exclude it
    high: list = []
    tr._walk_pairs(league, mini, r + 1e-3, 10, {0: True, 1: True}, high)
    assert high == []


def test_coverage_phase_only_hands_back_a_region_that_was_walked_11_13e(
    league, scoped_pool
):
    """§11.13(e): `_DropSpans` hands the sound phase's region back ONLY when
    that phase actually ran.

    The board's coverage phase (v5.0.1 key) skips crossings the sound top walk
    already owns, so the tallies stay counts of DISTINCT pairs. That skip is
    valid exactly because the sound walk enumerated them. A sound phase that
    never ran owns nothing: handing it a region would drop storable pairs
    nobody enumerated (measured on a deliberately starved walk: 487,795
    crossings handed back, 49,709 of them storable). So `trade_board` runs the
    sound phase only when `_tp_estimate` proves it fits the collection budget —
    the estimate upper-bounds the walk's visits, so fitting implies completing
    — and passes `sound_hi=None` when the phase was skipped. Pinned here at the
    adapter, where both branches are directly observable."""
    legs = scoped_pool.legs
    b_i, s_i = None, None
    for sig in sorted(scoped_pool.buckets):
        if not tr.canonical_sig(sig):
            continue
        comp = scoped_pool.buckets.get((-sig[0], -sig[1]))
        if comp:
            b_i, s_i = scoped_pool.buckets[sig][0], comp[0]
            break
    assert b_i is not None
    b, s = legs[b_i], legs[s_i]
    sent = b[tr.L_SENT] + s[tr.L_SENT]
    d_f = b[tr.L_DFACE] + s[tr.L_DFACE]
    owned = d_f / sent  # the crossing's ΔF-return: a walk at this r owns it
    row = (0.0, 0.0, owned, b_i, s_i, 0.0, d_f)

    kept: list = []
    tr._DropSpans(kept, [], legs, None).append(row)
    assert kept == [row], "no sound phase ran: nothing may be dropped"

    dropped: list = []
    tr._DropSpans(dropped, [], legs, owned).append(row)
    assert dropped == [], "the completed sound walk at r owns this crossing"

    passed: list = []
    tr._DropSpans(passed, [], legs, owned + 1e-3).append(row)
    assert passed == [row], "above the sound cutoff the coverage phase keeps it"
