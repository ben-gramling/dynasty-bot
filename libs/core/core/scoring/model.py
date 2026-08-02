"""League/team state built from a Snapshot: crosswalk join, replacement lines,
pick pricing, lineups (strength map + waiver ΔL only), posture, and the taxi/roster
mechanics (§8) that gate trade legality. Nothing here feeds the v4 trade
coordinates except raw KTC values: the `solve()` lineup built here is the league-tab /
waiver model (q, u, replacement) and never enters the trade path (§11.2), which
reads `lineup.starter_sum` over `act + taxi` instead."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Iterable, Mapping, Sequence

from core.scoring import ktc_picks as kp
from core.scoring import picks as pk
from core.scoring import posture as ps
from core.scoring.lineup import BIG, GROUPS, Lineup, PlayerV, solve
from core.scoring.params import Params
from core.scoring.snapshot import Snapshot


@dataclass(slots=True)
class TeamCtx:
    name: str
    rid: int
    pool: list[PlayerV]
    act: list[PlayerV]
    taxi: list[PlayerV]
    reserve_ids: frozenset[str]
    players_v_sum: float  # Σ v over ALL rostered players (incl taxi, IR)
    picks: list[pk.Pick]
    faab: int
    free_taxi: int
    lineup: Lineup = None  # type: ignore[assignment]

    @property
    def L(self) -> float:
        return self.lineup.L

    @property
    def picks_mv(self) -> float:
        """Pick wealth at face KTC tranche value (§1 — the number everyone sees)."""
        return sum(p.mv for p in self.picks)

    @property
    def a(self) -> float:
        """Total face wealth: players at v + picks at tranche."""
        return self.players_v_sum + self.picks_mv

    @property
    def f(self) -> float:
        """Future assets: picks at tranche + taxi stash values (league tab)."""
        return self.picks_mv + sum(p.v for p in self.taxi)


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
    group_rank: dict[str, dict[str, int]]  # group -> team -> league rank of lineup sum
    postures: dict[str, dict]  # §4: team -> posture dict (label, evidence, source)
    fa_rookies: list[PlayerV]
    fa_vets: list[PlayerV]
    rookie_rank: dict[str, int]
    roster_cap: int
    taxi_cap: int
    # §3.1 v3.4: the #1 overall KTC value in the snapshot (every player, not just
    # rostered ones) — KTC's calculator caps its adjustment curve at this + 80
    top_ktc_value: float
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
    """Deterministic 'today' for the injury return-window test: season start
    (Sleeper state; Sept 1 fallback) plus the elapsed weeks."""
    start = snapshot.state.get("season_start_date")
    season = int(snapshot.state.get("season") or snapshot.draft["season"])
    base = date.fromisoformat(start) if start else date(season, 9, 1)
    return base + timedelta(days=7 * max(0, snapshot.week - 1))


def _availability_u(params: Params, asset: Mapping | None, offseason: bool, ref: date) -> float:
    """u = 1 offseason; in-season OUT players are lineup-discounted, never revalued.
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
    # §3.1 v3.4 cap input: the top overall KTC value across the whole player
    # table (the site reads playersArray[0].value — rostered or not)
    top_ktc_value = max(
        (float((a.get("oneQBValues") or {}).get("value") or 0) for a in ktc_by_id.values()),
        default=0.0,
    )
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

    # free-agent pool + replacement lines (league-tab / waiver anchors)
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
        pool = pool + taxi_shadows(params, taxi)  # erratum 11 (no-op at mult 0)
        teams[name] = TeamCtx(
            name=name,
            rid=int(r["roster_id"]),
            pool=pool,
            act=act,
            taxi=taxi,
            reserve_ids=frozenset(reserve_ids),
            players_v_sum=sum(p.v for p in roster_players),
            picks=[],
            faab=budget - int((r.get("settings") or {}).get("waiver_budget_used") or 0),
            free_taxi=max(0, taxi_cap - len(taxi)),
        )
    for t in teams.values():
        t.lineup = solve(t.pool, replacement, params)

    rank_l = {
        name: i + 1
        for i, name in enumerate(sorted(teams, key=lambda n: (-teams[n].lineup.L, n)))
    }
    group_rank: dict[str, dict[str, int]] = {}
    for grp in GROUPS:
        ordered = sorted(
            teams, key=lambda n: (-teams[n].lineup.group_sums[grp], n)
        )
        group_rank[grp] = {name: i + 1 for i, name in enumerate(ordered)}

    # pick ownership + pricing (current-year picks cease to exist once the draft completes)
    rid2name = {t.rid: n for n, t in teams.items()}
    slot_of_roster = {int(rid): int(slot) for slot, rid in snapshot.draft["slot_to_roster_id"].items()}
    # §1 v7.4: KTC's own numbered current-year picks. The site generates these
    # client-side, so they are absent from the scraped payload and have to be
    # regenerated (`ktc_picks`) — and only when the two calculator globals say
    # the site is actually producing them, for this year. Missing globals means
    # NO current-year price: `price_pick` raises rather than quietly reverting
    # to the generic tranche, which is the failure that made our gate disagree
    # with the counterparty's screen in the first place.
    calc = snapshot.ktc_calculator or {}
    numbered = None
    if calc.get("league_year_phase") is not None and draft_pre:
        try:
            numbered = kp.numbered_pick_values(
                snapshot.ktc_assets,
                draft_year=current_year,
                phase=int(calc["league_year_phase"]),
                site_draft_year=calc.get("draft_year"),
            )
        except (ValueError, NotImplementedError) as exc:
            alerts.append(f"no KTC numbered picks for {current_year}: {exc}")
    elif draft_pre:
        alerts.append(
            "KTC calculator globals missing from the snapshot — current-year "
            "picks cannot be priced (see core.ktc.fetch_calculator_globals)"
        )

    years = [y for y in (current_year, current_year + 1, current_year + 2) if draft_pre or y != current_year]
    owner = pk.pick_ownership(list(rid2name), snapshot.traded_picks, years)
    for (year, rnd, origin_rid), owner_rid in sorted(owner.items()):
        p = pk.price_pick(
            year=year, rnd=rnd, origin_rid=origin_rid, origin_name=rid2name[origin_rid],
            owner_rid=owner_rid, owner_name=rid2name[owner_rid], current_year=current_year,
            slot_of_roster=slot_of_roster, tranches=tranches, rank_l=rank_l,
            my_rid=int(snapshot.my_roster_id), numbered=numbered,
        )
        teams[rid2name[owner_rid]].picks.append(p)

    # §4 posture (observed trades only; override wins)
    def name_of(sid: str) -> str:
        p = players.get(sid)
        if p is not None:
            return p.name
        sup = snapshot.player_names.get(sid)
        return sup.get("name", f"#{sid}") if sup else f"#{sid}"

    postures = ps.classify_postures(
        snapshot.transactions,
        rid2name,
        name_of,
        window_days=params.posture_window_days,
        min_trades=params.posture_min_trades,
        overrides=snapshot.posture_overrides,
    )
    if not snapshot.transactions:
        alerts.append("no transaction history in snapshot — every posture defaults NEUTRAL")

    return LeagueState(
        snapshot=snapshot, params=params, players=players, ktc_by_id=ktc_by_id,
        teams=teams, me=me, replacement=replacement, board=board, tranches=tranches,
        rank_l=rank_l, group_rank=group_rank, postures=postures,
        fa_rookies=fa_rookies, fa_vets=fa_vets, rookie_rank=rookie_rank,
        roster_cap=roster_cap, taxi_cap=taxi_cap, top_ktc_value=top_ktc_value,
        current_year=current_year,
        draft_pre=draft_pre, offseason=offseason, rostered=frozenset(rostered), alerts=alerts,
    )


