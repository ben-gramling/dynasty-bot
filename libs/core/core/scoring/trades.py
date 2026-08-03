"""§2/§3/§5 trades: the v4 TWO-COORDINATE score (ΔS, ΔF — no blend, no δ), the
exact KTC-calculator fairness gate, enumerate-then-filter pairing behind the
v5 sliders (§4a/§5: δ view over the stored coordinates, a floor on robust
TOTAL return, and a floor on counterparty FAVORABILITY — each leg's signed
KTC-calculator skew, from the same adjusted totals as the gate; storage
stratified by favor bucket with per-bucket unions of tops by robust return /
ΔS / ΔF so every dial position has whatever inventory exists), posture as a
hard pair-pool constraint, fully count-neutral pairs (§5 v3.2: a recommended
pair nets exactly 0 players AND 0 picks for my side).

What the score IS (§2, v4):

- Two parameter-free coordinates per side, both pure roster arithmetic:
  `ΔS` = change in STARTER value (the max-Σv legal lineup at raw KTC solved
  over ACTIVE + TAXI — taxi is promote-anytime, §8; IR and empty slots are 0)
  and `ΔF` = change in TOTAL FACE owned (Σ v in − Σ v out, players and picks
  alike; players at KTC v, picks at the §3.2 price — exact slot this year,
  flat Mid beyond, v7.6). Any single-number ledger is
  `ΔW(δ) = ΔS + δ·(ΔF − ΔS)` for some stored-value preference δ ∈ [0, 1] — a
  time preference, not a measurable fact — so v4 reports the endpoints
  themselves and blends nothing.
- VERDICT (objective): a spread is better for EVERY rational preference iff
  `ΔS ≥ 0 AND ΔF ≥ 0`, at least one strict. MAGNITUDE: the interval
  `[floor, ceiling] = [min(ΔS, ΔF), max(ΔS, ΔF)]` — the floor is the
  guaranteed gain. RANKING (maximin): floor desc, ceiling desc, ids. A spread
  failing one coordinate is a PREFERENCE trade and carries the derived
  breakeven `δ* = ΔS / (ΔS − ΔF)` — labeled, never recommended.
- Both coordinates are PER SIDE. §1 v7.5: `v` and `v_me` COINCIDE for every
  asset — the v7 lens split collapsed when the one §3.2 price became a future
  pick's only number (v7.6: flat Mid — no forecast band survives for the gate
  to read, and no direction either). The two fields remain (`v_me` drives ΔF,
  `v` the gate) so the v7 plumbing is untouched, but they can no longer
  disagree. The price vector is single, global and (v7.6) symmetric between
  seats — same (year, round) prices the same whoever holds it — so ΔF is
  exactly CONSERVED across a leg's parties and exactly ADDITIVE across legs,
  which is all any bound in this module uses. `ΔS` never negated anyway —
  deployment differs by roster, which is why both sides of a good spread can
  genuinely gain.
- A pair's coordinates are COMBINED (both legs applied together): ΔS via one
  combined starter re-solve — the legs interact through the lineup — and ΔF
  additive across legs. Leg cards carry their isolation coordinates, labeled;
  a buy leg alone can still be floor-negative.
- Only the raw starter-sum solve enters this module from the lineup model
  (§11.2, enforced by an import-graph test): no q insurance weights, no
  availability multipliers, no replacement lines — and no δ anywhere. Roster
  legality and taxi routing (§8) stay in model.apply_tx — legality and
  sequencing only.
- The fairness gate is the EXACT reverse-engineered KTC trade-calculator
  adjustment (core.scoring.ktc_adjust), not a fitted consolidation curve.
- The stored board is HARD-constrained to verdict-true pairs (§11.8b(d)): the
  stored universe is floor-based return ≥ 1%, and a positive floor IS both
  coordinates strictly positive — a verdict-violating stored pair is a
  must-never-emit.

Three engine-bound honesty notes (the raw space is combinatorial — billions of
pair permutations clear the band on real data):

- Per (counterparty, give-package, count-signature) only the top
  `variants_per_signature` gate-clean gets by ISOLATION FLOOR are pooled,
  chosen from the first `variant_scan_cap` gate-passers in Σv-descending order.
  This is a disclosed SELECTION HEURISTIC (§5 "legs are pre-ranked inside the
  pool by isolation floor"), not a dominance theorem: the same non-additivity
  v5.1 fixed in the walks applies here — a get-side that scores badly alone can
  be the one that fills the hole its partner leg opens — so a same-signature
  sibling can outperform the variant that was kept. It buys the count-signature
  diversity the v3.2 matcher starved on at a bounded gate cost. Consequence for
  every exactness claim below: they are statements about the POOLED legs, never
  about the whole legal package space.
- The pair walks cross legs ordered and pruned on `ΔF(leg) − r·Σsent(leg)`
  (v5.1, §4a "sound crossing bound"). That key is SOUND for the floor
  objective: ΔF is exactly additive across legs (a static per-asset price
  vector, §11.1b — NOT cross-party conservation, which the bound never uses) and
  `floor = min(ΔS, ΔF) ≤ ΔF`, so `u_buy + u_sell < 0 ⟹ ΔF_pair < r·sent_pair
  ⟹ floor_pair < r·sent_pair ⟹ return < r` — the prune can only discard pairs
  that genuinely fail the bar (exact ties on the bar are kept — `XTOL`). Every
  pair the walks keep is still priced by its EXACT combined coordinates.
  Consequence: a walk that runs to COMPLETION at a cutoff at or below the
  stored floor enumerated the whole stored universe OF POOLED LEGS, so its
  counts are EXACT (`saturated` False); only budget-truncated walks leave
  verified floors. (Through v5.0.1 the key was each leg's ISOLATION FLOOR,
  which implicitly treats the pair floor as additive — it is not, ΔS is jointly
  determined by both legs through the lineup — so complementary pairs were
  pruned unseen and no count could ever be certified.)
- The nightly board's collection cannot reach its floor on real data, so after
  the sound walk it runs the v5.0.1 walk (`_walk_pairs(key=L_FLOOR)`) as a
  pure COVERAGE phase over what the sound walk did not already own. That phase
  certifies nothing — it is simply where storable pairs are densest, since ΔF
  runs 2-5× the floor and the sound cutoff therefore starts far above the
  storable band. Counts stay tallies of DISTINCT pairs either way.
- Counters saturate honestly at `pair_scan_budget` / `pair_collect_budget`.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from heapq import heappush, heappushpop
from itertools import combinations
from typing import Any, Sequence

from core.scoring import ktc_adjust as ka
from core.scoring import ktc_fast as kf
from core.scoring import model as md
from core.scoring import posture as ps

# §11.2: the ONLY thing the trade path may take from the lineup model — the raw
# starter-sum solve and its incremental evaluator. Never solve()/removal_dl()/
# diff_terms(), never the q / u / replacement machinery.
from core.scoring.lineup import EMPTY4, StarterIndex, pos_columns, starter_sum


@dataclass(frozen=True, slots=True)
class Asset:
    kind: str  # "player" | "pick"
    key: str
    name: str
    v: float  # player KTC v; pick §3.2 price (v7.6: flat Mid beyond this year) — the gate's input
    # §1 v7.5: identical to `v` for EVERY asset — the lens split collapsed when
    # the §3.2 one price became a future pick's only number. Still the ΔF
    # coordinate's input, and only that; kept distinct so the v7 plumbing
    # (conservation identity, card note) needs no rewiring.
    v_me: float
    pos: str | None
    unvalued: bool
    concrete: float | None  # current-year picks: rookie-board slot value (display only)
    player: Any = None  # PlayerV (duck-typed — no lineup import here)
    pick: Any = None  # picks.Pick


def player_asset(p) -> Asset:
    return Asset(
        kind="player", key=p.sid, name=p.name, v=p.v, v_me=p.v, pos=p.pos,
        unvalued=p.unvalued, concrete=None, player=p,
    )


def pick_asset(league: md.LeagueState, p) -> Asset:
    concrete = p.p if p.year == league.current_year and p.p != p.mv else None
    return Asset(
        kind="pick", key=p.key, name=p.label, v=p.mv, v_me=p.p_me, pos=None,
        unvalued=False, concrete=concrete, pick=p,
    )


def give_list(league: md.LeagueState, t: md.TeamCtx) -> list[Asset]:
    """§5 enumeration inventory: ALL actives except the top-N cornerstones by v,
    plus all picks. Unvalued (v=0) players never enter enumeration (§11.7) —
    they remain explicitly proposable via team_assets."""
    protected = {
        p.sid
        for p in sorted(t.act, key=lambda p: (-p.v, p.sid))[
            : league.params.give_list_protect_top
        ]
    }
    assets = [
        player_asset(p)
        for p in sorted(t.act, key=lambda p: (-p.v, p.sid))
        if p.sid not in protected and not p.unvalued
    ]
    assets += [pick_asset(league, p) for p in t.picks]
    return assets


def team_assets(league: md.LeagueState, t: md.TeamCtx) -> dict[str, Asset]:
    """Every tradeable asset by name (actives, taxi, picks) — the propose/CLI pool."""
    out: dict[str, Asset] = {}
    for p in t.act + t.taxi:
        out[p.name] = player_asset(p)
    for p in t.picks:
        a = pick_asset(league, p)
        out[a.name] = a
    return out


@dataclass(frozen=True, slots=True)
class Package:
    assets: tuple[Asset, ...]
    v_sum: float
    # §1 v7: the same sum through MY lens. Differs from `v_sum` only when the
    # package holds picks, and drives ΔF(me) alone — every market-facing use
    # (the gate, the fleece ratio, the pricing bracket, the return denominator,
    # the anchor ask) stays on `v_sum`.
    v_me_sum: float
    n_players: int
    pos_out: tuple[tuple[str, int], ...]
    has_unvalued: bool
    # §3.1: asset values DESC — exactly what KTC's calculator sorts before it
    # runs processV over a side
    vals: tuple[float, ...]
    # §2 v4 ΔS input: the package's players as raw-value columns in
    # lineup.POS4 order (the ΔS solve). The ΔF coordinate needs no per-class
    # column — it reads `v_me_sum`, which already covers players AND picks.
    cols: tuple[tuple[float, ...], ...]

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(a.key for a in self.assets))

    @property
    def n_picks(self) -> int:
        """Picks count as picks regardless of year (§5 v3.2)."""
        return len(self.assets) - self.n_players

    @property
    def max_v(self) -> float:
        return self.vals[0] if self.vals else 0.0


def package_of(league: md.LeagueState, assets: Sequence[Asset]) -> Package:
    pos_out: dict[str, int] = {}
    for a in assets:
        if a.kind == "player" and a.pos:
            pos_out[a.pos] = pos_out.get(a.pos, 0) + 1
    return Package(
        assets=tuple(assets),
        v_sum=sum(a.v for a in assets),
        v_me_sum=sum(a.v_me for a in assets),
        n_players=sum(1 for a in assets if a.kind == "player"),
        pos_out=tuple(sorted(pos_out.items())),
        has_unvalued=any(a.unvalued for a in assets),
        vals=tuple(sorted((a.v for a in assets), reverse=True)),
        cols=pos_columns(
            a.player for a in assets if a.kind == "player" and a.player is not None
        ),
    )


def _packages(league: md.LeagueState, assets: list[Asset]) -> list[Package]:
    out = []
    for k in range(1, league.params.max_package + 1):
        for combo in combinations(assets, k):
            out.append(package_of(league, combo))
    return out


# -------------------------------------------- §2 v4 the two-coordinate score


def starter_pool(t: md.TeamCtx) -> list:
    """The players `S` is solved over: ACTIVE + TAXI (taxi is promote-anytime,
    §8). Bench players are in `act` and simply lose the max-Σv solve — they
    count only in the FACE coordinate. IR players are already out of `act` and
    never enter: they are in neither coordinate (§11.8)."""
    return t.act + t.taxi


def team_index(t: md.TeamCtx) -> StarterIndex:
    """Incremental raw starter-sum evaluator for one team's ΔS coordinate."""
    return StarterIndex(starter_pool(t))


def total_face(t: md.TeamCtx, *, lens: str) -> float:
    """§2 v4 the F coordinate's LEVEL: Σ face value the side owns — every
    player the S-solve ranges over (active + taxi, IR excluded — §11.8) at raw
    KTC v, plus every owned pick. `ΔF` on a trade is the change in this
    quantity; `ΔW(1) = ΔF` (the old face ledger's endpoint).

    §1 v7 — `lens` is REQUIRED and has no default on purpose: it must be the
    same lens `coords_delta` was given for that side, or the identity
    `ΔF == total_face(after) − total_face(before)` silently returns a plausible
    wrong number (on the counterparty's roster the my-lens answer comes back
    as `−ΔF(me)`, which looks exactly like conservation "proving" itself).
    `"me"` reads `Pick.p_me`, `"market"` reads `mv` — since v7.5 the same
    number (one §3.2 price; v7.6 makes it flat Mid for future picks); the
    switch survives so the identity stays checkable per lens.

    The identity holds because `p_me` is minted once at snapshot pricing time
    and `model.apply_tx` carries it across unchanged. Since v7.6 the price is
    also OWNER-INDEPENDENT (flat Mid whoever holds the pick), so `total_face`
    is a state function within AND across snapshots barring market movement —
    but nothing in the engine relies on the across-snapshot half; this is a
    test oracle, not a reported level."""
    if lens == "me":
        picks = sum(p.p_me for p in t.picks)
    elif lens == "market":
        picks = t.picks_mv
    else:
        raise ValueError(f"lens must be 'me' or 'market', got {lens!r}")
    return sum(p.v for p in starter_pool(t)) + picks


def verdict_of(d_s: float, d_f: float) -> bool:
    """§2 v4 the objective verdict: better for EVERY rational stored-value
    preference δ ∈ [0, 1] iff both coordinates are non-negative, at least one
    strictly positive."""
    return d_s >= 0.0 and d_f >= 0.0 and (d_s > 0.0 or d_f > 0.0)


def breakeven_of(d_s: float, d_f: float) -> float | None:
    """§2 v4 the derived per-trade breakeven `δ* = ΔS / (ΔS − ΔF)` — reported
    ONLY for preference trades (verdict false, exactly one coordinate
    positive): the trade is good for δ beyond δ* in the direction of the
    positive coordinate. None for verdict-true spreads, for spreads bad at
    every preference (both ≤ 0), and when ΔS == ΔF (ΔW(δ) is constant — no
    crossing exists)."""
    if verdict_of(d_s, d_f) or d_s == d_f:
        return None
    if (d_s > 0.0) == (d_f > 0.0):
        return None  # no coordinate positive: bad for every rational preference
    return d_s / (d_s - d_f)


def _merge4(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> tuple:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2], a[3] + b[3])


