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


def band_ceiling(league: md.LeagueState, opp_name: str, give: Package) -> float | None:
    """§3 v3.1 negotiating-room annotation: the maximum in-band, fleece-clean get
    Σv the opponent's give-list can form against this give package (what v3.0
    would have proposed). Information only — never the proposal. None when the
    opponent has no in-band package clearing W_min for this give."""
    params = league.params
    their_pkgs = sorted(
        _packages(league, give_list(league, league.teams[opp_name])),
        key=lambda p: (p.v_sum, p.keys),
    )
    vsums = [p.v_sum for p in their_pkgs]
    i0 = bisect_left(vsums, give.v_sum + params.w_min)
    i1 = bisect_right(vsums, params.fleece_ratio * give.v_sum)
    for i in range(i1 - 1, i0 - 1, -1):  # descending Σv: first in-band is the max
        t = their_pkgs[i]
        hi = t.adjv if t.adjv > give.adjv else give.adjv
        band = max(params.fairness_abs, params.fairness_rel * hi)
        if abs(t.adjv - give.adjv) <= band:
            return t.v_sum
    return None


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
    ceiling: float | None = None,
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
    if ceiling is not None:
        card["ceiling"] = {
            "value": round(ceiling),
            "note": (
                "band-edge ceiling for this give package — negotiating room above "
                "the proposal, never the opener (§3 v3.1)"
            ),
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
) -> list[tuple[float, int, str, Package, Package, float, int]]:
    """In-band, fleece-clean, minima-clean candidate legs against one opponent,
    (dW, shape_rank, opp, give, get, ceiling, variant). §3 v3.1 proposal policy —
    the band is a tolerance, not a target: per give-package the per_give_keep
    SMALLEST-gap gets that still clear W_min survive, ascending (variant 0 is THE
    proposal; later variants exist only as fallbacks for full-legality rejects,
    never to widen the gap). `ceiling` is the band-edge maximum in-band,
    fleece-clean get Σv for the give package — the package v3.0 would have
    proposed, carried as negotiating-room information only."""
    params = league.params
    me_t = league.teams[league.me]
    opp_t = league.teams[opp_name]
    label = league.postures.get(opp_name, {}).get("label", ps.NEUTRAL)
    their_pkgs = sorted(
        _packages(league, give_list(league, opp_t)), key=lambda p: (p.v_sum, p.keys)
    )
    vsums = [p.v_sum for p in their_pkgs]
    adjvs = [p.adjv for p in their_pkgs]
    # adjv-ordered view: the minimal-gap search walks outward from g.adjv, which
    # IS ascending-gap order — no full-range scan, no sort per give-package
    by_adj = sorted(range(len(their_pkgs)), key=lambda i: (adjvs[i], their_pkgs[i].keys))
    adjs = [adjvs[i] for i in by_adj]
    n = len(adjs)
    out: list[tuple[float, int, str, Package, Package, float, int]] = []
    w_min, fleece, keep = params.w_min, params.fleece_ratio, params.per_give_keep
    fairness_abs, fairness_rel = params.fairness_abs, params.fairness_rel
    for g in my_pkgs:
        gv, g_adj = g.v_sum, g.adjv
        lo, hi_v = gv + w_min, fleece * gv
        i0 = bisect_left(vsums, lo)
        i1 = bisect_right(vsums, hi_v)
        if i0 >= i1:
            continue
        # ceiling: max in-band, fleece-clean Σv — first band-pass descending from
        # the fleece edge (the package v3.0 would have proposed; info only)
        ceiling = None
        for i in range(i1 - 1, i0 - 1, -1):
            t_adj = adjvs[i]
            hi = t_adj if t_adj > g_adj else g_adj
            gap = t_adj - g_adj
            if gap < 0:
                gap = -gap
            if gap <= (fairness_abs if fairness_abs > fairness_rel * hi else fairness_rel * hi):
                ceiling = vsums[i]
                break
        if ceiling is None:
            continue  # nothing in-band for this give package
        # walk limits: beyond these no candidate can be in-band (left side band is
        # exactly max(abs, rel·g_adj); right side bound is the superset
        # max(g_adj+abs, g_adj/(1-rel)) — the exact band re-checks per candidate)
        band_g = fairness_abs if fairness_abs > fairness_rel * g_adj else fairness_rel * g_adj
        left_lim = g_adj - band_g
        right_lim = g_adj / (1.0 - fairness_rel)
        if g_adj + fairness_abs > right_lim:
            right_lim = g_adj + fairness_abs
        shape = _shape_rank(offer_shape(g), label)
        r = bisect_left(adjs, g_adj)
        l = r - 1
        kept = 0
        while kept < keep:
            lv = l >= 0 and adjs[l] >= left_lim
            rv = r < n and adjs[r] <= right_lim
            if not lv and not rv:
                break
            if lv and (not rv or g_adj - adjs[l] <= adjs[r] - g_adj):
                idx, t_adj = by_adj[l], adjs[l]
                l -= 1
            else:
                idx, t_adj = by_adj[r], adjs[r]
                r += 1
            tv = vsums[idx]
            if tv < lo or tv > hi_v:
                continue
            hi = t_adj if t_adj > g_adj else g_adj
            gap = t_adj - g_adj
            if gap < 0:
                gap = -gap
            if gap > (fairness_abs if fairness_abs > fairness_rel * hi else fairness_rel * hi):
                continue
            t = their_pkgs[idx]
            if not _pos_legal_cheap(me_t, g.pos_out, t.pos_out, t.n_players - g.n_players):
                continue
            if not _pos_legal_cheap(opp_t, t.pos_out, g.pos_out, g.n_players - t.n_players):
                continue
            out.append((tv - gv, shape, opp_name, g, t, ceiling, kept))
            kept += 1
    return out


