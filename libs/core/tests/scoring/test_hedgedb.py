"""§12 v8 hedge-database pins.

The DB path must be a bit-for-bit mirror of the finder on identical scopes:
same complete band pool, same seeded sound walk, same tie-breaks — so the
whole suite here is parity + round-trip identity at REDUCED params
(max_package=2 keeps the complete fixture pool at ~139k legs; the full-scale
build is exercised manually, never in the suite). Budgets are pinned EQUAL
across both engines inside these tests so truncation, if it ever bites,
truncates identically.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

import core.scoring.finder as fi
import core.scoring.hedgedb as hd
from core.scoring import Params
from core.scoring import model as md

pytest.importorskip("numpy", reason="hedgedb needs the core[hedgedb] extra")

_SLIDERS = {
    "min_return": 1.0,
    "favor_min": -5.0,
    "favor_max": 5.0,
    "delta": "robust",
    "top": 20,
    "use_intel": False,
    "use_posture": False,
}


@pytest.fixture(scope="module")
def hd_params() -> Params:
    # EQUAL budgets: a truncated walk must truncate identically in both
    # engines, and the numeric-δ flat walk always burns the full budget —
    # 2M keeps that test honest AND fast
    return Params(
        max_package=2,
        hedgedb_search_budget=2_000_000,
        finder_cross_budget=2_000_000,
    )


@pytest.fixture(scope="module")
def hd_league(snapshot, hd_params) -> md.LeagueState:
    return md.build_league(snapshot, hd_params)


@pytest.fixture(scope="module")
def db(snapshot, hd_params, tmp_path_factory) -> hd.HedgeDB:
    return hd.build(
        snapshot, hd_params, cache_dir=tmp_path_factory.mktemp("hedgedb"), bake=False
    )


def _finder(hd_league, query, cache_dir):
    fq = dict(query)
    fq["favor_band"] = 5.0
    return fi.find_spreads(hd_league, fq, intel=(), cache_dir=cache_dir)


@pytest.mark.parametrize(
    "extra",
    [
        {"with_team": "ronakpatel32"},
        {"with_team": "cmgaither43"},
        {},  # full slate
        {"with_team": "Jukinski", "min_return": 5.0},
        {"with_team": "trdouglas", "shape": "starter>team"},
    ],
    ids=["ronak", "colin", "full-slate", "jukinski-5pct", "trdouglas-shape"],
)
def test_search_parity_with_finder(db, hd_league, tmp_path, extra):
    """§12(a): hedgedb.search == find_spreads(favor_band) bit-for-bit —
    spreads (full cards), counts, exact — on identical scopes."""
    q = {**_SLIDERS, **extra}
    mine = db.search(q, intel=(), use_cache=False)
    ref = _finder(hd_league, q, tmp_path)
    assert mine["exact"] == ref["exact"]
    assert mine["counts"] == ref["counts"]
    assert json.dumps(mine["spreads"], sort_keys=True) == json.dumps(
        ref["spreads"], sort_keys=True
    )


def test_numeric_delta_parity(db, hd_league, tmp_path):
    """§12(a) on a numeric-δ VIEW: flat walk, same ordering heuristic — the
    scoped query keeps the crossing inside both (equal) budgets."""
    q = {**_SLIDERS, "with_team": "millj", "delta": 0.5}
    mine = db.search(q, intel=(), use_cache=False)
    ref = _finder(hd_league, q, tmp_path)
    assert mine["exact"] == ref["exact"]
    assert mine["counts"] == ref["counts"]
    assert json.dumps(mine["spreads"], sort_keys=True) == json.dumps(
        ref["spreads"], sort_keys=True
    )


def test_cache_hit_is_byte_identical(db):
    """§12(b): a repeated search serves from the cache byte-identically, and
    discloses it in db.cached."""
    q = {**_SLIDERS, "with_team": "ronakpatel32"}
    first = db.search(q, intel=())
    again = db.search(q, intel=())
    assert again["db"]["cached"] is True
    a = {k: v for k, v in first.items() if k != "db"}
    b = {k: v for k, v in again.items() if k != "db"}
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_content_fingerprint_ignores_mongo_bookkeeping(snapshot):
    """§12(c): _id/fetched_at churn and list order cannot flip the content
    fingerprint; a real value change must."""
    base = hd.content_fingerprint(snapshot)
    noisy = replace(
        snapshot,
        rosters=[
            {**r, "_id": i, "fetched_at": "2099-01-01T00:00:00"}
            for i, r in enumerate(snapshot.rosters)
        ][::-1],
    )
    assert hd.content_fingerprint(noisy) == base
    moved = replace(
        snapshot,
        ktc_assets=[
            {**a, "superflexValues": a.get("superflexValues")}
            if i else {**a, "oneQBValues": {**(a.get("oneQBValues") or {}), "value": 1}}
            for i, a in enumerate(snapshot.ktc_assets)
        ],
    )
    assert hd.content_fingerprint(moved) != base
    calc = replace(snapshot, ktc_calculator={"league_year_phase": 1, "draft_year": 2026})
    assert hd.content_fingerprint(calc) != base


def test_snapshot_roundtrip_league_identity(db, hd_league):
    """§12(d): the league rebuilt from the STORED snapshot prices identically
    to the league built from the in-memory snapshot."""
    stored = db.league
    assert stored.top_ktc_value == hd_league.top_ktc_value
    assert sorted(stored.teams) == sorted(hd_league.teams)
    for name in stored.teams:
        assert stored.teams[name].L == hd_league.teams[name].L
        assert stored.teams[name].picks_mv == hd_league.teams[name].picks_mv


def test_band_guard_raises_with_rebuild_hint(db):
    with pytest.raises(ValueError, match="build band"):
        db.search({**_SLIDERS, "favor_min": -10.0}, intel=())
    with pytest.raises(ValueError, match="rebuild"):
        db.search(
            {**_SLIDERS, "favor_for": {"millj": {"min": -8.0, "max": None}}}, intel=()
        )


def test_favor_for_tightens_one_team_only(db):
    """§12(e): a per-team favor floor binds THAT team's legs wherever they
    appear; every surviving spread obeys it and the unfiltered result is a
    superset."""
    base = db.search({**_SLIDERS, "top": 50}, intel=(), use_cache=False)
    tight = db.search(
        {**_SLIDERS, "top": 50, "favor_for": {"ronakpatel32": {"min": -1.0, "max": None}}},
        intel=(),
        use_cache=False,
    )
    for s in tight["spreads"]:
        for side in ("buy", "sell"):
            if s[side]["counterparty"] == "ronakpatel32":
                assert s[side]["favor"] >= -1.0
    assert tight["counts"]["matched"] <= base["counts"]["matched"]


def test_offer_count_neutral_stands_alone(db):
    """§12(f): a (0,0)-net proposal never crosses — disclosed, not silent."""
    league = db.league
    me = league.teams[league.me]
    opp_name = sorted(n for n in league.teams if n != league.me)[0]
    import core.scoring.trades as tr

    my_players = [a for a in tr.team_assets(league, me).values() if a.kind == "player"]
    their_players = [
        a
        for a in tr.team_assets(league, league.teams[opp_name]).values()
        if a.kind == "player"
    ]
    res = db.offer(
        opp_name, [my_players[0].name], [their_players[0].name], query=_SLIDERS, intel=()
    )
    assert res["hedges"] == []
    assert "count-neutral" in res["note"]
    assert res["offer"]["gate"]["verdict"]  # scored regardless
    # v8.1: the by_team shape holds even when the crossing never ran
    assert set(res["by_team"]) == {n for n in db.opp_names if n != opp_name}
    assert all(hs == [] for hs in res["by_team"].values())


def test_offer_hedges_are_exact_complements(db):
    """§12(g): offer-mode hedges offset the offer's count signature exactly,
    exclude the offer's counterparty, and every hedge pair is verdict-good at
    the floor. Cross-checked pairwise against a brute-force scan of the
    bucket."""
    league = db.league
    import core.scoring.trades as tr

    # find a stored leg shape to use as the "offer": buy 1 player for a pick
    # from whoever owns one — use a real pool leg's packages so the offer is
    # gate-clean and inside the DB universe
    buckets = db.buckets()
    sig = (1, -1) if (1, -1) in buckets else sorted(buckets)[0]
    li = int(buckets[sig][0])
    give = db.package(int(db._cols["give_pid"][li]))
    get = db.package(int(db._cols["get_pid"][li]))
    opp_name = db.opp_names[int(db._cols["opp"][li])]
    res = db.offer(
        opp_name,
        [a.name for a in give.assets],
        [a.name for a in get.assets],
        query={**_SLIDERS, "top": 10},
        intel=(),
    )
    assert res["counts"]["candidates"] > 0
    offer_np = get.n_players - give.n_players
    offer_nk = get.n_picks - give.n_picks
    for h in res["hedges"]:
        card = h["hedge"]
        assert card["counterparty"] != opp_name
        assert card["net_players"]["me"] == -offer_np
        assert card["net_picks"]["me"] == -offer_nk
        assert h["verdict"] is True
        # §11.17: the crossing's bar binds the NEUTRAL view return; the shown
        # robust return folds the pick-band swing and may sit below the bar
        assert h["return_view"] >= _SLIDERS["min_return"] - 1e-9
        assert h["return_robust"] <= h["return_view"] + 1e-9
        assert h["favor"]["min"] >= _SLIDERS["favor_min"]


def test_offer_hedges_group_by_counterparty(db):
    """§12(g) v8.1 (pinned-offer mode): `by_team` partitions the flat maximin
    list per counterparty — every non-offerer team present, per-team lists
    maximin-sorted top-K, teams ordered by best guaranteed pair floor with
    hedge-less teams trailing — and `counts.matched_by_team` carries the
    crossing's full per-team tallies, summing to `matched`."""
    buckets = db.buckets()
    sig = (1, -1) if (1, -1) in buckets else sorted(buckets)[0]
    li = int(buckets[sig][0])
    give = db.package(int(db._cols["give_pid"][li]))
    get = db.package(int(db._cols["get_pid"][li]))
    opp_name = db.opp_names[int(db._cols["opp"][li])]
    res = db.offer(
        opp_name,
        [a.name for a in give.assets],
        [a.name for a in get.assets],
        query={**_SLIDERS, "top": 10},
        intel=(),
    )
    flat = res["hedges"]
    by = res["by_team"]
    mb = res["counts"]["matched_by_team"]
    assert flat, "fixture precondition: a pool leg's offer must cross at 1%"
    assert set(by) == {n for n in db.opp_names if n != opp_name}
    assert set(mb) == set(by)
    assert sum(mb.values()) == res["counts"]["matched"]
    # partition: the same entries, nothing duplicated or dropped
    assert sorted(h["id"] for h in flat) == sorted(
        h["id"] for hs in by.values() for h in hs
    )
    # §11.17: order runs on the NEUTRAL figures — view return, then the
    # neutral ceiling recovered from coords (the shown ceiling folds the swing)
    nceil = lambda h: max(h["coords"]["dS"], h["coords"]["dF"])
    keys = [(-h["return_view"], -nceil(h)) for h in flat]
    assert keys == sorted(keys)  # global maximin order
    for name, hs in by.items():
        assert len(hs) <= 10  # per-team top-K
        assert len(hs) <= mb[name]
        assert [(-h["return_view"], -nceil(h)) for h in hs] == sorted(
            (-h["return_view"], -nceil(h)) for h in hs
        )  # per-team maximin order
        for h in hs:
            assert h["hedge"]["counterparty"] == name
    # team order: first appearance in the flat list (best pair floor first),
    # hedge-less teams after every team with inventory
    ids_flat = [h["id"] for h in flat]
    nonempty = [n for n, hs in by.items() if hs]
    firsts = [ids_flat.index(by[n][0]["id"]) for n in nonempty]
    assert firsts == sorted(firsts)
    assert list(by)[: len(nonempty)] == nonempty
    assert by[nonempty[0]][0]["id"] == "H1"


