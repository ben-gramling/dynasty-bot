"""§2/§3/§5 trades: ΔW = Σv(in) − Σv(out) at face KTC, the fairness gate,
enumerate-then-filter pairing behind the user's target-return dial (§3/§5 v3.3),
posture as a hard pair-pool constraint, fully count-neutral pairs (§5 v3.2:
a recommended pair nets exactly 0 players AND 0 picks for my side).

v3.3 replaces v3.1's prune-then-pair (minimal-gap selection starved the
count-neutral matcher to zero pairs): enumeration now keeps in-band,
fleece-clean, cheap-legality-clean package variants for EVERY (counterparty,
give-package, count-signature) combination, and selectivity moves to the
pair-level return dial. Two engine-bound honesty notes (the raw space is
combinatorial — billions of pair permutations clear the band on real data):

- Each leg must clear `return_floor` on its own Σv sent. The pair return is
  the sent-weighted mediant of its leg returns, so every pair built from
  floor-clean legs clears the dial floor by construction; pairs that would
  subsidize a sub-floor leg with the other leg's excess are not proposed.
- Per (counterparty, give-package, count-signature) only the top
  `variants_per_signature` in-band gets by ΔW are pooled. With distinct
  counterparties enforced, a partner leg can never collide with the get side,
  so a higher-ΔW same-signature variant strictly dominates its siblings for
  every pairing — the count-signature diversity the v3.2 matcher starved on
  is preserved in full. Counters saturate honestly at `pair_scan_budget`.

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

    @property
    def n_picks(self) -> int:
        """Picks count as picks regardless of year (§5 v3.2)."""
        return len(self.assets) - self.n_players


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


def _sorted_opp_pkgs(league: md.LeagueState, opp_name: str) -> tuple[list[float], list[Package]]:
    """The opponent's give-list packages sorted by (Σv, keys), plus the parallel
    Σv list for bisecting — shared by band_ceiling and the board's ceiling cache."""
    pkgs = sorted(
        _packages(league, give_list(league, league.teams[opp_name])),
        key=lambda p: (p.v_sum, p.keys),
    )
    return [p.v_sum for p in pkgs], pkgs


def _ceiling_from(
    params, give: Package, vsums: list[float], pkgs: list[Package]
) -> float | None:
    i0 = bisect_left(vsums, give.v_sum / params.fleece_ratio)
    i1 = bisect_right(vsums, params.fleece_ratio * give.v_sum)
    for i in range(i1 - 1, i0 - 1, -1):  # descending Σv: first in-band is the max
        t = pkgs[i]
        hi = t.adjv if t.adjv > give.adjv else give.adjv
        band = max(params.fairness_abs, params.fairness_rel * hi)
        if abs(t.adjv - give.adjv) <= band:
            return t.v_sum
    return None


def band_ceiling(league: md.LeagueState, opp_name: str, give: Package) -> float | None:
    """§3 negotiating-room annotation: the maximum in-band, fleece-clean get Σv
    the opponent's give-list can form against this give package (what v3.0 would
    have proposed). Information only — never the proposal. None when the opponent
    has no in-band, fleece-clean package for this give (v3.3: no W_min edge —
    W_min retired as a gate)."""
    vsums, pkgs = _sorted_opp_pkgs(league, opp_name)
    return _ceiling_from(league.params, give, vsums, pkgs)


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
        "dW": {"me": round(dw_me, 1), "them": round(-dw_me, 1)},
        # §5 v3.3 leg return on inventory deployed: ΔW(me) ÷ Σv sent, percent
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


# ------------------------------------------- the pair pool + the board (§5 v3.3)


_POS4 = ("QB", "RB", "WR", "TE")
_MIN4 = tuple(MIN_POS[p] for p in _POS4)

# leg tuple layout inside PairPool.legs
L_RET, L_DW, L_SENT, L_NP, L_NK, L_OPP, L_MASK, L_GIVE, L_GET = range(9)


@dataclass(slots=True)
class PairPool:
    """§5 v3.3 candidate-leg pool: for EVERY (counterparty, give-package,
    count-signature) combination, the top `variants_per_signature` in-band,
    fleece-clean, cheap-legality-clean gets by ΔW — each leg clearing
    `return_floor` on its own Σv sent, each posture-clean when
    `enforce_posture` (the pair-pool default; the CLI hedge finder disables it
    because the desk treats posture qualitatively)."""

    opp_names: list[str]
    legs: list[tuple]  # (ret, dw, sent, np, nk, opp_i, my_give_mask, give, get)
    buckets: dict[tuple[int, int], list[int]]  # (np, nk) signature -> leg indices
    opp_pkgs: dict[str, tuple[list[float], list[Package]]]  # Σv-sorted; ceilings
    enforce_posture: bool


