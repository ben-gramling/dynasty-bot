"""§3.2 pick pricing: concrete 2026 board truth, tranche perception, sell floors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

ROUND_WORD = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
WORD_ROUND = {v: k for k, v in ROUND_WORD.items()}
BANDS = ("Early", "Mid", "Late")


@dataclass(frozen=True, slots=True)
class BoardEntry:
    rank: int
    value: float
    pos: str
    name: str
    interpolated: bool = False


@dataclass(frozen=True, slots=True)
class Pick:
    year: int
    round: int
    origin_rid: int
    origin_name: str
    owner_rid: int
    slot: int | None  # 2026 only (order known)
    n: int | None  # overall pick number, 2026 only
    p: float  # truth value — Score/RV/A/F
    mv: float  # market-visible (tranche) value — fairness/anchoring layer
    sell_floor: float
    band: str
    band_reason: str
    label: str

    @property
    def key(self) -> str:
        return f"pick:{self.year}:R{self.round}:{self.origin_rid}"

    def pricing(self) -> dict:
        return {
            "rule": "board" if self.year == 2026 else "tranche",
            "band": self.band,
            "band_reason": self.band_reason,
        }


def build_board(ktc_assets: Sequence[Mapping]) -> dict[int, BoardEntry]:
    """Rookie board from the rookie-flagged KTC records (re-derived every snapshot)."""
    board: dict[int, BoardEntry] = {}
    for a in ktc_assets:
        if a.get("position") == "RDP" or not a.get("rookie"):
            continue
        one = a.get("oneQBValues") or {}
        rank = one.get("rookieRank")
        if rank:
            board[int(rank)] = BoardEntry(
                rank=int(rank),
                value=float(one["value"]),
                pos=a["position"],
                name=a["playerName"],
            )
    return board


def board_value(board: Mapping[int, BoardEntry], n: int) -> BoardEntry:
    """board(n); missing ranks interpolate linearly between neighbors."""
    if n in board:
        return board[n]
    lower = [k for k in board if k < n]
    higher = [k for k in board if k > n]
    if lower and higher:
        lo, hi = max(lower), min(higher)
        blo, bhi = board[lo], board[hi]
        val = blo.value + (bhi.value - blo.value) * (n - lo) / (hi - lo)
        return BoardEntry(rank=n, value=val, pos=blo.pos, name=f"(rank {n} interp.)", interpolated=True)
    edge = board[max(lower)] if lower else board[min(higher)]
    return BoardEntry(rank=n, value=edge.value, pos=edge.pos, name=f"(rank {n} clamp)", interpolated=True)


def build_tranches(ktc_assets: Sequence[Mapping]) -> dict[tuple[int, str, int], float]:
    """The 36 RDP generic tranche values, keyed (year, band, round)."""
    tranches: dict[tuple[int, str, int], float] = {}
    for a in ktc_assets:
        if a.get("position") != "RDP":
            continue
        year_s, band, rd_word = a["playerName"].split()
        tranches[(int(year_s), band, WORD_ROUND[rd_word])] = float(a["oneQBValues"]["value"])
    return tranches


def band_of_slot(slot: int) -> str:
    return "Early" if slot <= 4 else "Mid" if slot <= 8 else "Late"


def band_of_rank_l(rank_l: int) -> str:
    # §3.2: draft order is inverse of finish — weak lineups (rank 9–12) pick Early.
    return "Early" if rank_l >= 9 else "Mid" if rank_l >= 5 else "Late"


def price_pick(
    *,
    year: int,
    rnd: int,
    origin_rid: int,
    origin_name: str,
    owner_rid: int,
    owner_name: str,
    current_year: int,
    slot_of_roster: Mapping[int, int],
    board: Mapping[int, BoardEntry],
    tranches: Mapping[tuple[int, str, int], float],
    rank_l: Mapping[str, int],
) -> Pick:
    own = " (own)" if origin_rid == owner_rid else f" (from {origin_name})"
    if year == current_year:
        slot = slot_of_roster[origin_rid]
        n = 12 * (rnd - 1) + slot
        p = board_value(board, n).value
        band = band_of_slot(slot)
        mv = tranches[(year, band, rnd)]
        return Pick(
            year=year, round=rnd, origin_rid=origin_rid, origin_name=origin_name,
            owner_rid=owner_rid, slot=slot, n=n, p=p, mv=mv,
            sell_floor=max(p, mv), band=band, band_reason=f"slot {slot}",
            label=f"{year} {rnd}.{slot:02d}",
        )
    if year == current_year + 1:
        rl = rank_l[origin_name]
        band = band_of_rank_l(rl)
        reason = f"{origin_name} rank_L {rl}"
    else:  # two years out: flat Mid — no signal (§3.2; never extrapolate a year premium)
        band = "Mid"
        reason = "two years out: flat Mid"
    v = tranches[(year, band, rnd)]
    return Pick(
        year=year, round=rnd, origin_rid=origin_rid, origin_name=origin_name,
        owner_rid=owner_rid, slot=None, n=None, p=v, mv=v, sell_floor=v,
        band=band, band_reason=reason, label=f"{year} R{rnd}{own}",
    )


def pick_ownership(
    rids: Sequence[int], traded_picks: Sequence[Mapping], years: Sequence[int]
) -> dict[tuple[int, int, int], int]:
    """(year, round, origin_rid) -> owner_rid. Base = own picks; overlay trades."""
    owner = {(y, rd, rid): rid for y in years for rd in range(1, 5) for rid in rids}
    for t in traded_picks:
        key = (int(t["season"]), int(t["round"]), int(t["roster_id"]))
        if key in owner:
            owner[key] = int(t["owner_id"])
    return owner
