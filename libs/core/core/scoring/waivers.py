"""§6 waiver tab: rookie inventory, NetClaim board, drop queue, rival demand, bids."""

from __future__ import annotations

from math import floor

from core.scoring import model as md
from core.scoring import transactions as tx
from core.scoring.lineup import PlayerV, solve
from core.scoring.params import Params


def drop_queue(league: md.LeagueState, t: md.TeamCtx) -> list[dict]:
    """§6.2: actives ascending by crunch-aware RV; scheduled cuts carry the Aug-15
    badge. Rows carry the full §12 decomposition (sides/dL_terms/audit) of the drop."""
    cut_ids = {p.sid for p in t.cut_players}
    rows = []
    for p in t.act:
        res = tx.score_transaction(league, t, remove_ids=[p.sid])
        rv_val = -res.score
        rows.append(
            {
                "action": "DROP",
                "player": p.name,
                "sid": p.sid,
                "pos": p.pos,
                "v": p.v,
                "rv": round(rv_val, 1),
                "rv0": round(t.rv0[p.sid], 1),
                "scheduled_cut": p.sid in cut_ids,
                "unvalued": p.unvalued,
                "require_confirm": t.rv0[p.sid] > league.params.drop_floor,
                "sides": {"me": res.side_dict()},
                "audit": {"lineup_tables": res.audit_tables()},
                "_rv": rv_val,
            }
        )
    rows.sort(key=lambda r: (r["_rv"], r["rv0"], r["v"], r["player"]))
    for r in rows:
        del r["_rv"]
    return rows


def best_drop(league: md.LeagueState, t: md.TeamCtx) -> PlayerV | None:
    """The standing drop: head of the RV queue (Waller today). NetClaim for every
    claim is scored against this drop — the reference implementation's convention
    (a per-claim best-drop search would instead surface the −22.7 'swap-for-Flacco'
    variant for Richardson; the published board pins −45.8, i.e. fixed drop)."""
    if len(t.act) < league.roster_cap:
        return None
    queue = sorted(
        t.act,
        key=lambda p: (tx.rv(league, t, p), t.rv0.get(p.sid, 0.0), p.v, p.sid),
    )
    return queue[0]


def rival_demand(
    league: md.LeagueState, player: PlayerV, planned_bid: int
) -> int:
    """§6.3 D(a): rivals whose lineup visibly needs the player and who can pay."""
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


def _post_draft_swap(league: md.LeagueState, t: md.TeamCtx, player: PlayerV) -> dict | None:
    """§6.1 queued action: same-position swap scored in the post-draft world
    (crunch cleared, picks converted — no NC, no C terms)."""
    same_pos = [p for p in t.act if p.pos == player.pos]
    if not same_pos:
        return None
    drop = min(same_pos, key=lambda p: (t.rv0.get(p.sid, 0.0), p.v, p.sid))
    res = tx.score_transaction(
        league, t, add_players=[player], remove_ids=[drop.sid],
        include_nc=False, include_crunch=False,
    )
    return {"drop": drop.name, "score": round(res.score, 1)}


def ir_move_candidate(league: md.LeagueState, t: md.TeamCtx) -> PlayerV | None:
    """§9.4: when a claim needs a spot in-season and an active is game-status OUT
    with an IR slot free, the IR move is recommended before any drop. IR eligibility
    is strictly OUT; 2 slots; never suggested in the offseason."""
    if league.offseason or len(t.reserve_ids) >= 2:
        return None
    out = [p for p in t.act if p.u < league.params.u_healthy]
    if not out:
        return None
    return min(out, key=lambda p: (t.rv0.get(p.sid, 0.0), p.sid))