def _team_pos_vec(t: md.TeamCtx) -> tuple[int, int, int, int]:
    c = _pos_counts(t.act)
    return (c.get("QB", 0), c.get("RB", 0), c.get("WR", 0), c.get("TE", 0))


def _pos_vec(pkg: Package) -> tuple[int, int, int, int]:
    d = dict(pkg.pos_out)
    return (d.get("QB", 0), d.get("RB", 0), d.get("WR", 0), d.get("TE", 0))


def build_pair_pool(league: md.LeagueState, enforce_posture: bool = True) -> PairPool:
    """§5 v3.3 enumeration — no minimal-gap pruning, no W_min gate. Per opponent,
    per give-package, per get count-signature: walk the Σv window
    [gv·(1+return_floor), gv·fleece_ratio] descending (that order IS ΔW
    descending) and keep the first `variants_per_signature` candidates passing
    the EXACT §3.1 band and cheap positional legality on both sides. The band
    window on adjv is exact: below g_adj the tolerance is max(abs, rel·g_adj);
    above it, t_adj ≤ max(g_adj+abs, g_adj/(1−rel))."""
    params = league.params
    me_t = league.teams[league.me]
    my_pkgs = _packages(league, give_list(league, me_t))
    my_counts = _team_pos_vec(me_t)
    my_act = len(me_t.act)
    # partner-leg collisions can only involve MY give assets (distinct
    # counterparties own disjoint pools) — bitmask exactly those
    asset_bit: dict[str, int] = {}
    for g in my_pkgs:
        for k in g.keys:
            if k not in asset_bit:
                asset_bit[k] = 1 << len(asset_bit)
    K = params.variants_per_signature
    floor = params.return_floor
    fa, fr, fl = params.fairness_abs, params.fairness_rel, params.fleece_ratio
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
        classes: dict[tuple[int, int], tuple[list, list, list, list]] = {}
        for p in pkgs_all:
            c = classes.setdefault((p.n_players, p.n_picks), ([], [], [], []))
            c[0].append(p.v_sum)
            c[1].append(p.adjv)
            c[2].append(_pos_vec(p))
            c[3].append(p)
        for g, gp, shape, deficit, mask in g_info:
            if enforce_posture and not posture_allows(label, shape):
                continue
            gv, g_adj = g.v_sum, g.adjv
            lo_v, hi_v = gv * (1.0 + floor), gv * fl
            band_g = fa if fa > fr * g_adj else fr * g_adj
            left_lim = g_adj - band_g
            right_lim = g_adj / (1.0 - fr)
            if g_adj + fa > right_lim:
                right_lim = g_adj + fa
            for (tp_, tk), (vs, adjs, pvs, lst) in classes.items():
                if my_act + tp_ - g.n_players < 9 or opp_act + g.n_players - tp_ < 9:
                    continue
                i0 = bisect_left(vs, lo_v)
                i1 = bisect_right(vs, hi_v)
                if i0 >= i1:
                    continue
                np_, nk = tp_ - g.n_players, tk - g.n_picks
                kept = 0
                for i in range(i1 - 1, i0 - 1, -1):  # descending Σv == ΔW desc
                    t_adj = adjs[i]
                    if t_adj < left_lim or t_adj > right_lim:
                        continue
                    hi = t_adj if t_adj > g_adj else g_adj
                    gap = t_adj - g_adj
                    if gap < 0:
                        gap = -gap
                    if gap > (fa if fa > fr * hi else fr * hi):
                        continue  # exact §3.1 band recheck (same arithmetic as gate_info)
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
                    dw = vs[i] - gv
                    buckets.setdefault((np_, nk), []).append(len(legs))
                    legs.append((dw / gv, dw, gv, np_, nk, oi, mask, g, lst[i]))
                    kept += 1
                    if kept >= K:
                        break
    return PairPool(
        opp_names=list(league.opponents),
        legs=legs,
        buckets=buckets,
        opp_pkgs=opp_pkgs,
        enforce_posture=enforce_posture,
    )