def test_offer_favor_window_binds_hedge_legs_only(db):
    """§12(g) v8.0.1: an offer TOO FAVORABLE TO US (its own favor below the
    window floor) must still hedge — the favor window is a politeness filter
    on legs WE propose, and the counterparty already proposed this one. The
    pre-fix behavior folded the offer's favor into the pair minimum and
    silently emptied the hedge list for every generous offer."""
    league = db.league
    import core.scoring.trades as tr

    buckets = db.buckets()
    sig = (1, -1) if (1, -1) in buckets else sorted(buckets)[0]
    li = int(buckets[sig][0])
    give = db.package(int(db._cols["give_pid"][li]))
    get = db.package(int(db._cols["get_pid"][li]))
    opp_name = db.opp_names[int(db._cols["opp"][li])]
    # same count shape as the stored leg's get, but THEIR most valuable
    # assets — a deal skewed hard toward us, far outside the fair window
    theirs = sorted(
        tr.team_assets(league, league.teams[opp_name]).values(),
        key=lambda a: -a.v,
    )
    rich_get = [a for a in theirs if a.kind == "player"][: get.n_players] + [
        a for a in theirs if a.kind == "pick"
    ][: get.n_picks]
    res = db.offer(
        opp_name,
        [a.name for a in give.assets],
        [a.name for a in rich_get],
        query={**_SLIDERS, "top": 10},
        intel=(),
    )
    favor_off = res["offer"]["gate"]["favor"]
    assert favor_off < _SLIDERS["favor_min"], (
        "fixture precondition: the skewed offer must read below the favor "
        f"floor on their calculator (got {favor_off})"
    )
    assert res["hedges"], "a generous offer must still find hedges"
    for h in res["hedges"]:
        assert _SLIDERS["favor_min"] <= h["favor"]["hedge"] <= _SLIDERS["favor_max"]
        assert h["favor"]["offer"] == favor_off
        assert h["favor"]["min"] == round(min(favor_off, h["favor"]["hedge"]), 2)


