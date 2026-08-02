"""§3.2 pick pricing: concrete 2026 board truth, tranche perception, my lens.

v7 adds a SECOND lens. `mv` stays the market number — the generic KTC tranche
every league-mate sees in the calculator, and the only pick price the fairness
gate may use, because KTC ships no numbered per-pick asset (36 RDP tranche
records, `docs/keeptradecut.md`). `p_me` is MY lens, and it runs on TWO
different rules with two different justifications — do not describe it as
uniformly conservative:

- **Current year — EXACTNESS, not pessimism.** The draft order is known, so the
  slot is known: price the pick at its exact board rank,
  `board_value(12·(rnd−1) + slot)`. This is board-vs-tranche error and it points
  BOTH ways — on the committed fixture my 1.01 books 7,762 against a 6,243
  tranche while my 2.09 books 3,236 against 3,504. Acquiring an underpriced
  current-year pick can therefore book ΔF the market does not offer. That is the
  intended reading of "we can calculate it from the actual draft order", but it
  is not a safety property.
- **Future years — PESSIMISM.** The slot is unknown and KTC only publishes
  Early/Mid/Late. Assume the bad end of that range in whichever direction I
  would trade it: a pick I OWN is one I would send, so it is priced **Early**
  (the dear end); a pick the counterparty owns is one I would receive, so it is
  priced **Late** (the cheap end). Ownership fixes the direction because every
  leg is me ↔ one counterparty and the owner is always the sender. Here
  `p_me ≤ mv` on acquisition and `p_me ≥ mv` on disposal, always.

`p_me` is a single per-asset price vector fixed at snapshot build — every asset
has exactly one of them, whoever is looking. So ΔF is still exactly conserved
across a leg's parties WITHIN this lens; the cards simply choose to report my
side through it and the counterparty's through `mv` (§11.1b).

The next-year `rank_L` projection survives as the MARKET band on `mv` — it is
what the league prices the pick at; it just no longer sets what I am willing to
pay, since a forecast of the origin team's finish is not a guarantee of slot.
"""

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
    band: str
    band_reason: str
    label: str
    # §1 v7 MY lens: exact board price in the current year, pessimistic tranche
    # beyond it (Early when I own the pick, Late when the counterparty does).
    # This is the ΔF input; `mv` remains the gate's input.
    p_me: float
    band_me: str
    mine: bool

    @property
    def key(self) -> str:
        return f"pick:{self.year}:R{self.round}:{self.origin_rid}"


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


def pessimistic_band(mine: bool) -> str:
    """§1 v7: the band MY lens prices an unknown-slot pick at. A pick I own is
    one I would be sending, so assume it lands Early (the dear end of the
    round); a pick the counterparty owns is one I would be receiving, so assume
    it lands Late. Never a forecast — a deliberate worst case in the direction
    the asset would travel."""
    return "Early" if mine else "Late"


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
    my_rid: int,
) -> Pick:
    own = " (own)" if origin_rid == owner_rid else f" (from {origin_name})"
    mine = owner_rid == my_rid
    if year == current_year:
        slot = slot_of_roster[origin_rid]
        n = 12 * (rnd - 1) + slot
        # v7: rounded because this value now enters ΔF, and three separate
        # arguments (XTOL's reachable-tie rationale, the integer k5 walk key,
        # and §11.13f's no-tolerance bound) rest on the coordinates being
        # integral. `board_value` interpolates between missing ranks and can
        # return a fraction — today the board is gapless over 1..48, so this is
        # a no-op that keeps a snapshot accident from becoming a premise.
        p = float(round(board_value(board, n).value))
        band = band_of_slot(slot)
        mv = tranches[(year, band, rnd)]
        # v7: the order is known, so MY lens is the exact board price — no
        # pessimism where there is no uncertainty, in either direction.
        return Pick(
            year=year, round=rnd, origin_rid=origin_rid, origin_name=origin_name,
            owner_rid=owner_rid, slot=slot, n=n, p=p, mv=mv,
            band=band, band_reason=f"slot {slot}",
            label=f"{year} {rnd}.{slot:02d}",
            p_me=p, band_me=f"exact slot {slot}", mine=mine,
        )
    if year == current_year + 1:
        rl = rank_l[origin_name]
        band = band_of_rank_l(rl)
        reason = f"{origin_name} rank_L {rl}"
    else:  # two years out: flat Mid — no signal (§3.2; never extrapolate a year premium)
        band = "Mid"
        reason = "two years out: flat Mid"
    v = tranches[(year, band, rnd)]
    # v7: the slot is unknown, so MY lens takes the bad end of the round in the
    # direction this asset would travel (`pessimistic_band`). The rank_L / flat-Mid
    # projection above stays on `mv` — it is what the market charges, not what I pay.
    band_me = pessimistic_band(mine)
    return Pick(
        year=year, round=rnd, origin_rid=origin_rid, origin_name=origin_name,
        owner_rid=owner_rid, slot=None, n=None, p=v, mv=v,
        band=band, band_reason=reason, label=f"{year} R{rnd}{own}",
        p_me=tranches[(year, band_me, rnd)], band_me=band_me, mine=mine,
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
