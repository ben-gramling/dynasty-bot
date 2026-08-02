"""§4a v5 the spread finder + the §11.12 pins that live at query level:
(b) constraint soundness on the user's five pinned intel examples,
(c) δ-view ranking identities and robust == v4 maximin,
(d) warm/cold byte-identical determinism through the disk cache,
(e) exact-vs-floor count honesty under the crossing budget.

Queries here are deliberately CONSTRAINED (legs filters + asset requires) so
each call's gate scan and crossing stay small — the §4a design point under
test is precisely that constraints narrow the work."""

from __future__ import annotations

import json

import pytest

from core.scoring import Params
from core.scoring import constraints as cn
from core.scoring import finder as fd
from core.scoring import model as md
from core.scoring import trades as tr

from .test_constraints import INTEL


@pytest.fixture(scope="module")
def cache_dir(tmp_path_factory):
    """Shared finder cache — warm after the first query, exactly like prod."""
    return tmp_path_factory.mktemp("finder-cache")


# the (c)/(d)/(e) workhorse: the fixture-pinned Holani-buy/Burrow-sell shape,
# asset-required on ALL FOUR package sides so the crossing finishes
# exhaustively inside finder_cross_budget (constraint push-down at work)
NARROW_QUERY = {
    "legs": {"buy_with": ["cmgaither43"], "sell_with": ["Jukinski"]},
    "constraints": [
        {"who": "Jukinski", "side": "receives", "what": {"asset": "Joe Burrow"}, "mode": "require"},
        {"who": "Jukinski", "side": "sends", "what": {"asset": "2026 1.12"}, "mode": "require"},
        {"who": "cmgaither43", "side": "sends", "what": {"asset": "George Holani"}, "mode": "require"},
        {"who": "cmgaither43", "side": "receives", "what": {"asset": "2028 R4 (own)"}, "mode": "require"},
    ],
    "top": 50,
}


def _spread_packages(league, spread):
    return tr.card_packages(league, spread["buy"]), tr.card_packages(league, spread["sell"])


def test_finder_output_contract(league, cache_dir):
    r = fd.find_spreads(league, NARROW_QUERY, cache_dir=cache_dir)
    assert set(r) == {"spreads", "counts", "exact", "applied_constraints", "ignored_intel"}
    assert r["ignored_intel"] == []
    assert set(r["counts"]) == {"legs", "crossings", "valid", "matched", "returned"}
    assert r["counts"]["returned"] == len(r["spreads"]) <= 50
    assert r["counts"]["matched"] >= r["counts"]["returned"]
    assert r["counts"]["valid"] >= r["counts"]["matched"]
    assert r["counts"]["crossings"] >= r["counts"]["valid"]
    assert r["spreads"], "the pinned Holani/Burrow shape must produce spreads"
    seen_ids = [s["id"] for s in r["spreads"]]
    assert seen_ids == [f"F{i + 1}" for i in range(len(seen_ids))]
    me_t = league.teams[league.me]
    for s in r["spreads"]:
        assert set(s) == {
            "id", "buy", "sell", "coords", "verdict", "floor", "ceiling",
            "sent", "return_robust", "return_view", "favor", "preferred",
            "sequencing", "net_players", "net_picks", "net_roster",
        }
        # §3: every leg passes the EXACT gate — recomputed, not trusted
        (bg, bt), (sg, st) = _spread_packages(league, s)
        for give, get in ((bg, bt), (sg, st)):
            gate = tr.gate_info(league, give, get)
            assert gate["band_ok"] and gate["ratio_ok"]
        legal_b = tr.legality(league, me_t, league.teams[s["buy"]["counterparty"]], bg, bt)
        legal_s = tr.legality(league, me_t, league.teams[s["sell"]["counterparty"]], sg, st)
        assert legal_b["legal"] and legal_s["legal"]
        # count-neutral 0/0, distinct counterparties, asset-disjoint
        assert s["net_players"] == 0 and s["net_picks"] == 0
        assert tr.pair_count_deltas(s["buy"], s["sell"]) == (0, 0)
        assert s["buy"]["counterparty"] != s["sell"]["counterparty"]
        keys = lambda c: {a["key"] for a in c["give"] + c["get"]}
        assert not keys(s["buy"]) & keys(s["sell"])
        # exact combined coordinates: recomputed from the leg cards
        got = tr.pair_coords(league, s["buy"], s["sell"])
        assert s["coords"] == {"dS": got["dS"], "dF": got["dF"]}
        assert s["floor"] == got["floor"] and s["ceiling"] == got["ceiling"]
        assert s["sent"] == got["sent"]
        assert s["return_robust"] == got["return_pct"]
        assert s["verdict"] == got["verdict"]
        # favor: each leg's card figure and the min (§11.12(a) one source)
        assert s["favor"]["buy"] == s["buy"]["favor"]
        assert s["favor"]["sell"] == s["sell"]["favor"]
        assert s["favor"]["min"] == min(s["favor"]["buy"], s["favor"]["sell"])
        assert isinstance(s["preferred"], bool)
        # the required assets really flow: Burrow to Jukinski, Holani to me
        assert any(a["name"] == "Joe Burrow" for a in s["sell"]["give"])
        assert any(a["name"] == "George Holani" for a in s["buy"]["get"])