def _tp_estimate(pool: PairPool, r: float) -> int:
    """Uncorrected two-pointer size of the ≥r pair space: σ_r(leg) = ΔW − r·Σv
    sent, and σ_r(buy) + σ_r(sell) ≥ 0 ⟺ pair return ≥ r (return is the
    sent-weighted mediant). Upper bound on the valid count — no counterparty /
    overlap / legality corrections; used to place the collection cutoff and to
    detect sparse markets."""
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
    """Full §3.3 legality for pool leg i, memoized: verdicts dict when legal,
    False when not (an illegal leg can never appear in any pair or card)."""
    v = cache.get(i)
    if v is None:
        leg = pool.legs[i]
        verdicts = legality(
            league, me_t, league.teams[pool.opp_names[leg[L_OPP]]],
            give=leg[L_GIVE], get=leg[L_GET],
        )
        v = verdicts if verdicts["legal"] else False
        cache[i] = v
    return v


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
                out.append(((b_dw + s[L_DW]) / (b_sent + s[L_SENT]), bi, si))
    return visits, True


def _search_cutoff(pool: PairPool, floor: float, hi: float, target: int) -> float:
    """Highest return cutoff whose uncorrected pair count still reaches `target`
    — where the stored-pair collection walk starts in a dense market."""
    lo = floor
    for _ in range(22):
        mid = (lo + hi) / 2.0
        if _tp_estimate(pool, mid) >= target:
            lo = mid
        else:
            hi = mid
    return lo


