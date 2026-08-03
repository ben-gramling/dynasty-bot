"""§4a v5 the spread finder — deterministic constrained search with three
sliders, behind the trade-negotiator skill and the CLI `find` command.

Pipeline (deterministic, §4a): compile constraints (§4 — posture defaults,
market-intel, ad-hoc query, strict per-team precedence) → filter each side's
candidate packages BEFORE gate work (constraint push-down) → enumerate
surviving legs per counterparty through the exact §3 gate (band, fleece,
legality) → favor push-down (v5.0.1: a favor window filters LEGS before the
crossing — both pair favor checks decompose exactly onto the legs) → cross
buy × sell (asset-disjoint, distinct counterparties, count-neutral 0/0) →
exact combined coordinates per §2 (one incremental starter re-solve per
crossing) → slider filter/sort → top `finder_top` with honest counts.
Crossings that finish inside `finder_cross_budget` report EXACT counts over the
POOLED legs — the crossing is exhaustive (it never prunes), so a completed walk
visited and exactly priced every pair the pool can form, whatever the δ; the
favor-filtered space is usually small enough that favor-banded queries finish
exhaustively; a budget-truncated cross saturates to verified floors — never
estimates (§11.12(e)). "Exact" is bounded by the pool: `build_pair_pool` keeps
`variants_per_signature` gets per (counterparty, give, count-signature) as a
disclosed pre-ranking heuristic (§5), so "none exists" is always "none exists
among the pooled legs", never a statement about the whole legal package space.
Walk order decides what a truncation keeps: robust
(floor-objective) queries walk by the v5.1 SOUND key ΔF(leg) — exactly
additive across legs and an upper bound on the pair's guaranteed floor (§4a),
so the crossings that can carry a high floor come first, complementary pairs
included (v5.0.1's isolation-floor order buried them: a leg that ships a
starter scores terribly alone). Numeric-δ queries keep the v5.0.1 per-leg
δ-score leg_ΔW(δ) = iso_ΔS + δ·(ΔF_leg − iso_ΔS), which stays a disclosed
heuristic (combined ΔS is non-additive), so truncated δ-view counts are floors.

The three sliders (§4a — VIEWS and filters, never score parameters):

1. δ — view score `ΔW(δ) = ΔS + δ·(ΔF − ΔS)` and `return(δ) = ΔW(δ) ÷ Σ face
   sent`; presets 0/0.25/0.5/0.75/1 plus **robust** (default): the v4
   floor/verdict — good at every δ, ranked maximin (floor-return desc,
   ceiling desc, ids). §2's objective verdict is computed and shown whatever
   the slider says.
2. total return — floor on `return(δ)` at the selected δ (robust mode uses
   the guaranteed floor return), percent.
3. counterparty favorability — floor on pair favor `min(f_buy, f_sell)` (each
   leg's signed KTC-calculator skew, §4a, stored on the pool leg from the
   gate's own adjusted totals) plus an optional ceiling on EITHER leg's favor
   (stops giving edge away). The §3 band stays the hard outer bound.

Leg cache (§4a): the per-team give-list package enumerations are pure
snapshot data, computed once and disk-cached under `.cache/` keyed by
(snapshot fingerprint, params hash) — every query, warm or cold, flows
through the same descriptor tables, so warm and cold results are
byte-identical (§11.12(d)). Constraints only ever NARROW the cached tables;
adding one re-enumerates a smaller gate scan, and slider moves re-filter the
already-priced results.

No I/O beyond the cache directory; intel docs come from the caller (the
`market-intel` Mongo collection is read by the skill/CLI layer).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from heapq import heappush, heappushpop
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.scoring import constraints as cn
from core.scoring import model as md
from core.scoring import trades as tr
from core.scoring.lineup import pos_columns
from core.scoring.params import Params
from core.scoring.snapshot import Snapshot

_CACHE_VERSION = 1
# §4a v6: legs per side crossed in the warm-bar seed pass (see `find_spreads`)
_SEED_WIDTH = 150
DEFAULT_CACHE_DIR = Path(".cache")

_QUERY_DEFAULTS: dict[str, Any] = {
    "constraints": (),
    "use_intel": True,
    "use_posture": True,
    "delta": "robust",
    "min_return": 0.0,
    "favor_min": None,
    "favor_max": None,
    "legs": None,
    "with_team": None,
    "shape": None,
    "top": None,  # None -> params.finder_top
    # §4a v6: build the COMPLETE pool inside |favor| <= this instead of v5's
    # sampled scan. Per-QUERY, not a param, because it bounds what the pool can
    # represent: a band-5 pool cannot serve a `favor_min = -10` query at all, so
    # making it the default would silently break the slider's own presets.
    "favor_band": None,
}


# ------------------------------------------------------------------ the cache


def snapshot_fingerprint(snapshot: Snapshot) -> str:
    """Deterministic content hash of everything the leg tables can depend on."""
    payload = {
        "league": snapshot.league,
        "rosters": snapshot.rosters,
        "users": snapshot.users,
        "traded_picks": snapshot.traded_picks,
        "draft": snapshot.draft,
        "state": snapshot.state,
        "ktc_assets": snapshot.ktc_assets,
        "crosswalk": snapshot.crosswalk,
        "my_roster_id": snapshot.my_roster_id,
        "player_names": snapshot.player_names,
        "transactions": snapshot.transactions,
        "posture_overrides": snapshot.posture_overrides,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def params_fingerprint(params: Params) -> str:
    blob = json.dumps(asdict(params), sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def cache_path(league: md.LeagueState, cache_dir: Path | str | None = None) -> Path:
    d = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    sf = snapshot_fingerprint(league.snapshot)[:16]
    pf = params_fingerprint(league.params)[:16]
    return d / f"finder-{sf}-{pf}.json"


def _asset_index(league: md.LeagueState) -> dict[str, dict[str, tr.Asset]]:
    return {
        name: {a.key: a for a in tr.team_assets(league, t).values()}
        for name, t in league.teams.items()
    }


def _build_descriptors(league: md.LeagueState) -> dict[str, list[list[str]]]:
    """Per-team give-list package descriptors: asset keys IN PACKAGE ORDER —
    the pure-data artifact the cache stores. Rebuilding a Package from a
    descriptor reproduces it bit-for-bit (same asset order, so the same float
    summation order), which is what makes warm and cold queries byte-identical
    (§11.12(d))."""
    return {
        name: [
            [a.key for a in pkg.assets]
            for pkg in tr._packages(league, tr.give_list(league, t))
        ]
        for name, t in league.teams.items()
    }


def load_leg_tables(
    league: md.LeagueState, cache_dir: Path | str | None = None
) -> dict[str, list[tr.Package]]:
    """The §4a leg cache: per-team package tables from disk when the
    (snapshot fingerprint, params hash) entry exists, else built cold and
    written. BOTH paths materialize Packages from the same descriptors, so
    the result is identical either way; the disk round-trip only skips the
    give-list enumeration on re-queries."""
    path = cache_path(league, cache_dir)
    descriptors: dict[str, list[list[str]]] | None = None
    me_cols = [list(c) for c in pos_columns(tr.starter_pool(league.teams[league.me]))]
    if path.exists():
        try:
            doc = json.loads(path.read_text())
            if (
                doc.get("version") == _CACHE_VERSION
                and doc.get("me_starter_cols") == me_cols
                and set(doc.get("teams", {})) == set(league.teams)
            ):
                descriptors = doc["teams"]
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            descriptors = None  # unreadable cache: rebuild cold
    if descriptors is None:
        descriptors = _build_descriptors(league)
        doc = {
            "version": _CACHE_VERSION,
            "snapshot": snapshot_fingerprint(league.snapshot),
            "params": params_fingerprint(league.params),
            # §4a: "my starter index inputs" ride along — a stale-league guard
            # on top of the fingerprint in the file name
            "me_starter_cols": me_cols,
            "teams": descriptors,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(doc, fh, separators=(",", ":"))
            os.replace(tmp, path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    by_key = _asset_index(league)
    return {
        name: [
            tr.package_of(league, [by_key[name][k] for k in keys])
            for keys in descriptors[name]
        ]
        for name in league.teams
    }


# ------------------------------------------------------------------ the query


def _normalize_query(league: md.LeagueState, query: Mapping | None) -> dict:
    q = dict(_QUERY_DEFAULTS)
    for k, v in (query or {}).items():
        if k == "intel":
            continue  # carried separately
        if k not in _QUERY_DEFAULTS:
            raise ValueError(f"unknown query key {k!r}")
        q[k] = v
    delta = q["delta"]
    if delta != "robust" and not (isinstance(delta, (int, float)) and 0.0 <= delta <= 1.0):
        raise ValueError(f"delta must be 'robust' or a number in [0, 1], got {delta!r}")
    if q["shape"] not in (None, "starter>team", "team>starter"):
        raise ValueError("shape must be 'starter>team', 'team>starter', or None")
    if q["with_team"] is not None and (
        q["with_team"] not in league.teams or q["with_team"] == league.me
    ):
        raise ValueError(f"with_team={q['with_team']!r} is not a counterparty username")
    legs = q["legs"]
    if legs is not None:
        if not isinstance(legs, Mapping) or set(legs) - {"buy_with", "sell_with"}:
            raise ValueError("legs must be {'buy_with': [...], 'sell_with': [...]}")
        for side in ("buy_with", "sell_with"):
            for name in legs.get(side) or ():
                if name not in league.teams or name == league.me:
                    raise ValueError(f"legs.{side} names unknown counterparty {name!r}")
    fb = q["favor_band"]
    if fb is not None:
        if not (isinstance(fb, (int, float)) and fb > 0):
            raise ValueError(f"favor_band must be a positive number, got {fb!r}")
        # a band-β pool cannot answer a question about legs outside ±β
        for k in ("favor_min", "favor_max"):
            v = q[k]
            if v is not None and abs(v) > fb:
                raise ValueError(
                    f"{k}={v} lies outside favor_band={fb}: the complete pool is "
                    f"built to |favor| <= {fb} and cannot represent that leg"
                )
    top = q["top"]
    if top is None:
        q["top"] = league.params.finder_top
    elif not (isinstance(top, int) and top > 0):
        raise ValueError(f"top must be a positive int, got {top!r}")
    return q


def _view_return(d_s: float, d_f: float, sent: float, delta) -> float:
    """`return(δ)` as a FRACTION: robust → the guaranteed floor return
    (§2 v4 maximin); numeric δ → ΔW(δ) ÷ Σ face sent (a labeled view)."""
    if delta == "robust":
        w = d_s if d_s < d_f else d_f
    else:
        w = d_s + delta * (d_f - d_s)
    return w / sent


# ----------------------------------------------------------------- the finder


def find_spreads(
    league: md.LeagueState,
    query: Mapping | None = None,
    intel: Sequence[Mapping] | None = None,
    cache_dir: Path | str | None = None,
) -> dict:
    """§4a: constrained spread search. `query` per the §4a contract:

        {constraints: [...], use_intel: bool, use_posture: bool,
         delta: float | 'robust', min_return: float (percent),
         favor_min: float | None, favor_max: float | None,
         legs: {buy_with: [...], sell_with: [...]} | None,
         with_team: str | None, shape: 'starter>team'|'team>starter'|None,
         top: int}

    `intel` is the active `market-intel` doc list (the caller reads Mongo).
    Returns {spreads, counts, exact, applied_constraints, ignored_intel}:
    spreads are the top `top` under the selected δ ordering (robust default —
    §2 v4 maximin: floor-return desc, ceiling desc, deterministic ids), each
    carrying leg cards, exact combined coords, floor/ceiling, return_robust,
    return_view, favor {buy, sell, min}, preferred ★, sequencing, and net
    counts; `counts` are exact when the crossing finished inside
    `finder_cross_budget` (`exact` True) — exact over the POOLED legs, for any
    δ, since the crossing never prunes — and verified floors otherwise —
    never estimates (§11.12(e)). With a favor window set, `counts.legs` are
    the favor-ELIGIBLE legs (v5.0.1 push-down: the constrained crossing
    space), and the crossing is exhaustive whenever that filtered space fits
    the budget."""
    params = league.params
    q = _normalize_query(league, query)
    if intel is None:
        intel = (query or {}).get("intel") or ()

    compiled, ignored_intel = cn.compile_constraints(
        league,
        intel=intel,
        query=q["constraints"],
        use_posture=q["use_posture"],
        use_intel=q["use_intel"],
    )

    # counterparty subset: an explicit legs filter names every reachable team;
    # everything else needs the full slate (with_team constrains the PAIR, not
    # the enumeration — the partner leg may face anyone)
    legs_q = q["legs"]
    if legs_q is not None:
        buy_teams = set(legs_q.get("buy_with") or league.opponents)
        sell_teams = set(legs_q.get("sell_with") or league.opponents)
        opponents = [n for n in league.opponents if n in (buy_teams | sell_teams)]
    else:
        buy_teams = sell_teams = set(league.opponents)
        opponents = list(league.opponents)

    # §4a v6: which pool this query gets. `None` (the default) is v5's sampled
    # scan; a number builds the COMPLETE pool inside |favor| ≤ that band.
    pool_band = (
        q["favor_band"] if q["favor_band"] is not None else params.finder_favor_band
    )

    # §4a constraint push-down: candidate packages filtered BEFORE gate work.
    # Posture rides in `compiled` (§11.12(f)), so the pool's own posture gate
    # is off. Cached tables only ever get NARROWED here.
    tables = load_leg_tables(league, cache_dir)
    me_name = league.me
    my_filtered: dict[str, list[tr.Package]] = {}
    opp_filtered: dict[str, list[tr.Package]] = {}
    for opp in opponents:
        my_filtered[opp] = [
            p for p in tables[me_name] if cn.package_allowed(compiled, opp, "give", p)
        ]
        opp_filtered[opp] = [
            p for p in tables[opp] if cn.package_allowed(compiled, opp, "get", p)
        ]
    # §4a v6: the finder runs the COMPLETE fair-band pool — every gate-passer
    # inside `finder_favor_band` is kept, not the best 2 of the first 3 scanned.
    # This path is interactive and local, so it can afford the memory the
    # nightly collector cannot (the unconstrained band-5 pool measures ~3.9 GB;
    # a constrained negotiator query is a small fraction of that). The board
    # keeps `pool_favor_band = None` and v5's sampled scan — see §9.
    pool = tr.build_pair_pool(
        league,
        enforce_posture=False,
        opponents=opponents,
        my_pkgs_for=lambda opp: my_filtered[opp],
        opp_pkgs_for=lambda opp: opp_filtered[opp],
        favor_band=pool_band,
    )

    legs = pool.legs

    delta = q["delta"]
    min_ret = float(q["min_return"]) / 100.0
    favor_min = q["favor_min"]
    favor_max = q["favor_max"]
    shape = q["shape"]
    top = q["top"]
    budget = params.finder_cross_budget

    # ---- §4a v5.0.1 favor push-down: favor is a PER-LEG property (L_FAVOR)
    # and both pair-level favor checks decompose exactly onto the legs —
    #   pair min(f_b, f_s) ≥ favor_min ⟺ BOTH legs' favor ≥ favor_min,
    #   pair max(f_b, f_s) ≤ favor_max ⟺ BOTH legs' favor ≤ favor_max —
    # so a leg outside the window can never appear in a passing pair, and
    # dropping it BEFORE the crossing changes no pair's verdict. (The v5.0
    # walk crossed the FULL pool in floor order, and fair legs have small or
    # negative floors, so a favor-banded query could burn the whole budget
    # before reaching its own region.) The filtered crossing usually fits
    # `finder_cross_budget` and walks exhaustively → exact counts; the
    # pair-level checks below stay as belt-and-braces on the same semantics.
    if favor_min is not None or favor_max is not None:
        f_lo = float("-inf") if favor_min is None else favor_min
        f_hi = float("inf") if favor_max is None else favor_max
        favor_ok = [f_lo <= leg[tr.L_FAVOR] <= f_hi for leg in legs]
        eligible = favor_ok.__getitem__
    else:
        eligible = lambda i: True  # noqa: E731 — no window: every leg eligible

    # v6: "buy" is the leg that OWNS its crossing family and "sell" its exact
    # complement — not `L_NP > 0` / `L_NP < 0`, which counted the Δplayers == 0
    # family as neither. A (0, 0) leg is still in neither: it is roster-neutral
    # alone and never forms a spread (see `tr.canonical_sig`).
    n_buy = sum(
        1
        for i, leg in enumerate(legs)
        if tr.canonical_sig((leg[tr.L_NP], leg[tr.L_NK])) and eligible(i)
    )
    n_sell = sum(
        1
        for i, leg in enumerate(legs)
        if tr.canonical_sig((-leg[tr.L_NP], -leg[tr.L_NK])) and eligible(i)
    )

    # ---- cross buy × sell: asset-disjoint, distinct counterparties,
    # count-neutral 0/0 (complementary signatures). Deterministic descending
    # order, budgeted honestly: robust (floor-objective) queries walk by the
    # v5.1 SOUND key ΔF(leg) (§4a) — ΔF is exactly additive across legs and
    # bounds the pair's guaranteed floor from above, so the walk fronts exactly
    # the crossings that can carry a high floor, including the complementary
    # pairs whose legs score terribly alone (through v5.0.1 the key was the
    # leg's ISOLATION FLOOR, which the combined floor does not dominate — that
    # order buried them). Numeric-δ queries keep the v5.0.1 per-leg δ-score
    # leg_ΔW(δ) = iso_ΔS + δ·(ΔF_leg − iso_ΔS) from the stored leg fields, so a
    # truncated walk fronts the pairs the δ view actually ranks; combined pair
    # ΔS is not additive, so that order stays a disclosed heuristic and
    # truncated δ-view counts stay verified floors, never estimates.
    #
    # NB the crossing itself is EXHAUSTIVE over the constrained pool — the
    # order only decides what a budget truncation keeps — so `exact`
    # (== `complete` below) is a statement about the budget alone.
    if delta == "robust":

        def order_key(i: int) -> float:
            return -legs[i][tr.L_DFACE]

    else:
        dw_cache: dict[int, float] = {}

        def order_key(i: int) -> float:
            w = dw_cache.get(i)
            if w is None:
                leg = legs[i]
                iso_ds = pool.index.delta(leg[tr.L_OUT4], leg[tr.L_IN4])
                w = dw_cache[i] = iso_ds + delta * (leg[tr.L_DFACE] - iso_ds)
            return -w

    buy_allowed = {pool.opp_names.index(n) for n in pool.opp_names if n in buy_teams}
    sell_allowed = {pool.opp_names.index(n) for n in pool.opp_names if n in sell_teams}
    with_oi = (
        pool.opp_names.index(q["with_team"])
        if q["with_team"] is not None and q["with_team"] in pool.opp_names
        else None
    )
    if q["with_team"] is not None and with_oi is None:
        # the named team was filtered out of the enumeration entirely
        return {
            "spreads": [],
            "counts": {"legs": {"buy": n_buy, "sell": n_sell}, "crossings": 0, "valid": 0, "matched": 0, "returned": 0},
            "exact": True,
            "applied_constraints": [c.to_dict() for c in compiled],
            "ignored_intel": ignored_intel,
        }

    me_t = league.teams[me_name]
    legal_cache: dict[int, Any] = {}

    # §4a v6: the robust objective gets the SOUND two-pointer break (§11.13).
    # It needs `return = floor ÷ Σsent` to be the ranking, which is exactly what
    # robust mode is; a numeric-δ view scores ΔS and ΔF separately and `floor`
    # no longer bounds it, so those keep the v5.0.1 heuristic order and the flat
    # walk. `min_ret == 0` is still sound — the break is then simply "ΔF_pair
    # ≥ 0", which every qualifying pair satisfies.
    sound_break = delta == "robust"

    heap: list[tuple] = []  # (view_ret, ceiling, -bi, -si, d_s, d_f, ret, sent)

    def _qualifying(bi: int, si: int):
        """Exact price + every slider, or None. The single definition of "this
        pair counts", shared by the seed pass and the main walk so the bar the
        seed produces is always a return some QUALIFYING pair actually achieved."""
        b_, s_ = legs[bi], legs[si]
        if s_[tr.L_OPP] == b_[tr.L_OPP] or (s_[tr.L_MASK] & b_[tr.L_MASK]):
            return None
        if with_oi is not None and with_oi not in (b_[tr.L_OPP], s_[tr.L_OPP]):
            return None
        if tr._leg_legal(league, me_t, pool, bi, legal_cache) is False:
            return None
        if tr._leg_legal(league, me_t, pool, si, legal_cache) is False:
            return None
        ret_, floor_, ceil_, ds_, df_ = pool.pair_eval(bi, si)
        fb_, fs_, fmin_ = pool.pair_favor(bi, si)
        if favor_min is not None and fmin_ < favor_min:
            return None
        if favor_max is not None and (fb_ if fb_ > fs_ else fs_) > favor_max:
            return None
        if shape == "starter>team" and not ds_ > df_:
            return None
        if shape == "team>starter" and not df_ > ds_:
            return None
        if not tr.verdict_of(ds_, df_):
            return None
        return ret_ if ret_ >= min_ret - 1e-12 else None

    # §4a v6 WARM BAR. The sound break only bites when the bar is high, and
    # `min_return` defaults to 0 — where the break degenerates to "ΔF_pair ≥ 0"
    # and prunes almost nothing. So seed it: cross the richest few hundred legs
    # per side, price them exactly, and take the K-th best return as the bar.
    #
    # This is EXACT, not a heuristic. Every seed value is a return that a real
    # qualifying pair achieves, so the true K-th best return is ≥ the seed; a
    # walk at that bar therefore still reaches every member of the true top-K.
    # It only ever REMOVES crossings that provably cannot make the cut.
    seed_bar = min_ret

    def _u(leg) -> float:
        """§4a v6 the walk's SEPARABLE key, negated so `sorted` runs it
        descending: `k5 = 3·ΔF + 2·A` against `5·bar·Σsent`.

        Both halves bound the pair floor from above — ΔF exactly additively,
        `A` by matroid submodularity (§11.13(f)) — so their positively-weighted
        blend does too: `floor = (3·floor + 2·floor)/5 ≤ (3·ΔF + 2·A)/5`. The
        coefficients are INTEGERS on purpose: the float blend `0.6·ΔF + 0.4·A`
        has a real one-ULP counterexample (a pair with ΔS = ΔF = A_sum = 748
        whose blended bound comes out 747.9999999999999 and is dropped), and
        every input here is integral, so integer weights cannot round at all.

        ΔF alone is sound but a poor ORDER: it ranks a pair by face gained,
        so high-face/low-starter crossings flood the front of a truncated walk
        and the genuinely good pairs never get visited. Adding `A` makes the
        key see the starter half too."""
        return 5.0 * seed_bar * leg[tr.L_SENT] - (
            3.0 * leg[tr.L_DFACE] + 2.0 * leg[tr.L_A]
        )

    # The seed raises the walk's bar above `min_return`, which makes the RESULT
    # LIST exact but turns `counts.matched` into a floor — it can only count
    # pairs at or above the bar it actually walked. §11.12(e) pins those counts
    # as honest, so the seed runs ONLY on the complete-pool path, where the walk
    # is budget-truncated anyway (counts already floors) and where the search is
    # otherwise infeasible. The sampled path keeps exact v5 count semantics.
    if sound_break and top and pool_band is not None:
        seeds: list[float] = []
        for sig in sorted(pool.buckets):
            if not tr.canonical_sig(sig):
                continue
            comp_idx = pool.buckets.get((-sig[0], -sig[1]))
            if not comp_idx:
                continue
            rank = lambda i: -legs[i][tr.L_DFACE] / legs[i][tr.L_SENT]  # noqa: E731
            bs_seed = sorted(
                (i for i in pool.buckets[sig]
                 if legs[i][tr.L_OPP] in buy_allowed and eligible(i)),
                key=rank,
            )[:_SEED_WIDTH]
            ss_seed = sorted(
                (i for i in comp_idx
                 if legs[i][tr.L_OPP] in sell_allowed and eligible(i)),
                key=rank,
            )[:_SEED_WIDTH]
            for bi in bs_seed:
                for si in ss_seed:
                    r_ = _qualifying(bi, si)
                    if r_ is not None:
                        seeds.append(r_)
        if len(seeds) >= top:
            seeds.sort(reverse=True)
            seed_bar = max(min_ret, seeds[top - 1])
    visits = valid = matched = 0
    complete = True
    for sig in sorted(pool.buckets):
        if not complete:
            break
        if not tr.canonical_sig(sig):
            continue
        comp_idx = pool.buckets.get((-sig[0], -sig[1]))
        if not comp_idx:
            continue
        if sound_break:
            # §4a v6 SOUND ordering for the robust objective: sort by
            # `−u(leg)` with `u = ΔF − r·Σsent`, so the walk runs u-descending
            # and can stop the moment the best remaining sell cannot lift the
            # current buy to the bar. ΔF is exactly additive and
            # `floor ≤ ΔF`, so `u_b + u_s < 0 ⟹ return < r` — the break can
            # never discard a qualifying pair (§11.13). Through v5.1 this loop
            # had NO prune at all: it sorted by a yield heuristic and walked
            # until the budget ran out, which is survivable on a sampled pool
            # and hopeless on a complete one.
            bs = sorted(
                (_u(legs[i]), i)
                for i in pool.buckets[sig]
                if legs[i][tr.L_OPP] in buy_allowed and eligible(i)
            )
            ss = sorted(
                (_u(legs[i]), i)
                for i in comp_idx
                if legs[i][tr.L_OPP] in sell_allowed and eligible(i)
            )
        else:
            bs = sorted(
                (order_key(i), i)
                for i in pool.buckets[sig]
                if legs[i][tr.L_OPP] in buy_allowed and eligible(i)
            )
            ss = sorted(
                (order_key(i), i)
                for i in comp_idx
                if legs[i][tr.L_OPP] in sell_allowed and eligible(i)
            )
        if not bs or not ss:
            continue
        # §4a v6 `with_team` push-down. A pair is in scope iff the named team is
        # on ONE of its legs; legs in a pair always have distinct counterparties,
        # so exactly one of "buy leg is theirs" / "sell leg is theirs" holds and
        # the two cases PARTITION the in-scope crossings — no pair is counted
        # twice. Through v5.1 this test lived in the innermost loop AFTER
        # `visits += 1`, so a per-counterparty query walked (and charged its
        # whole budget to) the entire league-wide space and then discarded most
        # of it. Choosing the sell list per buy leg keeps the buy order and each
        # leg's relative sell order untouched, so what a truncation keeps is
        # unchanged for unscoped queries.
        if with_oi is None:
            ss_out = ss
        else:
            ss_out = [x for x in ss if legs[x[1]][tr.L_OPP] == with_oi]
        for ub, bi in bs:
            if not complete:
                break
            b = legs[bi]
            b_opp, b_mask = b[tr.L_OPP], b[tr.L_MASK]
            # buy leg is with the named team → every sell leg is in scope
            # (same-counterparty pairs are rejected below); otherwise only the
            # sell legs that ARE with the named team can form an in-scope pair
            my_ss = ss if (with_oi is None or b_opp == with_oi) else ss_out
            if not my_ss:
                continue
            if sound_break and ub + my_ss[0][0] > tr.XTOL:
                # even the best remaining sell cannot lift THIS buy to the bar,
                # and `bs` is u-descending, so no later buy can be lifted either
                break
            b_a = b[tr.L_A]
            vb = None
            for us, si in my_ss:
                if sound_break and ub + us > tr.XTOL:
                    break  # below the bar (XTOL keeps exact ties, which qualify)
                visits += 1
                if visits > budget:
                    visits -= 1
                    complete = False
                    break
                s = legs[si]
                if s[tr.L_OPP] == b_opp or (s[tr.L_MASK] & b_mask):
                    continue
                if vb is None:
                    vb = tr._leg_legal(league, me_t, pool, bi, legal_cache)
                if vb is False:
                    break  # illegal buy leg: no pair with it exists
                if tr._leg_legal(league, me_t, pool, si, legal_cache) is False:
                    continue
                valid += 1
                # §11.13(f) O(1) pricing skip: `floor ≤ A_buy + A_sell`, so a
                # pair whose add-only ceiling cannot clear the bar cannot clear
                # it at all — skip the exact starter re-solve, which is the
                # expensive part. Sound for the robust objective only (a δ-view
                # scores ΔS and ΔF separately), hence the same gate as the break.
                if sound_break and tr.pair_ds_bound(b_a, s[tr.L_A]) < seed_bar * (
                    b[tr.L_SENT] + s[tr.L_SENT]
                ) - tr.XTOL:
                    continue
                ret, floor, ceil, d_s, d_f = pool.pair_eval(bi, si)
                fb, fs, fmin = pool.pair_favor(bi, si)
                # ---- the three sliders (filters on the exact figures)
                if favor_min is not None and fmin < favor_min:
                    continue
                if favor_max is not None and (fb if fb > fs else fs) > favor_max:
                    continue
                if shape == "starter>team" and not d_s > d_f:
                    continue
                if shape == "team>starter" and not d_f > d_s:
                    continue
                if delta == "robust" and not tr.verdict_of(d_s, d_f):
                    continue  # robust = good at EVERY δ (§2 verdict)
                sent = b[tr.L_SENT] + s[tr.L_SENT]
                rv = _view_return(d_s, d_f, sent, delta)
                if rv < min_ret - 1e-12:
                    continue
                matched += 1
                e = (rv, ceil, -bi, -si, d_s, d_f, ret, sent)
                if len(heap) < top:
                    heappush(heap, e)
                elif e > heap[0]:
                    heappushpop(heap, e)

    # ---- docs for the kept spreads: view-return desc, ceiling desc, ids —
    # at DISPLAY precision (return 2dp, ceiling 1dp), exactly like the board
    # (§11.8b(e)): the order runs on the NEUTRAL flat-Mid scalars; raw-float
    # ties inside a display cell fall to the ids. §2 v8.2: the docs' shown
    # floor/ceiling fold the pick-band swing, so they may not be monotone in
    # this order — the swing never enters a selection or ranking key (§11.17)
    kept = sorted(
        heap,
        key=lambda e: (-round(100.0 * e[0], 2), -round(e[1], 1), -e[2], -e[3]),
    )
    card_cache: dict[int, dict] = {}

    def leg_card(i: int, leg_id: str) -> dict:
        base = card_cache.get(i)
        if base is None:
            leg = legs[i]
            base = tr.build_card(
                league, pool.opp_names[leg[tr.L_OPP]], leg[tr.L_GIVE], leg[tr.L_GET]
            )
            base["gate"]["verdict"] = "PASS"
            card_cache[i] = base
        card = dict(base)
        card["id"] = leg_id
        return card

    spreads: list[dict] = []
    for rv, ceil, nbi, nsi, d_s, d_f, ret, sent in kept:
        bi, si = -nbi, -nsi
        n = len(spreads) + 1
        b = leg_card(bi, f"F{n}-buy")
        s = leg_card(si, f"F{n}-sell")
        fb, fs, fmin = pool.pair_favor(bi, si)
        # §2 v8.2: the REPORTED interval folds the future-pick band swing.
        # Selection and order above ran on the neutral flat-Mid scalars
        # (§11.17 firewall) — only the disclosed floor/ceiling/return widen.
        sw = tr.pick_swing([
            (legs[bi][tr.L_GIVE], legs[bi][tr.L_GET]),
            (legs[si][tr.L_GIVE], legs[si][tr.L_GET]),
        ])
        floor = min(d_s, d_f + sw["down"])
        at_cap = b["sequencing"].startswith("at the roster cap")
        preferred = cn.leg_preferred(
            compiled, b["counterparty"], legs[bi][tr.L_GIVE], legs[bi][tr.L_GET]
        ) or cn.leg_preferred(
            compiled, s["counterparty"], legs[si][tr.L_GIVE], legs[si][tr.L_GET]
        )
        spreads.append(
            {
                "id": f"F{n}",
                "buy": b,
                "sell": s,
                # §2 exact combined coordinates — the δ slider re-scores from
                # exactly these plus `sent`, so slider moves are O(results)
                "coords": {"dS": round(d_s, 1), "dF": round(d_f, 1)},
                "verdict": tr.verdict_of(d_s, d_f),
                "floor": round(floor, 1),
                "ceiling": round(max(d_s, d_f + sw["up"]), 1),
                "sent": round(sent, 1),
                "return_robust": (
                    round(100.0 * floor / sent, 2) if sent > 0 else 0.0
                ),
                "return_view": round(100.0 * rv, 2),
                "swing": tr.swing_dict(sw, d_s, d_f),
                "favor": {
                    "buy": round(fb, 2),
                    "sell": round(fs, 2),
                    "min": round(fmin, 2),
                },
                "preferred": preferred,
                "sequencing": (
                    "at the roster cap: agreement-first — verbal yes on the buy, "
                    "execute the sell, then the buy (Sleeper processes trades instantly)"
                    if at_cap
                    else "roster space available: the buy may execute first — "
                    "agreement-first still applies"
                ),
                "net_players": 0,  # complementary signatures: exact by construction
                "net_picks": 0,
                "net_roster": b["net_roster"]["me"] + s["net_roster"]["me"],
            }
        )

    return {
        "spreads": spreads,
        "counts": {
            "legs": {"buy": n_buy, "sell": n_sell},
            "crossings": visits,
            "valid": valid,
            "matched": matched,
            "returned": len(spreads),
        },
        # §11.12(e)/§11.13(a): True ⟺ the constrained crossing space was walked
        # exhaustively — counts are exact tallies and "no spread matched" means
        # none exists in the constrained pool; False ⟺ the budget truncated the
        # walk — every count is a verified floor
        "exact": complete,
        "applied_constraints": [c.to_dict() for c in compiled],
        "ignored_intel": ignored_intel,
    }