def test_constraint_soundness_11_12b(league, cache_dir):
    """§11.12(b): with the five pinned intel examples active, NO returned
    spread violates any require/exclude — checked structurally per §4
    semantics AND via the compiled predicates, both recomputed from the
    returned cards."""
    query = {
        "legs": {
            "buy_with": ["ronakpatel32", "cmgaither43"],
            "sell_with": ["joeydavis299", "josbaski"],
        },
        "min_return": 1.0,
    }
    r = fd.find_spreads(league, query, intel=INTEL, cache_dir=cache_dir)
    assert r["ignored_intel"] == []
    origins = [c["origin"] for c in r["applied_constraints"]]
    # ronak's intel REPLACED his posture default (later source, same team)
    assert any("intel WANT: ronakpatel32" in o for o in origins)
    assert not any(o == "posture BUYER" for o in origins)
    assert any("intel DONT_WANT: *" in o for o in origins)
    assert r["spreads"], "the constrained fixture space is not empty"
    compiled, ignored = cn.compile_constraints(league, intel=INTEL)
    assert ignored == []
    for s in r["spreads"]:
        (bg, bt), (sg, st) = _spread_packages(league, s)
        for card, (give, get) in ((s["buy"], (bg, bt)), (s["sell"], (sg, st))):
            opp = card["counterparty"]
            # the compiled §4 predicates hold on every returned leg
            assert cn.leg_allowed(compiled, opp, give, get), (s["id"], opp)
            # …and the named example semantics, spelled out:
            give_names = {a["name"] for a in card["give"]}
            assert "Stefon Diggs" not in give_names  # nobody wants Diggs
            if opp == "ronakpatel32":  # ronak wants draft picks
                assert tr.offer_shape(give) == "picks"
            if opp == "joeydavis299":  # joey wants a running back
                assert any(a.kind == "player" and a.pos == "RB" for a in give.assets)
            if opp == "josbaski":  # josh b wants joe burrow
                assert "Joe Burrow" in give_names


