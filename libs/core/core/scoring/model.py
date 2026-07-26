"""League/team state built from a Snapshot: crosswalk join, replacement lines,
pick pricing, lineups, wealth, rookie now-credit and roster-crunch (§§0–4)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Iterable, Mapping, Sequence

from core.scoring import picks as pk
from core.scoring.lineup import BIG, Lineup, PlayerV, removal_dl, solve
from core.scoring.params import Params
from core.scoring.snapshot import Snapshot


@dataclass(slots=True)
class TeamCtx:
    name: str
    rid: int
    omega: float
    pool: list[PlayerV]
    act: list[PlayerV]
    taxi: list[PlayerV]
    reserve_ids: frozenset[str]
    players_v_sum: float  # Σ v over ALL rostered players (incl taxi, IR)
    picks: list[pk.Pick]
    faab: int
    free_taxi: int
    lineup: Lineup = None  # type: ignore[assignment]
    nc: float = 0.0
    a: float = 0.0
    f: float = 0.0
    cuts: int = 0
    c: float = 0.0
    cut_players: list[PlayerV] = field(default_factory=list)
    rv0: dict[str, float] = field(default_factory=dict)

    @property
    def L(self) -> float:
        return self.lineup.L

    @property
    def lam(self) -> float:
        return self.lineup.L + self.nc


@dataclass(slots=True)
class LeagueState:
    snapshot: Snapshot
    params: Params
    players: dict[str, PlayerV]
    ktc_by_id: dict[str, Mapping]
    teams: dict[str, TeamCtx]
    me: str
    replacement: dict[str, float]
    board: dict[int, pk.BoardEntry]
    tranches: dict[tuple[int, str, int], float]
    rank_l: dict[str, int]
    fa_rookies: list[PlayerV]
    fa_vets: list[PlayerV]
    rookie_rank: dict[str, int]
    roster_cap: int
    taxi_cap: int
    current_year: int
    draft_pre: bool
    offseason: bool
    rostered: frozenset[str]
    alerts: list[str]

    @property
    def opponents(self) -> list[str]:
        return [n for n in self.teams if n != self.me]


# ---------------------------------------------------------------- build helpers


_MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
_RETURN_RE = re.compile(r"([A-Za-z]{3})[A-Za-z]*\.?\s+(\d{1,2}),?\s+(\d{4})")


def _parse_return(s: str | None) -> date | None:
    """KTC `injuryReturn` ("Aug 13, 2026") -> date; None when absent/unparseable."""
    m = _RETURN_RE.search(s or "")
    if not m or m.group(1).lower() not in _MONTHS:
        return None
    try:
        return date(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
    except ValueError:
        return None


def _in_season_date(snapshot: Snapshot) -> date:
    """Deterministic 'today' for the §9.5 return-window test: season start
    (Sleeper state; Sept 1 fallback) plus the elapsed weeks."""
    start = snapshot.state.get("season_start_date")
    season = int(snapshot.state.get("season") or snapshot.draft["season"])
    base = date.fromisoformat(start) if start else date(season, 9, 1)
    return base + timedelta(days=7 * max(0, snapshot.week - 1))


def _availability_u(params: Params, asset: Mapping | None, offseason: bool, ref: date) -> float:
    """§9.5: u = 1 offseason; in-season OUT players are discounted, never revalued.
    0.6 only when `injuryReturn` is within u_out_short_weeks of `ref`, else 0.25."""
    if offseason or not asset:
        return params.u_healthy
    injury = asset.get("injury") or {}
    out = injury.get("injuryCode") == 4 or (asset.get("oneQBValues") or {}).get("isOutThisWeek")
    if not out:
        return params.u_healthy
    back = _parse_return(injury.get("injuryReturn"))
    if back is not None and (back - ref).days <= 7 * params.u_out_short_weeks:
        return params.u_out_short
    return params.u_out_long


def build_league(snapshot: Snapshot, params: Params) -> LeagueState:
    from core.scoring.snapshot import validate_snapshot

    alerts = validate_snapshot(snapshot)
    offseason = snapshot.offseason
    draft_pre = snapshot.draft_pre
    current_year = int(snapshot.draft["season"])
    positions = snapshot.league.get("roster_positions") or []
    roster_cap = len(positions)  # 9 starters + 10 BN = 19
    league_settings = snapshot.league.get("settings") or {}
    taxi_cap = int(league_settings.get("taxi_slots") or 3)
    budget = int(league_settings.get("waiver_budget") or 0)

    ref_date = _in_season_date(snapshot)
    ktc_by_id = {str(a["playerID"]): a for a in snapshot.ktc_assets if a.get("position") != "RDP"}
    players: dict[str, PlayerV] = {}
    for kid, entry in snapshot.crosswalk.items():
        asset = ktc_by_id.get(str(kid))
        players[str(entry["sleeper_id"])] = PlayerV(
            sid=str(entry["sleeper_id"]),
            name=entry.get("ktc_name") or entry.get("sleeper_name") or str(kid),
            pos=entry["position"],
            v=float(entry.get("oneqb_value") or 0),
            u=_availability_u(params, asset, offseason, ref_date),
            ktc_id=int(kid),
            rookie=bool(entry.get("rookie")),
            age=(asset or {}).get("age"),
        )

    users = {u["user_id"]: u.get("display_name") or u["user_id"] for u in snapshot.users}
    rostered: set[str] = set()
    for r in snapshot.rosters:
        rostered.update(r.get("players") or [])

    unvalued_rostered = sorted(rostered - set(players))
    for sid in unvalued_rostered:
        sup = snapshot.player_names.get(sid, {})
        players[sid] = PlayerV(
            sid=sid, name=sup.get("name", f"#{sid}"), pos=sup.get("pos", "UNK"),
            v=0.0, ktc_id=BIG, unvalued=True,
        )
    if len(unvalued_rostered) > 1:
        names = [players[s].name for s in unvalued_rostered]
        alerts.append(f"unvalued rostered players grew to {len(unvalued_rostered)}: {names}")

    # free-agent pool + replacement lines (§2.3)
    fa = sorted(
        (p for sid, p in players.items() if sid not in rostered and not p.unvalued),
        key=PlayerV.sort_key,
    )
    fa_rookies = [p for p in fa if p.rookie] if draft_pre else []
    fa_vets = [p for p in fa if not (draft_pre and p.rookie)]
    replacement: dict[str, float] = {}
    for pos in ("QB", "RB", "WR", "TE"):
        vals = [p.v for p in fa_vets if p.pos == pos and not p.rookie]
        idx = params.replacement_fa_rank - 1
        replacement[pos] = vals[idx] if len(vals) > idx else (vals[-1] if vals else 0.0)
    replacement["FLEX"] = max(replacement["RB"], replacement["WR"], replacement["TE"])

    board = pk.build_board(snapshot.ktc_assets)
    tranches = pk.build_tranches(snapshot.ktc_assets)
    # sleeper_id -> rookie board rank (for the waiver tab's rookie-inventory section)
    rookie_rank: dict[str, int] = {}
    for kid, entry in snapshot.crosswalk.items():
        rr = ((ktc_by_id.get(str(kid)) or {}).get("oneQBValues") or {}).get("rookieRank")
        if rr:
            rookie_rank[str(entry["sleeper_id"])] = int(rr)

    # team shells + lineups
    teams: dict[str, TeamCtx] = {}
    me = ""
    for r in snapshot.rosters:
        name = users.get(r["owner_id"], str(r["owner_id"]))
        if int(r["roster_id"]) == int(snapshot.my_roster_id):
            me = name
        taxi_ids = set(r.get("taxi") or [])
        reserve_ids = set(r.get("reserve") or [])
        roster_players = [players[s] for s in (r.get("players") or [])]
        taxi = [p for p in roster_players if p.sid in taxi_ids]
        if offseason:
            # July reserve tags are stale artifacts — IR players are healthy-next-season
            pool = [p for p in roster_players if p.sid not in taxi_ids]
        else:
            pool = [p for p in roster_players if p.sid not in taxi_ids and p.sid not in reserve_ids]
        act = [p for p in roster_players if p.sid not in taxi_ids and p.sid not in reserve_ids]
        omega = params.omega_for(name, me if me else "?")
        teams[name] = TeamCtx(
            name=name,
            rid=int(r["roster_id"]),
            omega=omega,
            pool=pool,
            act=act,
            taxi=taxi,
            reserve_ids=frozenset(reserve_ids),
            players_v_sum=sum(p.v for p in roster_players),
            picks=[],
            faab=budget - int((r.get("settings") or {}).get("waiver_budget_used") or 0),
            free_taxi=max(0, taxi_cap - len(taxi)),
        )
    # my omega may have been resolved before `me` was known — fix all omegas now
    seeds, games_back = _standings(snapshot)
    for name, t in teams.items():
        t.omega = params.omega_for(name, me)
        if not offseason and snapshot.week >= 1:
            from core.scoring.params import omega_in_season

            t.omega = omega_in_season(
                params, t.omega, snapshot.week, seeds.get(t.rid), games_back.get(t.rid, 0.0)
            )
        t.lineup = solve(t.pool, replacement, params)

    rank_l = {
        name: i + 1
        for i, name in enumerate(sorted(teams, key=lambda n: (-teams[n].lineup.L, n)))
    }

    # pick ownership + pricing (2026 picks cease to exist once the draft completes)
    rid2name = {t.rid: n for n, t in teams.items()}
    slot_of_roster = {int(rid): int(slot) for slot, rid in snapshot.draft["slot_to_roster_id"].items()}
    years = [y for y in (current_year, current_year + 1, current_year + 2) if draft_pre or y != current_year]
    owner = pk.pick_ownership(list(rid2name), snapshot.traded_picks, years)
    for (year, rnd, origin_rid), owner_rid in sorted(owner.items()):
        p = pk.price_pick(
            year=year, rnd=rnd, origin_rid=origin_rid, origin_name=rid2name[origin_rid],
            owner_rid=owner_rid, owner_name=rid2name[owner_rid], current_year=current_year,
            slot_of_roster=slot_of_roster, board=board, tranches=tranches, rank_l=rank_l,
        )
        teams[rid2name[owner_rid]].picks.append(p)

    league = LeagueState(
        snapshot=snapshot, params=params, players=players, ktc_by_id=ktc_by_id,
        teams=teams, me=me, replacement=replacement, board=board, tranches=tranches,
        rank_l=rank_l, fa_rookies=fa_rookies, fa_vets=fa_vets, rookie_rank=rookie_rank,
        roster_cap=roster_cap, taxi_cap=taxi_cap, current_year=current_year,
        draft_pre=draft_pre, offseason=offseason, rostered=frozenset(rostered), alerts=alerts,
    )
    for t in teams.values():
        finalize_team(league, t)
    return league


def _standings(snapshot: Snapshot) -> tuple[dict[int, int], dict[int, float]]:
    """Playoff seed (by record, points tiebreak — §2.5 of the league doc) and
    games back, for the in-season ω ramp."""
    rows = []
    for r in snapshot.rosters:
        s = r.get("settings") or {}
        wins = int(s.get("wins") or 0)
        fpts = float(s.get("fpts") or 0) + float(s.get("fpts_decimal") or 0) / 100
        rows.append((int(r["roster_id"]), wins, fpts))
    rows.sort(key=lambda x: (-x[1], -x[2], x[0]))
    seeds = {rid: i + 1 for i, (rid, _, _) in enumerate(rows)}
    top_wins = rows[0][1] if rows else 0
    games_back = {rid: float(top_wins - wins) for rid, wins, _ in rows}
    return seeds, games_back


# ------------------------------------------------------- derived team quantities


def e26_virtuals(league: LeagueState, picks: Iterable[pk.Pick]) -> list[PlayerV]:
    """§3.3 E26(T): expected selections of current-year picks as virtual players."""
    out = []
    for p in picks:
        if p.year == league.current_year and p.n is not None:
            b = pk.board_value(league.board, p.n)
            out.append(PlayerV(sid=f"virt:{p.n}", name=f"[{b.name}]", pos=b.pos, v=b.value, ktc_id=0))
    return out


def now_credit(league: LeagueState, pool: list[PlayerV], lineup: Lineup, picks: list[pk.Pick]) -> float:
    if not league.draft_pre:
        return 0.0
    virt = e26_virtuals(league, picks)
    if not virt:
        return 0.0
    aug = solve(pool + virt, league.replacement, league.params)
    return league.params.rho_rook * (aug.L - lineup.L)


def rv0_map(
    league: LeagueState,
    pool: list[PlayerV],
    act: list[PlayerV],
    lineup: Lineup,
    omega: float,
) -> dict[str, float]:
    """Gross retention value RV⁰ (§4) for every active, exact."""
    return {
        p.sid: omega * removal_dl(lineup, pool, p, league.replacement, league.params)
        + (1 - omega) * p.v
        for p in act
    }


def crunch(
    league: LeagueState,
    pool: list[PlayerV],
    act: list[PlayerV],
    lineup: Lineup,
    picks: Iterable[pk.Pick],
    free_taxi: int,
    omega: float,
) -> tuple[int, float, list[PlayerV]]:
    """§4: forced-cut count and Score-consistent value of the cuts at the next
    compression event. Lazy-exact for starters: their RV⁰ lower bound (1−ω)v
    almost always clears the cut line."""
    p26 = sum(1 for p in picks if p.year == league.current_year)
    if not league.draft_pre:
        p26 = 0
    cuts = max(0, len(act) + p26 - league.roster_cap - free_taxi)
    if cuts == 0:
        return 0, 0.0, []
    params, repl = league.params, league.replacement
    entries: list[tuple[float, bool, PlayerV]] = []  # (rv0_or_lb, is_exact, player)
    for p in act:
        if p.sid in lineup.starter_ids:
            entries.append(((1 - omega) * p.v, False, p))
        else:
            exact = omega * removal_dl(lineup, pool, p, repl, params) + (1 - omega) * p.v
            entries.append((exact, True, p))
    entries.sort(key=lambda e: (e[0], e[2].sid))
    while True:
        head = entries[:cuts]
        lazy = [i for i, e in enumerate(head) if not e[1]]
        if not lazy:
            break
        for i in lazy:
            val, _, p = entries[i]
            exact = omega * removal_dl(lineup, pool, p, repl, params) + (1 - omega) * p.v
            entries[i] = (exact, True, p)
        entries.sort(key=lambda e: (e[0], e[2].sid))
    head = entries[:cuts]
    return cuts, sum(e[0] for e in head), [e[2] for e in head]


def finalize_team(league: LeagueState, t: TeamCtx) -> None:
    t.nc = now_credit(league, t.pool, t.lineup, t.picks)
    picks_sum = sum(p.p for p in t.picks)
    t.a = t.players_v_sum + picks_sum
    t.f = picks_sum + sum(p.v for p in t.taxi)
    t.rv0 = rv0_map(league, t.pool, t.act, t.lineup, t.omega)
    t.cuts, t.c, t.cut_players = crunch(
        league, t.pool, t.act, t.lineup, t.picks, t.free_taxi, t.omega
    )


def apply_tx(
    league: LeagueState,
    t: TeamCtx,
    add_players: Sequence[PlayerV] = (),
    remove_ids: Iterable[str] = (),
    add_picks: Sequence[pk.Pick] = (),
    remove_pick_keys: Iterable[str] = (),
) -> TeamCtx:
    """Post-transaction team state. Added players join the active roster."""
    rm = set(remove_ids)
    rm_pk = set(remove_pick_keys)
    removed_v = sum(p.v for p in t.pool if p.sid in rm)
    pool = [p for p in t.pool if p.sid not in rm] + list(add_players)
    act = [p for p in t.act if p.sid not in rm] + list(add_players)
    picks = [p for p in t.picks if p.key not in rm_pk] + [
        replace(
            p,
            owner_rid=t.rid,
            label=p.label if p.slot is not None else f"{p.year} R{p.round}"
            + (" (own)" if p.origin_rid == t.rid else f" (from {p.origin_name})"),
        )
        for p in add_picks
    ]
    t2 = TeamCtx(
        name=t.name, rid=t.rid, omega=t.omega, pool=pool, act=act, taxi=t.taxi,
        reserve_ids=t.reserve_ids,
        players_v_sum=t.players_v_sum - removed_v + sum(p.v for p in add_players),
        picks=picks, faab=t.faab, free_taxi=t.free_taxi,
    )
    t2.lineup = solve(pool, league.replacement, league.params)
    t2.nc = now_credit(league, pool, t2.lineup, picks)
    picks_sum = sum(p.p for p in picks)
    t2.a = t2.players_v_sum + picks_sum
    t2.f = picks_sum + sum(p.v for p in t2.taxi)
    t2.cuts, t2.c, t2.cut_players = crunch(
        league, pool, act, t2.lineup, picks, t2.free_taxi, t.omega
    )
    return t2