def coords_delta(
    index: StarterIndex,
    out_pkgs: Sequence[Package],
    in_pkgs: Sequence[Package],
    *,
    mine: bool = True,
) -> tuple[float, float]:
    """§2 v4 `(ΔS, ΔF)` for ONE side when `out_pkgs` leave that roster and
    `in_pkgs` arrive, all applied together. Per-side — ΔS is never negated for
    the counterparty.

    §1 v7 — `mine` selects the FACE LENS, not the side: `v_me_sum` for my seat,
    `v_sum` for theirs. Since v7.5 the two coincide (one §3.2 price — flat Mid
    for future picks, v7.6), so the printed ΔFs negate again; the switch
    survives unchanged in case the lenses ever re-diverge.

    No stored-value bookkeeping exists: what a starter loses to the bench (or
    the bench gains from a promotion) is already inside `ΔS`, and `ΔF` is the
    leg's face delta, free by face conservation within the lens."""
    out4: tuple = EMPTY4
    in4: tuple = EMPTY4
    d_face = 0.0
    for pkg in out_pkgs:
        out4 = _merge4(out4, pkg.cols)
        d_face -= pkg.v_me_sum if mine else pkg.v_sum
    for pkg in in_pkgs:
        in4 = _merge4(in4, pkg.cols)
        d_face += pkg.v_me_sum if mine else pkg.v_sum
    return index.coords_delta(out4, in4, d_face)


def combined_coords(
    league: md.LeagueState, legs: Sequence[tuple[Package, Package]]
) -> dict:
    """§5 v4: the EXACT combined coordinates for MY side across `legs`
    ([(give, get), …]) applied TOGETHER — what a pair is stored and ranked by.
    ΔS is one combined re-solve (the legs interact through the starting
    lineup — never the sum of the legs' isolation ΔSs); ΔF is additive.
    `return_pct` is the §5 v4 floor-based return: guaranteed floor ÷ Σ face v
    I send across both legs."""
    me_t = league.teams[league.me]
    d_s, d_f = coords_delta(
        team_index(me_t), [g for g, _ in legs], [t for _, t in legs]
    )
    sent = sum(g.v_sum for g, _ in legs)
    floor = min(d_s, d_f)
    return {
        "dS": round(d_s, 1),
        "dF": round(d_f, 1),
        "verdict": verdict_of(d_s, d_f),
        "floor": round(floor, 1),
        "ceiling": round(max(d_s, d_f), 1),
        "breakeven": (
            round(b, 4) if (b := breakeven_of(d_s, d_f)) is not None else None
        ),
        "sent": round(sent, 1),
        "return_pct": round(100.0 * floor / sent, 2) if sent > 0 else None,
    }


# ------------------------------------------------------------------ the gate §3


MIN_POS = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}


def _pos_counts(players) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in players:
        counts[p.pos] = counts.get(p.pos, 0) + 1
    return counts


def _pos_legal_cheap(t: md.TeamCtx, out_pos, in_pos, net_bodies: int) -> bool:
    """Positional minima + fieldable size, on pre-routing arithmetic (fast filter)."""
    counts = _pos_counts(t.act)
    if len(t.act) + net_bodies < 9:
        return False
    inp = dict(in_pos)
    for pos, need in MIN_POS.items():
        if counts.get(pos, 0) - dict(out_pos).get(pos, 0) + inp.get(pos, 0) < need:
            return False
    return True


def adjusted_gap(league: md.LeagueState, give: Package, get: Package) -> tuple[float, float]:
    """§3.1 v3.4: the two adjusted package totals KTC's own trade calculator
    displays for this trade — the exact port, zero free parameters."""
    return ka.adjusted_totals(give.vals, get.vals, league.top_ktc_value)


def _band_ok(params, adj_give: float, adj_get: float) -> bool:
    hi = adj_give if adj_give > adj_get else adj_get
    gap = adj_give - adj_get
    if gap < 0:
        gap = -gap
    fa, fr = params.fairness_abs, params.fairness_rel
    return gap <= (fa if fa > fr * hi else fr * hi)


def favor_of(adj_receive: float, adj_give: float) -> float:
    """§4a v5 counterparty favorability, per leg: the SIGNED version of KTC's
    calculator equality metric, in the calculator's own units —
    `f = 100 · (adjTotal(they receive) − adjTotal(they give)) ÷ (adjTotal sum)`,
    with the magnitude quantized EXACTLY as `ktc_adjust.check_equality`
    quantizes it (JS half-up rounding to one decimal), so
    `|f| ≤ 5 ⟺ check_equality(adjT1, adjT2, 5)` — their calculator literally
    says FAIR at the default variance (§11.12(a)). `f > 0` skews to the
    counterparty. Inputs are the two adjusted totals the §3 gate already
    computed — one source of truth, the port never runs twice."""
    e = adj_receive if adj_receive > 0.0 else 0.0
    a = adj_give if adj_give > 0.0 else 0.0
    r = e + a
    n = min(100.0, abs(e - a) / r * 100.0) if r else 0.0
    q = ka.js_round(10.0 * n) / 10.0
    return q if e >= a else -q


def gate_info(league: md.LeagueState, give: Package, get: Package) -> dict:
    """§3.1/§3.2: the EXACT KTC-calculator band + anti-fleece cap (never
    exempted). `adj_give`/`adj_get` are the numbers the counterparty's own
    calculator shows; the gap between them is KTC's deserved gap. `favor` (v5)
    is derived from the SAME two adjusted totals — the leg's signed skew toward
    the counterparty in KTC's own variance units (§4a)."""
    params = league.params
    adj_give, adj_get = adjusted_gap(league, give, get)
    hi = max(adj_give, adj_get)
    gap = abs(adj_give - adj_get)
    band = max(params.fairness_abs, params.fairness_rel * hi)
    lo_sum = min(give.v_sum, get.v_sum)
    ratio = (max(give.v_sum, get.v_sum) / lo_sum) if lo_sum > 0 else float("inf")
    return {
        "adj_give": round(adj_give, 1),
        "adj_get": round(adj_get, 1),
        "gap": round(gap, 1),
        "gap_pct": round(100 * gap / hi, 1) if hi else 0.0,
        "band": round(band, 1),
        "band_pct": round(100 * params.fairness_rel, 0),
        "band_ok": gap <= band,
        "raw_ratio": round(ratio, 2) if ratio != float("inf") else None,
        "cap": params.fleece_ratio,
        "ratio_ok": ratio <= params.fleece_ratio,
        # v5: the counterparty receives `give`, gives `get` — + = they win
        "favor": round(favor_of(adj_give, adj_get), 2),
    }


def _sorted_opp_pkgs(league: md.LeagueState, opp_name: str) -> tuple[list[float], list[Package]]:
    """The opponent's give-list packages sorted by (Σv, keys), plus the parallel
    Σv list for bisecting — shared by band_ceiling and the board's ceiling cache."""
    pkgs = sorted(
        _packages(league, give_list(league, league.teams[opp_name])),
        key=lambda p: (p.v_sum, p.keys),
    )
    return [p.v_sum for p in pkgs], pkgs


def _ceiling_from(
    league: md.LeagueState, give: Package, vsums: list[float], pkgs: list[Package]
) -> float | None:
    """v3.4: scan the fleece bracket Σv-DESCENDING and return the first package
    clearing the exact gate. The exact band is not monotone in Σv, so a failure
    proves nothing about smaller packages — the scan may not stop early on a
    miss; the first HIT, however, is the maximum-Σv passer by construction."""
    params = league.params
    i0 = bisect_left(vsums, give.v_sum / params.fleece_ratio)
    i1 = bisect_right(vsums, params.fleece_ratio * give.v_sum)
    for i in range(i1 - 1, i0 - 1, -1):
        t = pkgs[i]
        adj_give, adj_get = adjusted_gap(league, give, t)
        if _band_ok(params, adj_give, adj_get):
            return t.v_sum
    return None


def band_ceiling(league: md.LeagueState, opp_name: str, give: Package) -> float | None:
    """§3 negotiating-room annotation: the maximum in-band, fleece-clean get Σv
    the opponent's give-list can form against this give package (what v3.0 would
    have proposed). Information only — never the proposal. None when the opponent
    has no in-band, fleece-clean package for this give (v3.3: no W_min edge —
    W_min retired as a gate)."""
    vsums, pkgs = _sorted_opp_pkgs(league, opp_name)
    return _ceiling_from(league, give, vsums, pkgs)


def _apply(league: md.LeagueState, t: md.TeamCtx, get: Package, give: Package) -> md.TeamCtx:
    return md.apply_tx(
        league,
        t,
        add_players=[a.player for a in get.assets if a.kind == "player"],
        remove_ids=[a.key for a in give.assets if a.kind == "player"],
        add_picks=[a.pick for a in get.assets if a.kind == "pick"],
        remove_pick_keys=[a.key for a in give.assets if a.kind == "pick"],
    )


def legality(
    league: md.LeagueState, me_t: md.TeamCtx, opp_t: md.TeamCtx, give: Package, get: Package
) -> dict:
    """§3.3 both post-trade rosters legal: positional minima, fieldable size, taxi
    routing per §8. Roster-cap overflow is SEQUENCING (§5), not illegality — it is
    reported for the pairing/sequencing notes."""
    t2_me = _apply(league, me_t, get=get, give=give)
    t2_opp = _apply(league, opp_t, get=give, give=get)
    verdicts = {}
    for tag, before, after in (("me", me_t, t2_me), ("them", opp_t, t2_opp)):
        counts = _pos_counts(after.act)
        minima_ok = all(counts.get(pos, 0) >= need for pos, need in MIN_POS.items())
        verdicts[tag] = {
            "minima_ok": minima_ok,
            "size_ok": len(after.act) >= 9,
            "net_roster": len(after.act) - len(before.act),
            "overflow": max(0, len(after.act) - league.roster_cap),
            "taxi_stashed": sorted(
                p.name for p in after.taxi if p.sid not in {x.sid for x in before.taxi}
            ),
        }
    verdicts["legal"] = all(v["minima_ok"] and v["size_ok"] for v in (verdicts["me"], verdicts["them"]))
    return verdicts


# --------------------------------------------------------------- posture shape §4


def offer_shape(give: Package) -> str:
    """What the counterparty receives, majority by COUNT of assets received
    (§5 v3.3): "players", "picks", or "mixed" on ties."""
    if give.n_players > give.n_picks:
        return "players"
    if give.n_picks > give.n_players:
        return "picks"
    return "mixed"


def _shape_rank(shape: str, label: str) -> int:
    """0 = shape fits posture, 1 = NEUTRAL counterparty, 2 = mismatched shape.
    Orders/annotates only; the PAIR-POOL constraint is posture_allows (§5 v3.3)."""
    if (shape == "players" and label == ps.BUYER) or (shape == "picks" and label == ps.SELLER):
        return 0
    if label == ps.NEUTRAL:
        return 1
    return 2


def posture_allows(label: str, shape: str) -> bool:
    """§5 v3.3 hard engine constraint: a BUYER counterparty must RECEIVE a
    players-majority package, a SELLER a picks-majority one; NEUTRAL accepts
    anything (mixed shapes clear only NEUTRAL). Overrides apply upstream
    (league.postures already folds `posture-overrides` in)."""
    if label == ps.BUYER:
        return shape == "players"
    if label == ps.SELLER:
        return shape == "picks"
    return True


def _holes(league: md.LeagueState, opp_name: str, give: Package) -> list[dict]:
    """§4 'aim at visible holes': counterparty's league rank at each position I send."""
    out = []
    for pos in sorted({a.pos for a in give.assets if a.kind == "player" and a.pos}):
        rank = league.group_rank.get(pos, {}).get(opp_name)
        if rank is not None:
            out.append({"pos": pos, "their_rank": rank})
    return out


def _dip_notes(league: md.LeagueState, get: Package) -> list[str]:
    """Display-only: incoming players trading below their trailing-30-day max."""
    out = []
    for a in get.assets:
        if a.kind != "player" or a.player is None:
            continue
        hist = league.snapshot.value_history_max.get(str(a.player.ktc_id))
        if hist and hist > 0 and (hist - a.v) / hist >= league.params.dip_threshold:
            out.append(a.name)
    return out


# ------------------------------------------------------------------- cards §5/§10


def _asset_dict(a: Asset) -> dict:
    d: dict = {"type": a.kind, "key": a.key, "name": a.name, "v": round(a.v)}
    if a.unvalued:
        d["unvalued"] = True
    if a.v_me != a.v:
        # §1 v7.5: unreachable — `v` and `v_me` coincide for every asset now
        # that a future pick has one §3.2 price (flat Mid, v7.6). Kept as a
        # tripwire: if the lenses ever re-diverge, the card discloses it.
        d["v_me"] = round(a.v_me)
        p = a.pick
        d["note"] = (
            f"pick priced {round(a.v_me)} on my side ({p.band_me}) vs "
            f"{round(a.v)} on the market ({p.band}) — ΔF uses mine, the gate uses theirs"
            if p is not None
            else "priced on my own lens; the gate uses the market value"
        )
    return d


