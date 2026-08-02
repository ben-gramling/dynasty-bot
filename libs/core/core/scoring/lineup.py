"""§2 expected lineup strength: exact greedy solver + q-weighted insurance,
plus the RAW starter-sum solve that the v4 ΔS coordinate is built on.

The greedy fill (dedicated slots take the positional top-K, FLEX takes the top-2
remaining flex-eligibles) is provably optimal for raw value and is the exact shape
the reference implementation uses — slot assignment matters because insurance
weights differ per slot type, so this ordering is part of the contract
(it is what makes ΔNC(1.01) = 1,406.4 rather than 1,408.9).

Two solves live here and must never be confused (§11.2):

- `solve()` / `removal_dl()` / `diff_terms()` — the league-tab + waiver strength
  model: q insurance weights, availability multipliers `u`, FA replacement
  lines. NONE of it may enter the trade path.
- `starter_sum()` / `StarterIndex` — the v4 ΔS coordinate: Σ RAW KTC v over the
  max-Σv legal starting lineup, no q, no u, no replacement — and NO δ: v4 has
  no stored-value discount anywhere. This is the ONLY thing `trades.py` is
  allowed to import from this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from core.scoring.params import Params

BIG = 10**9

DEDICATED: tuple[tuple[str, int], ...] = (("QB", 1), ("RB", 2), ("WR", 3), ("TE", 1))
GROUPS: tuple[str, ...] = ("QB", "RB", "WR", "TE", "FLEX")
GROUP_N: dict[str, int] = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 2}
FLEX_ELIGIBLE = ("RB", "WR", "TE")

# --------------------------------------------- §2 v4 the raw starter-sum solve

# Positions in a fixed order so the hot path can index instead of hashing.
POS4: tuple[str, ...] = ("QB", "RB", "WR", "TE")
POS_INDEX: dict[str, int] = {p: i for i, p in enumerate(POS4)}
# dedicated slots per position, then the deepest rung the 2 FLEX slots can reach
DEDICATED_N: tuple[int, int, int, int] = (1, 2, 3, 1)
DEPTH: tuple[int, int, int, int] = (1, 4, 5, 3)  # dedicated + 2 flex (QB is not flex-eligible)


def _greedy_sum(tops: Sequence[Sequence[float]]) -> float:
    """Σv of the max-Σv legal lineup (QB / 2 RB / 3 WR / TE / 2 FLEX) given the
    per-position value lists sorted DESC. Greedy is exact for raw Σv: dedicated
    slots take the positional tops, then the two FLEX slots take the best two
    survivors (§2; brute-force-verified in the test suite)."""
    qb, rb, wr, te = tops
    total = 0.0
    for v in qb[:1]:
        total += v
    for v in rb[:2]:
        total += v
    for v in wr[:3]:
        total += v
    for v in te[:1]:
        total += v
    rest = sorted(rb[2:4] + wr[3:5] + te[1:3], reverse=True)
    for v in rest[:2]:
        total += v
    return total


def _by_pos(players: Iterable) -> list[list[float]]:
    """Raw v per position, DESC. Ties are irrelevant to the SUM; when a caller
    needs the named starters it re-sorts on (−v, ktc_id, sid) (§2 v3.4)."""
    cols: list[list[float]] = [[], [], [], []]
    for p in players:
        i = POS_INDEX.get(p.pos)
        if i is not None:
            cols[i].append(p.v)
    for col in cols:
        col.sort(reverse=True)
    return cols


def starter_sum(players: Iterable) -> float:
    """§2 `S`: Σ raw KTC v over the max-Σv legal starting lineup, solved over
    the players given (active + taxi — taxi is promote-anytime, §8; IR and
    empty slots contribute 0). Non-starting players are worth 0 HERE — they
    count in the OTHER coordinate, total face owned (§2 v4)."""
    return _greedy_sum(_by_pos(players))


def starters(players: Iterable) -> dict[str, list]:
    """The named max-Σv starting lineup — deterministic ties on (−v, ktc_id,
    sid), the §2.1 convention WITHOUT the availability multiplier. Display and
    tests only; the trade coordinates read `starter_sum`."""
    key = lambda p: (-p.v, p.ktc_id, p.sid)
    by_pos: dict[str, list] = {pos: [] for pos in POS4}
    for p in players:
        if p.pos in by_pos:
            by_pos[p.pos].append(p)
    for lst in by_pos.values():
        lst.sort(key=key)
    out: dict[str, list] = {}
    used: set[str] = set()
    for i, pos in enumerate(POS4):
        out[pos] = by_pos[pos][: DEDICATED_N[i]]
        used.update(p.sid for p in out[pos])
    out["FLEX"] = sorted(
        (p for pos in FLEX_ELIGIBLE for p in by_pos[pos] if p.sid not in used), key=key
    )[:2]
    return out


class StarterIndex:
    """Incremental EXACT evaluator for `starter_sum` under small roster deltas
    (§11.10): the pair walk re-solves `S` millions of times, so a full re-solve
    per visit is out of budget.

    Holds one team's per-position raw-value columns (DESC). A delta of a handful
    of players out/in is evaluated by merging only the touched positions' short
    prefixes — the prefix `DEPTH[pos] + |out|` provably contains the post-delta
    top-`DEPTH[pos]`, so the result is identical to a full re-solve (asserted by
    a property test over the fixture rosters and seeded random deltas).

    Values only: `S` is a SUM, so tie-breaking never changes it.
    """

    __slots__ = ("_cols", "_base_tops", "base_sum")

    def __init__(self, players: Iterable):
        self._cols = _by_pos(players)
        self._base_tops = [col[:DEPTH[i]] for i, col in enumerate(self._cols)]
        self.base_sum = _greedy_sum(self._base_tops)

    def sum_after(
        self, out_v: Sequence[Sequence[float]], in_v: Sequence[Sequence[float]]
    ) -> float:
        """`S` after removing `out_v[pos]` and adding `in_v[pos]` (raw values,
        per position, in POS4 order)."""
        tops = self._base_tops
        merged: list[Sequence[float]] = [tops[0], tops[1], tops[2], tops[3]]
        for i in range(4):
            outs = out_v[i]
            ins = in_v[i]
            if not outs and not ins:
                continue
            depth = DEPTH[i]
            lst = list(self._cols[i][: depth + len(outs)])
            for v in outs:
                try:
                    lst.remove(v)  # a value outside the prefix cannot reach the top
                except ValueError:
                    pass
            if ins:
                lst.extend(ins)
                lst.sort(reverse=True)
            merged[i] = lst[:depth]
        return _greedy_sum(merged)

    def delta(
        self, out_v: Sequence[Sequence[float]], in_v: Sequence[Sequence[float]]
    ) -> float:
        """ΔS for this delta — the §2 v4 starter coordinate."""
        return self.sum_after(out_v, in_v) - self.base_sum

    def coords_delta(
        self,
        out_v: Sequence[Sequence[float]],
        in_v: Sequence[Sequence[float]],
        d_face: float,
    ) -> tuple[float, float]:
        """§2 v4 `(ΔS, ΔF)` for this delta — the two objective coordinates,
        raw. NO δ exists anywhere in this module (or the system): any blend
        `ΔW(δ) = ΔS + δ·(ΔF − ΔS)` is the caller's to form, and the v4 spec
        forms none — it reports the endpoints themselves.

        `d_face` IS `ΔF`: the change in Σ face value of everything the side
        owns (players at raw v; picks at whichever lens the caller passed —
        v7 my-lens for my side, tranche for theirs) — for a trade leg simply
        `get.v_sum − give.v_sum`, since face transfers exactly (§11.1). It is
        passed through untouched; `ΔS` costs one incremental starter re-solve.
        """
        return self.sum_after(out_v, in_v) - self.base_sum, d_face


EMPTY4: tuple[tuple[float, ...], ...] = ((), (), (), ())


def pos_columns(players: Iterable) -> tuple[tuple[float, ...], ...]:
    """Pack players into the POS4-ordered raw-value tuples `StarterIndex` eats.
    Off-position assets (picks, UNK) are dropped — they cannot start."""
    cols: list[list[float]] = [[], [], [], []]
    for p in players:
        i = POS_INDEX.get(p.pos)
        if i is not None:
            cols[i].append(p.v)
    return (tuple(cols[0]), tuple(cols[1]), tuple(cols[2]), tuple(cols[3]))


@dataclass(frozen=True, slots=True)
class PlayerV:
    """A lineup-poolable asset: real player or virtual rookie (§3.3)."""

    sid: str
    name: str
    pos: str
    v: float
    u: float = 1.0
    ktc_id: int = BIG
    rookie: bool = False
    age: float | None = None
    unvalued: bool = False

    @property
    def ev(self) -> float:
        return self.u * self.v

    def sort_key(self) -> tuple:
        # §2.1: descending ṽ, ties by KTC playerID asc (deterministic).
        return (-self.u * self.v, self.ktc_id, self.sid)


@dataclass(slots=True)
class Lineup:
    starters: dict[str, list[PlayerV]] = field(default_factory=dict)
    starter_ids: frozenset[str] = frozenset()
    # per backup group: (value used, player or None when falling to R_P)
    backups: dict[str, tuple[float, PlayerV | None]] = field(default_factory=dict)
    # valued non-starter candidates per position (sorted), for O(1) removal deltas
    ns_by_pos: dict[str, list[PlayerV]] = field(default_factory=dict)
    ns_flex: list[PlayerV] = field(default_factory=list)
    L: float = 0.0
    group_sums: dict[str, float] = field(default_factory=dict)

    def slot_rows(self) -> list[dict]:
        """The 9-row lineup table (audit artifact, §12)."""
        rows = []
        for grp in GROUPS:
            got = self.starters.get(grp, [])
            for i in range(GROUP_N[grp]):
                label = grp if GROUP_N[grp] == 1 else f"{grp}{i + 1}"
                if i < len(got):
                    p = got[i]
                    rows.append({"slot": label, "player": p.name, "v": round(p.ev, 1)})
                else:
                    rows.append({"slot": label, "player": None, "v": None})
        return rows


def solve(pool: Iterable[PlayerV], replacement: Mapping[str, float], params: Params) -> Lineup:
    by_pos: dict[str, list[PlayerV]] = {"QB": [], "RB": [], "WR": [], "TE": []}
    for p in pool:
        if p.pos in by_pos:
            by_pos[p.pos].append(p)
    for lst in by_pos.values():
        lst.sort(key=PlayerV.sort_key)

    starters: dict[str, list[PlayerV]] = {}
    used: set[str] = set()
    for grp, n in DEDICATED:
        starters[grp] = by_pos[grp][:n]
        used.update(p.sid for p in starters[grp])
    rem = sorted(
        (p for pos in FLEX_ELIGIBLE for p in by_pos[pos] if p.sid not in used),
        key=PlayerV.sort_key,
    )
    starters["FLEX"] = rem[:2]
    used.update(p.sid for p in starters["FLEX"])

    # §2.2 backups: best VALUED non-starter of the position; if none, R_P.
    # Unvalued (ṽ = 0) players are not deployable insurance (§9.6 — Waller never
    # counts as the TE backup); the roster falls to the FA replacement line instead.
    ns_by_pos: dict[str, list[PlayerV]] = {}
    backups: dict[str, tuple[float, PlayerV | None]] = {}
    for grp, _ in DEDICATED:
        cand = [p for p in by_pos[grp] if p.sid not in used and p.ev > 0]
        ns_by_pos[grp] = cand
        backups[grp] = (cand[0].ev, cand[0]) if cand else (float(replacement[grp]), None)
    ns_flex = sorted(
        (p for pos in FLEX_ELIGIBLE for p in ns_by_pos[pos]), key=PlayerV.sort_key
    )
    backups["FLEX"] = (
        (ns_flex[0].ev, ns_flex[0]) if ns_flex else (float(replacement["FLEX"]), None)
    )

    L = 0.0
    group_sums: dict[str, float] = {}
    for grp in GROUPS:
        q = params.q(grp)
        bval = backups[grp][0]
        got = starters[grp]
        for p in got:
            L += (1 - q) * p.ev + q * bval
        L += float(replacement[grp]) * (GROUP_N[grp] - len(got))  # unfillable slots
        group_sums[grp] = sum(p.v for p in got)

    return Lineup(
        starters=starters,
        starter_ids=frozenset(used),
        backups=backups,
        ns_by_pos=ns_by_pos,
        ns_flex=ns_flex,
        L=L,
        group_sums=group_sums,
    )


def removal_dl(
    lineup: Lineup,
    pool: list[PlayerV],
    p: PlayerV,
    replacement: Mapping[str, float],
    params: Params,
) -> float:
    """L(T) − L(T∖p). Exact; O(1) for non-starters, re-solve for starters."""
    if p.sid in lineup.starter_ids:
        rest = [x for x in pool if x.sid != p.sid]
        return lineup.L - solve(rest, replacement, params).L
    delta = 0.0
    if p.pos in lineup.ns_by_pos:
        cand = lineup.ns_by_pos[p.pos]
        if cand and cand[0].sid == p.sid:
            new = cand[1].ev if len(cand) > 1 else float(replacement[p.pos])
            delta += GROUP_N[p.pos] * params.q(p.pos) * (cand[0].ev - new)
    if p.pos in FLEX_ELIGIBLE and lineup.ns_flex and lineup.ns_flex[0].sid == p.sid:
        new = lineup.ns_flex[1].ev if len(lineup.ns_flex) > 1 else float(replacement["FLEX"])
        delta += GROUP_N["FLEX"] * params.q("FLEX") * (lineup.ns_flex[0].ev - new)
    return delta


def _fmt(p: PlayerV | None, val: float) -> str:
    return f"{p.name} {val:g}" if p is not None else f"FA replacement {val:g}"


def diff_terms(before: Lineup, after: Lineup, params: Params, replacement: Mapping[str, float]) -> list[dict]:
    """§12: dL_terms produced by diffing the solver's own before/after assignments.

    Starter slots are paired by label; each changed slot contributes
    (1−q)·Δṽ; each changed backup rung contributes (n_slots·q)·Δvalue.
    The terms sum to ΔL exactly (asserted by tests, §13.8).
    """
    terms: list[dict] = []
    for grp in GROUPS:
        q = params.q(grp)
        b_st, a_st = before.starters.get(grp, []), after.starters.get(grp, [])
        for i in range(GROUP_N[grp]):
            label = grp if GROUP_N[grp] == 1 else f"{grp}{i + 1}"
            bp = b_st[i] if i < len(b_st) else None
            ap = a_st[i] if i < len(a_st) else None
            bv = bp.ev if bp else float(replacement[grp])
            av = ap.ev if ap else float(replacement[grp])
            if (bp.sid if bp else None) != (ap.sid if ap else None) or bv != av:
                delta = (1 - q) * (av - bv) if (bp and ap) else _unfilled_delta(q, bp, ap, bv, av)
                if abs(delta) > 1e-9:
                    terms.append(
                        {"kind": "starter", "slot": label, "out": _fmt(bp, bv), "in": _fmt(ap, av), "delta": delta}
                    )
    for grp in GROUPS:
        q = params.q(grp)
        (bv, bp) = before.backups.get(grp, (0.0, None))
        (av, ap) = after.backups.get(grp, (0.0, None))
        # weight by the number of filled slots leaning on this rung
        n_b = len(before.starters.get(grp, []))
        n_a = len(after.starters.get(grp, []))
        if bv != av or (bp.sid if bp else None) != (ap.sid if ap else None):
            delta = q * (n_a * av - n_b * bv)
            if abs(delta) > 1e-9:
                terms.append(
                    {"kind": "backup", "slot": grp, "out": _fmt(bp, bv), "in": _fmt(ap, av), "delta": delta}
                )
    return terms


def _unfilled_delta(q: float, bp: PlayerV | None, ap: PlayerV | None, bv: float, av: float) -> float:
    # slot filled <-> unfilled: filled side carries (1−q)·ṽ (+ q·backup accounted in
    # backup terms); unfilled side carries R_P flat. Backup-side weight difference is
    # folded into the backup terms via the filled-slot counts.
    before_contrib = (1 - q) * bv if bp else bv
    after_contrib = (1 - q) * av if ap else av
    return after_contrib - before_contrib
