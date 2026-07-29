"""§4a v5 the spread finder — deterministic constrained search with three
sliders, behind the trade-negotiator skill and the CLI `find` command.

Pipeline (deterministic, §4a): compile constraints (§4 — posture defaults,
market-intel, ad-hoc query, strict per-team precedence) → filter each side's
candidate packages BEFORE gate work (constraint push-down) → enumerate
surviving legs per counterparty through the exact §3 gate (band, fleece,
legality) → cross buy × sell (asset-disjoint, distinct counterparties,
count-neutral 0/0) → exact combined coordinates per §2 (one incremental
starter re-solve per crossing) → slider filter/sort → top `finder_top` with
honest counts. Crossings that finish inside `finder_cross_budget` report
EXACT counts; a budget-truncated cross saturates to verified floors — never
estimates (§11.12(e)).

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
    `finder_cross_budget` (`exact` True), verified floors otherwise —
    never estimates (§11.12(e))."""
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
    pool = tr.build_pair_pool(
        league,
        enforce_posture=False,
        opponents=opponents,
        my_pkgs_for=lambda opp: my_filtered[opp],
        opp_pkgs_for=lambda opp: opp_filtered[opp],
    )

    legs = pool.legs
    n_buy = sum(1 for leg in legs if leg[tr.L_NP] > 0)
    n_sell = sum(1 for leg in legs if leg[tr.L_NP] < 0)

    # ---- cross buy × sell: asset-disjoint, distinct counterparties,
    # count-neutral 0/0 (complementary signatures). Deterministic isolation-
    # floor-descending order (the disclosed §5 heuristic), budgeted honestly.
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

    delta = q["delta"]
    min_ret = float(q["min_return"]) / 100.0
    favor_min = q["favor_min"]
    favor_max = q["favor_max"]
    shape = q["shape"]
    top = q["top"]
    budget = params.finder_cross_budget
    me_t = league.teams[me_name]
    legal_cache: dict[int, Any] = {}

    heap: list[tuple] = []  # (view_ret, ceiling, -bi, -si, d_s, d_f, ret, sent)
    visits = valid = matched = 0
    complete = True
    for sig in sorted(pool.buckets):
        if sig[0] <= 0 or not complete:
            if not complete:
                break
            continue
        comp_idx = pool.buckets.get((-sig[0], -sig[1]))
        if not comp_idx:
            continue
        bs = sorted(
            (-legs[i][tr.L_FLOOR], i)
            for i in pool.buckets[sig]
            if legs[i][tr.L_OPP] in buy_allowed
        )
        ss = sorted(
            (-legs[i][tr.L_FLOOR], i)
            for i in comp_idx
            if legs[i][tr.L_OPP] in sell_allowed
        )
        if not bs or not ss:
            continue
        for _, bi in bs:
            if not complete:
                break
            b = legs[bi]
            b_opp, b_mask = b[tr.L_OPP], b[tr.L_MASK]
            vb = None
            for _, si in ss:
                visits += 1
                if visits > budget:
                    visits -= 1
                    complete = False
                    break
                s = legs[si]
                if s[tr.L_OPP] == b_opp or (s[tr.L_MASK] & b_mask):
                    continue
                if with_oi is not None and with_oi not in (b_opp, s[tr.L_OPP]):
                    continue
                if vb is None:
                    vb = tr._leg_legal(league, me_t, pool, bi, legal_cache)
                if vb is False:
                    break  # illegal buy leg: no pair with it exists
                if tr._leg_legal(league, me_t, pool, si, legal_cache) is False:
                    continue
                valid += 1
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
    # (§11.8b(e)): the doc's order is the maximin/view order on the numbers
    # the doc shows; raw-float ties inside a display cell fall to the ids
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
        floor = d_s if d_s < d_f else d_f
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
                "ceiling": round(ceil, 1),
                "sent": round(sent, 1),
                "return_robust": round(100.0 * ret, 2),
                "return_view": round(100.0 * rv, 2),
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
        # §11.12(e): True ⟺ the constrained crossing space was walked
        # exhaustively — counts are exact tallies; False ⟺ the budget
        # truncated the walk — every count is a verified floor
        "exact": complete,
        "applied_constraints": [c.to_dict() for c in compiled],
        "ignored_intel": ignored_intel,
    }
