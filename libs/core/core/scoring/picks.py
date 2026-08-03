"""§3.2 pick pricing: KTC's real number this year, the flat Mid tranche beyond.

ONE price per pick (v7.5), and no forecast anywhere. Two rules by YEAR:

- **Current year — KTC'S OWN NUMBER.** The draft order is known, so the slot is
  known, and KTC publishes a price for that exact slot: "2026 Pick 4.01",
  generated client-side by the trade calculator and ported in `ktc_picks`.
  `p`, `mv` and `p_me` are all that number — it is the same figure the
  counterparty reads off their own screen, so my book and the market agree by
  construction. **v7.0 got this wrong**: believing KTC published no per-pick
  price, it used the rookie board's n-th-player value as a stand-in, which
  missed in both directions (7,762 vs KTC's 7,897 on a 1.01; 2,927 vs 2,821 on a
  3.03) and let the engine manufacture ΔF on picks that happened to proxy high.
- **Future years — FLAT MID (v7.6).** The slot is unknown and KTC only
  publishes Early/Mid/Late; NEVER estimate where inside the round a pick will
  land. Every future pick prices at its round's **Mid** tranche, whoever owns
  it and wherever its origin team is projected to finish. This replaced two
  earlier answers to slot-uncertainty in turn: the `rank_L` projection (v7's
  market band — a forecast, killed by the no-estimates ruling) and v7.5's
  directional pessimism (Early when I send / Late when I receive — no
  forecast, but seat-asymmetric; the user chose the neutral midpoint instead).
  Flat Mid makes the price vector SYMMETRIC: my 2028 2nd and yours are the
  same number, and a same-year same-round swap is exactly ΔF 0.

`p`, `mv` and `p_me` are therefore ONE per-asset price vector fixed at snapshot
build — every asset has exactly one price, whoever is looking, and (unlike
v7.5) the same price in either direction. The `p_me` / `band_me` fields survive
so v7 consumers (ΔF, the card lens note, `total_face`'s lens switch) keep
working, but they can no longer disagree with `mv`.

§2 v8.2: a future pick ALSO carries the ends of KTC's published band —
`mv_lo` (Late) and `mv_hi` (Early) — feeding the REPORTED floor/ceiling
interval only (`trades.pick_swing`). Never a price: every consumer above
still reads the flat Mid, and §11.17 pins that firewall.
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
    mv: float  # KTC's numbered pick this year; the flat Mid tranche beyond (v7.6)
    band: str
    band_reason: str
    label: str
    # §1 v7.5: identical to `p`/`mv` for every pick — the lens split is gone
    # (current year: KTC prices the exact slot; future: flat Mid IS the price,
    # all consumers, v7.6). Fields kept for v7 consumers (ΔF, the card note,
    # `total_face`'s lens switch).
    p_me: float
    band_me: str
    mine: bool
    # §2 v8.2: the ends of KTC's PUBLISHED band for this pick — Late (cheap)
    # and Early (dear) tranche values for a future year; both equal to `mv`
    # when the slot is known (current year), so `mv_hi == mv_lo` ⟺ no swing.
    # NEVER a price: the gate, ΔF, links and every ranking read `mv`/`p`/`p_me`
    # (flat Mid) — these two feed only the REPORTED interval (trades.pick_swing).
    mv_lo: float = 0.0
    mv_hi: float = 0.0

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


# §3.2 v7.6: THE band every unknown-slot pick prices at, for every consumer and
# in both directions. Not a forecast (the rank_L projection died in v7.5) and
# not a worst case (v7.5's Early-out/Late-in pessimism was seat-asymmetric; the
# user chose the neutral midpoint instead): simply the middle of the round.
FUTURE_BAND = "Mid"


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
            mv_lo=v, mv_hi=v,  # slot known — no band, no swing (§2 v8.2)
        )
    # §3.2 v7.6: the slot is unknown and never estimated — every future pick
    # prices at the middle of its round, whoever owns it. The gate, the deep
    # links, ΔF and the board all price this same number.
    band = FUTURE_BAND
    reason = "future year: flat Mid — slot never estimated"
    v = tranches[(year, band, rnd)]
    return Pick(
        year=year, round=rnd, origin_rid=origin_rid, origin_name=origin_name,
        owner_rid=owner_rid, slot=None, n=None, p=v, mv=v,
        band=band, band_reason=reason, label=f"{year} R{rnd}{own}",
        p_me=v, band_me=band, mine=mine,
        # §2 v8.2: the ends of KTC's published band, for the REPORTED interval
        # only — the price above stays flat Mid for every consumer.
        mv_lo=tranches[(year, "Late", rnd)], mv_hi=tranches[(year, "Early", rnd)],
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