def build_card(
    league: md.LeagueState,
    opp_name: str,
    give: Package,
    get: Package,
    leg: dict | None = None,
    ceiling: float | None = None,
) -> dict:
    """The §5/§10 card for one leg. `coords` carries EACH SIDE'S OWN (ΔS, ΔF)
    against its own roster (§2 v4) — mine through the v7 pick lens and theirs
    at market face, so the two ΔFs negate only when no pick crosses (§11.1b),
    ΔS not: a good leg can be objectively good for both sides (§11.1). Leg
    coordinates are ISOLATION figures; a pair's are the combined ones (§5)."""
    params = league.params
    me_t = league.teams[league.me]
    opp_t = league.teams[opp_name]
    ds_me, df_me = coords_delta(team_index(me_t), [give], [get])
    ds_them, df_them = coords_delta(team_index(opp_t), [get], [give], mine=False)
    floor_me, floor_them = min(ds_me, df_me), min(ds_them, df_them)
    gate = gate_info(league, give, get)
    verdicts = leg if leg is not None else legality(league, me_t, opp_t, give, get)
    gate["legal"] = verdicts["legal"]
    posture = league.postures.get(opp_name, {"label": ps.NEUTRAL, "source": "trades"})
    shape = offer_shape(give)
    fit = _shape_rank(shape, posture["label"]) == 0
    net_me = verdicts["me"]["net_roster"]
    # §5 v3.2 count deltas, my side: players count wherever they land (active or
    # taxi-routed); picks count as picks regardless of year. Counts are conserved,
    # so "them" is the exact negation on both currencies.
    np_me = get.n_players - give.n_players
    nk_me = get.n_picks - give.n_picks
    standalone = np_me == 0 and nk_me == 0
    # v6: leg_type follows the CROSSING family, not the player count alone.
    # "neutral" means genuinely standalone (0 players AND 0 picks); everything
    # else needs a complement, and `canonical_sig` says which side of the pair
    # it is. Through v5.1 a leg netting 0 players but ±k picks was mislabelled
    # "neutral" — it is not executable alone, and it is now pairable.
    if standalone:
        leg_type = "neutral"
    elif canonical_sig((np_me, nk_me)):
        leg_type = "buy"
    else:
        leg_type = "sell"
    if leg_type == "buy":
        if verdicts["me"]["overflow"] > 0:
            sequencing = (
                f"at the roster cap (+{verdicts['me']['overflow']} over): execute the "
                "paired sell-leg first — Sleeper trades process instantly"
            )
        else:
            sequencing = "roster space available: buy may execute before its paired sell"
    elif standalone:
        sequencing = "fully count-neutral (0 players / 0 picks net) — executable alone, order free"
    else:
        sequencing = (
            f"building block — nets {np_me:+d} players / {nk_me:+d} picks for you; "
            "not count-neutral alone — pair before executing"
        )
    unvalued = sorted(
        a.name for pkg in (give, get) for a in pkg.assets if a.unvalued
    )
    card = {
        "action": "TRADE",
        "counterparty": opp_name,
        "give": [_asset_dict(a) for a in give.assets],
        "get": [_asset_dict(a) for a in get.assets],
        # §2 v4: per-side coordinates against each side's OWN roster. ΔF is
        # reported in different lenses (mine v7, theirs market), so it negates
        # only when no pick crosses (§11.1b); ΔS never did. The ceiling
        # max(ΔS, ΔF) is derivable from `coords`; `ceiling` on this card stays
        # the §3 band-edge annotation.
        "coords": {
            "me": {"dS": round(ds_me, 1), "dF": round(df_me, 1)},
            "them": {"dS": round(ds_them, 1), "dF": round(df_them, 1)},
        },
        # §2 v4 verdict: objectively good ⟺ ΔS ≥ 0 AND ΔF ≥ 0, one strict
        "verdict": {
            "me": verdict_of(ds_me, df_me),
            "them": verdict_of(ds_them, df_them),
        },
        # §2 v4 guaranteed floor min(ΔS, ΔF) — the worst case over every
        # rational preference
        "floor": {"me": round(floor_me, 1), "them": round(floor_them, 1)},
        # §2 v4 breakeven δ* — only on preference trades (verdict false, one
        # coordinate positive); null everywhere else
        "breakeven": {
            "me": (round(b, 4) if (b := breakeven_of(ds_me, df_me)) is not None else None),
            "them": (
                round(b, 4) if (b := breakeven_of(ds_them, df_them)) is not None else None
            ),
        },
        "coords_basis": "isolation",  # this leg alone; pairs carry combined coords
        # §5 v4 leg return on inventory deployed: isolation floor(me) ÷ Σv
        # sent, percent — the disclosed pre-ranking heuristic
        "return_pct": round(100 * floor_me / give.v_sum, 2) if give.v_sum > 0 else None,
        # informational leg MARKET return: face ΔF(me) ÷ face Σv sent — the raw
        # face skim off this counterparty. v5 DEMOTED it from dial input to
        # annotation: the raw skim diverges from the counterparty's own
        # calculator by up to 14 pts; `favor` below is the dial's input
        "market_return_pct": (
            round(100 * (get.v_sum - give.v_sum) / give.v_sum, 2)
            if give.v_sum > 0
            else None
        ),
        # §4a v5 counterparty favorability — signed, 2dp, + = counterparty
        # wins; derived from the SAME adjusted totals as the gate above
        # (|favor| ≤ 5 ⟺ their calculator says FAIR at default variance)
        "favor": gate["favor"],
        "gate": gate,
        "posture": {
            "label": posture["label"],
            "source": posture.get("source", "trades"),
            "evidence_count": len(posture.get("evidence", [])),
            "shape": shape,
            "fit": fit,
        },
        "holes": _holes(league, opp_name, give),
        "net_roster": {"me": net_me, "them": verdicts["them"]["net_roster"]},
        "net_players": {"me": np_me, "them": -np_me},
        "net_picks": {"me": nk_me, "them": -nk_me},
        "standalone": standalone,
        "leg_type": leg_type,
        "sequencing": sequencing,
        "taxi_stashed": {
            "me": verdicts["me"]["taxi_stashed"],
            "them": verdicts["them"]["taxi_stashed"],
        },
        "anchor_ask": {
            "pct": params.anchor_ask_pct,
            "ask": round((1 + params.anchor_ask_pct / 100) * get.v_sum),
            "note": f"open {params.anchor_ask_pct:g}% above target (observed convention)",
        },
        "dip_notes": _dip_notes(league, get),
        "unvalued": unvalued,
    }
    if ceiling is not None:
        card["ceiling"] = {
            "value": round(ceiling),
            "note": (
                "band-edge ceiling for this give package — negotiating room above "
                "the proposal, never the opener (§3 v3.1)"
            ),
        }
    if unvalued:
        card["notes"] = [
            "unvalued assets contribute 0 to both coordinates and never enter "
            "a starting lineup — verify by hand (§11.7)"
        ]
    return card


def propose(
    league: md.LeagueState,
    opp_name: str,
    give_assets: Sequence[Asset],
    get_assets: Sequence[Asset],
) -> dict:
    """Score an explicit proposal (any assets, cornerstones and taxi included) and
    return its card plus the full gate verdict."""
    give = package_of(league, give_assets)
    get = package_of(league, get_assets)
    card = build_card(
        league, opp_name, give, get, ceiling=band_ceiling(league, opp_name, give)
    )
    g = card["gate"]
    reasons = []
    if not g["band_ok"]:
        reasons.append(f"outside fairness band (gap {g['gap_pct']}% > band)")
    if not g["ratio_ok"]:
        reasons.append(f"fleece ratio {g['raw_ratio']} > cap {g['cap']}")
    if not g["legal"]:
        reasons.append("post-trade roster illegal (positional minima / size)")
    card["gate"]["verdict"] = "PASS" if not reasons else "FAIL: " + "; ".join(reasons)
    if 0 < card["floor"]["me"] < league.params.w_min:
        card.setdefault("notes", []).append(
            f"guaranteed floor +{card['floor']['me']:g} sits inside KTC's "
            f"±{league.params.w_min:g} noise band — display note only; W_min is "
            "not a gate (v3.3)"
        )
    return card


def propose_by_names(
    league: md.LeagueState, opp_name: str, give_names: Sequence[str], get_names: Sequence[str]
) -> dict:
    mine = team_assets(league, league.teams[league.me])
    theirs = team_assets(league, league.teams[opp_name])
    return propose(
        league, opp_name, [mine[n] for n in give_names], [theirs[n] for n in get_names]
    )


def card_packages(league: md.LeagueState, card: dict) -> tuple[Package, Package]:
    """Rebuild a leg card's (give, get) packages from its asset keys — the way
    back from a stored board doc to the coordinate arithmetic (CLI + tests)."""
    by_key: dict[str, Asset] = {}
    for t in league.teams.values():
        for a in team_assets(league, t).values():
            by_key[a.key] = a
    return (
        package_of(league, [by_key[a["key"]] for a in card["give"]]),
        package_of(league, [by_key[a["key"]] for a in card["get"]]),
    )


def pair_coords(league: md.LeagueState, buy_card: dict, sell_card: dict) -> dict:
    """§5 v4 pair metrics recomputed from two leg cards: the EXACT combined
    coordinates (both legs applied together — ΔS one combined re-solve, ΔF
    additive) plus verdict/floor/ceiling/breakeven and the floor-based return
    on Σ face v I send across both legs. NOT the sum of the leg figures."""
    legs = [card_packages(league, buy_card), card_packages(league, sell_card)]
    return combined_coords(league, legs)


# ------------------------------------------- the pair pool + the board (§5 v3.3)


_POS4 = ("QB", "RB", "WR", "TE")
_MIN4 = tuple(MIN_POS[p] for p in _POS4)

# leg tuple layout inside PairPool.legs (indices 0-8 are the v3.3 contract and
# stay put; slots 0/1 hold the leg's ISOLATION floor return and floor — the
# pool's own variant-selection key and the ranking of the unpaired building
# blocks; indices 9-11 carry the coordinate inputs the pair walk needs — L_DFACE
# is the leg's ΔF, the v5.1 SOUND crossing key (§4a) — and 12 the leg's FAVOR,
# the §4a v5 signed counterparty skew in KTC's calculator units, derived from
# the same adjusted totals the gate read during the scan)
L_RET, L_FLOOR, L_SENT, L_NP, L_NK, L_OPP, L_MASK, L_GIVE, L_GET = range(9)
L_OUT4, L_IN4, L_DFACE, L_FAVOR = 9, 10, 11, 12
# §4a v6 the ADD-ONLY starter gain: what this leg's RECEIVED package alone would
# add to the current starting lineup, with nothing sent away. Depends only on
# the get package (so it is solved once per distinct package, not per leg), and
# it upper-bounds the pair's joint ΔS — see `_pair_ds_bound`.
L_A = 13

# v5.1 crossing tolerance. The walks test the pair bound in SPLIT form —
# `(r·sent_b − key_b) + (r·sent_s − key_s) ≤ 0` — while the bound itself is the
# pair form `key_pair ≥ r·sent_pair`. The two agree mathematically but not in
# float: on an EXACT tie (ΔF_pair == r·sent_pair, entirely reachable since ΔF
# and Σsent are integral and r is often round — e.g. ΔF 1256 vs 0.05·25120) the
# split sum can round to +5.7e-14 and prune a pair whose true return is exactly
# r. That is a one-ULP violation of "the prune can only discard pairs that
# genuinely fail the bar", so every walk keeps the boundary with this slack:
# key magnitudes here are ≤ ~1e5 (KTC face), whose float error is ≤ ~1e-11, and
# 1e-6 KTC points is far below any distinction the data can express. Over-
# inclusion is free — every kept crossing is priced by its EXACT combined
# coordinates and banded on those. Both the ≥-walks and the <-walks apply it
# with the SAME sign convention, so they still partition the crossing space
# exactly (no pair is counted twice, none is lost between them).
XTOL = 1e-6
# The counting passes compare `u_s` against a PRE-ADDED threshold while the
# walks add the two `u`s and compare the sum, so the two round differently by
# ~1 ULP and a bare XTOL threshold lets the estimate come out a few visits
# UNDER the walk (measured: ≤18 of ~1e6). `_deepest_cut` needs the other
# direction — "the estimate fits the budget" must IMPLY "the walk completes",
# since a walk that truncates where the estimate promised completion would let
# the board's coverage phase re-count what the sound phase already collected.
# This pad (1e-9 KTC points, 100× the worst rounding error at these magnitudes
# and 1000× below XTOL) makes every estimate a true upper bound on visits.
_EST_PAD = 1e-9


def pair_ds_bound(a_buy: float, a_sell: float) -> float:
    """§4a v6: a SOUND upper bound on a pair's joint ΔS from per-leg figures.

    Starter sum is the max-weight basis of a transversal matroid over the
    startable player pool (QB / 2RB / 3WR / TE / 2FLEX), so it is monotone and
    submodular in the set of players available. Write `R` for my current pool,
    `in_b`/`in_s` for the two legs' received players and `out_b`/`out_s` for the
    sent ones. Then

        ΔS_pair = L(R − out_b − out_s + in_b + in_s) − L(R)
                ≤ L(R + in_b + in_s) − L(R)                     (monotone: the
                                                     removals can only lower it)
                ≤ [L(R+in_b) − L(R)] + [L(R+in_s) − L(R)]       (submodular)
                = A(buy) + A(sell)

    which is exactly this. Note what it is NOT: the sum of the legs' ISOLATION
    ΔS values, which is not a bound at all (v5.1 was a coverage bug for
    precisely that reason — measured 5,875,757 violations over 20.1M crossings,
    worst overshoot 4,852). This one was audited at 0 violations over 24.4M
    crossings with no tolerance, and picks contribute nothing to either side
    since `pos_columns` drops them.

    Combined with the exactly-additive ΔF, it gives the pair floor a fully
    separable bound: floor = min(ΔS, ΔF) ≤ min(A_b + A_s, ΔF_b + ΔF_s)."""
    return a_buy + a_sell


def canonical_sig(sig: tuple[int, int]) -> bool:
    """§4a v6: is this count-signature the one that OWNS its crossing family?

    A legal spread's two legs have complementary signatures summing to (0, 0),
    so bucket `sig` crosses bucket `−sig` and every walk must visit each
    unordered bucket-pair exactly once. Through v5.1 the test was `sig[0] > 0`,
    which silently dropped the WHOLE Δplayers == 0 family: `(0, +k)` crosses
    `(0, −k)`, and `sig[0] > 0` rejects both sides, so no walk could ever reach
    them. Those are genuine hedges — swap players evenly with two teams while
    netting a pick from one to the other — and on the live pool they are 41,722
    legs carrying ~169M crossings (+6.1% of the space).

    `(0, 0)` is deliberately NOT canonical, and that is a scope decision rather
    than an oversight. A `(0, 0)` leg is already roster-neutral by itself, so
    pairing two of them is not a hedge — it is two unrelated even swaps stapled
    together, and there are 51,443 such legs on the live pool (≈1.3e9 pairings)
    which would swamp the board with noise. Single neutral legs already surface
    through `top_league_wide`; §5's `recommendations`."""
    return sig[0] > 0 or (sig[0] == 0 and sig[1] > 0)