def trade_board(league: md.LeagueState) -> dict:
    """§5 v3.1: the recommendation unit is the hedged PAIR (buy side + sell side,
    embedded full cards). `recommendations` is the labeled secondary list of
    sell-side legs (plus neutral legs) — standalone buys never surface; unpaired
    buys land on the `watch` list with their blocker."""
    params = league.params
    if not league.offseason and league.snapshot.week > params.trade_deadline_week:
        return {
            "disabled": True,
            "pairs": [],
            "recommendations": [],
            "watch": [],
            "notes": [f"trade deadline (week {params.trade_deadline_week}) has passed"],
        }
    me_t = league.teams[league.me]
    my_pkgs = _packages(league, give_list(league, me_t))
    candidates: list[tuple[float, int, str, Package, Package, float, int]] = []
    for opp_name in league.opponents:
        candidates.extend(_enumerate_opponent(league, my_pkgs, opp_name))

    # one proposal per (opponent, give-package): variants ascend by gap (§3 v3.1),
    # so the first fully-legal variant IS the minimal-gap proposal; later variants
    # only replace a full-legality reject, never widen the gap
    groups: dict[tuple[str, tuple[str, ...]], list] = {}
    for cand in candidates:
        groups.setdefault((cand[2], cand[3].keys), []).append(cand)
    # groups best-first: posture fit, then the proposal's ΔW, then keys (§11.9)
    ordered = sorted(
        groups.values(),
        key=lambda vs: (vs[0][1], -vs[0][0], vs[0][2], vs[0][3].keys, vs[0][4].keys),
    )

    cards: list[dict] = []
    seen_cores: dict[tuple[str, str, str], int] = {}
    budget = params.legality_budget
    # per-side quotas: the pair board needs BOTH buy-legs and sell-legs even when
    # the fit-first ordering front-loads one side (predicted by net bodies; the
    # emitted card's actual leg_type fills the quota)
    want_buy = 2 * params.max_pairs
    want_sell = params.top_league_wide + params.max_pairs
    n_buy = n_sell = 0
    for variants in ordered:
        if budget <= 0 or (n_buy >= want_buy and n_sell >= want_sell):
            break
        net_pred = variants[0][4].n_players - variants[0][3].n_players
        if net_pred > 0 and n_buy >= want_buy:
            continue
        if net_pred <= 0 and n_sell >= want_sell:
            continue
        for dw, shape, opp_name, g, t, ceiling, _var in variants:
            core = (
                opp_name,
                max(g.assets, key=lambda a: (a.v, a.key)).key,
                max(t.assets, key=lambda a: (a.v, a.key)).key,
            )
            if seen_cores.get(core, 0) >= params.dedup_variants:
                break  # a like-shaped proposal already displays — never widen the gap
            if budget <= 0:
                break
            budget -= 1
            verdicts = legality(league, me_t, league.teams[opp_name], give=g, get=t)
            if not verdicts["legal"]:
                continue  # fall to the next-smallest gap for this give package
            seen_cores[core] = seen_cores.get(core, 0) + 1
            card = build_card(league, opp_name, g, t, leg=verdicts, ceiling=ceiling)
            card["gate"]["verdict"] = "PASS"
            card["_keys"] = set(g.keys) | set(t.keys)
            card["_core"] = core
            card["_sort"] = (shape, -dw, opp_name, g.keys, t.keys)
            cards.append(card)
            if card["leg_type"] == "buy":
                n_buy += 1
            else:
                n_sell += 1
            break  # smallest legal gap found — this give package is settled

    buys = [c for c in cards if c["leg_type"] == "buy"]
    sells = [c for c in cards if c["leg_type"] == "sell"]
    neutrals = [c for c in cards if c["leg_type"] == "neutral"]

    # PAIRS (§5 v3.1): buy-leg × sell-leg, no shared assets, combined net roster
    # ≤ 0; different counterparties required unless a buy has no other exit
    pair_cands: list[tuple[int, float, tuple, tuple, dict, dict]] = []
    diff_cp_buys: set[int] = set()
    for b in buys:
        for s in sells:
            if b["_keys"] & s["_keys"]:
                continue
            if b["net_roster"]["me"] + s["net_roster"]["me"] > 0:
                continue
            fits = int(b["posture"]["fit"]) + int(s["posture"]["fit"])
            dwc = round(b["dW"]["me"] + s["dW"]["me"], 1)
            same_cp = b["counterparty"] == s["counterparty"]
            if not same_cp:
                diff_cp_buys.add(id(b))
            pair_cands.append((same_cp, fits, dwc, b, s))
    kept_pairs: list[tuple[dict, dict]] = []
    used_buy_cores: set[tuple] = set()
    used_sell_cores: set[tuple] = set()
    for same_cp, fits, dwc, b, s in sorted(
        pair_cands, key=lambda pc: (-pc[1], -pc[2], pc[3]["_sort"], pc[4]["_sort"])
    ):
        if same_cp and id(b) in diff_cp_buys:
            continue  # a different-counterparty exit exists — prefer it
        if b["_core"] in used_buy_cores or s["_core"] in used_sell_cores:
            continue  # dedup by buy-core / sell-core
        used_buy_cores.add(b["_core"])
        used_sell_cores.add(s["_core"])
        kept_pairs.append((b, s))
        if len(kept_pairs) >= params.max_pairs:
            break

    pairs: list[dict] = []
    for n, (b, s) in enumerate(kept_pairs, 1):
        b["id"] = f"P{n}-buy"
        s["id"] = f"P{n}-sell"
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
        pairs.append(
            {
                "id": f"P{n}",
                "buy": b,
                "sell": s,
                "dW_combined": round(b["dW"]["me"] + s["dW"]["me"], 1),
                "net_roster": b["net_roster"]["me"] + s["net_roster"]["me"],
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

    # secondary list: standalone SELL-legs (no hedge needed) + neutral legs,
    # ranked posture-fit first then ΔW (§5 v3.1); never a standalone buy
    paired = {id(b) for b, _ in kept_pairs} | {id(s) for _, s in kept_pairs}
    seconds = sorted(
        (c for c in sells + neutrals if id(c) not in paired), key=lambda c: c["_sort"]
    )
    recommendations = seconds[: params.top_league_wide]
    for i, card in enumerate(recommendations):
        card["id"] = f"S{i + 1}"
        card["rank"] = i + 1

    # unpaired buys: watch list only — a buy with no identified exit is not a
    # recommendation (§5 v3.1); one-line blocker, no card
    watch: list[dict] = []
    watch_cores: set[tuple] = set()
    for b in sorted((c for c in buys if id(c) not in paired), key=lambda c: c["_sort"]):
        if b["_core"] in used_buy_cores or b["_core"] in watch_cores:
            continue  # a sibling variant of this buy is already hedged/watched
        watch_cores.add(b["_core"])
        watch.append(
            {
                "counterparty": b["counterparty"],
                "give": [a["name"] for a in b["give"]],
                "get": [a["name"] for a in b["get"]],
                "dW": b["dW"]["me"],
                "blocker": "no clean exit — no non-conflicting sell-leg on today's board",
            }
        )
        if len(watch) >= params.watch_max:
            break

    # exclusive_with across all DISPLAYED legs (pair legs + sell list):
    # legs sharing any concrete asset cannot both execute (§5)
    displayed = [leg for p in pairs for leg in (p["buy"], p["sell"])] + recommendations
    for a in displayed:
        a["exclusive_with"] = [
            b["id"] for b in displayed if b is not a and a["_keys"] & b["_keys"]
        ]
    for c in cards:
        del c["_keys"]
        del c["_core"]
        del c["_sort"]

    notes = [
        "the recommendation unit is the hedged pair (§5 v3.1) — buys never go out without an exit",
        "proposals sit at the smallest in-band gap clearing W_min (§3 v3.1); each card's band ceiling is negotiating room, not the opener",
        "book recomputes from fresh rosters after any executed trade",
        "don't publicly fire-sale before making buy-side asks (§5 execution protocol)",
    ]
    per_opp: dict[str, int] = {}
    for c in displayed:
        per_opp[c["counterparty"]] = per_opp.get(c["counterparty"], 0) + 1
    for opp_name in sorted(per_opp):
        if per_opp[opp_name] > 1:
            notes.append(
                f"{per_opp[opp_name]} offers target {opp_name} — appetite is finite; stagger them"
            )
    return {
        "disabled": False,
        "pairs": pairs,
        "recommendations": recommendations,
        "watch": watch,
        "notes": notes,
    }
