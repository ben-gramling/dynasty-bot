"""§5 core scores: the ω-blended transaction score with explainability (§12).

Every recommendation's decomposition is generated from the SAME computation that
produced the score — dL_terms are diffs of the solver's own before/after
assignments, and the displayed components sum to the score (§13.8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from core.scoring import model as md
from core.scoring.lineup import PlayerV, diff_terms
from core.scoring.picks import Pick


@dataclass(slots=True)
class ScoreResult:
    score: float
    omega: float
    dl: float
    dnc: float
    da: float
    dc: float
    terms: list[dict] = field(default_factory=list)
    crunch_info: dict = field(default_factory=dict)
    before: md.TeamCtx = None  # type: ignore[assignment]
    after: md.TeamCtx = None  # type: ignore[assignment]

    def side_dict(self, with_terms: bool = True) -> dict:
        d = {
            "omega": round(self.omega, 2),
            "dL": round(self.dl, 1),
            "dNC": round(self.dnc, 1),
            "dA": round(self.da, 1),
            "dC": round(self.dc, 1),
            "score": round(self.score, 1),
            "lineup_weighted": round(self.omega * (self.dl + self.dnc), 1),
            "wealth_weighted": round((1 - self.omega) * self.da, 1),
            "crunch_term": round(-self.dc, 1),
        }
        if with_terms:
            d["dL_terms"] = [
                {**t, "delta": round(t["delta"], 1)} for t in self.terms
            ]
            d["crunch"] = self.crunch_info
        return d

    def audit_tables(self) -> dict:
        return {"before": self.before.lineup.slot_rows(), "after": self.after.lineup.slot_rows()}


def score_transaction(
    league: md.LeagueState,
    t: md.TeamCtx,
    add_players: Sequence[PlayerV] = (),
    remove_ids: Iterable[str] = (),
    add_picks: Sequence[Pick] = (),
    remove_pick_keys: Iterable[str] = (),
    omega: float | None = None,
    include_nc: bool = True,
    include_crunch: bool = True,
) -> ScoreResult:
    w = t.omega if omega is None else omega
    t2 = md.apply_tx(league, t, add_players, remove_ids, add_picks, remove_pick_keys)
    dl = t2.L - t.L
    dnc = (t2.nc - t.nc) if include_nc else 0.0
    da = t2.a - t.a
    if not include_crunch:
        dc = 0.0
        c_before, c_after = (t.cuts, t.cut_players), (t2.cuts, t2.cut_players)
    elif omega is None or omega == t.omega:
        dc = t2.c - t.c
        c_before, c_after = (t.cuts, t.cut_players), (t2.cuts, t2.cut_players)
    else:
        # §7.4 ω-sensitivity: the whole score, crunch included, re-prices at ω′
        cuts_b, c_b, cut_b = md.crunch(league, t.pool, t.act, t.lineup, t.picks, t.free_taxi, w)
        cuts_a, c_a, cut_a = md.crunch(league, t2.pool, t2.act, t2.lineup, t2.picks, t2.free_taxi, w)
        dc = c_a - c_b
        c_before, c_after = (cuts_b, cut_b), (cuts_a, cut_a)
    score = w * (dl + dnc) + (1 - w) * da - dc
    after_ids = {p.sid for p in t2.act}
    rescued = [
        p.name
        for p in c_before[1]
        if p.sid in after_ids and p.sid not in {x.sid for x in c_after[1]}
    ]
    return ScoreResult(
        score=score,
        omega=w,
        dl=dl,
        dnc=dnc,
        da=da,
        dc=dc,
        terms=diff_terms(t.lineup, t2.lineup, league.params, league.replacement),
        crunch_info={
            "cuts_before": c_before[0],
            "cuts_after": c_after[0],
            "rescued": rescued,
        },
        before=t,
        after=t2,
    )


def vtt(
    league: md.LeagueState,
    t: md.TeamCtx,
    player: PlayerV,
    include_nc: bool = True,
    include_crunch: bool = True,
) -> float:
    """§5.1 acquisition value VTT(a, T) = Score(acquire a)."""
    return score_transaction(
        league, t, add_players=[player], include_nc=include_nc, include_crunch=include_crunch
    ).score


def rv(
    league: md.LeagueState,
    t: md.TeamCtx,
    player: PlayerV,
    include_nc: bool = True,
    include_crunch: bool = True,
) -> float:
    """§5.1 retention value RV(a, T) = −Score(lose a) (crunch-aware)."""
    return -score_transaction(
        league, t, remove_ids=[player.sid], include_nc=include_nc, include_crunch=include_crunch
    ).score


def promote_score(
    league: md.LeagueState,
    t: md.TeamCtx,
    player: PlayerV,
    week: int = 0,
) -> dict:
    """§9.3 taxi promotion: a transaction plus the post-lock dead-slot charge."""
    if player.sid not in {p.sid for p in t.taxi}:
        raise ValueError(f"{player.name} is not on the taxi squad")
    drop: PlayerV | None = None
    if len(t.act) >= league.roster_cap:
        queue = sorted(t.act, key=lambda p: (rv(league, t, p), t.rv0.get(p.sid, 0.0), p.v, p.sid))
        drop = queue[0]
    # Baseline = the ORIGINAL state (its A already banks the taxi player's v and its
    # crunch is C(T)); the promotion frees a taxi slot, so the post-state crunch is
    # computed with free_taxi + 1. Before the lock the freed slot can be refilled.
    t_base = md.TeamCtx(
        name=t.name, rid=t.rid, omega=t.omega, pool=t.pool, act=t.act,
        taxi=[p for p in t.taxi if p.sid != player.sid], reserve_ids=t.reserve_ids,
        players_v_sum=t.players_v_sum - player.v,  # re-added by the transaction
        picks=t.picks, faab=t.faab, free_taxi=t.free_taxi + 1,
    )
    t_base.lineup = t.lineup
    t_base.nc = t.nc
    t_base.a = t.a - player.v  # apply_tx re-adds v: net ΔA = 0 for the promotion itself
    t_base.cuts, t_base.c, t_base.cut_players = t.cuts, t.c, t.cut_players
    res = score_transaction(
        league, t_base, add_players=[player], remove_ids=[drop.sid] if drop else []
    )
    res.da -= player.v  # promotion moves no wealth — cancel the re-add bookkeeping
    res.score = res.omega * (res.dl + res.dnc) + (1 - res.omega) * res.da - res.dc
    lock_penalty = league.params.tau_lock if week > league.params.taxi_lock_week else 0.0
    return {
        "action": "PROMOTE",
        "player": player.name,
        "attached_drop": drop.name if drop else None,
        "score": round(res.score - lock_penalty, 1),
        "lock_penalty": lock_penalty,
        "omega_dl": round(res.omega * res.dl, 1),
        "sides": {"me": res.side_dict()},
        "audit": {"lineup_tables": res.audit_tables()},
    }
