"""§6 waiver tab: rookie inventory, claim board, drop list, bids, taxi fill.

Claim score = v(add) − v(drop), drop = my lowest-v active (rational housekeeping).
Bids keep the v1 §6.4 mechanics verbatim (offseason $0/$1 ladder; in-season
formula backtested on the league's 2025 tape). The in-season formula's ΔL
allocates FAAB dollars to weekly lineup needs — a separate currency from trade
wealth, explicitly outside the no-lineup-term rule which governs trades.
"""

from __future__ import annotations

from math import floor

from core.scoring import model as md
from core.scoring.lineup import PlayerV, solve
from core.scoring.params import Params


def drop_queue(league: md.LeagueState, t: md.TeamCtx) -> list[dict]:
    """§6: actives ascending by v — informational housekeeping."""
    rows = [
        {
            "action": "DROP",
            "player": p.name,
            "sid": p.sid,
            "pos": p.pos,
            "v": p.v,
            "unvalued": p.unvalued,
        }
        for p in sorted(t.act, key=lambda p: (p.v, p.sid))
    ]
    return rows


def best_drop(league: md.LeagueState, t: md.TeamCtx) -> PlayerV | None:
    """The standing drop: my lowest-v active. None when the roster has open spots."""
    if len(t.act) < league.roster_cap:
        return None
    return min(t.act, key=lambda p: (p.v, p.sid))


def rival_demand(league: md.LeagueState, player: PlayerV, planned_bid: int) -> int:
    """§6.4 D(a): rivals whose lineup visibly needs the player and who can pay."""
    thresh = league.params.rival_dl_threshold
    need_budget = max(1, planned_bid)
    d = 0
    for name in league.opponents:
        o = league.teams[name]
        if o.faab < need_budget:
            continue
        aug = solve(o.pool + [player], league.replacement, league.params)
        if aug.L - o.L >= thresh:
            d += 1
    return d


def _round_half_up(x: float) -> int:
    return int(floor(x + 0.5))


def bid_offseason(params: Params, budget: int, d: int, netclaim_raw: float) -> int:
    ceiling = netclaim_raw / params.kappa
    if d <= 0:
        bid = 0
    elif d == 1:
        bid = params.offseason_bid_d1
    elif netclaim_raw >= params.offseason_bid_d2_min_raw:
        bid = min(params.offseason_bid_d2_cap, floor(params.offseason_bid_d2_budget_pct * budget))
    else:
        bid = params.offseason_bid_d1
    return max(0, min(int(bid), int(ceiling)))


def bid_in_season(
    params: Params, b_rem: int, dl: float, d: int, netclaim_raw: float
) -> int:
    """§6.4 in-season formula, calibrated on this league's 2025 tape."""
    if dl <= 0:
        return 0  # stash-only: $0 (user-tunable cap params.stash_bid_cap)
    g = params.g_contest[min(d, 2)]
    bid = min(
        b_rem * dl / params.k_need * g,
        netclaim_raw / params.kappa,
        params.inseason_bid_clamp * b_rem,
    )
    return max(0, _round_half_up(bid))


def waiver_board(league: md.LeagueState, t: md.TeamCtx) -> dict:
    params = league.params
    offseason = league.offseason
    budget = t.faab
    drop = best_drop(league, t)

    rookie_rows = [
        {
            "player": p.name,
            "pos": p.pos,
            "v": p.v,
            "rookie_rank": league.rookie_rank.get(p.sid),
            "note": "rookie-draft inventory — not claimable while the draft is pending",
        }
        for p in league.fa_rookies
    ]
    rookie_rows.sort(key=lambda r: (r["rookie_rank"] or 999, -r["v"]))

    targets = []
    for p in league.fa_vets:
        # erratum 10: a claim the roster would stash on taxi consumes no active
        # spot — no drop needed
        stash = bool(md.routed_split(league, t, [p])[1])
        drop_v = 0.0 if stash or drop is None else drop.v
        claim = p.v - drop_v
        dl = solve(t.pool + [p], league.replacement, params).L - t.L
        d = rival_demand(league, p, planned_bid=1)
        if offseason:
            bid = bid_offseason(params, budget, d, claim)
        else:
            bid = bid_in_season(params, budget, dl, d, claim)
        if d and bid > 1:
            d = rival_demand(league, p, planned_bid=bid)
        recommended = claim > 0
        row = {
            "action": "CLAIM",
            "player": p.name,
            "sid": p.sid,
            "pos": p.pos,
            "v": p.v,
            "claim": round(claim, 1),
            "dL": round(dl, 1),
            "taxi_stash": stash,
            "drop": None if stash else (drop.name if drop else None),
            "recommended": recommended,
            "dip": _dip_flag(league, p),
            "bid": {
                "mode": "offseason" if offseason else "in-season",
                "D": d,
                "claim": round(claim, 1),
                "ceiling": round(claim / params.kappa, 1),
                "clamp": None if offseason else round(params.inseason_bid_clamp * budget),
                "bid": bid,
            },
        }
        targets.append(row)
    targets.sort(key=lambda r: (-r["claim"], -r["v"], r["player"]))
    for i, row in enumerate(targets):
        row["rank"] = i + 1

    # erratum 12: an empty taxi slot at the week-4 lock is worth zero — nudge to
    # fill, but only SURPLUS slots (not the ones earmarked as overflow absorption)
    taxi_fill: list[dict] = []
    surplus_slots = max(0, t.free_taxi - md.taxi_slot_demand(league, t))
    if md.taxi_pre_lock(league) and surplus_slots > 0:
        elig = sorted(
            (p for p in league.fa_vets if md.taxi_eligible(league, p)),
            key=lambda p: (-p.v, p.sid),
        )
        taxi_fill = [
            {
                "player": p.name,
                "pos": p.pos,
                "v": p.v,
                "note": "stash before the week-4 taxi lock — a locked empty slot is worth zero",
            }
            for p in elig[: params.taxi_fill_top_n]
        ]
    return {
        "rookie_inventory": rookie_rows,
        "targets": targets,
        "drops": drop_queue(league, t),
        "taxi_fill": {
            "free_slots": t.free_taxi,
            "surplus_slots": surplus_slots,
            "candidates": taxi_fill,
        },
        "mode": "offseason" if offseason else "in-season",
        "faab_remaining": budget,
    }


def _dip_flag(league: md.LeagueState, p: PlayerV) -> bool:
    """Display note: value down ≥ threshold from trailing-30-day max (own archive)."""
    hist_max = league.snapshot.value_history_max.get(str(p.ktc_id))
    if not hist_max or hist_max <= 0:
        return False
    return (hist_max - p.v) / hist_max >= league.params.dip_threshold
