"""§2/§3/§5 trades: the v3.4 WEALTH LEDGER (W = starters + picks), the exact
KTC-calculator fairness gate, enumerate-then-filter pairing behind the user's
target-return RANGE (§3/§5 v3.3; v3.3.1 turned the min-only dial into min/max
over the presets, with stratified per-band pair storage so any range has
inventory), posture as a hard pair-pool constraint, fully count-neutral pairs
(§5 v3.2: a recommended pair nets exactly 0 players AND 0 picks for my side).

v3.4 changed what the score IS (§2):

- `W(side) = S + P` — `S` = Σ RAW KTC v over the max-Σv legal starting lineup
  solved over ACTIVE + TAXI (taxi is promote-anytime, §8; bench, IR and empty
  slots are worth 0), `P` = Σ picks at tranche. `ΔW` is PER SIDE and is not
  zero-sum: `dW.them` is the counterparty's own ledger delta, never `−dW.me`.
  What stays conserved is the face-KTC transfer on every leg (§11.1).
- A pair's ΔW is the COMBINED delta (both legs applied together), not the sum
  of the legs' isolation ΔWs — the legs interact through the lineup. Leg cards
  carry their isolation ΔW, labeled; a buy leg alone is usually negative.
- Only the raw starter-sum solve enters this module from the lineup model
  (§11.2, enforced by an import-graph test): no q insurance weights, no
  availability multipliers, no replacement lines. Roster legality and taxi
  routing (§8) stay in model.apply_tx — legality and sequencing only.
- The fairness gate is the EXACT reverse-engineered KTC trade-calculator
  adjustment (core.scoring.ktc_adjust), not a fitted consolidation curve.

Three engine-bound honesty notes (the raw space is combinatorial — billions of
pair permutations clear the band on real data):

- Per (counterparty, give-package, count-signature) only the top
  `variants_per_signature` gate-clean gets by ISOLATION ledger ΔW are pooled,
  chosen from the first `variant_scan_cap` gate-passers in Σv-descending order.
  With distinct counterparties enforced, a partner leg can never collide with
  the get side, so a higher-ΔW same-signature variant dominates its siblings
  for every pairing — the count-signature diversity the v3.2 matcher starved on
  is preserved in full.
- The pair walks cross legs ordered by ISOLATION ΔW (a disclosed heuristic —
  §5 v3.4), while every pair the walks keep is priced by its EXACT combined
  ΔW. Because the combined ledger is not additive across legs, no walk cutoff
  can certify that the space above it was fully enumerated: every band count is
  therefore a VERIFIED FLOOR (`saturated`), never an exact tally.
- Counters saturate honestly at `pair_scan_budget` / `pair_collect_budget`.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from heapq import heappush, heappushpop
from itertools import combinations
from typing import Any, Sequence

from core.scoring import ktc_adjust as ka
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
    v: float  # face value: player KTC v; pick KTC tranche (§1)
    pos: str | None
    unvalued: bool
    concrete: float | None  # current-year picks: rookie-board slot value (display only)
    player: Any = None  # PlayerV (duck-typed — no lineup import here)
    pick: Any = None  # picks.Pick


def player_asset(p) -> Asset:
    return Asset(
        kind="player", key=p.sid, name=p.name, v=p.v, pos=p.pos,
        unvalued=p.unvalued, concrete=None, player=p,
    )


def pick_asset(league: md.LeagueState, p) -> Asset:
    concrete = p.p if p.year == league.current_year and p.p != p.mv else None
    return Asset(
        kind="pick", key=p.key, name=p.label, v=p.mv, pos=None,
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
    n_players: int
    pos_out: tuple[tuple[str, int], ...]
    has_unvalued: bool
    # §3.1: asset values DESC — exactly what KTC's calculator sorts before it
    # runs processV over a side
    vals: tuple[float, ...]
    # §2 v3.4 ledger inputs: the package's players as raw-value columns in
    # lineup.POS4 order, and the Σ tranche value of its picks
    cols: tuple[tuple[float, ...], ...]
    picks_v: float

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
        n_players=sum(1 for a in assets if a.kind == "player"),
        pos_out=tuple(sorted(pos_out.items())),
        has_unvalued=any(a.unvalued for a in assets),
        vals=tuple(sorted((a.v for a in assets), reverse=True)),
        cols=pos_columns(
            a.player for a in assets if a.kind == "player" and a.player is not None
        ),
        picks_v=sum(a.v for a in assets if a.kind == "pick"),
    )


def _packages(league: md.LeagueState, assets: list[Asset]) -> list[Package]:
    out = []
    for k in range(1, league.params.max_package + 1):
        for combo in combinations(assets, k):
            out.append(package_of(league, combo))
    return out


# ------------------------------------------------------- §2 v3.4 wealth ledger


def starter_pool(t: md.TeamCtx) -> list:
    """The players `S` is solved over: ACTIVE + TAXI (taxi is promote-anytime,
    §8). Bench players are in `act` and simply lose the max-Σv solve; IR players
    are already out of `act` and never enter."""
    return t.act + t.taxi


def team_index(t: md.TeamCtx) -> StarterIndex:
    """Incremental raw starter-sum evaluator for one team's ledger."""
    return StarterIndex(starter_pool(t))


def wealth(t: md.TeamCtx) -> float:
    """§2 `W = S + P` for a team, at raw KTC / tranche values."""
    return starter_sum(starter_pool(t)) + t.picks_mv


def _merge4(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> tuple:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2], a[3] + b[3])