@dataclass(slots=True)
class PairPool:
    """§5 v4 candidate-leg pool: for EVERY (counterparty, give-package,
    count-signature) combination, the top `variants_per_signature` gate-clean,
    fleece-clean, cheap-legality-clean gets by ISOLATION FLOOR, each
    posture-clean when `enforce_posture` (the pair-pool default; the CLI hedge
    finder disables it because the desk treats posture qualitatively).

    `index` is MY incremental starter-sum evaluator: the pair walk prices every
    kept crossing with the EXACT combined coordinates through it (§11.10)."""

    opp_names: list[str]
    legs: list[tuple]  # see the L_* layout above
    buckets: dict[tuple[int, int], list[int]]  # (np, nk) signature -> leg indices
    opp_pkgs: dict[str, tuple[list[float], list[Package]]]  # Σv-sorted; ceilings
    enforce_posture: bool
    index: StarterIndex

    def pair_eval(self, buy_i: int, sell_i: int) -> tuple[float, float, float, float, float]:
        """EXACT combined (floor-based return FRACTION, floor, ceiling, ΔS, ΔF)
        for two legs applied TOGETHER (§5 v4) — never assembled from the legs'
        isolation figures. One combined starter re-solve gives ΔS; ΔF is
        additive; the return is min(ΔS, ΔF) ÷ Σ face v I send across both legs
        (denominator stays face KTC). v5 exposes the raw coordinates too — the
        δ-slider re-scores stored pairs as ΔW(δ) from exactly these."""
        b, s = self.legs[buy_i], self.legs[sell_i]
        bo, so = b[L_OUT4], s[L_OUT4]
        bi_, si_ = b[L_IN4], s[L_IN4]
        d_s = self.index.delta(
            (bo[0] + so[0], bo[1] + so[1], bo[2] + so[2], bo[3] + so[3]),
            (bi_[0] + si_[0], bi_[1] + si_[1], bi_[2] + si_[2], bi_[3] + si_[3]),
        )
        d_f = b[L_DFACE] + s[L_DFACE]
        floor = d_s if d_s < d_f else d_f
        ceiling = d_f if d_s < d_f else d_s
        return floor / (b[L_SENT] + s[L_SENT]), floor, ceiling, d_s, d_f

    def pair_return(self, buy_i: int, sell_i: int) -> float:
        """The pair's floor-based return FRACTION (§5 v4) — pair_eval's first
        component, kept as the single-value entry point for tests/CLI."""
        return self.pair_eval(buy_i, sell_i)[0]

    def pair_favor(self, buy_i: int, sell_i: int) -> tuple[float, float, float]:
        """§4a v5 (f_buy, f_sell, min): each leg's counterparty favorability
        (stored on the leg at scan time, from the gate's own adjusted totals)
        and the pair figure — min over the legs, the least-happy counterparty."""
        fb = self.legs[buy_i][L_FAVOR]
        fs = self.legs[sell_i][L_FAVOR]
        return fb, fs, fb if fb < fs else fs


def _raw_adj_total(vals_desc: Sequence[float], r_max: float, cap: float) -> float:
    """ktc_adjust.side_raw_adj's TOTAL only — no per-asset entry list. The pool
    scan's screen needs just the sum; the entries are built afterwards, for the
    minority of candidates that survive it."""
    half = 0.5 * r_max
    denom = 1.05 * r_max
    nerf = -1
    total = 0.0
    for v in vals_desc:
        if v < half:
            nerf += 1
        s = (0.05 * (v / cap) ** 1.3 + 0.05 * (v / denom) ** 6 + 0.1) * v
        if nerf > 0:
            m = 1.0 - 0.15 * nerf
            s *= m if m > 0.6 else 0.6
        total += s
    return total


def _process_v0(x: float, r_max: float, cap: float) -> float:
    """processV at nerf 0 — the un-nerfed (largest) raw adjustment a value maps
    to. Used only as the pool scan's necessary-condition threshold."""
    return (0.05 * (x / cap) ** 1.3 + 0.05 * (x / (1.05 * r_max)) ** 6 + 0.1) * x


def _team_pos_vec(t: md.TeamCtx) -> tuple[int, int, int, int]:
    c = _pos_counts(t.act)
    return (c.get("QB", 0), c.get("RB", 0), c.get("WR", 0), c.get("TE", 0))


def _pos_vec(pkg: Package) -> tuple[int, int, int, int]:
    d = dict(pkg.pos_out)
    return (d.get("QB", 0), d.get("RB", 0), d.get("WR", 0), d.get("TE", 0))


_POOL_BAND_DEFAULT = object()  # sentinel: "take it from params"


def build_pair_pool(
    league: md.LeagueState,
    enforce_posture: bool = True,
    *,
    opponents: Sequence[str] | None = None,
    my_pkgs_for=None,
    opp_pkgs_for=None,
    favor_band: float | None = _POOL_BAND_DEFAULT,
) -> PairPool:
    """§5 v3.3 enumeration — no minimal-gap pruning, no W_min gate. Per opponent,
    per give-package, per get count-signature: walk the Σv window
    [gv ÷ fleece_ratio, gv · fleece_ratio] descending — the whole fleece bracket
    now, because with the return floor retired (v3.4) a leg that ships MORE face
    value than it receives can still have a positive floor inside a pair.

    Per (give, count-signature) the scan keeps the top `variants_per_signature`
    by ISOLATION FLOOR min(ΔS, ΔF) among the first `variant_scan_cap` candidates
    that clear the exact §3.1 gate and cheap positional legality on both sides.
    Two disclosed bounds (v3.4): the exact gate is ~30× the cost of the retired
    adjv comparison and the ΔS coordinate needs a starter-sum re-solve, so the scan
    (a) short-circuits on a cheap NECESSARY condition derived from the
    calculator's own arithmetic — a gate-passer's adjusted gap S obeys
    S ≤ max(500, 0.25·max side total), and S is monotone in the raw-adjustment
    gap, so a raw gap above processV of that bound can never clear the band —
    and (b) stops after `variant_scan_cap` passers rather than draining the
    bracket.

    v5 finder hooks (§4a — defaults leave the board path bit-identical):
    `opponents` restricts the scan to a counterparty subset; `my_pkgs_for` /
    `opp_pkgs_for` are callables (opp_name -> list[Package]) supplying the
    CONSTRAINED package subsets (constraint push-down happens BEFORE gate
    work); when omitted the full give-list enumerations are used. The finder
    compiles posture into constraints (§4), so it passes
    enforce_posture=False and filters through `my_pkgs_for` instead."""
    params = league.params
    me_t = league.teams[league.me]
    my_pkgs = _packages(league, give_list(league, me_t))
    my_counts = _team_pos_vec(me_t)
    my_act = len(me_t.act)
    my_index = team_index(me_t)
    # partner-leg collisions can only involve MY give assets (distinct
    # counterparties own disjoint pools) — bitmask exactly those. The bitmap is
    # built over the FULL give-list so constrained subsets share it.
    asset_bit: dict[str, int] = {}
    for g in my_pkgs:
        for k in g.keys:
            if k not in asset_bit:
                asset_bit[k] = 1 << len(asset_bit)
    K = params.variants_per_signature
    scan_cap = params.variant_scan_cap
    fl = params.fleece_ratio
    top_v = league.top_ktc_value
    cap = top_v + 80.0
    # §4a v6: inside a favor band the bracket is DRAINED (no caps) and the
    # screen tightens to that band; outside one, v5's sampled scan survives.
    band = params.pool_favor_band if favor_band is _POOL_BAND_DEFAULT else favor_band
    if band is None:
        b_star_factor = None  # the §3.1 gate band — b* = max(500, 0.25·T_max)
    else:
        # |favor| ≤ β ⟹ the adjusted gap G ≤ (2β/100)·adj_max, and adj_max is
        # itself at most T_max + G, so G ≤ T_max · 2β/(100 − β). The adjustment
        # is monotone in the raw-adjustment gap, so a raw gap above processV of
        # that bound cannot land inside the band. Strictly tighter than the §3.1
        # screen for every β < 11.1, which is why it removes ~95% of gate calls.
        b_star_factor = 2.0 * band / (100.0 - band)
    slack = params.screen_slack

    def _g_info(pkgs: Sequence[Package]) -> list[tuple]:
        out = []
        for g in pkgs:
            gp = _pos_vec(g)
            deficit = (
                max(0, _MIN4[0] - (my_counts[0] - gp[0])),
                max(0, _MIN4[1] - (my_counts[1] - gp[1])),
                max(0, _MIN4[2] - (my_counts[2] - gp[2])),
                max(0, _MIN4[3] - (my_counts[3] - gp[3])),
            )
            mask = 0
            for k in g.keys:
                mask |= asset_bit[k]
            out.append((g, gp, offer_shape(g), deficit, mask))
        return out

    g_info_all = _g_info(my_pkgs) if my_pkgs_for is None else None
    # §4a v6: add-only starter gain per distinct GET package (see `pair_ds_bound`)
    a_cache: dict[tuple[str, ...], float] = {}
    legs: list[tuple] = []
    buckets: dict[tuple[int, int], list[int]] = {}
    opp_pkgs: dict[str, tuple[list[float], list[Package]]] = {}
    opp_names = list(opponents) if opponents is not None else list(league.opponents)
    for oi, opp_name in enumerate(opp_names):
        opp_t = league.teams[opp_name]
        label = league.postures.get(opp_name, {}).get("label", ps.NEUTRAL)
        if opp_pkgs_for is None:
            vsums_all, pkgs_all = _sorted_opp_pkgs(league, opp_name)
        else:
            pkgs_all = sorted(opp_pkgs_for(opp_name), key=lambda p: (p.v_sum, p.keys))
            vsums_all = [p.v_sum for p in pkgs_all]
        g_info = g_info_all if my_pkgs_for is None else _g_info(my_pkgs_for(opp_name))
        opp_pkgs[opp_name] = (vsums_all, pkgs_all)
        opp_counts = _team_pos_vec(opp_t)
        opp_act = len(opp_t.act)
        # partition their packages by class (n_players, n_picks); Σv-ascending
        # order carries over from the shared sort
        classes: dict[tuple[int, int], tuple[list, list, list, list, list]] = {}
        for p in pkgs_all:
            c = classes.setdefault((p.n_players, p.n_picks), ([], [], [], [], []))
            c[0].append(p.v_sum)
            c[1].append(p.vals)
            c[2].append(_pos_vec(p))
            c[3].append(p)
            # raw adjustment at r_max = the package's OWN max — valid for every
            # candidate whose max dominates the give side (about half of them)
            c[4].append(kf.side_raw_adj(p.vals, p.vals[0], top_v))
        for g, gp, shape, deficit, mask in g_info:
            if enforce_posture and not posture_allows(label, shape):
                continue
            gv = g.v_sum
            g_vals = g.vals
            g_max = g_vals[0]
            lo_v, hi_v = gv / fl, gv * fl
            e_cache: dict[float, tuple[float, list]] = {}
            for (tp_, tk), (vs, tvals, pvs, lst, tself) in classes.items():
                if my_act + tp_ - g.n_players < 9 or opp_act + g.n_players - tp_ < 9:
                    continue
                i0 = bisect_left(vs, lo_v)
                i1 = bisect_right(vs, hi_v)
                if i0 >= i1:
                    continue
                np_, nk = tp_ - g.n_players, tk - g.n_picks
                passers = 0
                best: list[tuple] = []
                for i in range(i1 - 1, i0 - 1, -1):  # descending Σv
                    tv_pos = pvs[i]
                    if (
                        tv_pos[0] < deficit[0]
                        or tv_pos[1] < deficit[1]
                        or tv_pos[2] < deficit[2]
                        or tv_pos[3] < deficit[3]
                    ):
                        continue  # my minima, pre-routing (cheap)
                    if (
                        opp_counts[0] - tv_pos[0] + gp[0] < _MIN4[0]
                        or opp_counts[1] - tv_pos[1] + gp[1] < _MIN4[1]
                        or opp_counts[2] - tv_pos[2] + gp[2] < _MIN4[2]
                        or opp_counts[3] - tv_pos[3] + gp[3] < _MIN4[3]
                    ):
                        continue  # their minima, pre-routing (cheap)
                    t_vals = tvals[i]
                    t_v = vs[i]
                    t_max = t_vals[0]
                    if t_max >= g_max:
                        r_max = t_max
                        pre2 = tself[i]  # precomputed: their max already rules
                        a_tot = pre2[0]
                    else:
                        r_max = g_max
                        pre2 = None  # entries built only if the screen passes
                        a_tot = kf.raw_adj_total(t_vals, r_max, top_v)
                    pre1 = e_cache.get(r_max)
                    if pre1 is None:
                        pre1 = e_cache[r_max] = kf.side_raw_adj(g_vals, r_max, top_v)
                    raw_gap = pre1[0] - a_tot
                    if raw_gap < 0.0:
                        raw_gap = -raw_gap
                    max_tot = gv if gv > t_v else t_v
                    if b_star_factor is None:
                        b_star = 0.25 * max_tot
                        if b_star < 500.0:
                            b_star = 500.0
                    else:
                        # v6: the favor band's own (much tighter) bound — no
                        # absolute floor, because the band is relative
                        b_star = b_star_factor * max_tot
                    # Necessary condition, from the calculator's own arithmetic:
                    # the adjusted gap S obeys S ≤ max(500, 0.25·max side total)
                    # (the band is 0.20 of a side that is itself at most
                    # max_total + S), and S rises monotonically with the raw
                    # gap — so a raw gap above processV of that bound can never
                    # clear the band. Evaluating processV at nerf 0 and at
                    # r_max (rather than reverseAdjust's rescaled max), plus the
                    # 1.15 factor for its 2.5% tolerance, all push the threshold
                    # UP — the screen can only reject trades the exact gate
                    # rejects too (§11.3 asserts the two agree on the fixtures).
                    if raw_gap > slack * _process_v0(b_star, r_max, cap):
                        continue
                    if pre2 is None:
                        pre2 = kf.side_raw_adj(t_vals, r_max, top_v)
                    t = lst[i]
                    # §3.1 v6: the memoized fast path (M5 hoists gv/t_v/r_max and
                    # both raw-adjustment passes — the scan already holds them).
                    # `ktc_fast` is pinned bit-identical to the port by §11.14.
                    adj_g, adj_t = kf.adjusted_totals_pre(
                        gv, t_v, r_max, pre1[0], pre1[1], pre2[0], pre2[1], top_v
                    )
                    if not _band_ok(params, adj_g, adj_t):
                        continue
                    # v5: leg favor from the SAME adjusted totals this scan just
                    # computed for the band — the port never runs twice (§11.12(a))
                    favor = favor_of(adj_g, adj_t)
                    if band is not None and not -band <= favor <= band:
                        continue  # v6: outside the pool's band — not inventory
                    # §1 v7: ΔF is MY lens (picks conservatively priced), while
                    # `gv`/`t_v` above stay market face — they are the gate's and
                    # the bracket's currency, and `L_SENT` below is the return
                    # denominator, which is what I shipped at market price.
                    d_face = t.v_me_sum - g.v_me_sum
                    d_s, d_f = my_index.coords_delta(g.cols, t.cols, d_face)
                    floor = d_s if d_s < d_f else d_f
                    best.append((-floor, t.keys, t, d_face, favor))
                    if band is None:
                        # v5 sampled path: stop after `variant_scan_cap` passers
                        passers += 1
                        if passers >= scan_cap:
                            break
                if not best:
                    continue
                # v6: inside a band the bracket was DRAINED and everything in it
                # is kept, so the sort/truncate is the wide-band path only. It
                # still runs there for byte-identical v5 behaviour.
                if band is None:
                    best.sort()  # isolation floor desc, deterministic on the keys
                    best = best[:K]
                for _neg_floor, _k, t, d_face, favor in best:
                    floor = -_neg_floor
                    # §4a v6 add-only starter gain. A function of the GET
                    # package alone, so it is solved once per distinct package
                    # and reused across every leg that receives it.
                    a_add = a_cache.get(t.keys)
                    if a_add is None:
                        a_add = a_cache[t.keys] = my_index.delta(EMPTY4, t.cols)
                    buckets.setdefault((np_, nk), []).append(len(legs))
                    legs.append(
                        (
                            floor / gv, floor, gv, np_, nk, oi, mask, g, t,
                            g.cols, t.cols, d_face,
                            favor,  # §4a v5 leg favor, from the gate's own totals
                            a_add,  # §4a v6 add-only ΔS bound contribution
                        )
                    )
    return PairPool(
        opp_names=opp_names,
        legs=legs,
        buckets=buckets,
        opp_pkgs=opp_pkgs,
        enforce_posture=enforce_posture,
        index=my_index,
    )