def test_delta_view_identities_11_12c(league, cache_dir):
    """§11.12(c): ranking by return(δ) at δ=0 equals ranking by ΔS-return, at
    δ=1 by ΔF-return; robust mode reproduces the v4 maximin exactly (floor
    return, ceiling tie-break, verdict required). The blend is evaluated from
    the STORED coordinates — the identities are checked against exact
    recomputation from the returned cards."""
    runs = {
        delta: fd.find_spreads(
            league, {**NARROW_QUERY, "delta": delta}, cache_dir=cache_dir
        )
        for delta in (0.0, 1.0, 0.5, "robust")
    }
    for delta, r in runs.items():
        assert r["spreads"], delta
        views = [s["return_view"] for s in r["spreads"]]
        assert views == sorted(views, reverse=True), delta
        for s in r["spreads"]:
            got = tr.pair_coords(league, s["buy"], s["sell"])
            d_s, d_f, sent = got["dS"], got["dF"], got["sent"]
            if delta == "robust":
                want = min(d_s, d_f)
            else:
                want = d_s + delta * (d_f - d_s)
            # ΔW(0)=ΔS, ΔW(1)=ΔF, robust=floor — within display rounding
            assert s["return_view"] == pytest.approx(100.0 * want / sent, abs=0.02), delta
        # ranking identity: view-return is non-increasing in the recomputed
        # ΔS-return (δ=0) / ΔF-return (δ=1) up to display-precision ties
        key = {0.0: "dS", 1.0: "dF"}.get(delta)
        if key:
            exact = [
                tr.pair_coords(league, s["buy"], s["sell"]) for s in r["spreads"]
            ]
            ratios = [g[key] / g["sent"] for g in exact]
            for a, b in zip(ratios, ratios[1:]):
                assert a >= b - 1e-4
    # robust == v4 maximin: verdict-true throughout, floor-return ranking with
    # ceiling desc tie-break, and view == robust figure
    rob = runs["robust"]
    for s in rob["spreads"]:
        assert s["verdict"] is True
        assert s["return_view"] == s["return_robust"]
    keys = [(-s["return_robust"], -s["ceiling"]) for s in rob["spreads"]]
    assert keys == sorted(keys)
    # every robust spread also appears under some δ view of the same query
    # (robust only ADDS the verdict filter — it never invents inventory)
    def id_set(r):
        return {
            (
                tuple(sorted(a["key"] for a in s["buy"]["give"] + s["buy"]["get"])),
                tuple(sorted(a["key"] for a in s["sell"]["give"] + s["sell"]["get"])),
            )
            for r_ in [r]
            for s in r_["spreads"]
        }
    if all(
        r["exact"] and r["counts"]["matched"] <= 50 for r in runs.values()
    ):
        # untruncated and under the top cap on every run: set containment holds
        assert id_set(rob) <= id_set(runs[0.0]) | id_set(runs[1.0]) | id_set(runs[0.5])


def test_finder_determinism_11_12d(league, tmp_path):
    """§11.12(d): a cold query (empty cache dir), then the same query warm —
    byte-identical results, and the cache file exists after the cold run.
    Identical query → identical results is the same comparison."""
    cache = tmp_path / "cache"
    assert not cache.exists()
    r_cold = fd.find_spreads(league, NARROW_QUERY, cache_dir=cache)
    files = list(cache.glob("finder-*.json"))
    assert len(files) == 1  # (snapshot fingerprint, params hash) entry
    r_warm = fd.find_spreads(league, NARROW_QUERY, cache_dir=cache)
    assert json.dumps(r_cold, sort_keys=True) == json.dumps(r_warm, sort_keys=True)
    assert list(cache.glob("finder-*.json")) == files  # same entry, no churn
    assert r_cold["spreads"]  # the comparison is not vacuous


def test_honest_counts_exact_vs_floor_11_12e(league, snapshot, cache_dir, tmp_path):
    """§11.12(e): a crossing that fits the budget reports EXACT counts —
    verified here by an independent recount over an independently built
    constrained pool — and a budget-starved run reports floors (≤ the exact
    tallies), never estimates."""
    r = fd.find_spreads(league, NARROW_QUERY, cache_dir=cache_dir)
    assert r["exact"] is True
    # ---- independent recount of the valid pair space
    compiled, _ = cn.compile_constraints(
        league, query=NARROW_QUERY["constraints"]
    )
    tables = fd.load_leg_tables(league, cache_dir)
    opponents = ["cmgaither43", "Jukinski"]
    pool = tr.build_pair_pool(
        league,
        enforce_posture=False,
        opponents=opponents,
        my_pkgs_for=lambda opp: [
            p for p in tables[league.me] if cn.package_allowed(compiled, opp, "give", p)
        ],
        opp_pkgs_for=lambda opp: [
            p for p in tables[opp] if cn.package_allowed(compiled, opp, "get", p)
        ],
    )
    colin_i = pool.opp_names.index("cmgaither43")
    juk_i = pool.opp_names.index("Jukinski")
    me_t = league.teams[league.me]
    legal: dict = {}
    valid = matched = 0
    for sig in sorted(pool.buckets):
        if not tr.canonical_sig(sig):
            continue
        comp = pool.buckets.get((-sig[0], -sig[1]))
        if not comp:
            continue
        for bi in pool.buckets[sig]:
            if pool.legs[bi][tr.L_OPP] != colin_i:
                continue
            for si in comp:
                s = pool.legs[si]
                if s[tr.L_OPP] != juk_i:
                    continue
                if pool.legs[bi][tr.L_MASK] & s[tr.L_MASK]:
                    continue
                if tr._leg_legal(league, me_t, pool, bi, legal) is False:
                    continue
                if tr._leg_legal(league, me_t, pool, si, legal) is False:
                    continue
                valid += 1
                ret, floor, _ceil, d_s, d_f = pool.pair_eval(bi, si)
                if tr.verdict_of(d_s, d_f) and ret >= -1e-12:
                    matched += 1
    # v6: `valid` counts the legal crossings the walk VISITED, and the walk now
    # carries a sound break, so it legitimately visits fewer than a brute force
    # that enumerates everything. What must NOT move is `matched`: the break is
    # sound precisely because it only ever skips crossings that provably cannot
    # qualify, so the matched set is still exhaustive. That is the assertion
    # worth pinning — equality on `valid` would pin the absence of a prune.
    assert r["counts"]["valid"] <= valid
    assert r["counts"]["matched"] == matched
    # ---- budget-starved: floors, disclosed, never estimates
    starved_league = md.build_league(snapshot, Params(finder_cross_budget=50))
    r2 = fd.find_spreads(starved_league, NARROW_QUERY, cache_dir=tmp_path)
    assert r2["exact"] is False
    assert r2["counts"]["crossings"] == 50  # saturated exactly at the budget
    for k in ("valid", "matched"):
        assert r2["counts"][k] <= r["counts"][k]
    # what it did return is still fully validated inventory
    for s in r2["spreads"]:
        assert s["verdict"] is True or NARROW_QUERY.get("delta", "robust") != "robust"


