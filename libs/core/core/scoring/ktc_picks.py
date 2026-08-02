"""KTC's numbered current-year draft picks — the prices the trade calculator
actually uses.

KTC's dynasty-rankings payload (our `data/ktc_raw.json` snapshot) carries only
the 36 generic RDP tranches ("2026 Early 3rd", id 1533). The trade calculator
prices the CURRENT draft year per numbered pick ("2026 Pick 3.02", id 202632)
and those 48 records exist nowhere in the payload: `startTradeCalculatorPage()`
calls `addNumberedPicks()`, which GENERATES them client-side from the rookie
ladder and this year's 12 tranches. This module is that generator.

Faithful port of the client-side JS in keeptradecut.com/js/site.min.js
(captured 2026-08-02, `data/fixtures/ktc/ktc_pick_js_2026-08-02.json`):
functions addNumberedPicks, calcPicksRookies, calcPicksRookiesSingleMode, and
the tepMode-0 slice of updateTEP. Pinned to
`data/fixtures/ktc/tc_capture_2026-08-02.json` — a one-shot live capture whose
500 inputs and 48 `calculated: true` outputs are self-consistent — and exact on
all 48 in both formats. Two of them are independently corroborated by the
user's browser (2026 Pick 3.02, 2026 Pick 4.01).

Scope. `addNumberedPicks` branches on LEAGUEYEARPHASE: 1 -> calcPicksDevy,
2 -> calcPicksRookies, and there is NO else branch — in any other phase the
calculator generates no numbered picks and prices the generic tranches, which
is what the rest of the engine already does. The live phase is 2 and only that
path is ported; `numbered_pick_values` raises for anything else rather than
return numbers it cannot vouch for. calcPicksDevy's source was not captured.
`calc_picks_simple_single_mode` is the (unreachable, unpinned) sibling
generator, ported because it is cheap and documents the shape of the family.

The tep modes (0..3) are computed by the same code with a different value
field; we port tepMode 0 only — the league has no tight-end premium — and the
`tep`/`tepp`/`teppp` columns are simply not produced.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .ktc_adjust import MAXPLAYERVAL, js_round

ROUNDS = 4
SLOTS = 12
NUMBERED_PICKS = ROUNDS * SLOTS  # 48 — calcPicksRookies' fixed 4x12 grid

_UNDEFINED = float("nan")  # stands in for a JS out-of-range array read


def _truthy(x: float) -> bool:
    """JS truthiness of a Number: 0, -0 and NaN are falsy, everything else
    (including ±Infinity) is truthy. Only ever applied to `g[V]`."""
    return bool(x) and not math.isnan(x)


def _at(seq: Sequence[float], i: int) -> float:
    """JS array read: an out-of-range index yields `undefined`. The one call
    site tests truthiness, and `undefined` and NaN are both falsy, so NaN is an
    exact stand-in. With a full board (12 tranches, >=48 rookies) g runs to 45
    and the reads stop at 45; a short rookie list makes g shorter than the push
    count and the tail of the ladder then falls through to the plain eighths."""
    return seq[i] if 0 <= i < len(seq) else _UNDEFINED


def _fmt_key(sf: bool) -> str:
    return "superflexValues" if sf else "oneQBValues"


def _value(rec: Mapping[str, Any], key: str) -> float:
    return rec[key]["value"]


def calc_picks_rookies_single_mode(
    rookie_values: Sequence[float], tranche_values: Sequence[float]
) -> list[float]:
    """calcPicksRookiesSingleMode(rookies, format, tepMode=0, tranches).

    `rookie_values` — every rookie's value in the chosen format, DESC. In the
    JS that is `updateTEP(e, 0, format)`, which writes `record.value` from the
    format block and sorts the array DESC in place, followed by a redundant
    `s.sort` on the same key. Both sorts read only `.value`, so tie order (JS
    sort is stable; the array arrives SF-DESC from calcPicksRookies and carries
    the previous mode's order over) cannot change any number below.

    `tranche_values` — this draft year's 12 generic tranche values in the same
    format, in playersArray order (see `_draft_year_tranches`).

    Returns the flat value array; calcPicksRookies reads it round-major,
    slot-minor at index (round-1)*12 + (slot-1).
    """
    # The JS sorts DESC twice inside this function (updateTEP's own sort, then
    # its own), so it is order-insensitive by construction; mirror that rather
    # than documenting a precondition callers will eventually violate — feeding
    # the snapshot's natural order straight in moves 44 of 48 prices.
    s = sorted(rookie_values, reverse=True)

    # --- shape of the top of the rookie board: the first two gaps, normalised
    # by the mean of the first six.
    n: list[float] = []
    l = 0.0  # h — first gap / mean gap
    i = 0.0  # f — second gap / mean gap
    if len(s) > 6:
        p = 0.0
        d = 0.0
        for u in range(6):
            c = s[u] - s[u + 1]
            p += c
            n.append(c)
            d = max(d, c)  # dead store in the JS too — `d` is never read again
        # If the top seven rookies were all exactly tied, m would be 0 and the
        # JS would price the 1.01/1.02 as NaN; here js_round raises instead.
        m = p / 6
        f = n[1] / m
        h = n[0] / m
        y = (h - 1 + (f - 1)) / 2
        o = min(max(y, 0.0), 1.0)  # likewise dead: computed, never read
        _ = (d, o)  # kept so the structure matches the JS line for line
        l = h
        i = f

    # --- curvature of the rookie ladder: second differences, each normalised
    # by the largest |second difference| in a ±3 window, scaled 0.8.
    v = [0.0]
    g = [0.0]
    k = min(len(s), 4 * len(tranche_values))
    for b in range(1, k - 1):
        v.append(s[b - 1] - s[b] - (s[b] - s[b + 1]))
    for b in range(1, len(v) - 1):
        lo = max(0, b - 3)
        hi = min(len(v) - 1, b + 3)
        d = 0.0
        for w in range(lo, hi + 1):
            d = max(d, abs(v[w]))
        # JS: v[b]/0 -> NaN here, never ±Infinity — d is a max over a window
        # that contains |v[b]|, so d == 0 implies v[b] == 0 (0/0 -> NaN).
        x = v[b] / d if d else _UNDEFINED
        g.append(0.8 * x)

    # --- lay the 48 picks along the tranche ladder: each adjacent tranche pair
    # spans four picks, spaced by eighths of the gap and bent by g[].
    S: list[float] = []
    V = 0
    for A in range(len(tranche_values) - 1):
        M = tranche_values[A]
        R = tranche_values[A + 1]
        O = (M - R) / 8

        if A == 0:
            # Picks 1.01 / 1.02 are priced off the top two rookies, not off the
            # tranche — the 1.01 is worth more than an "Early 1st" is.
            if M < s[0]:
                if M + js_round(1 * O) < s[1]:
                    D = min(MAXPLAYERVAL - 5, 1.02 * s[1])
                else:
                    E = 1 * i + 1
                    D = min(MAXPLAYERVAL - 1, M + js_round(E * O))
                C = min(MAXPLAYERVAL - 1, 1.03 * s[0])
                # `D and` guards a division Python would raise on: in JS a zero
                # D gives ±Infinity or NaN, neither of which is < 0.06, so
                # skipping the test is the identical outcome.
                if D and (C - D) / D < 0.06:
                    C = min(MAXPLAYERVAL - 1, 1.06 * s[0])
            else:
                Y = min(i, 3)
                E = 1 * Y + 1
                B = 1 * min(l, 3) + 1 + E
                D = min(MAXPLAYERVAL - 1, M + js_round(E * O))
                C = min(MAXPLAYERVAL - 1, M + js_round(B * O))
            S.append(C)
            V += 1
            S.append(D)
            V += 1

        # for (var F = 1; F < 8; F++) { ...; V++; F++ } — the body increments F
        # a SECOND time, so F takes 1, 3, 5, 7: four picks per tranche pair.
        F = 1
        while F < 8:
            j = (F - 1) * O
            gv = _at(g, V)
            if _truthy(gv):
                L = O + O * gv
                step = js_round(j + L)  # == round(F*O + O*g[V])
                if A == 0 and F == 1 and M - step < s[2]:
                    # keep pick 1.03 from falling under the RB3/WR3-ish rookie
                    I = min(MAXPLAYERVAL - 10, 1.01 * s[2])
                    S.append(I if I < S[1] else M - step)
                else:
                    S.append(M - step)
            else:
                S.append(M - js_round(F * O))
            V += 1
            F += 2

        if A == len(tranche_values) - 2:
            # tail: two more picks below the last tranche, floored at 0
            S.append(max(0, R - js_round(O)))
            V += 1
            S.append(max(0, R - js_round(3 * O)))
            V += 1

    return S


def calc_picks_simple_single_mode(tranche_values: Sequence[float]) -> list[float]:
    """calcPicksSimpleSingleMode — the rookie-free sibling: pure eighths of each
    tranche gap, no curvature term, 1.01/1.02 extrapolated 7 and 3 eighths above
    the top tranche.

    NOT on the live path and NOT pinned: `addNumberedPicks` only ever calls
    calcPicksDevy (phase 1) or calcPicksRookies (phase 2), and no capture exists
    to verify this against. Ported because it is cheap and it shows the family's
    skeleton without the rookie-board corrections. Its `tepMode` argument is
    accepted and never used by the JS, so all four tep modes coincide.
    """
    r: list[float] = []
    for s in range(len(tranche_values) - 1):
        n = tranche_values[s]
        l = tranche_values[s + 1]
        p = (n - l) / 8
        if s == 0:
            o = min(MAXPLAYERVAL - 1, n + js_round(3 * p))
            i = min(MAXPLAYERVAL - 1, n + js_round(7 * p))
            r.append(i)
            r.append(o)
        d = 1
        while d < 8:
            r.append(n - js_round(d * p))
            d += 2
        if s == len(tranche_values) - 2:
            r.append(max(0, l - js_round(p)))
            r.append(max(0, l - js_round(3 * p)))
    return r


def _draft_year_tranches(
    ktc_assets: Sequence[Mapping[str, Any]], draft_year: int, key: str
) -> list[float]:
    """`playersArray.filter(p => p.playerName.indexOf(DRAFTYEAR + "") > -1)`.

    Two deviations, both inert on real KTC data:
      * order — playersArray is sorted by the page FORMATTYPE's overall `rank`
        ASC; our snapshot's ordering is not guaranteed, so we sort by the
        REQUESTED format's value DESC. RDP ranks are a monotone function of RDP
        values, and both formats rank the 12 same-year tranches identically in
        the fixture and in data/ktc_raw.json, so the two orders coincide.
      * `calculated` records are excluded. The JS cannot see any (calcPicksRookies
        runs before the concat), but a caller could hand us a list that already
        has "2026 Pick 1.01" in it, and that would silently corrupt every price.
    """
    # Anchored and RDP-only. The JS filter is a bare name substring, which is
    # safe there because it runs against a known payload; as a public API it is
    # not — `draft_year=202` matched all 36 tranches across three years and
    # returned a full, plausible, entirely invented 48.
    tag = f"{draft_year} "
    picks = [
        a
        for a in ktc_assets
        if a.get("position") == "RDP"
        and str(a.get("playerName", "")).startswith(tag)
        and not a.get("calculated")
    ]
    picks.sort(key=lambda a: -_value(a, key))
    return [_value(a, key) for a in picks]


def numbered_pick_values(
    ktc_assets: Sequence[Mapping[str, Any]],
    *,
    draft_year: int,
    phase: int,
    sf: bool = False,
    site_draft_year: int | None = None,
) -> dict[tuple[int, int], float]:
    """The 48 numbered current-year picks the trade calculator prices, keyed
    (round, slot) for round 1..4, slot 1..12 — the same numbers the page shows
    in the 1QB column (`sf=True` for the superflex column).

    `ktc_assets` is the raw KTC record list our snapshot carries (the shape of
    `data/ktc_raw.json`'s `players`): each record needs `playerName`, `rookie`
    and `oneQBValues.value` / `superflexValues.value`.

    `phase` is the site's LEAGUEYEARPHASE and is REQUIRED — it is not a thing
    to assume. `core.ktc.fetch_calculator_globals()` scrapes it (and
    `site_draft_year`) straight out of `site.min.js`; pass both through so a
    phase flip becomes a loud failure instead of a wrong price. Only phase 2
    (rookie-draft season, the live value) is ported; see the module docstring.
    """
    if phase == 1:
        raise NotImplementedError(
            "LEAGUEYEARPHASE 1 uses calcPicksDevy, whose source was not captured"
        )
    if phase != 2:
        raise ValueError(
            f"LEAGUEYEARPHASE {phase}: addNumberedPicks generates no numbered "
            "picks outside phases 1 and 2 — price the generic tranches instead"
        )

    if site_draft_year is not None and int(site_draft_year) != int(draft_year):
        raise ValueError(
            f"KTC generates numbered picks only for its DRAFTYEAR "
            f"({site_draft_year}); asked for {draft_year}. Future years are "
            "priced at the generic tranche — there is no numbered pick to quote."
        )

    key = _fmt_key(sf)
    tranches = _draft_year_tranches(ktc_assets, draft_year, key)
    # Exactly 12, because the readout below is a hard 4x12 grid. A 13th tranche
    # makes the ladder emit 52 and shifts the tail block, silently re-pricing
    # 4.11/4.12 while still returning a full 48.
    if len(tranches) != SLOTS:
        raise ValueError(
            f"expected exactly {SLOTS} generic {draft_year} tranches "
            f"(3 bands x 4 rounds), found {len(tranches)}"
        )

    # rawPlayers.filter(p => p.rookie), then sorted DESC by value in the chosen
    # format — the SF pre-sort in calcPicksRookies and updateTEP's own sort both
    # collapse to this, and only the sorted values are ever read.
    rookies = sorted(
        (_value(a, key) for a in ktc_assets if a.get("rookie")), reverse=True
    )
    # The curvature term is indexed by PICK number and runs the whole ladder, so
    # a rookie list shorter than the pick count silently routes the tail into
    # the plain-eighths branch: measured, 47 rookies moves 1 slot, 40 moves 8,
    # 20 moves 26 — every one returning a full, monotone, plausible 48 with no
    # signal at all. Refuse instead.
    if len(rookies) < NUMBERED_PICKS:
        raise ValueError(
            f"the curvature term spans all {NUMBERED_PICKS} picks and needs at "
            f"least that many rookies on the board; found {len(rookies)}. A "
            "shorter ladder yields plausible-but-wrong prices, so this refuses "
            "rather than degrades."
        )

    values = calc_picks_rookies_single_mode(rookies, tranches)
    if len(values) < NUMBERED_PICKS:
        raise ValueError(
            f"the tranche ladder produced {len(values)} prices, need "
            f"{NUMBERED_PICKS} ({len(tranches)} tranches, expected {SLOTS})"
        )

    # `addNumberedPicks` ends by filtering out any generated pick whose value is
    # <= 0 in BOTH formats — such a pick is not on the calculator at all and
    # cannot be typed into a side, so returning it would let a caller price and
    # link an asset the page will not hold. Reachable only via the floored tail
    # (`max(0, R - round(3*O))`); never binds on real data.
    other = calc_picks_rookies_single_mode(
        sorted((_value(a, _fmt_key(not sf)) for a in ktc_assets if a.get("rookie")),
               reverse=True),
        _draft_year_tranches(ktc_assets, draft_year, _fmt_key(not sf)),
    )
    out: dict[tuple[int, int], float] = {}
    for rnd in range(1, ROUNDS + 1):
        for slot in range(1, SLOTS + 1):
            i = (rnd - 1) * SLOTS + (slot - 1)
            if values[i] <= 0 and (i >= len(other) or other[i] <= 0):
                continue
            out[(rnd, slot)] = float(values[i])
    return out


def numbered_pick_id(draft_year: int, rnd: int, slot: int) -> int:
    """`parseInt(DRAFTYEAR + "" + round + slot)` — the slot is NOT zero-padded,
    so 2026 3.02 is 202632 and 2026 3.12 is 2026312."""
    return int(f"{draft_year}{rnd}{slot}")


def numbered_pick_name(draft_year: int, rnd: int, slot: int) -> str:
    """`DRAFTYEAR + " Pick " + round + "." + slot` — here the slot IS zero-padded
    below 10, so 2026 3.2 is "2026 Pick 3.02"."""
    return f"{draft_year} Pick {rnd}.{slot:02d}"