# ------------------------------------------------- taxi/roster mechanics (§8)


def taxi_pre_lock(league: LeagueState) -> bool:
    """Taxi adds are legal until the league's lock (offseason + weeks 1..taxi_lock_week)."""
    return league.offseason or league.snapshot.week <= league.params.taxi_lock_week


def taxi_eligible(league: LeagueState, p: PlayerV) -> bool:
    """House rule: only 1st/2nd-year players can be placed on taxi."""
    rec = league.ktc_by_id.get(str(p.ktc_id))
    if rec is not None:
        return int(rec.get("seasonsExperience") or 0) <= league.params.taxi_eligible_max_exp
    return bool(p.rookie)


def taxi_shadows(params: Params, taxi: Sequence[PlayerV]) -> list[PlayerV]:
    """Erratum 11: discounted copies of stashed players, backup-insurance only in
    effect (a shadow outranking a starter models 'would promote him'). sid gets a
    ':taxi' suffix so shadows never collide with real removals or starter ids."""
    m = params.taxi_insurance_mult
    if m <= 0:
        return []
    return [
        replace(p, sid=f"{p.sid}:taxi", v=m * p.v) for p in taxi if p.v > 0
    ]


def _min_starter_v(lineup) -> float:
    """Would-he-start threshold: the weakest current starter. 0 if any slot is
    unfilled (a thin roster starts any warm body — never stash him)."""
    starters = [p for grp in lineup.starters.values() for p in grp]
    if len(starters) < 9:
        return 0.0
    return min(p.v for p in starters)