def _tp_estimate(pool: PairPool, r: float, key: int = L_DFACE) -> int:
    """Uncorrected two-pointer size of the ≥r crossing space under the v5.1
    SOUND bound (§4a): u_r(leg) = ΔF(leg) − r·Σv sent, and
    u_r(buy) + u_r(sell) ≥ 0 ⟺ ΔF_pair ≥ r·sent_pair. Since ΔF is exactly
    additive and floor ≤ ΔF, that region CONTAINS every pair whose exact
    combined floor return is ≥ r. An UPPER BOUND on the crossing count
    `_walk_pairs` visits at r, equal to it in every measurement (the pad in
    `_EST_PAD` covers the one-ULP gap between adding the two `u`s and
    thresholding one of them, in the direction that keeps "the estimate fits
    the budget ⟹ the walk completes"). No counterparty / overlap / legality
    corrections; used to place collection cutoffs and to detect sparse markets.
    Every visited pair is then priced by its EXACT combined coordinates, so
    this counts CROSSINGS — an upper bound on the qualifying pairs, never their
    tally.

    `key` selects the leg field the crossing is keyed on, so the same counter
    sizes the board's COVERAGE phase (`key=L_FLOOR`, the v5.0.1 ordering — a
    yield heuristic that certifies nothing, §5) as well as the sound one."""
    legs = pool.legs
    total = 0
    for sig, idxs in pool.buckets.items():
        if not canonical_sig(sig):
            continue
        comp = pool.buckets.get((-sig[0], -sig[1]))
        if not comp:
            continue
        bs = sorted(legs[i][key] - r * legs[i][L_SENT] for i in idxs)
        ss = sorted(legs[i][key] - r * legs[i][L_SENT] for i in comp)
        n = len(ss)
        for sb in reversed(bs):
            # the walk's keep set (u_b + u_s ≥ −XTOL), padded so this counts
            # at least every crossing the walk visits
            lo = bisect_left(ss, -(XTOL + _EST_PAD) - sb)
            if lo >= n:
                break
            total += n - lo
    return total


def _leg_legal(league: md.LeagueState, me_t: md.TeamCtx, pool: PairPool, i: int, cache: dict):
    """Full §3.3 legality for pool leg i, memoized as a BOOLEAN (an illegal leg
    can never appear in any pair or card). v3.3.1: the cache holds booleans, not
    verdict dicts — the collection walks touch hundreds of thousands of legs and
    the collector Lambda runs at 512MB; card building recomputes full verdicts
    for the handful of stored legs."""
    v = cache.get(i)
    if v is None:
        leg = pool.legs[i]
        v = legality(
            league, me_t, league.teams[pool.opp_names[leg[L_OPP]]],
            give=leg[L_GIVE], get=leg[L_GET],
        )["legal"]
        cache[i] = v
    return v


def _tp_estimate_below(pool: PairPool, r: float, key: int = L_DFACE) -> int:
    """Mirror of _tp_estimate for the LOW end: uncorrected two-pointer size of
    the sub-r crossing space under the same v5.1 key (u_r(leg) = ΔF − r·Σv sent;
    u_r(buy) + u_r(sell) < 0, which by the sound bound implies the pair's exact
    floor return really is < r). Exact on crossings — the visit count of a
    below-walk at r; the two walks partition the crossing space at r. v3.4
    retired the per-leg return floor, so this space is NOT bounded below by the
    dial floor: buy legs are legitimately negative alone and the below-walk can
    be as deep as the top one. `key` mirrors `_tp_estimate`'s — the board's
    coverage phase sizes its below-walk with `key=L_FLOOR`."""
    legs = pool.legs
    total = 0
    for sig, idxs in pool.buckets.items():
        if not canonical_sig(sig):
            continue
        comp = pool.buckets.get((-sig[0], -sig[1]))
        if not comp:
            continue
        bs = sorted(legs[i][key] - r * legs[i][L_SENT] for i in idxs)
        ss = sorted(legs[i][key] - r * legs[i][L_SENT] for i in comp)
        for tb in bs:  # ascending u: the count of complements only shrinks
            # sells with τ_s < −τ_b − XTOL, strictly (padded upward, same
            # reason as _tp_estimate: never under-count the walk's visits)
            lo = bisect_left(ss, _EST_PAD - XTOL - tb)
            if lo == 0:
                break
            total += lo
    return total


def _walk_pairs_below(
    league: md.LeagueState,
    pool: PairPool,
    r: float,
    budget: int,
    legal: dict,
    out: list[tuple[float, float, float, int, int, float, float]],
    key: int = L_DFACE,
) -> tuple[int, bool]:
    """Enumerate the crossing space BELOW r — the exact complement of
    _walk_pairs at r under the v5.1 sound key (crossings with
    u_r(buy) + u_r(sell) ≥ 0 belong to the ≥ walk). Every pair reached here has
    ΔF_pair < r·sent_pair, hence an exact floor return < r. Identical
    constraints and honesty contract; u_r-ASCENDING crossing with early exit, so
    the low end of the return space is reachable without sweeping the (much
    deeper) top. Deterministic throughout."""
    legs = pool.legs
    me_t = league.teams[league.me]
    visits = 0
    for sig in sorted(pool.buckets):
        if not canonical_sig(sig):
            continue
        comp_idx = pool.buckets.get((-sig[0], -sig[1]))
        if not comp_idx:
            continue
        # (u_r, pool index): ascending sort == lowest crossing returns first
        bs = sorted((legs[i][key] - r * legs[i][L_SENT], i) for i in pool.buckets[sig])
        ss = sorted((legs[i][key] - r * legs[i][L_SENT], i) for i in comp_idx)
        ss0 = ss[0][0]
        for tb, bi in bs:
            if tb + ss0 >= -XTOL:
                break  # even the lowest sell keeps this (and any later) buy at ≥ r
            b = legs[bi]
            b_opp, b_mask, b_key, b_sent = b[L_OPP], b[L_MASK], b[key], b[L_SENT]
            vb = None
            for ts, si in ss:
                if tb + ts >= -XTOL:
                    break  # ≥ r side of the boundary (XTOL: exact ties belong there)
                visits += 1
                if visits > budget:
                    return visits - 1, False
                s = legs[si]
                if s[L_OPP] == b_opp or (s[L_MASK] & b_mask):
                    continue
                if vb is None:
                    vb = _leg_legal(league, me_t, pool, bi, legal)
                if vb is False:
                    break  # illegal buy leg: no pair with it exists
                if _leg_legal(league, me_t, pool, si, legal) is False:
                    continue
                # (exact combined return, exact ceiling, ΔF-return of the
                # crossing, buy, sell, exact ΔS, exact ΔF): the sink bands and
                # RANKS on the EXACT figures (floor-return desc, ceiling
                # tie-break — §2 v4 maximin; v5 also keeps per-bucket tops by
                # ΔS and ΔF for the δ slider); the walks' disjointness is
                # defined by the v5.1 crossing key ΔF_pair ÷ sent_pair (§4a),
                # which bounds the exact floor return from ABOVE
                ret, _floor, ceil, d_s, d_f = pool.pair_eval(bi, si)
                out.append(
                    (
                        ret,
                        ceil,
                        (b_key + s[key]) / (b_sent + s[L_SENT]),
                        bi,
                        si,
                        d_s,
                        d_f,
                    )
                )
    return visits, True


def _walk_pairs(
    league: md.LeagueState,
    pool: PairPool,
    r: float,
    budget: int,
    legal: dict,
    out: list[tuple[float, float, float, int, int, float, float]],
    key: int = L_DFACE,
) -> tuple[int, bool]:
    """Enumerate the VALID pair space at return ≥ r: complementary
    count-signature buckets crossed in u_r-descending order with early exit,
    where `u_r(leg) = ΔF(leg) − r·Σv sent` is the v5.1 SOUND crossing key
    (§4a). ΔF is exactly additive across legs and `floor = min(ΔS, ΔF) ≤ ΔF`,
    so `u_r(buy) + u_r(sell) < 0 ⟹ floor_pair < r·sent_pair ⟹ return < r`:
    the early exit can only skip pairs that genuinely fail the bar, and a walk
    that COMPLETES has enumerated every valid pair with exact return ≥ r.
    Constraints per §5 v3.3 — distinct counterparties, disjoint assets (my-give
    masks; get-sides cannot collide across distinct counterparties), both legs
    full-legality PASS (memoized in `legal`). Appends (exact combined return,
    exact ceiling, crossing ΔF-return, buy_i, sell_i, exact ΔS, exact ΔF) to
    `out`. Returns (pairs_visited, completed) — completed=False means the visit
    budget truncated the walk and `out` is a verified floor, not the whole
    space. Deterministic throughout.

    `key` swaps the leg field the crossing is ordered and pruned on. The board
    also runs this walk with `key=L_FLOOR` as a pure COVERAGE pass (the v5.0.1
    ordering): the isolation-floor sum neither bounds the combined floor above
    nor below — pairs are lineup-coupled — so that pass certifies NOTHING; it
    is simply where high-floor pairs are densest, and it only ADDS inventory.
    Every soundness/exactness claim rests on the default key. `out`'s crossing
    coordinate (slot 2) is the ΔF-return either way, so the walks' disjointness
    bookkeeping is in one set of units."""
    legs = pool.legs
    me_t = league.teams[league.me]
    visits = 0
    for sig in sorted(pool.buckets):
        if not canonical_sig(sig):
            continue
        comp_idx = pool.buckets.get((-sig[0], -sig[1]))
        if not comp_idx:
            continue
        # (−u_r, pool index): ascending sort == u_r-descending walk, deterministic
        bs = sorted((r * legs[i][L_SENT] - legs[i][key], i) for i in pool.buckets[sig])
        ss = sorted((r * legs[i][L_SENT] - legs[i][key], i) for i in comp_idx)
        ns0 = ss[0][0]
        for nb, bi in bs:
            if nb + ns0 > XTOL:
                break  # even the best sell can't lift this (or any later) buy to r
            b = legs[bi]
            b_opp, b_mask, b_key, b_sent = b[L_OPP], b[L_MASK], b[key], b[L_SENT]
            vb = None
            for ns, si in ss:
                if nb + ns > XTOL:
                    break  # below r (XTOL keeps exact ties, which qualify)
                visits += 1
                if visits > budget:
                    return visits - 1, False
                s = legs[si]
                if s[L_OPP] == b_opp or (s[L_MASK] & b_mask):
                    continue
                if vb is None:
                    vb = _leg_legal(league, me_t, pool, bi, legal)
                if vb is False:
                    break  # illegal buy leg: no pair with it exists
                if _leg_legal(league, me_t, pool, si, legal) is False:
                    continue
                # (exact combined return, exact ceiling, ΔF-return of the
                # crossing, buy, sell, exact ΔS, exact ΔF): the sink bands and
                # RANKS on the EXACT figures (floor-return desc, ceiling
                # tie-break — §2 v4 maximin; v5 also keeps per-bucket tops by
                # ΔS and ΔF for the δ slider); the walks' disjointness is
                # defined by the v5.1 crossing key ΔF_pair ÷ sent_pair (§4a),
                # which bounds the exact floor return from ABOVE
                ret, _floor, ceil, d_s, d_f = pool.pair_eval(bi, si)
                out.append(
                    (
                        ret,
                        ceil,
                        (b_key + s[key]) / (b_sent + s[L_SENT]),
                        bi,
                        si,
                        d_s,
                        d_f,
                    )
                )
    return visits, True


def _walk_pairs_range(
    league: md.LeagueState,
    pool: PairPool,
    lo_r: float,
    hi_r: float,
    budget: int,
    scan_cap: int,
    legal: dict,
    out,
    key: int = L_DFACE,
) -> tuple[int, bool]:
    """Enumerate the VALID pair space with lo_r ≤ return < hi_r — the gap left
    between a complete top-down walk (≥ hi_r) and a complete below-walk
    (< lo_r). The ≥ lo_r crossings are scanned top-down, but pairs the top walk
    already owns (crossing ΔF-return ≥ hi_r) are skipped with one multiply and
    do NOT consume the visit budget — only in-range crossings do; `scan_cap`
    bounds the raw scanning time. Same v5.1 sound key, constraints and honesty
    contract as _walk_pairs; deterministic throughout."""
    legs = pool.legs
    me_t = league.teams[league.me]
    visits = 0
    scanned = 0
    for sig in sorted(pool.buckets):
        if not canonical_sig(sig):
            continue
        comp_idx = pool.buckets.get((-sig[0], -sig[1]))
        if not comp_idx:
            continue
        bs = sorted((lo_r * legs[i][L_SENT] - legs[i][key], i) for i in pool.buckets[sig])
        ss = sorted((lo_r * legs[i][L_SENT] - legs[i][key], i) for i in comp_idx)
        ns0 = ss[0][0]
        for nb, bi in bs:
            if nb + ns0 > XTOL:
                break
            b = legs[bi]
            b_opp, b_mask, b_key, b_sent = b[L_OPP], b[L_MASK], b[key], b[L_SENT]
            # the hi_r ownership test below is evaluated in exactly the split
            # form (and with exactly the tolerance) the top walk at hi_r uses,
            # so the two agree bit-for-bit and the slices stay disjoint
            hb = hi_r * b_sent - b_key
            vb = None
            for ns, si in ss:
                if nb + ns > XTOL:
                    break
                scanned += 1
                if scanned > scan_cap:
                    return visits, False
                s = legs[si]
                if hb + (hi_r * s[L_SENT] - s[key]) <= XTOL:
                    continue  # ≥ hi_r: the top walk owns it — budget-free skip
                visits += 1
                if visits > budget:
                    return visits - 1, False
                if s[L_OPP] == b_opp or (s[L_MASK] & b_mask):
                    continue
                if vb is None:
                    vb = _leg_legal(league, me_t, pool, bi, legal)
                if vb is False:
                    break  # illegal buy leg: no pair with it exists
                if _leg_legal(league, me_t, pool, si, legal) is False:
                    continue
                # (exact combined return, exact ceiling, ΔF-return of the
                # crossing, buy, sell, exact ΔS, exact ΔF): the sink bands and
                # RANKS on the EXACT figures (floor-return desc, ceiling
                # tie-break — §2 v4 maximin; v5 also keeps per-bucket tops by
                # ΔS and ΔF for the δ slider); the walks' disjointness is
                # defined by the v5.1 crossing key ΔF_pair ÷ sent_pair (§4a),
                # which bounds the exact floor return from ABOVE
                ret, _floor, ceil, d_s, d_f = pool.pair_eval(bi, si)
                out.append(
                    (
                        ret,
                        ceil,
                        (b_key + s[key]) / (b_sent + s[L_SENT]),
                        bi,
                        si,
                        d_s,
                        d_f,
                    )
                )
    return visits, True


