"""§3.2 pick pricing: KTC's real number this year, a pessimistic tranche beyond.

`mv` is the market number — what the counterparty's own calculator charges.
`p_me` is MY lens. They run on two different rules by YEAR, and the split only
ever bites in one of them:

- **Current year — KTC'S OWN NUMBER, one price for everything.** The draft
  order is known, so the slot is known, and KTC publishes a price for that exact
  slot: "2026 Pick 4.01", generated client-side by the trade calculator and
  ported in `ktc_picks`. `p`, `mv` and `p_me` are all that number. There is no
  lens split here and nothing to be pessimistic about — it is the same figure
  the counterparty reads off their own screen, so my book and the market agree
  by construction. **v7.0 got this wrong**: believing KTC published no per-pick
  price, it used the rookie board's n-th-player value as a stand-in, which
  missed in both directions (7,762 vs KTC's 7,897 on a 1.01; 2,927 vs 2,821 on a
  3.03) and let the engine manufacture ΔF on picks that happened to proxy high.
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
side through it and the counterparty's through `mv` (§11.1b). Current-year picks
have `p == mv == p_me`, so the two lenses only ever differ on FUTURE picks —
which is exactly where the uncertainty the pessimism prices actually lives.

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
    mv: float  # market value: KTC's numbered pick this year, the tranche beyond
    band: str
    band_reason: str
    label: str
    # §1 MY lens and the ΔF input. Identical to `mv` for a current-year pick
    # (v7.4 — KTC prices that slot, so there is nothing to disagree about); the
    # pessimistic tranche beyond it (Early when I own the pick, Late when the
    # counterparty does), where the slot is genuinely unknown.
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
    tranches: Mapping[tuple[int, str, int], float],
    rank_l: Mapping[str, int],
    my_rid: int,
    numbered: Mapping[tuple[int, int], float] | None,
) -> Pick:
    own = " (own)" if origin_rid == owner_rid else f" (from {origin_name})"
    mine = owner_rid == my_rid
    if year == current_year:
        slot = slot_of_roster[origin_rid]
        n = 12 * (rnd - 1) + slot
        if numbered is None or (rnd, slot) not in numbered:
            raise ValueError(
                f"no KTC price for {year} {rnd}.{slot:02d}: the numbered-pick "
                "table is unavailable (LEAGUEYEARPHASE / DRAFTYEAR unknown, or "
                "the site is not generating numbered picks). Current-year picks "
                "have no price without it — see core.scoring.ktc_picks."
            )
        # §1 v7.4: ONE number, and it is KTC's own. The draft order is known, so
        # the slot is known, and the calculator publishes a price for that exact
        # slot — the same number the counterparty sees when they type "2026 Pick
        # 4.01" into their side. No proxy, no lens split: `p`, `mv` and `p_me`
        # are all this, because there is nothing here for a lens to disagree
        # about. (v7.0 used the rookie board's n-th player value as a stand-in,
        # on the mistaken belief that KTC published no per-pick price. It does —
        # the calculator generates the 48 client-side — and the stand-in missed
        # in BOTH directions: 7,762 vs 7,897 on the 1.01, 2,927 vs 2,821 on a
        # 3.03. A proxy for a number we can read is just an error.)
        v = float(numbered[(rnd, slot)])
        return Pick(
            year=year, round=rnd, origin_rid=origin_rid, origin_name=origin_name,
            owner_rid=owner_rid, slot=slot, n=n, p=v, mv=v,
            band=band_of_slot(slot), band_reason=f"slot {slot}",
            label=f"{year} {rnd}.{slot:02d}",
            p_me=v, band_me=f"KTC {year} Pick {rnd}.{slot:02d}", mine=mine,
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