def test_favor_pushdown_coverage_pin_v5_0_1(league, cache_dir):
    """v5.0.1 coverage pin: for a δ-view favor-banded query, find_spreads'
    matched count EQUALS an exhaustive in-test crossing of the same
    constrained pool that applies every validity rule at PAIR level only
    (distinct counterparties, disjoint masks, complementary signatures, leg
    legality, pair_eval + all three sliders) — i.e. the leg-level favor
    push-down provably drops no qualifying pair, and the filtered crossing
    finished exhaustively (exact counts, not floors).

    The v5.0 defect this pins against: the walk crossed the FULL pool in
    isolation-floor order, and fair legs have small or NEGATIVE floors, so a
    favor-banded δ-view query could burn the whole budget without reaching
    the fair region (a production-shaped query returned matched=0 while an
    exhaustive crossing held 3.1M qualifying pairs)."""
    query = {
        **NARROW_QUERY,
        "delta": 0.25,
        "min_return": 1.0,
        "favor_min": -5.0,
        "favor_max": 5.0,
    }
    r = fd.find_spreads(league, query, cache_dir=cache_dir)
    assert r["exact"] is True  # the favor-filtered crossing fits the budget
    # ---- independent exhaustive crossing: pool built exactly like the
    # finder's, but the favor window applied ONLY at pair level
    compiled, _ = cn.compile_constraints(league, query=query["constraints"])
    tables = fd.load_leg_tables(league, cache_dir)
    opponents = [n for n in league.opponents if n in ("cmgaither43", "Jukinski")]
    pool = tr.build_pair_pool(
        league,
        enforce_posture=False,
        opponents=opponents,
        my_pkgs_for=lambda opp: [
            p for p in tables[league.me] if cn.package_allowed(compiled, opp, "give", p)
        ],
        opp_pkgs_for=lambda opp: [
            p for p in tables[opp] if cn.package_allowed(compiled, opp, "get", p)
        ],
    )
    colin_i = pool.opp_names.index("cmgaither43")
    juk_i = pool.opp_names.index("Jukinski")
    me_t = league.teams[league.me]
    legs = pool.legs
    legal: dict = {}
    min_ret = query["min_return"] / 100.0
    matched = 0
    for sig in sorted(pool.buckets):
        if not tr.canonical_sig(sig):
            continue
        comp = pool.buckets.get((-sig[0], -sig[1]))
        if not comp:
            continue
        for bi in pool.buckets[sig]:
            if legs[bi][tr.L_OPP] != colin_i:  # buy_with cmgaither43
                continue
            for si in comp:
                s = legs[si]
                if s[tr.L_OPP] != juk_i:  # sell_with Jukinski
                    continue
                if legs[bi][tr.L_OPP] == s[tr.L_OPP]:
                    continue
                if legs[bi][tr.L_MASK] & s[tr.L_MASK]:
                    continue
                if tr._leg_legal(league, me_t, pool, bi, legal) is False:
                    continue
                if tr._leg_legal(league, me_t, pool, si, legal) is False:
                    continue
                fb, fs, fmin = pool.pair_favor(bi, si)
                if fmin < query["favor_min"]:
                    continue
                if (fb if fb > fs else fs) > query["favor_max"]:
                    continue
                _ret, _floor, _ceil, d_s, d_f = pool.pair_eval(bi, si)
                sent = legs[bi][tr.L_SENT] + s[tr.L_SENT]
                rv = (d_s + query["delta"] * (d_f - d_s)) / sent
                if rv < min_ret - 1e-12:
                    continue
                matched += 1
    assert matched > 0  # non-vacuous (2,787 on the committed fixtures)
    assert r["counts"]["matched"] == matched