def _walk_pairs_below_range(
    league: md.LeagueState,
    pool: PairPool,
    lo_r: float,
    hi_r: float,
    budget: int,
    scan_cap: int,
    legal: dict,
    out,
    key: int = L_DFACE,
) -> tuple[int, bool]:
    """Enumerate the VALID pair space with lo_r ≤ return < hi_r from BENEATH:
    u_{hi_r}-ascending crossing (lowest ΔF-returns first, the v5.1 sound key),
    crossings the below-walk already owns (ΔF-return < lo_r) skipped with one
    multiply and no budget. When the visit budget truncates, the collected set
    is the RANGE'S BOTTOM — a verified, deterministic partial fill for bands
    unreachable from the top."""
    legs = pool.legs
    me_t = league.teams[league.me]
    visits = 0
    scanned = 0
    for sig in sorted(pool.buckets):
        if not canonical_sig(sig):
            continue
        comp_idx = pool.buckets.get((-sig[0], -sig[1]))
        if not comp_idx:
            continue
        bs = sorted((legs[i][key] - hi_r * legs[i][L_SENT], i) for i in pool.buckets[sig])
        ss = sorted((legs[i][key] - hi_r * legs[i][L_SENT], i) for i in comp_idx)
        ss0 = ss[0][0]
        for tb, bi in bs:
            if tb + ss0 >= -XTOL:
                break
            b = legs[bi]
            b_opp, b_mask, b_key, b_sent = b[L_OPP], b[L_MASK], b[key], b[L_SENT]
            # the lo_r ownership test below is evaluated in exactly the split
            # form (and with exactly the tolerance) the below-walk at lo_r
            # uses, so the two agree bit-for-bit and the slices stay disjoint
            lb = b_key - lo_r * b_sent
            vb = None
            for ts, si in ss:
                if tb + ts >= -XTOL:
                    break
                scanned += 1
                if scanned > scan_cap:
                    return visits, False
                s = legs[si]
                if lb + (s[key] - lo_r * s[L_SENT]) < -XTOL:
                    continue  # < lo_r: the below-walk owns it — budget-free skip
                visits += 1
                if visits > budget:
                    return visits - 1, False
                if s[L_OPP] == b_opp or (s[L_MASK] & b_mask):
                    continue
                if vb is None:
                    vb = _leg_legal(league, me_t, pool, bi, legal)
                if vb is False:
                    break  # illegal buy leg: no pair with it exists
                if _leg_legal(league, me_t, pool, si, legal) is False:
                    continue
                # (exact combined return, exact ceiling, ΔF-return of the
                # crossing, buy, sell, exact ΔS, exact ΔF): the sink bands and
                # RANKS on the EXACT figures (floor-return desc, ceiling
                # tie-break — §2 v4 maximin; v5 also keeps per-bucket tops by
                # ΔS and ΔF for the δ slider); the walks' disjointness is
                # defined by the v5.1 crossing key ΔF_pair ÷ sent_pair (§4a),
                # which bounds the exact floor return from ABOVE
                ret, _floor, ceil, d_s, d_f = pool.pair_eval(bi, si)
                out.append(
                    (
                        ret,
                        ceil,
                        (b_key + s[key]) / (b_sent + s[L_SENT]),
                        bi,
                        si,
                        d_s,
                        d_f,
                    )
                )
    return visits, True


class _DropSpans:
    """append() adapter that drops pairs an EARLIER walk already owns, so sink
    tallies stay exact counts of DISTINCT pairs. Two ownership forms:

    - `spans` — crossing-return spans (percent, half-open) in the walks' OWN
      key units (slot 2 of the walk tuple); keeps the range slices and the
      catch-all sweep disjoint from each other and from their phase's top walk.
    - `sound_hi` — the region the v5.1 SOUND top walk owns, i.e. crossings with
      `ΔF_pair ≥ sound_hi · sent_pair` (a FRACTION). That walk runs first and
      completes, so the coverage phase must hand its region back (§5 v5.1).
      None when the sound walk did not run — a truncated phase A owns nothing,
      and dropping a region nobody enumerated would lose storable pairs.
    """

    __slots__ = ("sink", "spans", "legs", "sound_hi")

    def __init__(self, sink, spans: list[tuple[float, float]], legs=None, sound_hi=None):
        self.sink = sink
        self.spans = spans
        self.legs = legs
        self.sound_hi = sound_hi

    def append(self, t: tuple[float, float, float, int, int, float, float]) -> None:
        pct = 100.0 * t[2]  # the crossing return in this walk's key units
        for a, b in self.spans:
            if a <= pct < b:
                return
        if self.sound_hi is not None:
            b_leg, s_leg = self.legs[t[3]], self.legs[t[4]]
            r = self.sound_hi
            # evaluated in exactly the split form (and tolerance) the sound top
            # walk at r* used, so ownership agrees with it bit-for-bit
            if (r * b_leg[L_SENT] - b_leg[L_DFACE]) + (
                r * s_leg[L_SENT] - s_leg[L_DFACE]
            ) <= XTOL:
                return  # the sound top walk owns it
        self.sink.append(t)


def _deepest_cut(
    pool: PairPool, floor: float, hi: float, budget: int, key: int = L_DFACE
) -> float:
    """Lowest return cutoff in [floor, hi] whose crossing count fits the walk
    budget. _tp_estimate upper-bounds the crossings _walk_pairs visits (it
    upper-bounds only the VALID pairs), so a walk at the returned cutoff is
    guaranteed to complete — except when even `hi` does not fit (then `hi` is
    returned; the caller checks the estimate before walking). v5.1: a
    completed walk at a cutoff ≤ the stored floor certifies the whole stored
    universe, because the crossing key bounds the floor from above (§4a).
    `key` sizes the same search for the board's tight coverage pass."""
    if _tp_estimate(pool, floor, key) <= budget:
        return floor
    if _tp_estimate(pool, hi, key) > budget:
        return hi
    lo_r, hi_r = floor, hi
    for _ in range(18):
        mid = (lo_r + hi_r) / 2.0
        if _tp_estimate(pool, mid, key) > budget:
            lo_r = mid
        else:
            hi_r = mid
    return hi_r


def _highest_cut_below(
    pool: PairPool, floor: float, hi: float, budget: int, key: int = L_DFACE
) -> float:
    """Highest return cutoff in [floor, hi] whose BELOW-crossing count fits the
    walk budget — how far up from the floor a complete below-walk can reach.
    v3.4: with the per-leg return floor retired the below-space at `floor` is
    no longer empty, so this can legitimately return `floor` itself (the
    below-walk then contributes nothing and the range slices carry the band)."""
    if _tp_estimate_below(pool, hi, key) <= budget:
        return hi
    lo_r, hi_r = floor, hi
    for _ in range(18):
        mid = (lo_r + hi_r) / 2.0
        if _tp_estimate_below(pool, mid, key) <= budget:
            lo_r = mid
        else:
            hi_r = mid
    return lo_r


def return_bands(presets: Sequence[float]) -> list[tuple[float, float | None]]:
    """§5 total-return bands, percent, derived from the floor presets:
    [p0, p1), [p1, p2), …, [p_last, ∞) — ascending, hi=None on the open top.
    These are the `by_total` grid columns; storage strata are the FAVOR
    buckets (favor_buckets, v5)."""
    ps = sorted(float(p) for p in presets)
    return [(ps[i], ps[i + 1] if i + 1 < len(ps) else None) for i in range(len(ps))]


def band_index(bands: Sequence[tuple[float, float | None]], ret_pct: float) -> int | None:
    """Index of the half-open band containing ret_pct (percent, the doc's
    2-dp-rounded return), or None below the lowest band's lo."""
    idx = None
    for i, (lo, _hi) in enumerate(bands):
        if ret_pct >= lo:
            idx = i
    return idx


def favor_buckets(edges: Sequence[float]) -> list[tuple[float | None, float | None]]:
    """§5 v5 favorability storage buckets from the band edges
    (favor_band_edges): (−∞, e0), [e0, e1), …, [e_last, ∞) — half-open,
    lo=None on the open bottom (a leg can skew arbitrarily far toward me),
    hi=None on the open top. Pairs bucket on min(f_buy, f_sell) — the
    least-happy counterparty; the favor dial is a FLOOR, so a floor at a
    bucket edge selects exactly the buckets with lo ≥ that edge."""
    cs = sorted(float(c) for c in edges)
    out: list[tuple[float | None, float | None]] = [(None, cs[0])]
    out += [(cs[i], cs[i + 1] if i + 1 < len(cs) else None) for i in range(len(cs))]
    return out


def bucket_index(
    buckets: Sequence[tuple[float | None, float | None]], value: float
) -> int:
    """Index of the half-open bucket containing `value` (v5: the doc's
    2-dp-rounded pair favor min). Total: every value has a bucket."""
    idx = 0
    for i, (lo, _hi) in enumerate(buckets):
        if lo is not None and value >= lo:
            idx = i
    return idx


class _BucketSink:
    """append()-compatible walk output that stratifies on the fly (§5 v5):
    per FAVOR BUCKET (pair favor = min(f_buy, f_sell), the least-happy
    counterparty, in KTC's own variance units) THREE bounded min-heaps — the
    top-`quota` pairs by EXACT combined floor-based TOTAL return (§2 v4
    maximin), by ΔS, and by ΔF — whose deduped UNION is the bucket's stored
    inventory, so both δ-slider extremes have stock; plus a tally of every
    valid pair seen and the bucket × robust-return-band count grid the
    inventory line is served from. Pairs with floor-based return below the
    lowest floor preset are outside the stored universe — never stored, never
    counted; since the lowest preset is positive, everything stored has
    floor > 0, i.e. BOTH coordinates strictly positive — the §11.8b(d)/§11.12(g)
    verdict constraint is enforced here as a hard, explicit guard as well. The
    collection walks cover DISJOINT HEURISTIC return ranges, so no pair is
    ever offered twice and no cross-walk dedupe is needed — and memory stays
    O(buckets · quota) where full lists would blow the collector's 512MB."""

    __slots__ = ("buckets", "tbands", "quota", "legs", "h_ret", "h_ds", "h_df", "counts", "grid")

    def __init__(
        self,
        buckets: Sequence[tuple[float | None, float | None]],
        tbands: Sequence[tuple[float, float | None]],
        quota: int,
        legs: Sequence[tuple],
    ):
        self.buckets = buckets
        self.tbands = tbands
        self.quota = quota
        self.legs = legs
        # heap entries put the ranking key first and the NEGATED pool ids
        # after it, so lexicographic order inverts the deterministic storage
        # sort (key desc, tie-break desc, ids asc) and the min-heap root is
        # always the worst kept pair under that order. Trailing fields carry
        # the pair's other exact figures for the union rebuild.
        #   h_ret: (ret, ceiling, -bi, -si, ΔS, ΔF)   — §2 v4 maximin
        #   h_ds:  (ΔS, ΔF, -bi, -si, ret, ceiling)   — δ = 0 extreme
        #   h_df:  (ΔF, ΔS, -bi, -si, ret, ceiling)   — δ = 1 extreme
        self.h_ret: list[list[tuple]] = [[] for _ in buckets]
        self.h_ds: list[list[tuple]] = [[] for _ in buckets]
        self.h_df: list[list[tuple]] = [[] for _ in buckets]
        self.counts: list[int] = [0] * len(buckets)
        self.grid: list[list[int]] = [[0] * len(tbands) for _ in buckets]

    def append(self, t: tuple[float, float, float, int, int, float, float]) -> None:
        ret, ceil, _heur, bi, si, d_s, d_f = t
        if ret <= 0.0:
            # §11.8b(d)/§11.12(g) HARD verdict constraint: a non-positive floor
            # means the pair is not objectively good — must never be stored,
            # whatever the presets say
            return
        ti = band_index(self.tbands, round(100.0 * ret, 2))
        if ti is None:
            return  # total below the lowest floor preset: outside the universe
        legs = self.legs
        fb = legs[bi][L_FAVOR]
        fs = legs[si][L_FAVOR]
        i = bucket_index(self.buckets, round(fb if fb < fs else fs, 2))
        self.counts[i] += 1
        self.grid[i][ti] += 1
        for h, e in (
            (self.h_ret[i], (ret, ceil, -bi, -si, d_s, d_f)),
            (self.h_ds[i], (d_s, d_f, -bi, -si, ret, ceil)),
            (self.h_df[i], (d_f, d_s, -bi, -si, ret, ceil)),
        ):
            if len(h) < self.quota:
                heappush(h, e)
            elif e > h[0]:
                heappushpop(h, e)

    def bucket_pairs(self, i: int) -> list[tuple[float, float, int, int]]:
        """Stored pairs of bucket i — the deduped UNION of the three top-quota
        heaps (§5 v5), returned floor-return desc, ceiling desc, deterministic
        ids (§2 v4 maximin — the flat doc order; the δ dial re-sorts client-side
        from the stored coordinates)."""
        union: dict[tuple[int, int], tuple[float, float]] = {}
        for e in self.h_ret[i]:
            union[(-e[2], -e[3])] = (e[0], e[1])
        for h in (self.h_ds[i], self.h_df[i]):
            for e in h:
                union[(-e[2], -e[3])] = (e[4], e[5])
        return sorted(
            ((ret, ceil, bi, si) for (bi, si), (ret, ceil) in union.items()),
            key=lambda t: (-t[0], -t[1], t[2], t[3]),
        )


def find_pool_leg(pool: PairPool, opp_name: str, give_keys, get_keys) -> int | None:
    """Locate a pool leg by counterparty + exact asset multisets (tests/CLI)."""
    gk, tk = tuple(sorted(give_keys)), tuple(sorted(get_keys))
    oi = pool.opp_names.index(opp_name)
    for i, leg in enumerate(pool.legs):
        if leg[L_OPP] == oi and leg[L_GIVE].keys == gk and leg[L_GET].keys == tk:
            return i
    return None


