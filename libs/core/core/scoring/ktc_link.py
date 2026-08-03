"""KTC trade-calculator deep links — a companion to the §3.1 fairness gate.

A link opens the SAME calculator our gate ports (`core.scoring.ktc_adjust`) at the
settings the gate assumes. Any deviation in the query parameters makes the number on
the league-mate's screen disagree with `gate.adj_give` / `gate.adj_get`, which is the
whole point of the link. The parameter contract is documented, with its derivation,
in `docs/keeptradecut.md` § "trade-calculator URL contract".

Two facts drive the design:

- **Picks link at whatever the gate priced, which is the point.** `Asset.v` is
  `Pick.mv`, and since v7.4 that is KTC's NUMBERED entry for a current-year pick
  ("2026 Pick 1.01", id 202611) and the generic tranche for a future one. So a
  current-year pick links numbered, a future pick links its tranche, and either
  way the page total equals `adj_give`/`adj_get`. Through v7.3 this linked the
  tranche for everything and disclosed the numbered id as an alternative — that
  was backwards, and it is exactly why our gate read 9,415/10,069 against a page
  showing 9,421/10,198.
- **A future pick's band follows its TRADE DIRECTION (v7.5), never a forecast.**
  `Pick.band` encodes it: my picks link Early (I would send them — the dear end),
  everyone else's link Late (I would receive them — the cheap end). A current-year
  pick's band is its known slot. Read the stored field; never key on
  `(year, round)` alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlencode

from core.scoring import ktc_picks as pk_ids
from core.scoring import picks as pk

TC_BASE = "https://keeptradecut.com/trade-calculator"

# Mirror of lineup.BIG, the "no KTC id" sentinel on PlayerV.ktc_id. Mirrored rather
# than imported to keep this module off the lineup import path (§11.2).
NO_KTC_ID = 10**9

# KTC's client-side cap: total assets across BOTH sides of the calculator.
# Live `addPlayer`: if(!(teamOne.players.length+teamTwo.players.length>=12)).
MAX_TC_ASSETS = 12

# The settings our gate assumes. `format=1` is load-bearing: without it the site
# falls back to its Superflex cookie and every value on the page is the wrong column.
TC_PARAMS: tuple[tuple[str, str], ...] = (
    ("var", "5"),        # tcFilters.variance; ktc_adjust hardcodes 5
    ("pickVal", "0"),    # no RDP scaling: value = round(v + v*pickVal/100)
    ("format", "1"),     # 1 = 1QB (our league), 2 = Superflex
    ("isStartup", "0"),  # dynasty, not startup
    ("tep", "0"),        # tight-end premium off
)

# Emission order of the query string, verbatim from the live site's setURL({...}).
_KEY_ORDER = ("var", "pickVal", "teamOne", "teamTwo", "format", "isStartup", "tep")


@dataclass(frozen=True, slots=True)
class NumberedNote:
    """A current-year pick that KTC also carries as a numbered entry, priced above
    the tranche we link. Disclosed to the user, never silently substituted."""

    name: str          # engine label, e.g. "2026 1.01"
    tranche_id: int    # the id we actually link, e.g. 1527 ("2026 Early 1st")
    numbered_id: int   # KTC's numbered entry, e.g. 202611 ("2026 Pick 1.01")
    tranche_v: float   # the value our gate priced it at


@dataclass(frozen=True, slots=True)
class Link:
    """A built calculator link.

    `url` is None when a side would be emitted EMPTY although its input was not —
    KTC treats `teamOne=` as absent and would render a one-sided giveaway, so we
    refuse to hand back a structurally-valid wrong link. Check `complete` (or
    `url is None`) before printing.

    `pairs` has exactly one entry per INPUT asset, in `give + get` order, so a
    renderer can always zip it against its own labels; a dropped asset carries
    `None`. Never zip `one`/`two` against input assets — drops shift them.
    """

    url: str | None
    one: tuple[int, ...]
    two: tuple[int, ...]
    dropped: tuple[str, ...]
    pairs: tuple[tuple[str, int | None], ...]
    numbered: tuple[NumberedNote, ...]
    complete: bool

    @property
    def numbered_url(self) -> str | None:
        """The same trade with current-year picks swapped to KTC's NUMBERED ids —
        what the counterparty sees if they type the pick into their own search box.
        Its total will NOT equal our gate's adjusted totals. None when there is
        nothing to disclose or the primary link is incomplete."""
        if not self.numbered or self.url is None:
            return None
        swap = {n.tranche_id: n.numbered_id for n in self.numbered}
        one = tuple(swap.get(i, i) for i in self.one)
        two = tuple(swap.get(i, i) for i in self.two)
        return _build_url(one, two)


def _build_url(one: Sequence[int], two: Sequence[int]) -> str:
    fixed = dict(TC_PARAMS)
    fields = {
        **fixed,
        "teamOne": "|".join(str(i) for i in one),
        "teamTwo": "|".join(str(i) for i in two),
    }
    # urlencode percent-encodes the pipes; the site decodeURIComponent's the whole
    # query, so %7C and a literal | are equivalent. Encoded is the safe form.
    return f"{TC_BASE}?{urlencode([(k, fields[k]) for k in _KEY_ORDER])}"


def rdp_ids(league: Any) -> dict[tuple[int, str, int], int]:
    """(year, band, round) -> KTC playerID for the generic RDP tranches.

    Derived from the snapshot every call — `docs/keeptradecut.md` warns the pick
    asset list rolls forward during the season, so this must never be hardcoded.
    Malformed RDP names are SKIPPED rather than raising: a partial table degrades
    individual picks into `dropped` (disclosed), whereas raising here would take
    down every command that builds a league.

    Note `league.ktc_by_id` cannot be used — it filters RDP out.
    """
    out: dict[tuple[int, str, int], int] = {}
    for a in league.snapshot.ktc_assets:
        if a.get("position") != "RDP":
            continue
        parts = str(a.get("playerName", "")).split()
        if len(parts) != 3:
            continue
        year_s, band, rd_word = parts
        if not year_s.isdigit() or rd_word not in pk.WORD_ROUND:
            continue
        try:
            out[(int(year_s), band, pk.WORD_ROUND[rd_word])] = int(a["playerID"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def ktc_names(league: Any) -> dict[int, str]:
    """KTC playerID -> playerName over the whole snapshot, RDP included."""
    out: dict[int, str] = {}
    for a in league.snapshot.ktc_assets:
        try:
            out[int(a["playerID"])] = str(a["playerName"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


# One implementation of the id rule, two names. The whole deep-link contract
# rests on it, so a second copy would be a drift hazard (§ ktc_picks).
numbered_pick_id = pk_ids.numbered_pick_id


def ktc_id_of(a: Any, ids: Mapping[tuple[int, str, int], int]) -> int | None:
    """The KTC playerID an engine Asset links as, or None if it has none.

    None means "cannot be represented on the calculator" and the caller MUST
    disclose it — never drop it silently.
    """
    if a.kind == "player":
        p = a.player
        if p is None or a.unvalued:
            return None
        kid = getattr(p, "ktc_id", NO_KTC_ID)
        return None if kid is None or kid >= NO_KTC_ID else int(kid)
    if a.kind == "pick":
        p = a.pick
        if p is None:
            return None
        # §1 v7.4: a pick with a KNOWN SLOT is a current-year pick, and the gate
        # now prices it at KTC's NUMBERED entry — so the link must carry the
        # numbered id or the page total would not be the number we quoted. (Up
        # to v7.3 this linked the tranche and disclosed the numbered id as an
        # alternative; that was backwards once the numbered price became the
        # one we score.)
        slot = getattr(p, "slot", None)
        if slot is not None:
            return numbered_pick_id(int(p.year), int(p.round), int(slot))
        # band from the stored field — v7.5: the pessimistic trade-direction
        # band (mine → Early, theirs → Late), which is what the gate priced.
        return ids.get((int(p.year), str(p.band), int(p.round)))
    return None


def _numbered_note(a: Any, kid: int, current_year: int | None) -> NumberedNote | None:
    """v7.4: nothing to disclose any more. The primary link carries the numbered
    id and the gate prices the numbered value, so the page total IS what we
    quoted — the whole reason this note existed (two prices for one pick, only
    one of them linked) is gone. Kept as a no-op so `Link.numbered` /
    `numbered_url` stay in the dataclass for old callers."""
    return None


def tc_link(
    give: Iterable[Any],
    get: Iterable[Any],
    ids: Mapping[tuple[int, str, int], int],
    *,
    current_year: int | None = None,
) -> Link:
    """Build the calculator link for one leg.

    Convention: `teamOne` = what WE SEND. On the page Team 1 is the left column and
    is labelled "Team 1 gets", i.e. the counterparty's receive side — which matches
    `ktc_adjust.adjusted_totals(give_values, get_values, ...)` treating side one as
    `give`. So teamOne total == `gate.adj_give`.

    Raises ValueError when the trade exceeds KTC's 12-asset cap, counted on INPUT
    assets as well as emitted ids (a package KTC would truncate must not slip
    through just because one asset was dropped for an unrelated reason).
    """
    give = list(give)
    get = list(get)
    if len(give) + len(get) > MAX_TC_ASSETS:
        raise ValueError(
            f"KTC's calculator holds at most {MAX_TC_ASSETS} assets across both "
            f"sides; got {len(give)} + {len(get)}"
        )

    one: list[int] = []
    two: list[int] = []
    dropped: list[str] = []
    pairs: list[tuple[str, int | None]] = []
    numbered: list[NumberedNote] = []

    for side, assets in (("one", give), ("two", get)):
        for a in assets:
            kid = ktc_id_of(a, ids)
            pairs.append((a.name, kid))
            if kid is None:
                dropped.append(a.name)
                continue
            (one if side == "one" else two).append(kid)
            note = _numbered_note(a, kid, current_year)
            if note is not None:
                numbered.append(note)

    if len(one) + len(two) > MAX_TC_ASSETS:
        raise ValueError(
            f"KTC's calculator holds at most {MAX_TC_ASSETS} assets across both "
            f"sides; resolved {len(one)} + {len(two)} ids"
        )

    # A side that empties out although it had input would render as a giveaway.
    complete = not ((give and not one) or (get and not two))
    url = _build_url(one, two) if complete else None

    return Link(
        url=url,
        one=tuple(one),
        two=tuple(two),
        dropped=tuple(dropped),
        pairs=tuple(pairs),
        numbered=tuple(numbered),
        complete=complete,
    )