def taxi_slot_demand(league: LeagueState, t: TeamCtx) -> int:
    """Roster-spot shortfall the team already faces (incoming current-year picks
    included pre-draft) — free taxi slots up to this count are spoken for as
    overflow absorption and must not be consumed by stash routing."""
    p_cy = sum(1 for p in t.picks if p.year == league.current_year) if league.draft_pre else 0
    return max(0, len(t.act) + p_cy - league.roster_cap)


def routed_split(
    league: LeagueState,
    t: TeamCtx,
    add_players: Sequence[PlayerV],
    route_taxi: bool = True,
    slots: int | None = None,
) -> tuple[list[PlayerV], list[PlayerV]]:
    """Erratum 10: pre-lock, incoming taxi-eligible players who would not crack the
    starting lineup are stashed on SURPLUS free taxi slots (no active spot consumed);
    everyone else joins the active roster. Slots already needed to absorb the team's
    own overflow (taxi_slot_demand) are never consumed. Post-lock: everyone is active."""
    if not route_taxi or not taxi_pre_lock(league):
        return list(add_players), []
    left = (t.free_taxi if slots is None else slots) - taxi_slot_demand(league, t)
    thresh = _min_starter_v(t.lineup) if t.lineup is not None else 0.0
    to_active: list[PlayerV] = []
    to_taxi: list[PlayerV] = []
    for p in sorted(add_players, key=lambda x: (-x.v, x.sid)):
        if left > 0 and p.v < thresh and taxi_eligible(league, p):
            to_taxi.append(p)
            left -= 1
        else:
            to_active.append(p)
    return to_active, to_taxi


def apply_tx(
    league: LeagueState,
    t: TeamCtx,
    add_players: Sequence[PlayerV] = (),
    remove_ids: Iterable[str] = (),
    add_picks: Sequence[pk.Pick] = (),
    remove_pick_keys: Iterable[str] = (),
    route_taxi: bool = True,
) -> TeamCtx:
    """Post-transaction team state (legality/sequencing only — never a score input).
    Added players join the active roster unless erratum-10 routing stashes them."""
    rm = set(remove_ids)
    rm_pk = set(remove_pick_keys)
    # Erratum 9: departures debit full value wherever the player lives — pool OR
    # taxi (shadows carry a ':taxi' sid suffix and discounted v; never sum them).
    removed_v = sum(p.v for p in t.pool if p.sid in rm)
    removed_v += sum(p.v for p in t.taxi if p.sid in rm)
    taxi_kept = [p for p in t.taxi if p.sid not in rm]
    n_taxi_out = len(t.taxi) - len(taxi_kept)
    free_taxi = t.free_taxi
    if n_taxi_out and taxi_pre_lock(league):
        # pre-lock the freed slot is refillable; post-lock it is dead capacity
        free_taxi += n_taxi_out
    to_active, to_taxi = routed_split(league, t, add_players, route_taxi, slots=free_taxi)
    taxi = taxi_kept + to_taxi
    free_taxi -= len(to_taxi)
    pool = [
        p
        for p in t.pool
        if p.sid not in rm and not (p.sid.endswith(":taxi") and p.sid[:-5] in rm)
    ] + to_active + taxi_shadows(league.params, to_taxi)
    act = [p for p in t.act if p.sid not in rm] + to_active
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
        name=t.name, rid=t.rid, pool=pool, act=act, taxi=taxi,
        reserve_ids=t.reserve_ids,
        players_v_sum=t.players_v_sum - removed_v + sum(p.v for p in add_players),
        picks=picks, faab=t.faab, free_taxi=free_taxi,
    )
    t2.lineup = solve(pool, league.replacement, league.params)
    return t2