def pair_in_space(league: md.LeagueState, pool: PairPool, buy_i: int, sell_i: int) -> float | None:
    """Validate the §5 v3.3 pair constraints for two pool legs; returns the
    pair's EXACT combined return FRACTION (§5 v3.4) when the pair is in the
    computed space, else None. (Exhaustiveness spot-checks and the CLI use this
    — no enumeration needed: the cross over complementary buckets is total, so
    pool membership plus these constraints IS membership in the pair space.)"""
    b, s = pool.legs[buy_i], pool.legs[sell_i]
    # v6: the buy leg must own its crossing family (`canonical_sig`) and the
    # sell leg must be its exact complement. Through v5.1 this read
    # `b[L_NP] <= 0 or s[L_NP] >= 0`, which — like the walks — excluded the
    # whole Δplayers == 0 family from the pair space.
    if not canonical_sig((b[L_NP], b[L_NK])):
        return None
    if b[L_NP] + s[L_NP] != 0 or b[L_NK] + s[L_NK] != 0:
        return None
    if b[L_OPP] == s[L_OPP] or (b[L_MASK] & s[L_MASK]):
        return None
    me_t = league.teams[league.me]
    cache: dict[int, Any] = {}
    if _leg_legal(league, me_t, pool, buy_i, cache) is False:
        return None
    if _leg_legal(league, me_t, pool, sell_i, cache) is False:
        return None
    return pool.pair_return(buy_i, sell_i)


def pair_count_deltas(buy_card: dict, sell_card: dict) -> tuple[int, int]:
    """Combined (Δplayers, Δpicks) for MY side across a candidate pair.
    §5 v3.2 strict: a recommended pair requires exactly (0, 0) — the same number
    of players and picks after execution as before."""
    return (
        buy_card["net_players"]["me"] + sell_card["net_players"]["me"],
        buy_card["net_picks"]["me"] + sell_card["net_picks"]["me"],
    )