def waiver_board(league: md.LeagueState, t: md.TeamCtx) -> dict:
    params = league.params
    offseason = league.offseason
    budget = t.faab
    ir_cand = ir_move_candidate(league, t) if len(t.act) >= league.roster_cap else None
    claim_ctx = t
    if ir_cand is not None:
        # model the IR move: the OUT player leaves pool and active count, keeps his v
        claim_ctx = md.TeamCtx(
            name=t.name, rid=t.rid, omega=t.omega,
            pool=[p for p in t.pool if p.sid != ir_cand.sid],
            act=[p for p in t.act if p.sid != ir_cand.sid],
            taxi=t.taxi, reserve_ids=frozenset(t.reserve_ids | {ir_cand.sid}),
            players_v_sum=t.players_v_sum, picks=t.picks, faab=t.faab,
            free_taxi=t.free_taxi,
        )
        claim_ctx.lineup = md.solve(claim_ctx.pool, league.replacement, league.params)
        md.finalize_team(league, claim_ctx)
        drop = None
    else:
        drop = best_drop(league, t)
    drop_ids = [drop.sid] if drop else []

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
    queued = []
    for p in league.fa_vets:
        full = tx.score_transaction(league, claim_ctx, add_players=[p], remove_ids=drop_ids)
        raw = tx.score_transaction(
            league, claim_ctx, add_players=[p], remove_ids=drop_ids, include_crunch=False
        )
        netclaim, netclaim_raw = full.score, raw.score
        d = rival_demand(league, p, planned_bid=1)
        if offseason:
            bid = bid_offseason(params, budget, d, netclaim_raw)
        else:
            bid = bid_in_season(params, budget, full.dl, d, netclaim_raw)
        if d and bid > 1:
            d = rival_demand(league, p, planned_bid=bid)
        free_option = (
            t.cuts > 0
            and netclaim >= -params.free_option_eps
            and netclaim_raw >= params.n_min
            and bid == 0
        )
        # §6.1: a claim that only clears via the free-option rule (crunch cancels
        # its NetClaim) is recommended solely at $0 — never pay for doomed inventory.
        recommended = (
            netclaim >= -params.free_option_eps
            and netclaim_raw >= params.n_min
            and (bid == 0 or netclaim >= params.n_min)
        )
        dip = _dip_flag(league, p)
        row = {
            "action": "CLAIM",
            "player": p.name,
            "sid": p.sid,
            "pos": p.pos,
            "v": p.v,
            "dL": round(full.dl, 1),
            "netclaim": round(netclaim, 1),
            "netclaim_raw": round(netclaim_raw, 1),
            "drop": drop.name if drop else None,
            "ir_move": ir_cand.name if ir_cand else None,
            "recommended": recommended,
            "free_option": free_option,
            "dip": dip,
            "bid": {
                "mode": "offseason" if offseason else "in-season",
                "D": d,
                "netclaim": round(netclaim, 1),
                "netclaim_raw": round(netclaim_raw, 1),
                "ceiling": round(netclaim_raw / params.kappa, 1),
                "clamp": None if offseason else round(params.inseason_bid_clamp * budget),
                "bid": bid,
            },
            "sides": {"me": full.side_dict()},
            "audit": {"lineup_tables": full.audit_tables()},
        }
        targets.append(row)
        if not recommended and full.dl > 0:
            post = _post_draft_swap(league, claim_ctx, p)
            if post and post["score"] >= params.n_min and league.draft_pre:
                queued.append(
                    {
                        "action": "CLAIM",
                        "player": p.name,
                        "drop": post["drop"],
                        "score_today": round(netclaim, 1),
                        "score_post_draft": post["score"],
                        "note": "queued: positive post-draft swap once the crunch clears",
                    }
                )
    targets.sort(key=lambda r: (-r["netclaim"], -r["netclaim_raw"], -r["v"], r["player"]))
    for i, row in enumerate(targets):
        row["rank"] = i + 1
    week = league.snapshot.week
    return {
        "rookie_inventory": rookie_rows,
        "targets": targets,
        "drops": drop_queue(league, t),
        "queued": queued,
        "taxi_promotions": [tx.promote_score(league, t, p, week=week) for p in t.taxi],
        "mode": "offseason" if offseason else "in-season",
        "faab_remaining": budget,
    }


def _dip_flag(league: md.LeagueState, p: PlayerV) -> bool:
    """§7.6 DIP: value down ≥ threshold from trailing-30-day max (own archive)."""
    hist_max = league.snapshot.value_history_max.get(str(p.ktc_id))
    if not hist_max or hist_max <= 0:
        return False
    return (hist_max - p.v) / hist_max >= league.params.dip_threshold
