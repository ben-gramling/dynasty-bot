"""§3.1 the exact KTC trade-calculator value adjustment (v3.4).

Faithful port of the client-side JS in keeptradecut.com/js/site.min.js
(v=WiwBAk3n2D7licE0meE7j34jogL0jLU7m3b7pzOejA4, fetched 2026-07-27): functions
processV, reverseAdjust, checkEquality, adjustPackage. Pinned by §11.11 to 13
live calculator trades captured the same day — integer-exact.

The algorithm is reproduced EXACTLY (iterative reverse mapping with 2.5%
relative tolerance and 0.75/0.25 step factors, JS Math.round semantics, floor
of the raw gap, the max(0.6, 1 − 0.15k) nerf ladder for a side's k-th asset
below half the trade max, cap C = top overall KTC value + 80, the negative
contribution ÷4 rule, the winner-top-up / silent-loser-top-up branches and the
rarely-taken fallback branch). One guard the JS reaches only by accident: a
zero raw-adjustment gap short-circuits reverse_adjust to 0 — the relative-
tolerance loop would otherwise divide by zero (§11.11).

Inputs, as the site uses them at runtime:
  side values — integer asset values in the current format (1QB, tep 0);
  top_value  — the #1 overall KTC value in the snapshot (playersArray[0]);
  variance   — the calculator's tolerance slider, default 5 (league-mates
               check the default);
  max_val1/2 — per-side max asset value, only read by the fallback branch
               (the site passes possibly-unrounded numbered-pick values).
"""

from __future__ import annotations

import math
from typing import Sequence

MAXPLAYERVAL = 10000


def js_round(x: float) -> int:
    """JS Math.round: half-up toward +Infinity."""
    return math.floor(x + 0.5)


def process_v(e: float, a: float, t: float, r: int) -> float:
    """processV(value, tradeMax, cap, nerfIndex) -> per-asset raw adjustment:
    s = (0.05·(e/t)^1.3 + 0.05·(e/(1.05·a))^6 + 0.1) · e, nerfed by
    max(0.6, 1 − 0.15·r) when r > 0; negative results are divided by 4."""
    s = (0.05 * (e / t) ** 1.3 + 0.05 * (e / (1.05 * a)) ** 6 + 0.1) * e
    if r > 0:
        s *= max(0.6, 1 - 0.15 * r)
    if s < 0:
        s /= 4
    return s


def reverse_adjust(e: float, a: float, t: float, r: int) -> int:
    """reverseAdjust(target, tradeMax, cap, nerfCount): the value x with
    process_v(x, n, cap, nerfCount) within 2.5% of target — iterative search,
    0.75 step factor with a 0.25-factor restart pass when the first ten
    iterations miss. Guard (§11.11): target 0 returns 0 — a zero gap needs no
    top-up and the relative-tolerance loop cannot divide by it."""
    if e == 0:
        return 0
    s = process_v(a, a, t, -1)
    n = a
    if s < e:
        n = max(e / s * a * 0.8, a)
    d = 1.0
    u = 0
    c = 1.0
    m = -1.0
    o = None
    l = n / 2
    while d > 0.025 and u <= 10:
        i = process_v(l, n, t, r)
        d = min(abs(i - e) / e, 1)
        if not d <= 0.025:
            o = l
            p = d * l * 0.75
            if i <= e:
                l += p
            else:
                l -= p
        if d < c:
            c = d
            m = o if o is not None else m
            if m is not None and m > a:
                n = m
        if u == 10 and d > 0.05:
            f = 0
            l = max(1, m)
            while d > 0.025 and f <= 10:
                i = process_v(l, n, t, r)
                d = min(abs(i - e) / e, 1)
                if not d <= 0.025:
                    o = l
                    p = d * l * 0.25
                    if i <= e:
                        l += p
                    else:
                        l -= p
                if d < c:
                    c = d
                    m = o
                    if m is not None and m > a:
                        n = m
                f += 1
            l = m
        u += 1
    return js_round(l)


def check_equality(e: float, a: float, t: float) -> bool:
    """checkEquality: side totals within t percent of their sum (JS rounding)."""
    e = max(0, e)
    a = max(0, a)
    r = e + a
    s = abs(e - a)
    n = min(100, s / r * 100) if r != 0 else 0.0
    return not (js_round(10 * n) / 10 > t)