def test_offer_received_basis_verdicts(db):
    """§12(g) v8.0.2: band/fleece violations waive exactly when their excess
    flows TO us (they proposed it), and stay FAIL when we'd be the ones
    overpaying. Both directions pinned with 1-for-1 player offers (count-
    neutral — the verdict rewrite applies before the standalone return)."""
    league = db.league
    import core.scoring.trades as tr

    me = league.teams[league.me]
    opp_name = sorted(n for n in league.teams if n != league.me)[0]
    mine = sorted(
        (a for a in tr.team_assets(league, me).values()
         if a.kind == "player" and a.v > 0),
        key=lambda a: a.v,
    )
    theirs = sorted(
        (a for a in tr.team_assets(league, league.teams[opp_name]).values()
         if a.kind == "player" and a.v > 0),
        key=lambda a: a.v,
    )
    # generous: my cheapest valued player for their most valuable one
    gen = db.offer(opp_name, [mine[0].name], [theirs[-1].name], query=_SLIDERS, intel=())
    gg = gen["offer"]["gate"]
    assert gg["origin_verdict"].startswith("FAIL"), "fixture precondition"
    assert gg["verdict"].startswith("PASS (received basis"), gg["verdict"]
    assert gg["waived"], "the waived list is the disclosure"
    # overpay: my most valuable give-able player for their cheapest one
    over = db.offer(opp_name, [mine[-1].name], [theirs[0].name], query=_SLIDERS, intel=())
    og = over["offer"]["gate"]
    assert og["verdict"].startswith("FAIL"), og["verdict"]
    assert "against you" in og["verdict"]


def test_query_fingerprint_moves_with_intel(db):
    """§12(h): intel compiles into constraints, so a WANT arriving must MISS
    the cache — the fingerprint covers compiled constraints, not just flags."""
    q = {**_SLIDERS, "use_intel": True}
    compiled_a, _, _ = db._compile(db._normalize_query(q), intel=())
    fp_a = db.query_fingerprint(db._normalize_query(q), compiled_a)
    intel = [
        {"kind": "WANT", "team": "millj", "subject": "picks", "active": True}
    ]
    compiled_b, _, _ = db._compile(db._normalize_query(q), intel=intel)
    fp_b = db.query_fingerprint(db._normalize_query(q), compiled_b)
    assert fp_a != fp_b


def test_open_for_refuses_content_mismatch(snapshot, hd_params, tmp_path):
    changed = replace(
        snapshot, ktc_calculator={"league_year_phase": 1, "draft_year": 2026}
    )
    with pytest.raises(FileNotFoundError, match="hedgedb build"):
        hd.HedgeDB.open_for(changed, hd_params, cache_dir=tmp_path)