def test_favor_band_delta_view_full_slate_regression(snapshot, tmp_path):
    """v5.0.1 regression: a δ-view query with a favor window over the FULL
    fixture slate under a tight crossing budget MUST find matches. Pre-fix,
    the floor-ordered full-pool walk found 6 matches in these 50,000
    crossings (and the production case found 0 in 50M); post-fix the walk's
    crossing space IS the favor band, δ-score ordered, so the same budget
    yields tens of thousands. The truncation itself stays honestly disclosed:
    exact=False, floors only.

    v6 re-pin: 36,945 → 29,110 at this deliberately tiny budget, because
    `canonical_sig` restored the Δplayers == 0 crossing family and a FIXED
    budget spread over a larger space reaches less of it. That is the same
    starvation `pair_collect_budget` was raised 10× for; this test pins the
    budget at 50,000 on purpose, so it sees the trade-off undiluted. The
    assertion's job is unchanged — guard the v5.0 defect, where this was 6."""
    league = md.build_league(snapshot, Params(finder_cross_budget=50_000))
    r = fd.find_spreads(
        league,
        {"delta": 0.25, "min_return": 1.0, "favor_min": -5, "favor_max": 5},
        cache_dir=tmp_path,
    )
    assert r["counts"]["matched"] > 25_000  # pre-fix: 6; v5.1: 36,945; v6: 29,110
    assert r["counts"]["returned"] == len(r["spreads"]) == league.params.finder_top
    # legs counts are the favor-ELIGIBLE legs — the constrained crossing space
    assert 0 < r["counts"]["legs"]["buy"] < 20_000
    assert 0 < r["counts"]["legs"]["sell"] < 60_000
    # budget-truncated: a verified floor, never an estimate — and said so
    assert r["exact"] is False
    assert r["counts"]["crossings"] == 50_000
    for s in r["spreads"]:
        assert s["favor"]["min"] >= -5
        assert max(s["favor"]["buy"], s["favor"]["sell"]) <= 5
        assert s["return_view"] >= 1.0