def ledger_delta(
    index: StarterIndex, out_pkgs: Sequence[Package], in_pkgs: Sequence[Package]
) -> tuple[float, float, float]:
    """§2 v3.4 ΔW for ONE side: (ΔS, ΔP, ΔW) when `out_pkgs` leave that roster
    and `in_pkgs` arrive, all applied together. Per-side — never negated for the
    counterparty (§11.1)."""
    out4: tuple = EMPTY4
    in4: tuple = EMPTY4
    d_p = 0.0
    for pkg in out_pkgs:
        out4 = _merge4(out4, pkg.cols)
        d_p -= pkg.picks_v
    for pkg in in_pkgs:
        in4 = _merge4(in4, pkg.cols)
        d_p += pkg.picks_v
    d_s = index.delta(out4, in4)
    return d_s, d_p, d_s + d_p


def combined_ledger(
    league: md.LeagueState, legs: Sequence[tuple[Package, Package]]
) -> dict:
    """§5 v3.4: the EXACT combined ledger for MY side across `legs`
    ([(give, get), …]) applied TOGETHER — the number a pair is stored and
    ranked by. Not the sum of the legs' isolation ΔWs: the legs interact
    through the starting lineup."""
    me_t = league.teams[league.me]
    d_s, d_p, d_w = ledger_delta(
        team_index(me_t), [g for g, _ in legs], [t for _, t in legs]
    )
    sent = sum(g.v_sum for g, _ in legs)
    return {
        "dS": round(d_s, 1),
        "dP": round(d_p, 1),
        "dW": round(d_w, 1),
        "sent": round(sent, 1),
        "return_pct": round(100.0 * d_w / sent, 2) if sent > 0 else None,
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


def gate_info(league: md.LeagueState, give: Package, get: Package) -> dict:
    """§3.1/§3.2: the EXACT KTC-calculator band + anti-fleece cap (never
    exempted). `adj_give`/`adj_get` are the numbers the counterparty's own
    calculator shows; the gap between them is KTC's deserved gap."""
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
    if a.concrete is not None:
        d["concrete"] = round(a.concrete)
        d["note"] = "rookie-board slot value shown for information — ΔW uses the tranche"
    return d


def build_card(
    league: md.LeagueState,
    opp_name: str,
    give: Package,
    get: Package,
    leg: dict | None = None,
    ceiling: float | None = None,
) -> dict:
    """The §5/§10 card for one leg. `dW` carries EACH SIDE'S OWN ledger delta
    (§2 v3.4) — not a zero-sum pair: a good leg can lift both ledgers. What is
    conserved is the face-KTC transfer (§11.1). Leg ΔW is an ISOLATION figure;
    a pair's ΔW is the combined one (§5)."""
    params = league.params
    me_t = league.teams[league.me]
    opp_t = league.teams[opp_name]
    ds_me, dp_me, dw_me = ledger_delta(team_index(me_t), [give], [get])
    ds_them, dp_them, dw_them = ledger_delta(team_index(opp_t), [get], [give])
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
    leg_type = "buy" if np_me > 0 else "sell" if np_me < 0 else "neutral"
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
        # §2 v3.4: per-side OWN-ledger deltas (never negations of each other)
        "dW": {"me": round(dw_me, 1), "them": round(dw_them, 1)},
        "dW_parts": {
            "me": {"dS": round(ds_me, 1), "dP": round(dp_me, 1)},
            "them": {"dS": round(ds_them, 1), "dP": round(dp_them, 1)},
        },
        "dW_basis": "isolation",  # this leg alone; pairs carry the combined ΔW
        # §5 leg return on inventory deployed: isolation ΔW(me) ÷ Σv sent, percent
        "return_pct": round(100 * dw_me / give.v_sum, 2) if give.v_sum > 0 else None,
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
            "unvalued assets contribute 0 to ΔW and never enter a starting "
            "lineup — verify by hand (§11.7)"
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
    if 0 < card["dW"]["me"] < league.params.w_min:
        card.setdefault("notes", []).append(
            f"ΔW +{card['dW']['me']:g} sits inside KTC's ±{league.params.w_min:g} noise "
            "band — display note only; W_min is not a gate (v3.3)"
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
    back from a stored board doc to the ledger arithmetic (CLI + tests)."""
    by_key: dict[str, Asset] = {}
    for t in league.teams.values():
        for a in team_assets(league, t).values():
            by_key[a.key] = a
    return (
        package_of(league, [by_key[a["key"]] for a in card["give"]]),
        package_of(league, [by_key[a["key"]] for a in card["get"]]),
    )


def pair_ledger(league: md.LeagueState, buy_card: dict, sell_card: dict) -> dict:
    """§5 v3.4 pair metrics recomputed from two leg cards: the EXACT combined
    ledger ΔW (both legs applied together) and the return on Σ face v I send
    across both legs. NOT the sum of the leg ΔWs."""
    legs = [card_packages(league, buy_card), card_packages(league, sell_card)]
    return combined_ledger(league, legs)


# ------------------------------------------- the pair pool + the board (§5 v3.3)


_POS4 = ("QB", "RB", "WR", "TE")
_MIN4 = tuple(MIN_POS[p] for p in _POS4)

# leg tuple layout inside PairPool.legs (indices 0-8 are the v3.3 contract and
# stay put; v3.4 appends the ledger inputs the pair walk needs)
L_RET, L_DW, L_SENT, L_NP, L_NK, L_OPP, L_MASK, L_GIVE, L_GET = range(9)
L_OUT4, L_IN4, L_DP = 9, 10, 11


@dataclass(slots=True)
class PairPool:
    """§5 v3.4 candidate-leg pool: for EVERY (counterparty, give-package,
    count-signature) combination, the top `variants_per_signature` gate-clean,
    fleece-clean, cheap-legality-clean gets by ISOLATION ledger ΔW, each
    posture-clean when `enforce_posture` (the pair-pool default; the CLI hedge
    finder disables it because the desk treats posture qualitatively).

    `index` is MY incremental starter-sum evaluator: the pair walk prices every
    kept crossing with the EXACT combined ledger through it (§11.10)."""

    opp_names: list[str]
    legs: list[tuple]  # see the L_* layout above
    buckets: dict[tuple[int, int], list[int]]  # (np, nk) signature -> leg indices
    opp_pkgs: dict[str, tuple[list[float], list[Package]]]  # Σv-sorted; ceilings
    enforce_posture: bool
    index: StarterIndex

    def pair_ledger_dw(self, buy_i: int, sell_i: int) -> float:
        """EXACT combined ledger ΔW(me) for two legs applied TOGETHER (§5 v3.4)
        — never the sum of their isolation ΔWs."""
        b, s = self.legs[buy_i], self.legs[sell_i]
        bo, so = b[L_OUT4], s[L_OUT4]
        bi_, si_ = b[L_IN4], s[L_IN4]
        return (
            self.index.delta(
                (bo[0] + so[0], bo[1] + so[1], bo[2] + so[2], bo[3] + so[3]),
                (bi_[0] + si_[0], bi_[1] + si_[1], bi_[2] + si_[2], bi_[3] + si_[3]),
            )
            + b[L_DP]
            + s[L_DP]
        )

    def pair_return(self, buy_i: int, sell_i: int) -> float:
        """The stored pair's return FRACTION: exact combined ΔW(me) ÷ Σ face v
        I send across both legs (§5 v3.4 — denominator stays face KTC)."""
        b, s = self.legs[buy_i], self.legs[sell_i]
        return self.pair_ledger_dw(buy_i, sell_i) / (b[L_SENT] + s[L_SENT])


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


def build_pair_pool(league: md.LeagueState, enforce_posture: bool = True) -> PairPool:
    """§5 v3.3 enumeration — no minimal-gap pruning, no W_min gate. Per opponent,
    per give-package, per get count-signature: walk the Σv window
    [gv ÷ fleece_ratio, gv · fleece_ratio] descending — the whole fleece bracket
    now, because with the return floor retired (v3.4) a leg that ships MORE face
    value than it receives can still lift the ledger.

    Per (give, count-signature) the scan keeps the top `variants_per_signature`
    by ISOLATION ledger ΔW among the first `variant_scan_cap` candidates that
    clear the exact §3.1 gate and cheap positional legality on both sides. Two
    disclosed bounds (v3.4): the exact gate is ~30× the cost of the retired
    adjv comparison and the ledger ΔW needs a starter-sum re-solve, so the scan
    (a) short-circuits on a cheap NECESSARY condition derived from the
    calculator's own arithmetic — a gate-passer's adjusted gap S obeys
    S ≤ max(500, 0.25·max side total), and S is monotone in the raw-adjustment
    gap, so a raw gap above processV of that bound can never clear the band —
    and (b) stops after `variant_scan_cap` passers rather than draining the
    bracket."""
    params = league.params
    me_t = league.teams[league.me]
    my_pkgs = _packages(league, give_list(league, me_t))
    my_counts = _team_pos_vec(me_t)
    my_act = len(me_t.act)
    my_index = team_index(me_t)
    # partner-leg collisions can only involve MY give assets (distinct
    # counterparties own disjoint pools) — bitmask exactly those
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
    g_info = []
    for g in my_pkgs:
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
        g_info.append((g, gp, offer_shape(g), deficit, mask))
    legs: list[tuple] = []
    buckets: dict[tuple[int, int], list[int]] = {}
    opp_pkgs: dict[str, tuple[list[float], list[Package]]] = {}
    for oi, opp_name in enumerate(league.opponents):
        opp_t = league.teams[opp_name]
        label = league.postures.get(opp_name, {}).get("label", ps.NEUTRAL)
        vsums_all, pkgs_all = _sorted_opp_pkgs(league, opp_name)
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
            c[4].append(ka.side_raw_adj(p.vals, p.vals[0], cap, presorted=True))
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
                        a_tot = _raw_adj_total(t_vals, r_max, cap)
                    pre1 = e_cache.get(r_max)
                    if pre1 is None:
                        pre1 = e_cache[r_max] = ka.side_raw_adj(
                            g_vals, r_max, cap, presorted=True
                        )
                    raw_gap = pre1[0] - a_tot
                    if raw_gap < 0.0:
                        raw_gap = -raw_gap
                    max_tot = gv if gv > t_v else t_v
                    b_star = 0.25 * max_tot
                    if b_star < 500.0:
                        b_star = 500.0
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
                    if raw_gap > 1.15 * _process_v0(b_star, r_max, cap):
                        continue
                    if pre2 is None:
                        pre2 = ka.side_raw_adj(t_vals, r_max, cap, presorted=True)
                    t = lst[i]
                    adj_g, adj_t = ka.adjusted_totals(
                        g_vals, t_vals, top_v, pre1=pre1, pre2=pre2, presorted=True
                    )
                    if not _band_ok(params, adj_g, adj_t):
                        continue
                    d_s = my_index.delta(g.cols, t.cols)
                    d_p = t.picks_v - g.picks_v
                    dw = d_s + d_p
                    best.append((-dw, t.keys, t, d_p))
                    passers += 1
                    if passers >= scan_cap:
                        break
                if not best:
                    continue
                best.sort()  # isolation ΔW desc, deterministic ties on the keys
                for _neg_dw, _k, t, d_p in best[:K]:
                    dw = -_neg_dw
                    buckets.setdefault((np_, nk), []).append(len(legs))
                    legs.append(
                        (dw / gv, dw, gv, np_, nk, oi, mask, g, t, g.cols, t.cols, d_p)
                    )
    return PairPool(
        opp_names=list(league.opponents),
        legs=legs,
        buckets=buckets,
        opp_pkgs=opp_pkgs,
        enforce_posture=enforce_posture,
        index=my_index,
    )


def _tp_estimate(pool: PairPool, r: float) -> int:
    """Uncorrected two-pointer size of the ≥r pair space in the walk's ORDERING
    HEURISTIC (§5 v3.4): σ_r(leg) = isolation ΔW − r·Σv sent, and
    σ_r(buy) + σ_r(sell) ≥ 0 ⟺ the ISOLATION-SUM pair return ≥ r. Exactly the
    crossing count `_walk_pairs` visits at r — no counterparty / overlap /
    legality corrections; used to place collection cutoffs and to detect sparse
    markets. Every visited pair is then priced by its EXACT combined ledger, so
    this is a walk-sizing device, never a claim about the exact space."""
    legs = pool.legs
    total = 0
    for sig, idxs in pool.buckets.items():
        if sig[0] <= 0:
            continue
        comp = pool.buckets.get((-sig[0], -sig[1]))
        if not comp:
            continue
        bs = sorted(legs[i][L_DW] - r * legs[i][L_SENT] for i in idxs)
        ss = sorted(legs[i][L_DW] - r * legs[i][L_SENT] for i in comp)
        n = len(ss)
        for sb in reversed(bs):
            lo = bisect_left(ss, -sb)
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


def _tp_estimate_below(pool: PairPool, r: float) -> int:
    """Mirror of _tp_estimate for the LOW end: uncorrected two-pointer size of
    the < r heuristic pair space (τ_r(leg) = isolation ΔW − r·Σv sent;
    τ_r(buy) + τ_r(sell) < 0 ⟺ the isolation-sum pair return < r). Exact on
    crossings — the visit count of a below-walk at r. v3.4 retired the per-leg
    return floor, so this space is NOT bounded below by the dial floor: buy legs
    are legitimately negative alone and the below-walk can be as deep as the
    top one."""
    legs = pool.legs
    total = 0
    for sig, idxs in pool.buckets.items():
        if sig[0] <= 0:
            continue
        comp = pool.buckets.get((-sig[0], -sig[1]))
        if not comp:
            continue
        bs = sorted(legs[i][L_DW] - r * legs[i][L_SENT] for i in idxs)
        ss = sorted(legs[i][L_DW] - r * legs[i][L_SENT] for i in comp)
        for tb in bs:  # ascending τ: the count of complements only shrinks
            lo = bisect_left(ss, -tb)  # sells with τ_s < −τ_b, strictly
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
    out: list[tuple[float, int, int]],
) -> tuple[int, bool]:
    """Enumerate the VALID pair space at return < r — the exact complement of
    _walk_pairs at r (boundary pairs at exactly r belong to the ≥ walk).
    Identical constraints and honesty contract; τ_r-ASCENDING crossing with
    early exit, so the low end of the return space is reachable without
    sweeping the (much deeper) top. Deterministic throughout."""
    legs = pool.legs
    me_t = league.teams[league.me]
    visits = 0
    for sig in sorted(pool.buckets):
        if sig[0] <= 0:
            continue
        comp_idx = pool.buckets.get((-sig[0], -sig[1]))
        if not comp_idx:
            continue
        # (τ_r, pool index): ascending sort == lowest pair returns first
        bs = sorted((legs[i][L_DW] - r * legs[i][L_SENT], i) for i in pool.buckets[sig])
        ss = sorted((legs[i][L_DW] - r * legs[i][L_SENT], i) for i in comp_idx)
        ss0 = ss[0][0]
        for tb, bi in bs:
            if tb + ss0 >= 0.0:
                break  # even the lowest sell keeps this (and any later) buy at ≥ r
            b = legs[bi]
            b_opp, b_mask, b_dw, b_sent = b[L_OPP], b[L_MASK], b[L_DW], b[L_SENT]
            vb = None
            for ts, si in ss:
                if tb + ts >= 0.0:
                    break
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
                # (exact combined return, heuristic crossing return, buy, sell):
                # the sink bands on the EXACT one; the walks' disjointness is
                # defined by the heuristic one (§5 v3.4)
                out.append(
                    (
                        pool.pair_return(bi, si),
                        (b_dw + s[L_DW]) / (b_sent + s[L_SENT]),
                        bi,
                        si,
                    )
                )
    return visits, True


def _walk_pairs(
    league: md.LeagueState,
    pool: PairPool,
    r: float,
    budget: int,
    legal: dict,
    out: list[tuple[float, int, int]],
) -> tuple[int, bool]:
    """Enumerate the VALID pair space at return ≥ r: complementary
    count-signature buckets crossed in σ_r-descending order with early exit;
    constraints per §5 v3.3 — distinct counterparties, disjoint assets (my-give
    masks; get-sides cannot collide across distinct counterparties), both legs
    full-legality PASS (memoized in `legal`). Appends (return, buy_i, sell_i)
    to `out`. Returns (pairs_visited, completed) — completed=False means the
    visit budget truncated the walk and `out` is a verified floor, not the
    whole space. Deterministic throughout."""
    legs = pool.legs
    me_t = league.teams[league.me]
    visits = 0
    for sig in sorted(pool.buckets):
        if sig[0] <= 0:
            continue
        comp_idx = pool.buckets.get((-sig[0], -sig[1]))
        if not comp_idx:
            continue
        # (−σ_r, pool index): ascending sort == σ_r-descending walk, deterministic
        bs = sorted((r * legs[i][L_SENT] - legs[i][L_DW], i) for i in pool.buckets[sig])
        ss = sorted((r * legs[i][L_SENT] - legs[i][L_DW], i) for i in comp_idx)
        ns0 = ss[0][0]
        for nb, bi in bs:
            if nb + ns0 > 0.0:
                break  # even the best sell can't lift this (or any later) buy to r
            b = legs[bi]
            b_opp, b_mask, b_dw, b_sent = b[L_OPP], b[L_MASK], b[L_DW], b[L_SENT]
            vb = None
            for ns, si in ss:
                if nb + ns > 0.0:
                    break
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
                # (exact combined return, heuristic crossing return, buy, sell):
                # the sink bands on the EXACT one; the walks' disjointness is
                # defined by the heuristic one (§5 v3.4)
                out.append(
                    (
                        pool.pair_return(bi, si),
                        (b_dw + s[L_DW]) / (b_sent + s[L_SENT]),
                        bi,
                        si,
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
) -> tuple[int, bool]:
    """Enumerate the VALID pair space with lo_r ≤ return < hi_r — the gap left
    between a complete top-down walk (≥ hi_r) and a complete below-walk
    (< lo_r). The ≥ lo_r crossings are scanned top-down, but pairs the top walk
    already owns (return ≥ hi_r) are skipped with one multiply and do NOT
    consume the visit budget — only in-range pairs do; `scan_cap` bounds the
    raw scanning time. Same constraints and honesty contract as _walk_pairs;
    deterministic throughout."""
    legs = pool.legs
    me_t = league.teams[league.me]
    visits = 0
    scanned = 0
    for sig in sorted(pool.buckets):
        if sig[0] <= 0:
            continue
        comp_idx = pool.buckets.get((-sig[0], -sig[1]))
        if not comp_idx:
            continue
        bs = sorted((lo_r * legs[i][L_SENT] - legs[i][L_DW], i) for i in pool.buckets[sig])
        ss = sorted((lo_r * legs[i][L_SENT] - legs[i][L_DW], i) for i in comp_idx)
        ns0 = ss[0][0]
        for nb, bi in bs:
            if nb + ns0 > 0.0:
                break
            b = legs[bi]
            b_opp, b_mask, b_dw, b_sent = b[L_OPP], b[L_MASK], b[L_DW], b[L_SENT]
            vb = None
            for ns, si in ss:
                if nb + ns > 0.0:
                    break
                scanned += 1
                if scanned > scan_cap:
                    return visits, False
                s = legs[si]
                if b_dw + s[L_DW] >= hi_r * (b_sent + s[L_SENT]):
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
                # (exact combined return, heuristic crossing return, buy, sell):
                # the sink bands on the EXACT one; the walks' disjointness is
                # defined by the heuristic one (§5 v3.4)
                out.append(
                    (
                        pool.pair_return(bi, si),
                        (b_dw + s[L_DW]) / (b_sent + s[L_SENT]),
                        bi,
                        si,
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
) -> tuple[int, bool]:
    """Enumerate the VALID pair space with lo_r ≤ return < hi_r from BENEATH:
    τ_{hi_r}-ascending crossing (lowest returns first), pairs the below-walk
    already owns (return < lo_r) skipped with one multiply and no budget. When
    the visit budget truncates, the collected set is the RANGE'S BOTTOM — a
    verified, deterministic partial fill for bands unreachable from the top."""
    legs = pool.legs
    me_t = league.teams[league.me]
    visits = 0
    scanned = 0
    for sig in sorted(pool.buckets):
        if sig[0] <= 0:
            continue
        comp_idx = pool.buckets.get((-sig[0], -sig[1]))
        if not comp_idx:
            continue
        bs = sorted((legs[i][L_DW] - hi_r * legs[i][L_SENT], i) for i in pool.buckets[sig])
        ss = sorted((legs[i][L_DW] - hi_r * legs[i][L_SENT], i) for i in comp_idx)
        ss0 = ss[0][0]
        for tb, bi in bs:
            if tb + ss0 >= 0.0:
                break
            b = legs[bi]
            b_opp, b_mask, b_dw, b_sent = b[L_OPP], b[L_MASK], b[L_DW], b[L_SENT]
            vb = None
            for ts, si in ss:
                if tb + ts >= 0.0:
                    break
                scanned += 1
                if scanned > scan_cap:
                    return visits, False
                s = legs[si]
                if b_dw + s[L_DW] < lo_r * (b_sent + s[L_SENT]):
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
                # (exact combined return, heuristic crossing return, buy, sell):
                # the sink bands on the EXACT one; the walks' disjointness is
                # defined by the heuristic one (§5 v3.4)
                out.append(
                    (
                        pool.pair_return(bi, si),
                        (b_dw + s[L_DW]) / (b_sent + s[L_SENT]),
                        bi,
                        si,
                    )
                )
    return visits, True


class _DropSpans:
    """append() adapter that drops pairs whose return falls in any span
    (percent, half-open) — keeps the catch-all sweep disjoint from every walk
    that came before it, so sink tallies stay exact counts of DISTINCT pairs."""

    __slots__ = ("sink", "spans")

    def __init__(self, sink, spans: list[tuple[float, float]]):
        self.sink = sink
        self.spans = spans

    def append(self, t: tuple[float, float, int, int]) -> None:
        pct = 100.0 * t[1]  # the HEURISTIC return — what the walks partition on
        for a, b in self.spans:
            if a <= pct < b:
                return
        self.sink.append(t)


def _deepest_cut(pool: PairPool, floor: float, hi: float, budget: int) -> float:
    """Lowest return cutoff in [floor, hi] whose crossing count fits the walk
    budget. _tp_estimate counts EXACTLY the crossings _walk_pairs visits (it
    upper-bounds only the VALID pairs), so a walk at the returned cutoff is
    guaranteed to complete — except when even `hi` does not fit (then `hi` is
    returned and the walk truncates, disclosed honestly downstream)."""
    if _tp_estimate(pool, floor) <= budget:
        return floor
    if _tp_estimate(pool, hi) > budget:
        return hi
    lo_r, hi_r = floor, hi
    for _ in range(18):
        mid = (lo_r + hi_r) / 2.0
        if _tp_estimate(pool, mid) > budget:
            lo_r = mid
        else:
            hi_r = mid
    return hi_r


def _highest_cut_below(pool: PairPool, floor: float, hi: float, budget: int) -> float:
    """Highest return cutoff in [floor, hi] whose BELOW-crossing count fits the
    walk budget — how far up from the floor a complete below-walk can reach.
    v3.4: with the per-leg return floor retired the below-space at `floor` is
    no longer empty, so this can legitimately return `floor` itself (the
    below-walk then contributes nothing and the range slices carry the band)."""
    if _tp_estimate_below(pool, hi) <= budget:
        return hi
    lo_r, hi_r = floor, hi
    for _ in range(18):
        mid = (lo_r + hi_r) / 2.0
        if _tp_estimate_below(pool, mid) <= budget:
            lo_r = mid
        else:
            hi_r = mid
    return lo_r


def return_bands(presets: Sequence[float]) -> list[tuple[float, float | None]]:
    """§5 v3.3.1 return bands, percent, derived from the range presets:
    [p0, p1), [p1, p2), …, [p_last, ∞) — ascending, hi=None on the open top."""
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


class _BandSink:
    """append()-compatible walk output that stratifies on the fly: per band a
    bounded min-heap of the top-`quota` pairs (by EXACT combined return desc,
    deterministic ties) plus an exact tally of every valid pair seen. The
    collection walks cover DISJOINT HEURISTIC return ranges (top ≥ r*, below
    < u*, range [u*, r*)), so no pair is ever offered twice and no dedupe
    structure is needed — and memory stays O(bands · quota) where full lists of
    the walked space would blow the collector Lambda's 512MB."""

    __slots__ = ("bands", "quota", "heaps", "counts")

    def __init__(self, bands: Sequence[tuple[float, float | None]], quota: int):
        self.bands = bands
        self.quota = quota
        # heap entries (ret, -bi, -si): lexicographic order on the negated-index
        # tuple exactly inverts the storage sort key (-ret, bi, si), so the
        # min-heap root is always the worst kept pair
        self.heaps: list[list[tuple[float, int, int]]] = [[] for _ in bands]
        self.counts: list[int] = [0] * len(bands)

    def append(self, t: tuple[float, float, int, int]) -> None:
        ret, _heur, bi, si = t
        i = band_index(self.bands, round(100.0 * ret, 2))
        if i is None:
            return  # below the lowest preset: never stored, never counted
        self.counts[i] += 1
        h = self.heaps[i]
        e = (ret, -bi, -si)
        if len(h) < self.quota:
            heappush(h, e)
        elif e > h[0]:
            heappushpop(h, e)

    def band_pairs(self, i: int) -> list[tuple[float, int, int]]:
        """Stored pairs of band i, return-desc with deterministic ties."""
        return [(e[0], -e[1], -e[2]) for e in sorted(self.heaps[i], reverse=True)]


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
    if b[L_NP] <= 0 or s[L_NP] >= 0:
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
    """§5 v3.3.1: the exhaustively-crossed, range-filtered PAIR board with
    STRATIFIED storage. `pairs` holds the top-`pairs_per_band` by return WITHIN
    each return band (bands derived from the presets: [1,2.5), [2.5,5), [5,10),
    [10,20), [20,∞) percent), bands concatenated return-descending — so any
    user range [min, max) over the presets has inventory, and the whole list
    still reads return-desc globally. Every stored pair is fully count-neutral,
    both legs gate-PASS, posture-clean, distinct counterparties, no shared
    assets. `bands` carries per-band honest disclosure ({lo, hi|None, stored,
    count, saturated} — a saturated count is a verified floor, never an
    estimate); `counts_by_threshold` and `truncated` stay for ≥-style compat
    reads. Pairs below the lowest preset are never stored (with the default
    config the return floor IS the lowest preset). `recommendations` (top
    unpaired sell/neutral legs by ΔW) and `watch` (unpaired buys) stay as data
    for the trade-negotiator desk — the web renders pairs only."""
    params = league.params
    presets = sorted(float(p) for p in params.return_presets)
    bands = return_bands(presets)
    nb = len(bands)
    quota = params.pairs_per_band
    if not league.offseason and league.snapshot.week > params.trade_deadline_week:
        return {
            "disabled": True,
            "pairs": [],
            "presets": presets,
            "counts_by_threshold": [
                {"threshold": p, "count": 0, "saturated": False} for p in presets
            ],
            "bands": [
                {"lo": lo, "hi": hi, "stored": 0, "count": 0, "saturated": False}
                for lo, hi in bands
            ],
            "truncated": None,
            "recommendations": [],
            "watch": [],
            "notes": [f"trade deadline (week {params.trade_deadline_week}) has passed"],
        }

    pool = build_pair_pool(league)
    budget = params.pair_scan_budget
    floor = presets[0] / 100.0  # the lowest preset: nothing below it is stored
    # the heuristic pair return is the sent-weighted mediant of its legs'
    # isolation returns, so no crossing sits above the best leg return
    hi_edge = max((leg[L_RET] for leg in pool.legs), default=floor)
    if hi_edge < floor:
        hi_edge = floor
    legal: dict[int, Any] = {}

    # ---- collection (v3.3.1 stratified): fill every band toward its quota ----
    # _tp_estimate / _tp_estimate_below count EXACTLY the crossings the walks
    # visit, so completability is predictable without walking: a walk at r
    # completes iff its crossing count fits the budget. The saturating-budget
    # approach, extended per band, over DISJOINT HEURISTIC return ranges:
    #   0. if the WHOLE crossing space fits the budget, walk it outright — the
    #      only branch that can certify exact band counts (v3.4);
    #   1. top-down at the deepest affordable cutoff r*;
    #   2. bottom-up below-walk at the highest affordable u*, but only where the
    #      sub-floor space is small enough to be worth entering (v3.4 retired the
    #      per-leg return floor, so that space is no longer empty);
    #   3. per band still touching the gap [floor, r*): the deepest COMPLETE
    #      range walk under the band's hi (out-of-range crossings cost one
    #      multiply and no budget) — the stored pairs become the band's TRUE top
    #      within the heuristic ordering.
    # Output streams into per-band bounded heaps (_BandSink): tallies plus the
    # top-quota pairs per band, O(bands · quota) memory (512MB Lambda).
    #
    # HONESTY (v3.4): the walks are ordered by the legs' ISOLATION ΔWs while
    # every pair is priced by its EXACT combined ledger. The two orderings do
    # not agree (lineup interactions), so outside branch 0 no cutoff can prove
    # a band was fully enumerated — every band count is a VERIFIED FLOOR.
    collect_budget = max(params.pair_collect_budget, budget)
    sink = _BandSink(bands, quota)
    ALL_R = -1e9  # below every crossing: σ_r > 0 for all legs, nothing prunes
    exact_all = False
    if _tp_estimate(pool, ALL_R) <= collect_budget:
        _, exact_all = _walk_pairs(league, pool, ALL_R, collect_budget, legal, sink)
    else:
        r_star = _deepest_cut(pool, floor, hi_edge, collect_budget)
        _walk_pairs(league, pool, r_star, collect_budget, legal, sink)
        if r_star > floor + 1e-12:
            # per-band slices of the surviving gap [floor, r*), descending. Two
            # feasibility-checked entries per slice (skipped crossings cost one
            # multiply, so the scan cap runs wider than the visit budget):
            #   (a) top segment — complete scan from above; the stored pairs
            #       are the band's top within the walk ordering;
            #   (b) below segment — complete scan from beneath; bottom-up fill
            #       as far as the visit budget carries.
            # Every slice is disjoint from the top walk and from each other; the
            # catch-all sweep afterward drops anything a slice touched, so the
            # tallies stay counts of DISTINCT pairs.
            seg_cap = 4 * collect_budget
            blocked: list[tuple[float, float]] = []
            if _tp_estimate_below(pool, floor) <= collect_budget:
                # the sub-floor space is small: the classic bottom-up edge walk
                # is affordable and its budget is not eaten by unstorable pairs
                u_star = _highest_cut_below(pool, floor, r_star, collect_budget)
                if u_star > floor + 1e-12:
                    _walk_pairs_below(league, pool, u_star, collect_budget, legal, sink)
                    blocked.append((0.0, 100.0 * u_star))
            for lo, hi in reversed(bands):
                lo_f = max(lo / 100.0, floor)
                hi_f = min(hi / 100.0 if hi is not None else hi_edge, r_star)
                if hi_f <= lo_f + 1e-12:
                    continue  # the edge walks already own this band's range
                tp_hi = _tp_estimate(pool, hi_f)
                if tp_hi <= seg_cap:
                    x_b = _deepest_cut(
                        pool, lo_f, hi_f, min(seg_cap, tp_hi + collect_budget)
                    )
                    if x_b < hi_f - 1e-12:
                        _walk_pairs_range(
                            league, pool, x_b, hi_f, collect_budget, seg_cap,
                            legal, _DropSpans(sink, blocked),
                        )
                        blocked.append((100.0 * x_b, 100.0 * hi_f))
                elif _tp_estimate_below(pool, lo_f) <= seg_cap:
                    y_b = _highest_cut_below(pool, lo_f, hi_f, seg_cap)
                    if y_b > lo_f + 1e-12:
                        _walk_pairs_below_range(
                            league, pool, lo_f, y_b, collect_budget, seg_cap,
                            legal, _DropSpans(sink, blocked),
                        )
                        blocked.append((100.0 * lo_f, 100.0 * y_b))
            # catch-all: one truncated top-range sweep over the gap for the
            # slices no complete walk could enter — best found within budget,
            # verified floors, never estimates
            _walk_pairs_range(
                league, pool, floor, r_star, collect_budget, seg_cap,
                legal, _DropSpans(sink, blocked),
            )

    # per-band counts. Only the whole-space walk (branch 0) certifies an exact
    # tally; every other branch leaves each band a verified floor (v3.4).
    band_counts = [(sink.counts[i], not exact_all) for i in range(nb)]

    # ---- stored pairs: top-quota per band, return-desc within band, bands
    # concatenated desc (bands partition the range, so the whole list is also
    # globally return-desc) ----
    band_top = [sink.band_pairs(i) for i in range(nb)]
    stored: list[tuple[float, int, int]] = []
    for i in range(nb - 1, -1, -1):
        stored.extend(band_top[i])

    bands_doc = [
        {
            "lo": lo,
            "hi": hi,
            "stored": len(band_top[i]),
            "count": band_counts[i][0],
            "saturated": band_counts[i][1],
        }
        for i, (lo, hi) in enumerate(bands)
    ]

    # per-preset honesty (compat): presets coincide with band los, so the bands
    # at or above a threshold tile its ≥-space exactly
    counts_by_threshold = []
    for k, p in enumerate(presets):
        n_stored = sum(1 for ret, _, _ in stored if round(100.0 * ret, 2) >= p)
        band_sum = sum(band_counts[j][0] for j in range(k, nb))
        counts_by_threshold.append(
            {
                "threshold": p,
                "count": max(n_stored, band_sum),
                "saturated": any(band_counts[j][1] for j in range(k, nb)),
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

    def leg_card(i: int, leg_id: str) -> dict:
        leg = legs[i]
        opp_name = pool.opp_names[leg[L_OPP]]
        give, get = leg[L_GIVE], leg[L_GET]
        ck = (leg[L_OPP], give.keys)
        if ck not in ceil_cache:
            vsums, pkgs = pool.opp_pkgs[opp_name]
            ceil_cache[ck] = _ceiling_from(league, give, vsums, pkgs)
        # leg=None: build_card recomputes the full legality verdicts — the walk
        # cache holds booleans only (v3.3.1 memory bound), and only the stored
        # legs ever reach a card
        card = build_card(
            league, opp_name, give, get, ceiling=ceil_cache[ck]
        )
        card["gate"]["verdict"] = "PASS"
        card["id"] = leg_id
        card["exclusive_with"] = []
        return card

    pairs_docs: list[dict] = []
    keysets: list[frozenset] = []
    seen_multiset: set[tuple] = set()
    stored_leg_ids: set[int] = set()
    for ret, bi, si in stored:
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
        # §5 v3.4: the pair ledger is the EXACT combined delta (both legs applied
        # together), never the sum of the legs' isolation ΔWs
        combined = combined_ledger(
            league,
            [(legs[bi][L_GIVE], legs[bi][L_GET]), (legs[si][L_GIVE], legs[si][L_GET])],
        )
        pairs_docs.append(
            {
                "id": f"P{n}",
                "buy": b,
                "sell": s,
                "return_pct": round(100.0 * ret, 2),
                "dW_combined": combined["dW"],
                "dW_combined_parts": {"dS": combined["dS"], "dP": combined["dP"]},
                "dW_legs_isolated": round(b["dW"]["me"] + s["dW"]["me"], 1),
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
        (i for i, leg in enumerate(legs) if leg[L_NP] <= 0 and i not in stored_leg_ids),
        key=lambda i: (-legs[i][L_DW], i),
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
        (i for i, leg in enumerate(legs) if leg[L_NP] > 0 and i not in stored_leg_ids),
        key=lambda i: (-legs[i][L_DW], i),
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
                "dW": round(leg[L_DW], 1),
                "blocker": (
                    "no clean exit in the stored pairs — needs a non-conflicting "
                    f"sell netting {-leg[L_NP]:+d} players / {-leg[L_NK]:+d} picks"
                ),
            }
        )

    notes = [
        "v3.3 enumerate-then-filter: the board is the legal PAIR space behind your "
        "target-return range (v3.3.1: min/max over the presets) — every stored pair "
        "nets exactly 0 players / 0 picks for you, ranked by return on inventory "
        "deployed (combined ΔW ÷ Σv you send)",
        "ΔW is the v3.4 wealth ledger (starters at raw KTC over active+taxi, plus "
        "picks at tranche) and is PER SIDE — a good pair can lift both ledgers. A "
        "pair's ΔW is the two legs applied TOGETHER; each leg card also shows its "
        "isolation ΔW, and a buy leg alone is normally negative",
        f"stratified storage (v3.3.1): up to {quota} pairs kept per return band "
        "(bands derived from the presets), return-desc within band — bands marked "
        "saturated carry verified-floor counts; their space runs deeper than the "
        "collection budget",
        "posture is a hard engine constraint (§5 v3.3): BUYERs only receive "
        "players-majority packages, SELLERs picks-majority, NEUTRAL either; "
        "overrides apply first",
        "the per-leg return floor is retired (v3.4): legs may lose value on their "
        "own and be recouped by their partner — only the PAIR has to clear the dial",
        f"per (counterparty, give-package, count-signature) the top "
        f"{params.variants_per_signature} gets by ISOLATION ledger ΔW are pooled, "
        f"chosen among the first {params.variant_scan_cap} gate-passers in Σv-desc "
        "order — count-signature coverage is complete; deeper sweetener permutations "
        "are not enumerated",
        "the fairness gate is KTC's own trade-calculator adjustment, ported exactly "
        "(§3.1) — `adj_give`/`adj_get` on a card are the numbers your league-mate's "
        "calculator shows",
        "counts marked saturated are verified floors — the pair walk is ordered by "
        "the legs' isolation ΔWs while pairs are priced by the exact combined "
        "ledger, so completeness above a cutoff cannot be certified (v3.4)",
        "band ceilings on cards are negotiating room, not the opener; anchor asks "
        "open +8% (§3)",
        "book recomputes from fresh rosters after any executed trade",
        "don't publicly fire-sale before making buy-side asks (§5 execution protocol)",
    ]
    if truncated:
        notes.insert(
            1,
            f"storage cap: {truncated['stored']} pairs stored across the bands "
            f"(top of each band by return), of "
            f"{'at least ' if total_sat else ''}{truncated['total']} found in the "
            "collection walk",
        )

    return {
        "disabled": False,
        "pairs": pairs_docs,
        "presets": presets,
        "counts_by_threshold": counts_by_threshold,
        "bands": bands_doc,
        "truncated": truncated,
        "recommendations": recommendations,
        "watch": watch,
        "notes": notes,
    }


