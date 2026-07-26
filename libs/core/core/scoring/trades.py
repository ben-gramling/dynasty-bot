"""§7 trades tab: candidate generation, market-realism filters, two-sided scoring,
ranking, acceptance layer, trade-zone diagnostic, market-timing flags."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from itertools import combinations
from typing import Sequence

from core.scoring import model as md
from core.scoring import transactions as tx
from core.scoring.lineup import PlayerV, solve
from core.scoring.params import ACTIVITY_PRIOR
from core.scoring.picks import Pick


@dataclass(frozen=True, slots=True)
class Asset:
    kind: str  # "player" | "pick"
    key: str
    name: str
    mv: float  # market-visible value (players: KTC; picks: generic tranche)
    truth: float  # players: v; picks: P(p)
    pos: str | None
    age: float | None
    is_cut: bool
    is_2026: bool
    sell_floor: float
    player: PlayerV | None = None
    pick: Pick | None = None


def give_list(league: md.LeagueState, t: md.TeamCtx) -> list[Asset]:
    """§7.1: top-N actives by gross surplus σ⁰ = v − RV⁰ (cornerstones protected),
    plus scheduled cuts (doomed inventory is always shoppable), plus all picks."""
    cut_ids = {p.sid for p in t.cut_players}
    protected = {
        p.sid
        for p in sorted(t.act, key=lambda p: (-p.v, p.sid))[
            : league.params.give_list_protect_top
        ]
    }
    ranked = sorted(
        (p for p in t.act if p.sid not in protected),
        key=lambda p: (-(p.v - t.rv0.get(p.sid, 0.0)), -p.v, p.sid),
    )
    chosen = {p.sid: p for p in ranked[: league.params.give_list_size]}
    for p in t.cut_players:
        chosen.setdefault(p.sid, p)
    assets = [
        Asset(
            kind="player", key=p.sid, name=p.name, mv=p.v, truth=p.v, pos=p.pos,
            age=p.age, is_cut=p.sid in cut_ids, is_2026=False, sell_floor=p.v, player=p,
        )
        for p in chosen.values()
    ]
    for p in t.picks:
        assets.append(
            Asset(
                kind="pick", key=p.key, name=p.label, mv=p.mv, truth=p.p, pos=None,
                age=0.0, is_cut=False, is_2026=(p.year == league.current_year),
                sell_floor=p.sell_floor, pick=p,
            )
        )
    return assets


def adj_value(mvs: Sequence[float], coeffs: Sequence[float]) -> float:
    """§7.2 AdjV: consolidation-discounted package value, assets sorted mv desc."""
    out = 0.0
    for i, mv in enumerate(sorted(mvs, reverse=True)):
        out += coeffs[i] * mv if i < len(coeffs) else coeffs[-1] * mv
    return out


@dataclass(slots=True)
class Package:
    assets: tuple[Asset, ...]
    adjv: float
    mv_sum: float
    n_players: int
    n_2026: int
    all_cuts: bool
    pos_out: dict[str, int]
    sell_floor_2026: float


def _packages(league: md.LeagueState, assets: list[Asset]) -> list[Package]:
    params = league.params
    out = []
    for k in range(1, params.max_package + 1):
        for combo in combinations(assets, k):
            mvs = [a.mv for a in combo]
            pos_out: dict[str, int] = {}
            for a in combo:
                if a.kind == "player" and a.pos:
                    pos_out[a.pos] = pos_out.get(a.pos, 0) + 1
            out.append(
                Package(
                    assets=combo,
                    adjv=adj_value(mvs, params.consolidation),
                    mv_sum=sum(mvs),
                    n_players=sum(1 for a in combo if a.kind == "player"),
                    n_2026=sum(1 for a in combo if a.is_2026),
                    all_cuts=all(a.is_cut for a in combo),
                    pos_out=pos_out,
                    sell_floor_2026=sum(a.sell_floor for a in combo if a.is_2026),
                )
            )
    return out


MIN_POS = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}


def _pos_legal(t: md.TeamCtx, out_pos: dict[str, int], in_pos: dict[str, int], net_bodies: int) -> bool:
    counts: dict[str, int] = {}
    for p in t.act:
        counts[p.pos] = counts.get(p.pos, 0) + 1
    total = len(t.act) + net_bodies
    if total < 9:
        return False
    for pos, need in MIN_POS.items():
        if counts.get(pos, 0) - out_pos.get(pos, 0) + in_pos.get(pos, 0) < need:
            return False
    return True


def _attach_drops(
    league: md.LeagueState, t: md.TeamCtx, incoming: int, outgoing_ids: set[str]
) -> list[PlayerV]:
    """§7.2 legality: bodies beyond 19 + free taxi (pre-lock stash) attach min-RV drops."""
    overflow = len(t.act) - len(outgoing_ids & {p.sid for p in t.act}) + incoming - (
        league.roster_cap + (t.free_taxi if league.offseason or league.snapshot.week <= league.params.taxi_lock_week else 0)
    )
    if overflow <= 0:
        return []
    cand = sorted(
        (p for p in t.act if p.sid not in outgoing_ids),
        key=lambda p: (t.rv0.get(p.sid, 0.0), p.v, p.sid),
    )
    return cand[:overflow]


def _score_side(
    league: md.LeagueState,
    t: md.TeamCtx,
    get: Package,
    give: Package,
    omega: float | None = None,
) -> tx.ScoreResult:
    in_players = [a.player for a in get.assets if a.kind == "player"]
    out_ids = {a.key for a in give.assets if a.kind == "player"}
    attached = _attach_drops(league, t, len(in_players), out_ids)
    return tx.score_transaction(
        league,
        t,
        add_players=in_players,
        remove_ids=list(out_ids) + [p.sid for p in attached],
        add_picks=[a.pick for a in get.assets if a.kind == "pick"],
        remove_pick_keys=[a.key for a in give.assets if a.kind == "pick"],
        omega=omega,
    )


def _fairness(league: md.LeagueState, give: Package, get: Package) -> tuple[bool, dict]:
    params = league.params
    hi = max(give.adjv, get.adjv)
    gap = abs(give.adjv - get.adjv)
    band = max(params.fairness_abs, params.fairness_rel * hi)
    ok = gap <= band
    info = {
        "adj_give": round(give.adjv, 1),
        "adj_get": round(get.adjv, 1),
        "gap_pct": round(100 * gap / hi, 1) if hi else 0.0,
        "band_pct": round(100 * params.fairness_rel, 0),
        "adj": f"{give.adjv:g} vs {get.adjv:g} (gap {100 * gap / hi:.1f}%, band {params.fairness_rel:.0%})",
    }
    return ok, info


def _acceptance(
    league: md.LeagueState, opp: md.TeamCtx, res_them: tx.ScoreResult, get_theirs: Package, give_mine: Package
) -> tuple[str, bool]:
    """§7.4: posture-fit + tiers + activity demotion. give_mine = what THEY receive."""
    params = league.params
    fit = True
    if opp.omega >= params.contender_omega:
        players = [a for a in give_mine.assets if a.kind == "player"]
        biggest_is_player = bool(players) and max(
            (a.mv for a in give_mine.assets), default=0
        ) == max((a.mv for a in players), default=-1)
        fit = res_them.dl > 0 or biggest_is_player
    elif opp.omega <= params.rebuilder_omega:
        future = sum(
            a.mv
            for a in give_mine.assets
            if a.kind == "pick" or (a.age is not None and a.age < params.under_age)
        )
        fit = give_mine.adjv > 0 and future >= params.rebuilder_future_share * give_mine.mv_sum
    if res_them.score >= params.tier_a and fit:
        tier = "A"
    elif res_them.score >= params.tier_b:
        tier = "B"
    elif res_them.score >= 0:
        tier = "C"
    else:
        tier = "D"
    if ACTIVITY_PRIOR.get(opp.name, "Med") == "Low" and tier in ("A", "B"):
        tier = {"A": "B", "B": "C"}[tier]
    return tier, fit


def _card(
    league: md.LeagueState,
    opp: md.TeamCtx,
    give: Package,
    get: Package,
    res_me: tx.ScoreResult,
    res_them: tx.ScoreResult,
    h: float,
    fair_info: dict,
    raw_ratio: float,
) -> dict:
    params = league.params
    me = league.teams[league.me]
    sens = {}
    for dw in (-0.1, 0.0, 0.1):
        w = round(me.omega + dw, 2)
        if dw == 0.0:
            sens[f"{w:g}"] = round(res_me.score, 1)
        else:
            sens[f"{w:g}"] = round(_score_side(league, me, get, give, omega=w).score, 1)
    tier, fit = _acceptance(league, opp, res_them, get, give)
    dip = [
        a.name
        for a in get.assets
        if a.kind == "player" and _dip(league, a)
    ]
    pick_notes = []
    for side, assets in (("give", give.assets), ("get", get.assets)):
        for a in assets:
            if a.kind == "pick" and a.pick and a.pick.year == league.current_year:
                note = {
                    "side": side,
                    "pick": a.name,
                    "concrete": round(a.pick.p),
                    "tranche": round(a.pick.mv),
                    "sell_floor": round(a.pick.sell_floor),
                }
                # §7.6 pick-anchor arbitrage guard: selling below SellFloor is
                # flagged, not filtered — crunch-relief sales of liability picks
                # (§9.8: the 4.01) are legitimately below floor.
                if side == "give" and get.adjv < give.sell_floor_2026:
                    note["below_sell_floor"] = True
                pick_notes.append(note)
    return {
        "action": "TRADE",
        "counterparty": opp.name,
        "give": [_asset_dict(a) for a in give.assets],
        "get": [_asset_dict(a) for a in get.assets],
        "sides": {"me": res_me.side_dict(), "them": res_them.side_dict()},
        "fairness": {**fair_info, "raw_ratio": round(raw_ratio, 2), "cap": params.fleece_ratio},
        "tier": tier,
        "posture_fit": fit,
        "activity": ACTIVITY_PRIOR.get(opp.name, "Med"),
        "anchor_ask_pct": params.anchor_ask_pct,
        "omega_sensitivity": sens,
        "dip_targets": dip,
        "pick_anchor": pick_notes,
        "audit": {
            "lineup_tables": {
                "me": res_me.audit_tables(),
                "them": res_them.audit_tables(),
            }
        },
        "rank_score_H": round(h, 1),
    }


def _dip(league: md.LeagueState, a: Asset) -> bool:
    if a.player is None:
        return False
    hist = league.snapshot.value_history_max.get(str(a.player.ktc_id))
    return bool(hist) and (hist - a.player.v) / hist >= league.params.dip_threshold


def _asset_dict(a: Asset) -> dict:
    d = {"type": a.kind, "name": a.name, "v": round(a.truth)}
    if a.kind == "pick" and a.pick:
        d["mv"] = round(a.mv)
        d["pricing"] = a.pick.pricing()
    return d


def _proxy_singles(
    league: md.LeagueState, t: md.TeamCtx, assets: list[Asset], incoming: bool
) -> dict[str, float]:
    """Additive proxy for pruning: single-asset VTT (incoming) / −RV (outgoing).
    Marginals are not additive — packages are re-scored jointly (§5.1). The sum
    over-estimates lineup-side joint gains (two incoming WRs cannot both claim
    the same hole) but UNDER-estimates multi-body crunch relief: every outgoing
    singleton only ever rescues the cheapest scheduled cut, while a joint removal
    rescues the m cheapest (§4). candidate_buckets adds that interaction bound
    back via _crunch_interaction before ordering."""
    out = {}
    for a in assets:
        if incoming:
            if a.kind == "player":
                s = tx.score_transaction(league, t, add_players=[a.player]).score
            else:
                s = tx.score_transaction(league, t, add_picks=[a.pick]).score
        else:
            if a.kind == "player":
                s = tx.score_transaction(league, t, remove_ids=[a.key]).score
            else:
                s = tx.score_transaction(league, t, remove_pick_keys=[a.key]).score
        out[a.key] = s
    return out


_TIER_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}


def _crunch_interaction(cutvals: list[float], pkg: Package) -> float:
    """Joint crunch relief the additive out-proxy misses: m outgoing bodies /
    current-year picks rescue the m cheapest scheduled cuts (RV⁰ asc), while each
    singleton proxy only counts the cheapest. Non-negative by construction."""
    m = min(pkg.n_players + pkg.n_2026, len(cutvals))
    return sum(cutvals[:m]) - m * cutvals[0] if m >= 2 else 0.0


def _pkg_row(
    pkg: Package, proxy_in: dict[str, float], proxy_out: dict[str, float], cutvals: list[float]
) -> tuple:
    return (
        pkg.adjv,
        pkg.mv_sum,
        sum(proxy_in[a.key] for a in pkg.assets),
        sum(proxy_out[a.key] for a in pkg.assets) + _crunch_interaction(cutvals, pkg),
        pkg,
    )


def candidate_buckets(
    league: md.LeagueState, opp_name: str
) -> dict[tuple[int, int], list[tuple[float, Package, Package]]]:
    """§7.1 enumeration + cheap §7.2 pre-filters against one opponent, grouped
    into (give-count × get-count) buckets sorted proxy best-first. Every entry
    would be jointly evaluated by scored_candidates (§13.10 tests assert the
    per-bucket cap is non-binding on the fixture snapshot)."""
    params = league.params
    me = league.teams[league.me]
    my_assets = give_list(league, me)
    my_pkgs = _packages(league, my_assets)
    my_out = _proxy_singles(league, me, my_assets, incoming=False)
    fleece = params.fleece_ratio
    g_min = params.g_min
    floor_slack = params.their_floor - 250.0  # proxy slack before joint eval
    mutual = params.mutual_weight

    my_cutvals = sorted(me.rv0.get(p.sid, 0.0) for p in me.cut_players)

    opp = league.teams[opp_name]
    opp_cutvals = sorted(opp.rv0.get(p.sid, 0.0) for p in opp.cut_players)
    their_assets = give_list(league, opp)
    their_pkgs = _packages(league, their_assets)
    my_in = _proxy_singles(league, me, their_assets, incoming=True)
    their_out = _proxy_singles(league, opp, their_assets, incoming=False)
    their_in = _proxy_singles(league, opp, my_assets, incoming=True)
    rows = sorted(
        (_pkg_row(p, my_in, their_out, opp_cutvals) for p in their_pkgs), key=lambda r: r[0]
    )
    adjvs = [r[0] for r in rows]
    cut_rows = [r for r in rows if r[4].all_cuts]

    buckets: dict[tuple[int, int], list[tuple[float, Package, Package]]] = {}
    for g in my_pkgs:
        g_out = sum(my_out[a.key] for a in g.assets) + _crunch_interaction(my_cutvals, g)
        g_in_them = sum(their_in[a.key] for a in g.assets)
        g_mv, g_adjv = g.mv_sum, g.adjv
        if g.all_cuts:
            lo, hi = float("-inf"), float("inf")
            candidates = rows
        else:
            lo = min(g_adjv - params.fairness_abs, (1 - params.fairness_rel) * g_adjv)
            hi = max(g_adjv + params.fairness_abs, g_adjv / (1 - params.fairness_rel))
            i0, i1 = bisect_left(adjvs, lo), bisect_right(adjvs, hi)
            candidates = rows[i0:i1] + [r for r in cut_rows if not lo <= r[0] <= hi]
        n_g = len(g.assets)
        for _t_adjv, t_mv, t_in_me, t_out, gt in candidates:
            proxy_me = g_out + t_in_me
            if proxy_me < g_min:
                continue
            proxy_them = t_out + g_in_them
            if proxy_them < floor_slack:
                continue
            if g_mv > fleece * t_mv or t_mv > fleece * g_mv:
                continue
            if g.n_players == 0 and gt.n_players == 0 and g.n_2026 == gt.n_2026:
                continue  # §7.1 pick-for-pick only when a P26 count changes
            if not _pos_legal(me, g.pos_out, gt.pos_out, gt.n_players - g.n_players):
                continue
            if not _pos_legal(opp, gt.pos_out, g.pos_out, g.n_players - gt.n_players):
                continue
            proxy_h = proxy_me + mutual * min(max(proxy_them, 0.0), proxy_me)
            buckets.setdefault((n_g, len(gt.assets)), []).append((proxy_h, g, gt))
    for bucket in buckets.values():
        bucket.sort(key=lambda s: -s[0])
    return buckets


def scored_candidates(
    league: md.LeagueState, opp_name: str
) -> list[tuple[str, float, Package, Package, tx.ScoreResult, tx.ScoreResult]]:
    """All §7.1/§7.2-surviving candidates against one opponent, jointly scored.

    Joint-evaluation budget is per size bucket (give-count × get-count), proxy
    best-first, so simple 1×1/2×1 deals always get evaluated alongside the
    three-for-three consolidations. Returns (tier, H, give, get, res_me, res_them),
    sorted acceptance-tier first then H."""
    params = league.params
    me = league.teams[league.me]
    opp = league.teams[opp_name]
    mutual = params.mutual_weight
    scored: list[tuple[str, float, Package, Package, tx.ScoreResult, tx.ScoreResult]] = []
    for bucket in candidate_buckets(league, opp_name).values():
        for _proxy_h, g, gt in bucket[: params.trade_eval_cap_per_bucket]:
            res_me = _score_side(league, me, get=gt, give=g)
            if res_me.score < params.g_min:
                continue
            res_them = _score_side(league, opp, get=g, give=gt)
            if res_them.score < params.their_floor:
                continue
            h = res_me.score + mutual * min(max(res_them.score, 0.0), res_me.score)
            tier, _fit = _acceptance(league, opp, res_them, gt, g)
            scored.append((tier, h, g, gt, res_me, res_them))
    # acceptance-first ranking: an A-tier deal the counterparty should take
    # outranks a bigger-H deal that "needs selling" (§7.4 drives the display)
    scored.sort(key=lambda s: (_TIER_ORDER[s[0]], -s[1]))
    return scored


def _package_of(league: md.LeagueState, assets: Sequence[Asset]) -> Package:
    params = league.params
    pos_out: dict[str, int] = {}
    for a in assets:
        if a.kind == "player" and a.pos:
            pos_out[a.pos] = pos_out.get(a.pos, 0) + 1
    return Package(
        assets=tuple(assets),
        adjv=adj_value([a.mv for a in assets], params.consolidation),
        mv_sum=sum(a.mv for a in assets),
        n_players=sum(1 for a in assets if a.kind == "player"),
        n_2026=sum(1 for a in assets if a.is_2026),
        all_cuts=all(a.is_cut for a in assets),
        pos_out=pos_out,
        sell_floor_2026=sum(a.sell_floor for a in assets if a.is_2026),
    )


def propose(
    league: md.LeagueState, opp_name: str, give_names: Sequence[str], get_names: Sequence[str]
) -> dict:
    """Score an explicit trade proposal and return its full §12 card."""
    params = league.params
    me = league.teams[league.me]
    opp = league.teams[opp_name]
    mine = {a.name: a for a in give_list(league, me)}
    theirs = {a.name: a for a in give_list(league, opp)}
    give = _package_of(league, [mine[n] for n in give_names])
    get = _package_of(league, [theirs[n] for n in get_names])
    res_me = _score_side(league, me, get=get, give=give)
    res_them = _score_side(league, opp, get=give, give=get)
    h = res_me.score + params.mutual_weight * min(max(res_them.score, 0.0), res_me.score)
    _ok, fair_info = _fairness(league, give, get)
    raw_ratio = (
        max(give.mv_sum, get.mv_sum) / min(give.mv_sum, get.mv_sum)
        if min(give.mv_sum, get.mv_sum) > 0
        else float("inf")
    )
    return _card(league, opp, give, get, res_me, res_them, h, fair_info, raw_ratio)


def trade_candidates(league: md.LeagueState) -> list[dict]:
    params = league.params
    if not league.offseason and league.snapshot.week > params.trade_deadline_week:
        return []
    cards: list[tuple[int, float, dict]] = []
    for opp_name in league.opponents:
        opp = league.teams[opp_name]
        scored = scored_candidates(league, opp_name)
        seen_pairs: dict[tuple[str, str], int] = {}
        kept = 0
        keep_limit = max(params.top_per_opponent, params.top_league_wide)
        crunch_arb_kept = 0
        for tier, h, g, gt, res_me, res_them in scored:
            is_crunch_arb = g.all_cuts
            if kept >= keep_limit and not (is_crunch_arb and crunch_arb_kept < 3):
                continue
            core = (
                max(g.assets, key=lambda a: a.mv).key,
                max(gt.assets, key=lambda a: a.mv).key,
            )
            if seen_pairs.get(core, 0) >= params.dedup_variants:
                continue
            seen_pairs[core] = seen_pairs.get(core, 0) + 1
            _ok, fair_info = _fairness(league, g, gt)
            raw_ratio = (
                max(g.mv_sum, gt.mv_sum) / min(g.mv_sum, gt.mv_sum)
                if min(g.mv_sum, gt.mv_sum) > 0
                else float("inf")
            )
            cards.append(
                (
                    _TIER_ORDER[tier],
                    h,
                    _card(league, opp, g, gt, res_me, res_them, h, fair_info, raw_ratio),
                )
            )
            kept += 1
            if is_crunch_arb:
                crunch_arb_kept += 1

    cards.sort(key=lambda c: (c[0], -c[1]))
    ordered = [c for _, _, c in cards]
    # DIP boost: §7.6 — bump display rank one notch
    for i in range(1, len(ordered)):
        if ordered[i]["dip_targets"] and not ordered[i - 1]["dip_targets"]:
            ordered[i - 1], ordered[i] = ordered[i], ordered[i - 1]
    return ordered


def trade_zone(
    league: md.LeagueState, targets: Sequence[PlayerV] | None = None
) -> list[dict]:
    """§7.5 single-target buy diagnostic: my ceiling vs their floor, honest empties."""
    me = league.teams[league.me]
    if targets is None:
        targets = _default_zone_targets(league)
    rows = []
    for p in targets:
        owner = next(
            (t for t in league.teams.values() if any(x.sid == p.sid for x in t.act)), None
        )
        if owner is None or owner.name == league.me:
            continue
        dl_me = solve(me.pool + [p], league.replacement, league.params).L - me.L
        rem = owner.L - solve(
            [x for x in owner.pool if x.sid != p.sid], league.replacement, league.params
        ).L
        w_me, w_o = me.omega, owner.omega
        ceiling = p.v + w_me / (1 - w_me) * dl_me
        floor = p.v + w_o / (1 - w_o) * rem
        zone = ceiling - floor
        rows.append(
            {
                "target": p.name,
                "v": p.v,
                "owner": owner.name,
                "their_floor": round(floor),
                "my_ceiling": round(ceiling),
                "zone": round(zone) if zone > 0 else None,
            }
        )
    rows.sort(key=lambda r: -(r["zone"] or -10**9))
    return rows


def _default_zone_targets(league: md.LeagueState) -> list[PlayerV]:
    """Display heuristic (not part of the scoring contract): players at my
    weakest-ranked slot group, held by non-contenders, with real market value."""
    me = league.teams[league.me]
    ranks: dict[str, int] = {}
    for grp in ("QB", "RB", "WR", "TE", "FLEX"):
        ordered = sorted(league.teams.values(), key=lambda t: -t.lineup.group_sums[grp])
        for i, t in enumerate(ordered):
            if t.name == league.me:
                ranks[grp] = i + 1
    weakest = max((g for g in ranks if g != "FLEX"), key=lambda g: ranks[g])
    out = []
    for t in league.teams.values():
        if t.name == league.me or t.omega > 0.55:
            continue
        out.extend(p for p in t.act if p.pos == weakest and p.v >= 4000)
    return sorted(out, key=lambda p: -p.v)
