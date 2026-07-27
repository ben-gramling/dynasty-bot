"""§2/§3/§5 trades: ΔW = Σv(in) − Σv(out) at face KTC, the fairness gate,
posture-shaped ranking, roster-neutral pairing.

The scoring path is pure face-value arithmetic — this module imports NOTHING
from the lineup solver (§11.2; enforced by an import-graph test). Roster
legality and taxi routing (§8) are delegated to model.apply_tx, which affects
legality and sequencing only, never ΔW.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Sequence

from core.scoring import model as md
from core.scoring import posture as ps


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


def adj_value(vs: Sequence[float], coeffs: Sequence[float]) -> float:
    """§3.1 AdjV: consolidation-discounted package value, assets sorted v desc."""
    out = 0.0
    for i, v in enumerate(sorted(vs, reverse=True)):
        out += coeffs[i] * v if i < len(coeffs) else coeffs[-1] * v
    return out


@dataclass(frozen=True, slots=True)
class Package:
    assets: tuple[Asset, ...]
    adjv: float
    v_sum: float
    n_players: int
    pos_out: tuple[tuple[str, int], ...]
    has_unvalued: bool

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(a.key for a in self.assets))


def package_of(league: md.LeagueState, assets: Sequence[Asset]) -> Package:
    pos_out: dict[str, int] = {}
    for a in assets:
        if a.kind == "player" and a.pos:
            pos_out[a.pos] = pos_out.get(a.pos, 0) + 1
    return Package(
        assets=tuple(assets),
        adjv=adj_value([a.v for a in assets], league.params.consolidation),
        v_sum=sum(a.v for a in assets),
        n_players=sum(1 for a in assets if a.kind == "player"),
        pos_out=tuple(sorted(pos_out.items())),
        has_unvalued=any(a.unvalued for a in assets),
    )


def _packages(league: md.LeagueState, assets: list[Asset]) -> list[Package]:
    out = []
    for k in range(1, league.params.max_package + 1):
        for combo in combinations(assets, k):
            out.append(package_of(league, combo))
    return out


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


def gate_info(league: md.LeagueState, give: Package, get: Package) -> dict:
    """§3.1/§3.2: adjusted-value band + anti-fleece cap (never exempted)."""
    params = league.params
    hi = max(give.adjv, get.adjv)
    gap = abs(give.adjv - get.adjv)
    band = max(params.fairness_abs, params.fairness_rel * hi)
    lo_sum = min(give.v_sum, get.v_sum)
    ratio = (max(give.v_sum, get.v_sum) / lo_sum) if lo_sum > 0 else float("inf")
    return {
        "adj_give": round(give.adjv, 1),
        "adj_get": round(get.adjv, 1),
        "gap": round(gap, 1),
        "gap_pct": round(100 * gap / hi, 1) if hi else 0.0,
        "band": round(band, 1),
        "band_pct": round(100 * params.fairness_rel, 0),
        "band_ok": gap <= band,
        "raw_ratio": round(ratio, 2) if ratio != float("inf") else None,
        "cap": params.fleece_ratio,
        "ratio_ok": ratio <= params.fleece_ratio,
    }


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
    """What the counterparty receives: mostly players, mostly picks, or mixed."""
    pv = sum(a.v for a in give.assets if a.kind == "player")
    kv = sum(a.v for a in give.assets if a.kind == "pick")
    if pv > kv:
        return "players"
    if kv > pv:
        return "picks"
    return "mixed"


def _shape_rank(shape: str, label: str) -> int:
    """0 = shape fits posture, 1 = NEUTRAL counterparty, 2 = mismatched shape.
    Orders within equal ΔW only — never gates, never scores (§4)."""
    if (shape == "players" and label == ps.BUYER) or (shape == "picks" and label == ps.SELLER):
        return 0
    if label == ps.NEUTRAL:
        return 1
    return 2


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
) -> dict:
    """The §5/§10 card for one leg. dW is exactly zero-sum by construction (§11.1)."""
    params = league.params
    me_t = league.teams[league.me]
    opp_t = league.teams[opp_name]
    dw_me = get.v_sum - give.v_sum
    gate = gate_info(league, give, get)
    verdicts = leg if leg is not None else legality(league, me_t, opp_t, give, get)
    gate["legal"] = verdicts["legal"]
    posture = league.postures.get(opp_name, {"label": ps.NEUTRAL, "source": "trades"})
    shape = offer_shape(give)
    fit = _shape_rank(shape, posture["label"]) == 0
    net_me = verdicts["me"]["net_roster"]
    leg_type = "buy" if net_me > 0 else "sell" if net_me < 0 else "neutral"
    if leg_type == "buy":
        if verdicts["me"]["overflow"] > 0:
            sequencing = (
                f"at the roster cap (+{verdicts['me']['overflow']} over): execute the "
                "paired sell-leg first — Sleeper trades process instantly"
            )
        else:
            sequencing = "roster space available: buy may execute before its paired sell"
    elif leg_type == "sell":
        sequencing = "standalone sell-leg — no pairing needed"
    else:
        sequencing = "roster-neutral leg — order free"
    unvalued = sorted(
        a.name for pkg in (give, get) for a in pkg.assets if a.unvalued
    )
    card = {
        "action": "TRADE",
        "counterparty": opp_name,
        "give": [_asset_dict(a) for a in give.assets],
        "get": [_asset_dict(a) for a in get.assets],
        "dW": {"me": round(dw_me, 1), "them": round(-dw_me, 1)},
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
    if unvalued:
        card["notes"] = ["unvalued assets contribute 0 to ΔW — verify by hand (§11.7)"]
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
    card = build_card(league, opp_name, give, get)
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
            f"ΔW +{card['dW']['me']:g} is below the W_min {league.params.w_min:g} noise floor"
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


# ------------------------------------------------------------------ the board §5


def _enumerate_opponent(
    league: md.LeagueState,
    my_pkgs: list[Package],
    opp_name: str,
) -> list[tuple[float, int, str, Package, Package]]:
    """In-band, fleece-clean, minima-clean candidate legs against one opponent,
    (dW, shape_rank, opp, give, get). Per give-package only the best per_give_keep
    gets survive — the engine always proposes the most-favorable in-band package."""
    params = league.params
    me_t = league.teams[league.me]
    opp_t = league.teams[opp_name]
    label = league.postures.get(opp_name, {}).get("label", ps.NEUTRAL)
    their_pkgs = sorted(
        _packages(league, give_list(league, opp_t)), key=lambda p: (p.v_sum, p.keys)
    )
    vsums = [p.v_sum for p in their_pkgs]
    out: list[tuple[float, int, str, Package, Package]] = []
    w_min, fleece, keep = params.w_min, params.fleece_ratio, params.per_give_keep
    fairness_abs, fairness_rel, coeffs = params.fairness_abs, params.fairness_rel, params.consolidation
    for g in my_pkgs:
        gv, g_adj = g.v_sum, g.adjv
        i0 = bisect_left(vsums, gv + w_min)
        i1 = bisect_right(vsums, fleece * gv)
        kept = 0
        for i in range(i1 - 1, i0 - 1, -1):  # descending ΔW(me)
            t = their_pkgs[i]
            hi = t.adjv if t.adjv > g_adj else g_adj
            if abs(t.adjv - g_adj) > (fairness_abs if fairness_abs > fairness_rel * hi else fairness_rel * hi):
                continue
            if not _pos_legal_cheap(me_t, g.pos_out, t.pos_out, t.n_players - g.n_players):
                continue
            if not _pos_legal_cheap(opp_t, t.pos_out, g.pos_out, g.n_players - t.n_players):
                continue
            out.append((t.v_sum - gv, _shape_rank(offer_shape(g), label), opp_name, g, t))
            kept += 1
            if kept >= keep:
                break
    return out


def trade_board(league: md.LeagueState) -> dict:
    """§5: ranked gated legs, roster-neutral bundles, exclusive_with, notes."""
    params = league.params
    if not league.offseason and league.snapshot.week > params.trade_deadline_week:
        return {
            "disabled": True,
            "recommendations": [],
            "pairs": [],
            "notes": [f"trade deadline (week {params.trade_deadline_week}) has passed"],
        }
    me_t = league.teams[league.me]
    my_pkgs = _packages(league, give_list(league, me_t))
    candidates: list[tuple[float, int, str, Package, Package]] = []
    for opp_name in league.opponents:
        candidates.extend(_enumerate_opponent(league, my_pkgs, opp_name))
    # ΔW desc; posture shape orders within equal ΔW; then deterministic keys (§11.9)
    candidates.sort(key=lambda c: (-c[0], c[1], c[2], c[3].keys, c[4].keys))

    cards: list[dict] = []
    seen_pairs: dict[tuple[str, str, str], int] = {}
    budget = params.legality_budget
    want = 3 * params.top_league_wide  # slack for pairing + exclusivity display
    for dw, shape, opp_name, g, t in candidates:
        if budget <= 0 or len(cards) >= want:
            break
        core = (
            opp_name,
            max(g.assets, key=lambda a: (a.v, a.key)).key,
            max(t.assets, key=lambda a: (a.v, a.key)).key,
        )
        if seen_pairs.get(core, 0) >= params.dedup_variants:
            continue
        budget -= 1
        verdicts = legality(league, me_t, league.teams[opp_name], give=g, get=t)
        if not verdicts["legal"]:
            continue
        seen_pairs[core] = seen_pairs.get(core, 0) + 1
        card = build_card(league, opp_name, g, t, leg=verdicts)
        card["gate"]["verdict"] = "PASS"
        card["_keys"] = set(g.keys) | set(t.keys)
        card["_sort"] = (-dw, shape, opp_name, g.keys, t.keys)
        cards.append(card)

    recommendations = cards[: params.top_league_wide]
    extras = cards[params.top_league_wide :]

    # roster-neutral bundles (§5): pair each buy-leg with the best non-conflicting
    # sell-leg; a hedge found only among the extras is promoted onto the board
    raw_pairs: list[tuple[dict, dict | None]] = []
    extra_sells = [c for c in extras if c["leg_type"] == "sell"]
    used_sells: set[int] = set()
    for buy in [c for c in recommendations if c["leg_type"] == "buy"]:
        hedge = None
        for sell in [c for c in recommendations if c["leg_type"] == "sell"] + extra_sells:
            if id(sell) in used_sells or sell["_keys"] & buy["_keys"]:
                continue
            if buy["net_roster"]["me"] + sell["net_roster"]["me"] <= 0:
                hedge = sell
                break
        raw_pairs.append((buy, hedge))
        if hedge is not None:
            used_sells.add(id(hedge))
            if not any(hedge is c for c in recommendations):
                recommendations.append(hedge)  # promoted to make the bundle whole

    # final display order: ΔW desc (posture shape within equal ΔW), ids assigned last
    recommendations.sort(key=lambda c: c["_sort"])
    for i, card in enumerate(recommendations):
        card["id"] = f"R{i + 1}"
        card["rank"] = i + 1
    pairs: list[dict] = []
    for buy, hedge in raw_pairs:
        if hedge is None:
            pairs.append(
                {
                    "legs": [buy["id"]],
                    "dW": buy["dW"]["me"],
                    "net_roster": buy["net_roster"]["me"],
                    "note": "no hedge sell-leg on the board — find a sell before executing (§5)",
                }
            )
        else:
            pairs.append(
                {
                    "legs": [buy["id"], hedge["id"]],
                    "dW": round(buy["dW"]["me"] + hedge["dW"]["me"], 1),
                    "net_roster": buy["net_roster"]["me"] + hedge["net_roster"]["me"],
                    "note": "agreement-first: verbal yes on the buy, execute the sell, then the buy",
                }
            )
    pairs.sort(key=lambda p: (-p["dW"], p["legs"]))

    # exclusive_with: legs sharing any concrete asset cannot both execute
    for i, a in enumerate(recommendations):
        a["exclusive_with"] = [
            b["id"] for j, b in enumerate(recommendations) if j != i and a["_keys"] & b["_keys"]
        ]
    for c in recommendations:
        del c["_keys"]
        del c["_sort"]

    notes = [
        "book recomputes from fresh rosters after any executed trade",
        "don't publicly fire-sale before making buy-side asks (§5 execution protocol)",
    ]
    per_opp: dict[str, int] = {}
    for c in recommendations:
        per_opp[c["counterparty"]] = per_opp.get(c["counterparty"], 0) + 1
    for opp_name in sorted(per_opp):
        if per_opp[opp_name] > 1:
            notes.append(
                f"{per_opp[opp_name]} offers target {opp_name} — appetite is finite; stagger them"
            )
    return {
        "disabled": False,
        "recommendations": recommendations,
        "pairs": pairs,
        "notes": notes,
    }
