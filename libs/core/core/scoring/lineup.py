"""§2 expected lineup strength: exact greedy solver + q-weighted insurance.

The greedy fill (dedicated slots take the positional top-K, FLEX takes the top-2
remaining flex-eligibles) is provably optimal for raw value and is the exact shape
the reference implementation uses — slot assignment matters because insurance
weights differ per slot type, so this ordering is part of the contract
(it is what makes ΔNC(1.01) = 1,406.4 rather than 1,408.9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from core.scoring.params import Params

BIG = 10**9

DEDICATED: tuple[tuple[str, int], ...] = (("QB", 1), ("RB", 2), ("WR", 3), ("TE", 1))
GROUPS: tuple[str, ...] = ("QB", "RB", "WR", "TE", "FLEX")
GROUP_N: dict[str, int] = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 2}
FLEX_ELIGIBLE = ("RB", "WR", "TE")


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