def test_sliders_filter_on_exact_figures(league, cache_dir):
    """Slider 2/3 + structural filters: favor floor/ceiling, shape, and
    with_team all filter on the exact stored figures."""
    base = fd.find_spreads(league, NARROW_QUERY, cache_dir=cache_dir)
    assert base["spreads"]
    fmins = sorted(s["favor"]["min"] for s in base["spreads"])
    cut = fmins[len(fmins) // 2]  # a floor that really splits the results
    floored = fd.find_spreads(
        league, {**NARROW_QUERY, "favor_min": cut}, cache_dir=cache_dir
    )
    assert all(s["favor"]["min"] >= cut for s in floored["spreads"])
    assert floored["counts"]["matched"] <= base["counts"]["matched"]
    ceiled = fd.find_spreads(
        league, {**NARROW_QUERY, "favor_max": 0.0}, cache_dir=cache_dir
    )
    for s in ceiled["spreads"]:
        assert max(s["favor"]["buy"], s["favor"]["sell"]) <= 0.0
    for shape, cmp in (("starter>team", lambda c: c["dS"] > c["dF"]),
                       ("team>starter", lambda c: c["dF"] > c["dS"])):
        shaped = fd.find_spreads(
            league, {**NARROW_QUERY, "shape": shape, "delta": 0.5}, cache_dir=cache_dir
        )
        for s in shaped["spreads"]:
            assert cmp(s["coords"]), shape
    with_t = fd.find_spreads(
        league, {**NARROW_QUERY, "with_team": "Jukinski"}, cache_dir=cache_dir
    )
    for s in with_t["spreads"]:
        assert "Jukinski" in (s["buy"]["counterparty"], s["sell"]["counterparty"])
    # a min_return floor narrows matched monotonically (the efficiency
    # contract's filter direction)
    high = fd.find_spreads(
        league, {**NARROW_QUERY, "min_return": 5.0}, cache_dir=cache_dir
    )
    assert high["counts"]["matched"] <= base["counts"]["matched"]
    assert all(s["return_view"] >= 5.0 for s in high["spreads"])


def test_with_team_is_scoped_before_the_walk_not_after(snapshot, tmp_path):
    """§4a v6: `with_team` decides which crossings are WALKED, not which ones
    survive after the budget has already been charged for them.

    Through v5.1 the test lived in the innermost loop AFTER `visits += 1`, so a
    per-counterparty query spent its whole budget walking the league-wide space
    and then discarded everything off-team. The full slate under a tight budget
    is exactly that pathology: pinned here so a regression cannot hide behind a
    query (like `NARROW_QUERY`) that already restricts both sides to a single
    counterparty, where scoping is legitimately a no-op.

    Scoping is a PARTITION, not a sample: legs in a pair always have distinct
    counterparties, so "the buy leg is theirs" and "the sell leg is theirs" are
    mutually exclusive and jointly cover every in-scope pair — nothing is lost
    and nothing is counted twice."""
    league = md.build_league(snapshot, Params(finder_cross_budget=50_000))
    q = {"delta": 0.25, "min_return": 1.0, "favor_min": -5, "favor_max": 5}
    base = fd.find_spreads(league, q, cache_dir=tmp_path)
    assert base["exact"] is False, "budget must bind for this pin to mean anything"

    team = base["spreads"][0]["buy"]["counterparty"]
    scoped = fd.find_spreads(league, {**q, "with_team": team}, cache_dir=tmp_path)

    assert all(
        team in (s["buy"]["counterparty"], s["sell"]["counterparty"])
        for s in scoped["spreads"]
    )
    # the same budget now buys strictly more of the region actually asked for:
    # pre-fix both walks visited the identical league-wide crossings and the
    # scoped one merely threw most away, so its matched count could only be
    # LOWER than base's. Post-fix every visit is in scope.
    assert scoped["counts"]["matched"] > 0
    base_in_scope = sum(
        1
        for s in base["spreads"]
        if team in (s["buy"]["counterparty"], s["sell"]["counterparty"])
    )
    assert len(scoped["spreads"]) >= base_in_scope


def test_prefer_is_soft_never_filters_or_reorders(league, cache_dir):
    """§4: a prefer-constraint tags ★ and NOTHING else — the identical query
    with a prefer added returns the same counts and the same spreads in the
    same order (only the `preferred` flags may change). Pinned at finder
    level: the predicate-level softness test cannot see a filter/reorder bug
    in the query pipeline itself."""
    base = fd.find_spreads(league, NARROW_QUERY, cache_dir=cache_dir)
    assert base["spreads"] and not any(s["preferred"] for s in base["spreads"])
    pref_q = {
        **NARROW_QUERY,
        "constraints": list(NARROW_QUERY["constraints"])
        + [
            {
                "who": "me", "side": "receives",
                "what": {"asset": "George Holani"},
                "mode": "prefer", "with": "cmgaither43",
            }
        ],
    }
    starred = fd.find_spreads(league, pref_q, cache_dir=cache_dir)
    assert starred["counts"] == base["counts"]

    def strip(r):
        return [{k: v for k, v in s.items() if k != "preferred"} for s in r["spreads"]]

    assert strip(starred) == strip(base)
    # every buy leg of the pinned shape receives Holani from cmgaither43, so
    # the prefer matches every spread — the ★ really fires
    assert all(s["preferred"] for s in starred["spreads"])


def test_query_validation(league, cache_dir):
    for bad in [
        {"delta": 1.5},
        {"delta": "balanced"},
        {"shape": "sideways"},
        {"with_team": "nobody"},
        {"legs": {"buy_with": ["bengramling"]}},
        {"legs": {"buys": ["millj"]}},
        {"top": 0},
        {"unknown_key": 1},
    ]:
        with pytest.raises(ValueError):
            fd.find_spreads(league, bad, cache_dir=cache_dir)