def pair_return_pct(buy_card: dict, sell_card: dict) -> float:
    """§5 v3.3 pair return on inventory deployed, from two leg cards:
    combined ΔW(me) ÷ Σv of every asset I send across both legs, in percent."""
    sent = sum(a["v"] for a in buy_card["give"]) + sum(a["v"] for a in sell_card["give"])
    dw = buy_card["dW"]["me"] + sell_card["dW"]["me"]
    return round(100.0 * dw / sent, 2)


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
    pair's return FRACTION when the pair is in the computed space, else None.
    (Exhaustiveness spot-checks and the CLI use this — no enumeration needed:
    the cross over complementary buckets is total, so pool membership plus
    these constraints IS membership in the pair space.)"""
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
    return (b[L_DW] + s[L_DW]) / (b[L_SENT] + s[L_SENT])


def pair_count_deltas(buy_card: dict, sell_card: dict) -> tuple[int, int]:
    """Combined (Δplayers, Δpicks) for MY side across a candidate pair.
    §5 v3.2 strict: a recommended pair requires exactly (0, 0) — the same number
    of players and picks after execution as before."""
    return (
        buy_card["net_players"]["me"] + sell_card["net_players"]["me"],
        buy_card["net_picks"]["me"] + sell_card["net_picks"]["me"],
    )


def trade_board(league: md.LeagueState) -> dict:
    """§5 v3.3: the exhaustively-crossed, dial-filtered PAIR board. `pairs` is
    the stored top-`max_stored_pairs` by return (each fully count-neutral, both
    legs gate-PASS, posture-clean, distinct counterparties, no shared assets),
    `counts_by_threshold` carries honest per-preset counts (exact, or a verified
    floor flagged `saturated` when the space outruns the counting budget),
    `truncated` reports the storage cap honestly. `recommendations` (top
    unpaired sell/neutral legs by ΔW) and `watch` (unpaired buys) stay as data
    for the trade-negotiator desk — the web renders pairs only."""
    params = league.params
    presets = sorted(float(p) for p in params.return_presets)
    if not league.offseason and league.snapshot.week > params.trade_deadline_week:
        return {
            "disabled": True,
            "pairs": [],
            "presets": presets,
            "counts_by_threshold": [
                {"threshold": p, "count": 0, "saturated": False} for p in presets
            ],
            "truncated": None,
            "recommendations": [],
            "watch": [],
            "notes": [f"trade deadline (week {params.trade_deadline_week}) has passed"],
        }

    pool = build_pair_pool(league)
    budget = params.pair_scan_budget
    floor = params.return_floor
    hi_edge = params.fleece_ratio - 1.0  # leg returns cap at the fleece edge
    legal: dict[int, Any] = {}
    counts: dict[float, tuple[int, bool]] = {}

    stored_complete = True
    tp_floor = _tp_estimate(pool, floor)
    if tp_floor <= budget:
        # sparse market: the whole ≥floor space fits the budget — everything exact
        out: list[tuple[float, int, int]] = []
        _walk_pairs(league, pool, floor, budget, legal, out)
        all_pairs = sorted(out, key=lambda x: (-x[0], x[1], x[2]))
        for p in presets:
            counts[p] = (sum(1 for ret, _, _ in all_pairs if 100.0 * ret >= p), False)
        stored = all_pairs[: params.max_stored_pairs]
        total, total_sat = len(all_pairs), False
    else:
        # dense market: exact counts preset-by-preset (descending) until a pass
        # saturates the budget; lower presets inherit that verified floor
        sat: tuple[int, bool] | None = None
        best_floor = 0
        for p in sorted(presets, reverse=True):
            if sat is not None:
                counts[p] = sat
                continue
            out = []
            _, done = _walk_pairs(league, pool, p / 100.0, budget, legal, out)
            n = len(out) if done else max(len(out), best_floor)
            counts[p] = (n, not done)
            best_floor = max(best_floor, n)
            if not done:
                sat = counts[p]
        # stored pairs: adaptive cutoff — the highest return whose uncorrected
        # pair count still covers the storage cap with correction headroom. The
        # very top of the space can be almost entirely correction losses (a
        # single dominant leg crossed against colliding partners — collisions
        # cost sub-microsecond visits, hence the deeper collection budget), so
        # the ladder rescales on VALID yield, ending at the full budget.
        collect_budget = max(params.pair_collect_budget, budget)
        stored: list[tuple[float, int, int]] = []
        stored_complete = True
        for target in (
            max(2000, 4 * params.max_stored_pairs),
            max(40_000, 80 * params.max_stored_pairs),
            collect_budget,
        ):
            target = min(target, collect_budget)
            r_star = (
                floor
                if _tp_estimate(pool, floor) <= target
                else _search_cutoff(pool, floor, hi_edge, target)
            )
            out = []
            _, done = _walk_pairs(league, pool, r_star, collect_budget, legal, out)
            stored = sorted(out, key=lambda x: (-x[0], x[1], x[2]))
            stored_complete = done
            if len(stored) >= params.max_stored_pairs or r_star <= floor or not done:
                break
        stored = stored[: params.max_stored_pairs]
        lowest = presets[0]
        if abs(lowest / 100.0 - floor) < 1e-9:
            total, total_sat = counts[lowest]
        else:  # non-default config: the floor sits below the lowest preset
            out = []
            _, done = _walk_pairs(league, pool, floor, budget, legal, out)
            total, total_sat = max(len(out), counts[lowest][0]), not done

    # per-preset honesty: stored pairs are themselves verified floors
    counts_by_threshold = []
    for p in presets:
        c, s = counts[p]
        n_stored = sum(1 for ret, _, _ in stored if 100.0 * ret >= p)
        counts_by_threshold.append(
            {"threshold": p, "count": max(c, n_stored), "saturated": s}
        )

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
            ceil_cache[ck] = _ceiling_from(params, give, vsums, pkgs)
        card = build_card(
            league, opp_name, give, get, leg=legal[i], ceiling=ceil_cache[ck]
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
        pairs_docs.append(
            {
                "id": f"P{n}",
                "buy": b,
                "sell": s,
                "return_pct": round(100.0 * ret, 2),
                "dW_combined": round(b["dW"]["me"] + s["dW"]["me"], 1),
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
        "target-return dial — every stored pair nets exactly 0 players / 0 picks for "
        "you, ranked by return on inventory deployed (combined ΔW ÷ Σv you send)",
        "posture is a hard engine constraint (§5 v3.3): BUYERs only receive "
        "players-majority packages, SELLERs picks-majority, NEUTRAL either; "
        "overrides apply first",
        f"every leg clears the {100 * floor:g}% return floor on its own Σv sent, so "
        "every pair clears the dial floor by construction — sub-floor legs are never "
        "subsidized by a partner leg",
        f"per (counterparty, give-package, count-signature) the top "
        f"{params.variants_per_signature} in-band gets by ΔW are pooled — "
        "count-signature coverage is complete; deeper sweetener permutations are not "
        "enumerated",
        "counts marked saturated are verified floors — the legal pair space is deeper "
        "than the counting budget",
        "band ceilings on cards are negotiating room, not the opener; anchor asks "
        "open +8% (§3)",
        "book recomputes from fresh rosters after any executed trade",
        "don't publicly fire-sale before making buy-side asks (§5 execution protocol)",
    ]
    if truncated:
        notes.insert(
            1,
            f"storage cap: top {truncated['stored']} pairs by return stored, of "
            f"{'at least ' if total_sat else ''}{truncated['total']} clearing the floor",
        )
    if not stored_complete:
        notes.insert(
            1,
            "stored pairs are the best found within the enumeration budget — the "
            "space above the collection cutoff outran a full sweep",
        )

    return {
        "disabled": False,
        "pairs": pairs_docs,
        "presets": presets,
        "counts_by_threshold": counts_by_threshold,
        "truncated": truncated,
        "recommendations": recommendations,
        "watch": watch,
        "notes": notes,
    }