def side_raw_adj(
    values: Sequence[float], r_max: float, cap: float, presorted: bool = False
) -> tuple[float, list[tuple[float, float, int]]]:
    """One side's processV pass, values DESC: the k-th asset below r_max/2
    takes nerf index k−1 (0.85/0.70/0.60… ladder inside process_v). Entries are
    (value, adj, nerf_index) tuples. `presorted` skips the sort for callers
    that already hold v-descending values (the pool scan does)."""
    half = 0.5 * r_max
    denom = 1.05 * r_max
    nerf = -1
    total = 0.0
    entries = []
    for v in values if presorted else sorted(values, reverse=True):
        if v < half:
            nerf += 1
        adj = (0.05 * (v / cap) ** 1.3 + 0.05 * (v / denom) ** 6 + 0.1) * v
        if nerf > 0:
            m = 1.0 - 0.15 * nerf
            adj *= m if m > 0.6 else 0.6
        if adj < 0:
            adj /= 4
        total += adj
        entries.append((v, adj, nerf))
    return total, entries


_side_raw_adj = side_raw_adj  # legacy alias


def _adjust(
    side_one_values: Sequence[float],
    side_two_values: Sequence[float],
    top_value: float,
    variance: int,
    max_val1: float | None,
    max_val2: float | None,
    pre1: tuple[float, list] | None = None,
    pre2: tuple[float, list] | None = None,
    presorted: bool = False,
) -> tuple:
    """adjustPackage() itself. Returns the raw tuple
    (e, a, T, side, value, w, adj1, adj2, total1, total2, entries1, entries2);
    the dict-shaped `ktc_adjustment` wraps it. `pre1`/`pre2` accept a side's
    already-computed (raw adjustment, entries) — the pool scan reuses the give
    side across a whole bracket — and `presorted` skips re-sorting v-descending
    inputs. Both are pure caching: the arithmetic is unchanged."""
    total1 = sum(side_one_values)
    total2 = sum(side_two_values)
    if max_val1 is None:
        max_val1 = max(side_one_values)
    if max_val2 is None:
        max_val2 = max(side_two_values)

    cap = top_value + 80
    r_max = max(max(side_one_values), max(side_two_values))

    e, entries1 = pre1 if pre1 is not None else side_raw_adj(
        side_one_values, r_max, cap, presorted
    )
    a, entries2 = pre2 if pre2 is not None else side_raw_adj(
        side_two_values, r_max, cap, presorted
    )

    o = process_v(0.5 * r_max, r_max, cap, -1)

    h = e / total1 if total1 else 0.0
    y = a / total2 if total2 else 0.0
    v = math.floor(abs(e - a))
    g = int(variance)
    k = check_equality(total1, total2, g)
    b = check_equality(e, a, g)
    w = True

    # tmpNerfCount: nerf level to reverse the gap at, read off the LOSING side's
    # adjustment-sorted assets when the raw gap sits below processV(r_max/2)
    T = 0
    if v < o:
        for _val, adj, nerf_index in sorted(
            entries2 if e > a else entries1, key=lambda x: -x[1]
        ):
            if adj < v:
                T = nerf_index + 1
                break

    side = -1
    value = 0
    adj1 = 0
    adj2 = 0

    if k and b:
        if e > a:
            side = 1
            S = reverse_adjust(v, r_max, cap, T)
            A = total2 + S - total1
            if A > 0:
                value = A
                adj1 = value
            else:
                w = False
                side = 2
                value = -1 * A
                adj2 = value
        elif a > e:
            side = 2
            S = reverse_adjust(v, r_max, cap, T)
            A = total1 + S - total2
            if A > 0:
                value = A
                adj2 = value
            else:
                w = False
                side = 1
                value = -1 * A
                adj1 = value
    elif h > y:
        side = 1
        if e > a:
            S = reverse_adjust(v, r_max, cap, T)
            A = total2 + S - total1
            if A > 0:
                value = A
                adj1 = value
            else:
                w = False
                side = 2
                value = abs(A)
                adj2 = value
        else:
            V = -1
            if total1 + adj1 < total2 + adj2:
                V = 1
            elif total2 + adj2 < total1 + adj1:
                V = 2
            M = reverse_adjust(abs(e - a), max(max_val1, max_val2), 10099, T)
            if M > 0 and V > 0:
                side = V
                if V == 2:
                    R = M - (total1 - total2)
                    if R > 0:
                        value = R
                        adj2 = value
                    else:
                        w = False
                        value = R
                        adj2 = value
                elif V == 1:
                    R = M - (total2 - total1)
                    if R > 0:
                        if R > MAXPLAYERVAL:
                            w = False
                            value = 0
                            side = 1
                            adj1 = 0
                        else:
                            side = 2
                            value = R
                            adj2 = value
                    else:
                        w = True
                        value = -1 * R
                        adj1 = value
            else:
                w = False
    else:
        side = 2
        if a > e:
            S = reverse_adjust(v, r_max, cap, T)
            A = total1 + S - total2
            if A > 0:
                value = A
                adj2 = value
            else:
                w = False
                side = 1
                value = abs(A)
                adj1 = value
        else:
            V = -1
            if total1 + adj1 < total2 + adj2:
                V = 1
            elif total2 + adj2 < total1 + adj1:
                V = 2
            M = reverse_adjust(abs(e - a), max(max_val1, max_val2), 10099, T)
            if M > 0 and V > 0:
                side = V
                if V == 1:
                    R = M - (total2 - total1)
                    if R > 0:
                        value = R
                        adj1 = value
                    else:
                        w = False
                        value = R
                        adj1 = value
                elif V == 2:
                    R = M - (total1 - total2)
                    if R > 0:
                        if R > MAXPLAYERVAL:
                            w = False
                            value = 0
                            side = 1
                            adj2 = 0
                        else:
                            side = 1
                            value = R
                            adj1 = value
                    else:
                        w = True
                        value = -1 * R
                        adj2 = value
            else:
                w = False

    return (e, a, T, side, value, w, adj1, adj2, total1, total2, entries1, entries2)