def trade_board(league: md.LeagueState) -> dict:
    """§5 v5: the exhaustively-crossed PAIR board behind the finder's THREE
    sliders, over stored inventory — a δ SELECTOR (robust default + the δ
    presets: return(δ) re-scored client-side from each stored pair's exact
    coordinates, a labeled preference VIEW), a floor on TOTAL return (robust
    mode = guaranteed-floor return, §2 v4 / §5), and a FLOOR on counterparty
    favorability min(f_buy, f_sell) (§4a — each leg's signed KTC-calculator
    skew toward its counterparty, from the same adjusted totals as the gate;
    replaces the v3.4.1 raw-skim leg cap). Every stored pair passes the §2
    objective verdict — the stored universe is robust floor-based return ≥ 1%,
    so both coordinates are strictly positive on everything stored
    (§11.8b(d)/§11.12(g), hard). Storage is STRATIFIED BY FAVOR BUCKET: pairs
    bucket on min(f_buy, f_sell) over (−∞,−10), [−10,−5), [−5,0), [0,+5),
    [+5,∞); per bucket the DEDUPED UNION of the top `pairs_per_band` by robust
    floor-return, by ΔS, and by ΔF is kept — so both δ-slider extremes have
    inventory — and `pairs` lists every stored pair in the §2 maximin order
    globally (floor-return desc, ceiling desc, ids; the δ and favor dials
    re-sort/filter client-side from the stored coords/favor). Every stored
    pair is fully count-neutral, both legs gate-PASS, posture-clean, distinct
    counterparties, no shared assets, and carries coords/floor/ceiling/favor/
    sent so every dial move is O(stored). `bands` carries per-BUCKET honest
    disclosure ({lo|None, hi|None, stored, count, saturated, by_total} —
    by_total is the bucket's count per robust-return band, so the inventory
    line is honest for any (floor, favor) combination; v5.1: a count is EXACT
    (`saturated` False) when the floor-objective collection walk ran to
    completion under the sound crossing bound (§4a), and a verified FLOOR only
    when the budget truncated it). `counts_by_threshold` and `truncated` stay for
    ≥-style compat reads on robust total return. `recommendations` (top
    unpaired sell/neutral legs by isolation floor) and `watch` (unpaired
    buys) stay as data for the trade-negotiator desk — the web renders pairs
    only. Deep or constrained queries beyond stored inventory belong to the
    finder (§4a), not the board."""
    params = league.params
    presets = sorted(float(p) for p in params.return_presets)
    tbands = return_bands(presets)
    buckets = favor_buckets(params.favor_band_edges)
    nb = len(buckets)
    quota = params.pairs_per_band
    if not league.offseason and league.snapshot.week > params.trade_deadline_week:
        return {
            "disabled": True,
            "pairs": [],
            "presets": presets,
            "favor_presets": [float(c) for c in params.favor_presets],
            "delta_presets": [float(d) for d in params.delta_presets],
            "counts_by_threshold": [
                {"threshold": p, "count": 0, "saturated": False} for p in presets
            ],
            "bands": [
                {
                    "lo": lo,
                    "hi": hi,
                    "stored": 0,
                    "count": 0,
                    "saturated": False,
                    "by_total": [0] * len(tbands),
                }
                for lo, hi in buckets
            ],
            "truncated": None,
            "recommendations": [],
            "watch": [],
            "notes": [f"trade deadline (week {params.trade_deadline_week}) has passed"],
        }

    pool = build_pair_pool(league)
    budget = params.pair_scan_budget
    floor = presets[0] / 100.0  # the lowest preset: nothing below it is stored
    # the crossing key's pair return is the sent-weighted mediant of its legs'
    # ΔF-returns, so no crossing sits above the best leg ΔF-return (v5.1)
    hi_edge = max(
        (leg[L_DFACE] / leg[L_SENT] for leg in pool.legs if leg[L_SENT] > 0),
        default=floor,
    )
    if hi_edge < floor:
        hi_edge = floor
    legal: dict[int, Any] = {}

    # ---- collection (v3.3.1 stratified): fill every band toward its quota ----
    # _tp_estimate / _tp_estimate_below count EXACTLY the crossings the walks
    # visit, so completability is predictable without walking: a walk at r
    # completes iff its crossing count fits the budget.
    #
    # v5.1 runs the collection in TWO PHASES, and the phases are keyed
    # differently on purpose:
    #
    #   A. SOUND (key = ΔF, §4a). One top-down walk at the deepest affordable
    #      cutoff r*. `u_r(leg) = ΔF − r·Σsent` is exactly additive and
    #      `floor = min(ΔS, ΔF) ≤ ΔF`, so the region it walks CONTAINS every
    #      pair whose exact combined floor return is ≥ r*. Complete at
    #      r* ≤ the storage floor ⇒ the whole stored universe was enumerated
    #      and every count below is EXACT. This is the phase that can certify.
    #   B. COVERAGE (key = isolation floor — the v5.0.1 collection verbatim:
    #      top walk, below-walk, per-band range slices, catch-all sweep). The
    #      isolation-floor sum neither bounds the combined floor above nor
    #      below (ΔS is jointly determined by both legs through the lineup), so
    #      phase B certifies NOTHING. It earns its place empirically: ΔF runs
    #      2-5× the floor, so the sound cutoff r* starts far above the storable
    #      band, while the isolation key concentrates on exactly the pairs that
    #      end up stored. Phase B only ADDS inventory; it drops every crossing
    #      phase A already owns (ΔF-return ≥ r*), so tallies stay counts of
    #      DISTINCT pairs and phase A ∪ phase B ⊇ what v5.0.1 collected
    #      (§11.13(d)). Skipped entirely when phase A already certified.
    #
    # Inside phase B the ranges are DISJOINT in its own key units:
    #   1. top-down at the deepest affordable cutoff;
    #   2. bottom-up below-walk at the highest affordable cutoff, but only where
    #      the sub-floor space is small enough to be worth entering (v3.4
    #      retired the per-leg return floor, so that space is no longer empty);
    #   3. per band still touching the surviving gap: the deepest COMPLETE
    #      range walk under the band's hi (out-of-range crossings cost one
    #      multiply and no budget). v5: the STORAGE strata are FAVOR buckets —
    #      a dimension the walks cannot target (a leg's KTC-calculator skew is
    #      uncorrelated with the crossing ordering) — so the total-band slices
    #      serve purely as coverage spreading across the total dimension; every
    #      visited valid pair lands in its favor bucket and grid cell.
    # Output streams into per-bucket bounded heaps (_BucketSink): tallies, the
    # bucket × total-band grid, and the top-quota pairs per bucket by TOTAL
    # return — O(buckets · quota) memory (512MB Lambda).
    collect_budget = max(params.pair_collect_budget, budget)
    sink = _BucketSink(buckets, tbands, quota, pool.legs)
    ALL_R = -1e9  # below every crossing: u_r > 0 for all legs, nothing prunes
    # the sink admits on the DISPLAYED return (2 dp of a percent), so the
    # storable set reaches half a display step below the lowest preset — a
    # certifying walk has to cover that sliver too, or `exact` would be a claim
    # about `floor` while the tallies are about `store_floor`
    store_floor = floor - 5e-5
    exact_all = False
    if _tp_estimate(pool, ALL_R) <= collect_budget:
        _, exact_all = _walk_pairs(league, pool, ALL_R, collect_budget, legal, sink)
    else:
        # ---- phase A: the SOUND top walk (the only certifying pass)
        r_star = _deepest_cut(pool, store_floor, hi_edge, collect_budget)
        # `_deepest_cut` returns `hi_edge` when even that cutoff overflows the
        # budget, and a phase A that TRUNCATES owns no region cleanly: handing
        # its region to phase B drops storable pairs phase A never reached,
        # while NOT handing it back tallies phase A's own pairs twice. So phase
        # A runs only when its crossing count provably fits — `_tp_estimate`
        # upper-bounds the walk's visits exactly (§11.13(e)), so "the estimate
        # fits" IMPLIES "the walk completes" — and is skipped entirely
        # otherwise (it could certify nothing in that state anyway), leaving
        # the space untouched for coverage. If a walk ever truncated anyway,
        # its region is still handed back: an under-count stays an honest
        # floor, a double count would not.
        sound_hi = None
        if _tp_estimate(pool, r_star) <= collect_budget:
            _, top_done = _walk_pairs(league, pool, r_star, collect_budget, legal, sink)
            # phase A owns {ΔF_pair ≥ r*·sent_pair}
            sound_hi = r_star
            # …and if it also reached the storage floor, then by the sound
            # bound every pair with an exact floor return ≥ `store_floor` has
            # ΔF_pair ≥ store_floor·sent_pair, so it was visited: nothing
            # storable was missed and the tallies below are exact counts, not
            # floors.
            exact_all = top_done and r_star <= store_floor
        if not exact_all:
            # ---- phase B: COVERAGE, isolation-floor keyed, phase A's region
            # handed back (sound_hi = r*) so nothing is counted twice
            iso_hi = max((leg[L_RET] for leg in pool.legs), default=floor)
            if iso_hi < floor:
                iso_hi = floor
            iso_star = _deepest_cut(pool, floor, iso_hi, collect_budget, L_FLOOR)
            _walk_pairs(
                league, pool, iso_star, collect_budget, legal,
                _DropSpans(sink, [], pool.legs, sound_hi), L_FLOOR,
            )
            if iso_star > floor + 1e-12:
                # per-band slices of the surviving gap [floor, iso*), descending.
                # Two feasibility-checked entries per slice (skipped crossings
                # cost one multiply, so the scan cap runs wider than the visit
                # budget):
                #   (a) top segment — complete scan from above; the stored pairs
                #       are the band's top within the walk ordering;
                #   (b) below segment — complete scan from beneath; bottom-up
                #       fill as far as the visit budget carries.
                # Every slice is disjoint from phase B's top walk and from each
                # other; the catch-all sweep afterward drops anything a slice
                # touched, so the tallies stay counts of DISTINCT pairs.
                seg_cap = 4 * collect_budget
                blocked: list[tuple[float, float]] = []
                if _tp_estimate_below(pool, floor, L_FLOOR) <= collect_budget:
                    # the sub-floor space is small: the classic bottom-up edge
                    # walk is affordable and its budget is not eaten by
                    # unstorable pairs
                    u_star = _highest_cut_below(
                        pool, floor, iso_star, collect_budget, L_FLOOR
                    )
                    if u_star > floor + 1e-12:
                        _walk_pairs_below(
                            league, pool, u_star, collect_budget, legal,
                            _DropSpans(sink, [], pool.legs, sound_hi), L_FLOOR,
                        )
                        blocked.append((0.0, 100.0 * u_star))
                for lo, hi in reversed(tbands):
                    lo_f = max(lo / 100.0, floor)
                    hi_f = min(hi / 100.0 if hi is not None else iso_hi, iso_star)
                    if hi_f <= lo_f + 1e-12:
                        continue  # the edge walks already own this band's range
                    tp_hi = _tp_estimate(pool, hi_f, L_FLOOR)
                    if tp_hi <= seg_cap:
                        x_b = _deepest_cut(
                            pool, lo_f, hi_f, min(seg_cap, tp_hi + collect_budget),
                            L_FLOOR,
                        )
                        if x_b < hi_f - 1e-12:
                            _walk_pairs_range(
                                league, pool, x_b, hi_f, collect_budget, seg_cap,
                                legal, _DropSpans(sink, blocked, pool.legs, sound_hi),
                                L_FLOOR,
                            )
                            blocked.append((100.0 * x_b, 100.0 * hi_f))
                    elif _tp_estimate_below(pool, lo_f, L_FLOOR) <= seg_cap:
                        y_b = _highest_cut_below(pool, lo_f, hi_f, seg_cap, L_FLOOR)
                        if y_b > lo_f + 1e-12:
                            _walk_pairs_below_range(
                                league, pool, lo_f, y_b, collect_budget, seg_cap,
                                legal, _DropSpans(sink, blocked, pool.legs, sound_hi),
                                L_FLOOR,
                            )
                            blocked.append((100.0 * lo_f, 100.0 * y_b))
                # catch-all: one truncated top-range sweep over the gap for the
                # slices no complete walk could enter — best found within
                # budget, verified floors, never estimates
                _walk_pairs_range(
                    league, pool, floor, iso_star, collect_budget, seg_cap,
                    legal, _DropSpans(sink, blocked, pool.legs, sound_hi), L_FLOOR,
                )

    # per-bucket counts. v5.1: a floor-objective walk that ran to completion
    # over the whole stored universe certifies an EXACT tally (branch 0, or a
    # top walk that reached the storage floor); anything the budget truncated
    # leaves every count a verified floor.
    saturated = not exact_all

    # ---- stored pairs: the deduped union of the three top-quota heaps per
    # favor bucket (§5 v5); the flat list is sorted by the §2 v4 maximin order
    # GLOBALLY — floor-based TOTAL return desc, ceiling desc as tie-break,
    # deterministic ids (the favor dial only filters; the δ dial re-sorts
    # client-side from the stored coordinates) ----
    bucket_top = [sink.bucket_pairs(i) for i in range(nb)]
    # the sort key rounds to the DISPLAYED precision (return 2dp, ceiling 1dp)
    # so the doc's order is exactly the §11.8b(e) maximin order on the numbers
    # the doc shows — raw-float ties inside a display cell fall to the ids
    stored: list[tuple[float, float, int, int]] = sorted(
        (t for top in bucket_top for t in top),
        key=lambda t: (-round(100.0 * t[0], 2), -round(t[1], 1), t[2], t[3]),
    )

    bands_doc = [
        {
            "lo": lo,
            "hi": hi,
            "stored": len(bucket_top[i]),
            "count": sink.counts[i],
            "saturated": saturated,
            # the bucket's counts per robust-return band ([1,2.5), [2.5,5),
            # [5,10), [10,20), [20,∞) — aligned with `presets`): the grid any
            # (floor, favor) inventory line is served from
            "by_total": list(sink.grid[i]),
        }
        for i, (lo, hi) in enumerate(buckets)
    ]

    # per-preset honesty (compat, TOTAL return): the grid columns at or above a
    # threshold tile its ≥-space exactly, summed across every bucket
    counts_by_threshold = []
    ntb = len(tbands)
    for k, p in enumerate(presets):
        n_stored = sum(1 for ret, _, _, _ in stored if round(100.0 * ret, 2) >= p)
        grid_sum = sum(sink.grid[b][j] for b in range(nb) for j in range(k, ntb))
        counts_by_threshold.append(
            {
                "threshold": p,
                "count": max(n_stored, grid_sum),
                "saturated": saturated,
            }
        )

    total = counts_by_threshold[0]["count"]
    total_sat = counts_by_threshold[0]["saturated"]
    truncated = None
    if total_sat or total > len(stored):
        truncated = {
            "stored": len(stored),
            "total": max(total, len(stored)),
            "total_saturated": total_sat,
        }

    # ---- cards ----
    me_t = league.teams[league.me]
    legs = pool.legs
    ceil_cache: dict[tuple[int, tuple], float | None] = {}

    card_cache: dict[int, dict] = {}

    def leg_card(i: int, leg_id: str) -> dict:
        # v5: the union storage can hold up to 3× the v4 pair count and pairs
        # share legs, so the base card is built ONCE per pool leg (legality +
        # ceiling recomputed there) and stamped with the per-pair id here. The
        # copy is shallow — nested structures are never mutated downstream.
        base = card_cache.get(i)
        if base is None:
            leg = legs[i]
            opp_name = pool.opp_names[leg[L_OPP]]
            give, get = leg[L_GIVE], leg[L_GET]
            ck = (leg[L_OPP], give.keys)
            if ck not in ceil_cache:
                vsums, pkgs = pool.opp_pkgs[opp_name]
                ceil_cache[ck] = _ceiling_from(league, give, vsums, pkgs)
            # leg=None: build_card recomputes the full legality verdicts — the
            # walk cache holds booleans only (v3.3.1 memory bound), and only
            # the stored legs ever reach a card
            base = build_card(league, opp_name, give, get, ceiling=ceil_cache[ck])
            base["gate"]["verdict"] = "PASS"
            card_cache[i] = base
        card = dict(base)
        card["id"] = leg_id
        card["exclusive_with"] = []
        return card

    pairs_docs: list[dict] = []
    keysets: list[frozenset] = []
    seen_multiset: set[tuple] = set()
    stored_leg_ids: set[int] = set()
    for ret, _ceil, bi, si in stored:
        mk = (
            legs[bi][L_GIVE].keys, legs[bi][L_GET].keys,
            legs[si][L_GIVE].keys, legs[si][L_GET].keys,
        )
        if mk in seen_multiset:  # structurally impossible; guarded anyway (§5 v3.3)
            continue
        seen_multiset.add(mk)
        n = len(pairs_docs) + 1
        b = leg_card(bi, f"P{n}-buy")
        s = leg_card(si, f"P{n}-sell")
        stored_leg_ids.add(bi)
        stored_leg_ids.add(si)
        fits = int(b["posture"]["fit"]) + int(s["posture"]["fit"])
        if fits == 2:
            fit_summary = "both legs fit posture"
        elif fits == 0:
            fit_summary = "neither leg fits posture"
        else:
            fit_summary = (
                "buy leg fits posture" if b["posture"]["fit"] else "sell leg fits posture"
            )
        at_cap = b["sequencing"].startswith("at the roster cap")
        np_pair, nk_pair = pair_count_deltas(b, s)
        # §5 v4: the pair's coordinates are the EXACT combined ones (both legs
        # applied together — ΔS one combined re-solve, ΔF additive), never
        # assembled from the legs' isolation figures; the embedded cards keep
        # their isolation coords
        combined = combined_coords(
            league,
            [(legs[bi][L_GIVE], legs[bi][L_GET]), (legs[si][L_GIVE], legs[si][L_GET])],
        )
        # §4a/§5 v5: each leg's counterparty favorability (from the gate's own
        # adjusted totals, stored on the pool leg at scan time) and the pair
        # figure min(f_buy, f_sell) — the favor dial's filter key; the bucket
        # this pair was stored under is bucket_index(favor.min)
        fav_b = round(legs[bi][L_FAVOR], 2)
        fav_s = round(legs[si][L_FAVOR], 2)
        pairs_docs.append(
            {
                "id": f"P{n}",
                "buy": b,
                "sell": s,
                # §5 v4 robust floor-based TOTAL return: guaranteed floor ÷
                # Σ face v I send across both legs — the floor dial's robust
                # key and the primary sort key
                "return_pct": round(100.0 * ret, 2),
                "favor": {
                    "buy": fav_b,
                    "sell": fav_s,
                    "min": fav_b if fav_b < fav_s else fav_s,
                },
                # §2 v4 combined coordinates + derived figures. Every stored
                # pair is verdict-true by hard constraint (§11.8b(d)/§11.12(g)).
                # The δ slider re-scores return(δ) from exactly these plus
                # `sent` — every dial move is O(stored).
                "coords": {"dS": combined["dS"], "dF": combined["dF"]},
                "verdict": combined["verdict"],
                "floor": combined["floor"],
                "ceiling": combined["ceiling"],
                "sent": combined["sent"],
                "net_roster": b["net_roster"]["me"] + s["net_roster"]["me"],
                "net_players": np_pair,  # exactly 0 by construction (§5 v3.2)
                "net_picks": nk_pair,  # exactly 0 by construction (§5 v3.2)
                "fit_summary": fit_summary,
                "sequencing": (
                    "at the roster cap: agreement-first — verbal yes on the buy, "
                    "execute the sell, then the buy (Sleeper processes trades instantly)"
                    if at_cap
                    else "roster space available: the buy may execute first — "
                    "agreement-first still applies"
                ),
            }
        )
        keysets.append(frozenset(mk[0]) | frozenset(mk[1]) | frozenset(mk[2]) | frozenset(mk[3]))
    for idx, pd in enumerate(pairs_docs):
        ks = keysets[idx]
        # inventory-overlap tally (leg-level exclusive_with across a 500-pair
        # board would be O(pairs²) id lists — the count is the honest summary)
        pd["overlaps"] = sum(1 for j, k2 in enumerate(keysets) if j != idx and ks & k2)

    # ---- secondary data (web renders pairs only; the desk reads these) ----
    recommendations: list[dict] = []
    seen_rec: set[tuple] = set()
    attempts = 0
    for i in sorted(
        (
            i
            for i, leg in enumerate(legs)
            # v6: sell/neutral == NOT the leg that owns its crossing family —
            # which now correctly routes a (0, +k) leg to `watch` (it needs a
            # complement) instead of here. A (0, 0) leg is neutral and
            # standalone-executable, so it belongs in this list.
            if not canonical_sig((leg[L_NP], leg[L_NK])) and i not in stored_leg_ids
        ),
        key=lambda i: (-legs[i][L_FLOOR], i),
    ):
        if len(recommendations) >= params.top_league_wide or attempts >= 200:
            break
        rk = (legs[i][L_OPP], legs[i][L_GIVE].keys)
        if rk in seen_rec:
            continue
        attempts += 1
        if _leg_legal(league, me_t, pool, i, legal) is False:
            continue
        seen_rec.add(rk)
        card = leg_card(i, f"S{len(recommendations) + 1}")
        card["rank"] = len(recommendations) + 1
        recommendations.append(card)
    rec_keys = [{a["key"] for a in c["give"] + c["get"]} for c in recommendations]
    for x, c in enumerate(recommendations):
        c["exclusive_with"] = [
            recommendations[y]["id"]
            for y in range(len(recommendations))
            if y != x and rec_keys[x] & rec_keys[y]
        ]

    watch: list[dict] = []
    seen_w: set[tuple] = set()
    attempts = 0
    for i in sorted(
        (
            i
            for i, leg in enumerate(legs)
            # v6: an unpaired leg that OWNS its crossing family is the one still
            # looking for an exit — including the (0, +k) family the walks
            # could not reach before.
            if canonical_sig((leg[L_NP], leg[L_NK])) and i not in stored_leg_ids
        ),
        key=lambda i: (-legs[i][L_FLOOR], i),
    ):
        if len(watch) >= params.watch_max or attempts >= 200:
            break
        leg = legs[i]
        wk = (leg[L_OPP], leg[L_GIVE].keys)
        if wk in seen_w:
            continue
        attempts += 1
        if _leg_legal(league, me_t, pool, i, legal) is False:
            continue
        seen_w.add(wk)
        watch.append(
            {
                "counterparty": pool.opp_names[leg[L_OPP]],
                "give": [a.name for a in leg[L_GIVE].assets],
                "get": [a.name for a in leg[L_GET].assets],
                "floor": round(leg[L_FLOOR], 1),
                "blocker": (
                    "no clean exit in the stored pairs — needs a non-conflicting "
                    f"sell netting {-leg[L_NP]:+d} players / {-leg[L_NK]:+d} picks"
                ),
            }
        )

    notes = [
        "v3.3 enumerate-then-filter: the board is the legal PAIR space behind the "
        "finder's three sliders over stored inventory (§4a/§5 v5): a δ SELECTOR "
        "(robust default + presets 0/0.25/0.5/0.75/1 — return(δ) re-scored "
        "instantly from each stored pair's coords and sent, a labeled preference "
        "view, never a score parameter), a FLOOR on total return (robust mode = "
        "guaranteed floor ÷ Σv you send across both legs), and a FLOOR on "
        "counterparty favorability min(f_buy, f_sell); every stored pair nets "
        "exactly 0 players / 0 picks for you, always sorted by robust total "
        "return desc, ceiling as tie-break",
        "counterparty favorability (v5): per leg, favor = the signed skew toward "
        "that counterparty in KTC's own calculator units, from the SAME adjusted "
        "totals as the gate — |favor| ≤ 5 means their calculator literally says "
        "FAIR at default variance, favor > 0 skews to them; it replaces the "
        "v3.4.1 raw-skim leg cap (the raw skim diverges from the calculator's "
        "number by up to 14 pts); the §3 band stays the hard outer bound — "
        "favor selects WITHIN it",
        "the score is two objective coordinates (§2 v4): dS = change in starter "
        "value (max-Σv lineup at raw KTC over active+taxi) and dF = change in "
        "total face owned (players at KTC, picks at ONE price: KTC's exact "
        "numbered slot this year, the flat Mid tranche beyond — the slot is "
        "never estimated, v7.6) — no blend, no parameter. "
        "Every stored pair is objectively good: dS > 0 AND dF > 0, so the gain is "
        "guaranteed between the floor and the ceiling for every rational "
        "stored-value preference. Coordinates are PER SIDE (dF negates exactly; "
        "dS does not): a good pair can be good for both parties. A pair's coordinates "
        "are the two legs applied TOGETHER; each leg card carries its isolation "
        "coords, and a buy leg alone can still be floor-negative",
        f"stratified storage (v5): per FAVOR bucket (min(f_buy, f_sell) over the "
        f"favor bands) the deduped UNION of the top {quota} by robust "
        "floor-return, by dS, and by dF is kept — both δ-slider extremes have "
        "inventory — and `by_total` on each bucket is its count per "
        "robust-return band, so any (floor, favor) inventory read is honest",
        "posture is a hard engine constraint (§5 v3.3): BUYERs only receive "
        "players-majority packages, SELLERs picks-majority, NEUTRAL either; "
        "overrides apply first",
        "the per-leg return FLOOR is retired (v3.4): legs may lose value on their "
        "own and be recouped by their partner — only the PAIR has to clear the "
        "floor dial; the v5 favor FLOOR is the opposite guard, keeping every leg "
        "attractive enough in the counterparty's own calculator, with an "
        "optional ceiling against giving edge away",
        f"per (counterparty, give-package, count-signature) the top "
        f"{params.variants_per_signature} gets by ISOLATION floor are pooled, "
        f"chosen among the first {params.variant_scan_cap} gate-passers in Σv-desc "
        "order — count-signature coverage is complete; deeper sweetener permutations "
        "are not enumerated. That pre-ranking is a disclosed heuristic (§5), not a "
        "dominance rule — the same non-additivity v5.1 fixed in the walks applies to "
        "it — so every EXACT count below is exact over these pooled legs",
        "the fairness gate is KTC's own trade-calculator adjustment, ported exactly "
        "(§3.1) — `adj_give`/`adj_get` on a card are the numbers your league-mate's "
        "calculator shows",
        "counts are EXACT when the collection walk ran to completion and verified "
        "FLOORS when it saturated (`saturated`, v5.1): the walk crosses on "
        "dF - r*(v you send), which is exactly additive across legs and bounds the "
        "guaranteed floor from above, so a completed walk provably enumerated every "
        "storable pair — 'none found' means none exists in the enumerated pool; a "
        "budget-truncated walk still reports only what it verified",
        "band ceilings on cards are negotiating room, not the opener; anchor asks "
        "open +8% (§3)",
        "deep or constrained queries beyond stored inventory belong to the "
        "spread finder (§4a), not the board",
        "book recomputes from fresh rosters after any executed trade",
        "don't publicly fire-sale before making buy-side asks (§5 execution protocol)",
    ]
    if truncated:
        notes.insert(
            1,
            f"storage cap: {truncated['stored']} pairs stored across the favor "
            f"buckets (per-bucket union of tops by robust return, dS, dF), of "
            f"{'at least ' if total_sat else ''}{truncated['total']} found in the "
            "collection walk",
        )

    return {
        "disabled": False,
        "pairs": pairs_docs,
        "presets": presets,
        "favor_presets": [float(c) for c in params.favor_presets],
        "delta_presets": [float(d) for d in params.delta_presets],
        "counts_by_threshold": counts_by_threshold,
        "bands": bands_doc,
        "truncated": truncated,
        "recommendations": recommendations,
        "watch": watch,
        "notes": notes,
    }