def ktc_adjustment(
    side_one_values: Sequence[float],
    side_two_values: Sequence[float],
    top_value: float,
    variance: int = 5,
    max_val1: float | None = None,
    max_val2: float | None = None,
) -> dict:
    """Full port of adjustPackage(). Returns:
      raw_adj1/raw_adj2      per-side processV sums
      side                   1 or 2 — the side whose total the adjustment joins
      value                  the adjustment (int; ≥ 0 on the normal paths)
      display                whether the site shows the "+X Value Adjustment" chip
      adj1/adj2              teamOne.adjust / teamTwo.adjust
      adj_total1/adj_total2  totalValue + adjust — the numbers the calculator
                             compares (the §3.1 gate reads exactly these)
      entries1/entries2      per-asset processV detail
    """
    (e, a, T, side, value, w, adj1, adj2, total1, total2, entries1, entries2) = _adjust(
        side_one_values, side_two_values, top_value, variance, max_val1, max_val2
    )
    if value != 0:
        display = bool(w)
        if abs(value / (total1 + total2)) < 0.033:
            display = False
    else:
        display = False
    return {
        "raw_adj1": e,
        "raw_adj2": a,
        "nerf_count": T,
        "side": side,
        "value": value,
        "display": display,
        "adj1": adj1,
        "adj2": adj2,
        "adj_total1": total1 + adj1 if adj1 else total1,
        "adj_total2": total2 + adj2 if adj2 else total2,
        "entries1": [
            {"value": v, "adj": adj, "nerfed": adj_i >= 0, "nerf_index": adj_i}
            for v, adj, adj_i in entries1
        ],
        "entries2": [
            {"value": v, "adj": adj, "nerfed": adj_i >= 0, "nerf_index": adj_i}
            for v, adj, adj_i in entries2
        ],
    }


def adjusted_totals(
    give_values: Sequence[float],
    get_values: Sequence[float],
    top_value: float,
    pre1: tuple[float, list] | None = None,
    pre2: tuple[float, list] | None = None,
    presorted: bool = False,
) -> tuple[float, float]:
    """The §3.1 gate's view: the two adjusted totals KTC's calculator displays
    for (give, get) at the default variance. This is the hot-path entry point —
    the pool scan calls it once per candidate package pair, handing back the
    raw-adjustment passes it already made."""
    r = _adjust(give_values, get_values, top_value, 5, None, None, pre1, pre2, presorted)
    adj1, adj2, total1, total2 = r[6], r[7], r[8], r[9]
    return float(total1 + adj1), float(total2 + adj2)
