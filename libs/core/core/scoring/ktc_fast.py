"""§3.1 v6 the memoized fast path for the KTC gate — an IDENTITY, not a model.

`ktc_adjust` stays the pristine, auditable port of keeptradecut.com's client-side
JS (pinned integer-exact to 13 live calculator trades, §11.11). This module is
that same arithmetic with the redundancy taken out, and it must agree with it
BIT FOR BIT on every input: §11.14 pins the two against each other over the whole
pool scan plus a synthetic fuzz that deliberately reaches the fallback arms.

Every operation below is the same operation, in the same order, on the same
float operands as `ktc_adjust._adjust` / `reverse_adjust` / `side_raw_adj`. The
only changes are memo tables on EXACT discrete keys and two branch merges that
are textually equivalent:

  M1  memoize reverse_adjust at the TOP-UP call site on (v, r_max, T) — v is
      `math.floor(|e−a|)`, an int; r_max is an integer-valued KTC max; T ∈ 0..3;
      the cap is a snapshot constant. Measured 1,850,522 calls → 77,700 distinct.
      The FALLBACK call site is NOT memoized: its target is an un-floored float,
      7.4% hit rate, and quantising the key breaks exactness long before it buys
      reuse (6 significant digits already mismatches on 983 of 559,718).
  M2  memoize o = process_v(0.5·r_max, r_max, cap, −1) on r_max — 2,455,184 → 201.
  M3  memoize reverse_adjust's seed s = process_v(a, a, t, −1) on (a, t). Keyed
      on t as well as a BECAUSE the fallback arm legitimately runs at t = 10099
      while the snapshot's top-up cap is top_value + 80.
  M4  tmpNerfCount without the sort: an equivalent linear max-scan, strict `>`
      on update so ties keep the earliest original position exactly as the
      stable descending sort did.
  M5  hoist total1/total2/r_max/e/a from the caller — the pool scan already
      holds them as `Package.v_sum` and `vals[0]` (verified bit-identical:
      v_sum == sum(vals) for all 48,539 packages, and vals are v-descending).
  M6  per-asset memo on (v, r_max, nerf) — this is what removes the two `pow`
      calls; 5,898,935 evaluations → 10,177 distinct (0.17% miss).
  M8  branch merge: the `k and b` arm and the `h>y` / `h≤y` arms run the SAME
      top-up code when e>a / a>e respectively, so the test collapses to
      "e>a and ((k and b) or h>y)". The only textual difference between the arms
      is `-1*A` vs `abs(A)` for A ≤ 0, and `x + (-0.0) == x + 0.0` exactly.
  M9  LAZY check_equality: when e>a and h>y (or a>e and h≤y) the top-up arm is
      taken whatever k and b are, so NEITHER check_equality runs — measured on
      73.8% of gate calls.
  M10 e == a ⇒ adj1 = adj2 = 0 on every path (the k&b arm does nothing; the
      fallbacks call reverse_adjust(0, …) which short-circuits to 0, so M > 0
      then fails), so return the raw totals immediately.

Measured: gate 2.939 → 0.631 µs/call (4.66×); the ablation says the gate is the
entire win (a full pool build 17.22 s → 11.76 s from this alone).

PRECONDITION (§11.14). `adjusted_totals_pre` reproduces `_adjust`'s FALLBACK arm
using `r_max` where the port writes `max(max_val1, max_val2)`. Those coincide
exactly when the caller passes `max_val1=max_val2=None` — which is the entire
`adjusted_totals` call shape, and the only shape the pool scan uses. Callers who
supply explicit per-side maxima (the site's possibly-unrounded numbered-pick
values) MUST stay on `ktc_adjust.ktc_adjustment`; there is no fast path for them.
"""

from __future__ import annotations

import math
from typing import Sequence

_FLOOR = math.floor

CAP: float | None = None  # top_value + 80, set by `init`
_O: dict[float, float] = {}  # r_max -> process_v(0.5·r_max, r_max, CAP, -1)
_S: dict[tuple[float, float], float] = {}  # (a, t) -> process_v(a, a, t, -1)
_RA: dict[tuple[int, float, int], int] = {}  # (v, r_max, T) -> reverse_adjust
_ASSET: dict[tuple[float, float, int], float] = {}  # (v, r_max, nerf) -> raw adj


def init(top_value: float) -> None:
    """Bind the snapshot's cap and drop every table.

    `_RA` and `_ASSET` are keyed WITHOUT the cap (it is constant per snapshot,
    and carrying it would put a 4-tuple on the 5.9M-lookup hot path). That is
    only safe if the cap cannot change under a live table, so every entry point
    calls `_ensure` — a single float compare — rather than trusting that some
    caller remembered to `init` first (§11.14)."""
    global CAP
    CAP = top_value + 80.0
    _O.clear()
    _S.clear()
    _RA.clear()
    _ASSET.clear()


def _ensure(top_value: float) -> float:
    """Return the cap for `top_value`, re-initialising if the snapshot changed."""
    cap = top_value + 80.0
    if CAP != cap:
        init(top_value)
    return cap


# ------------------------------------------------------------------ per-asset


def asset_adj(v: float, r_max: float, nerf: int) -> float:
    """`side_raw_adj`'s inner expression (M6), on the exact discrete key."""
    k = (v, r_max, nerf)
    r = _ASSET.get(k)
    if r is None:
        s = (0.05 * (v / CAP) ** 1.3 + 0.05 * (v / (1.05 * r_max)) ** 6 + 0.1) * v
        if nerf > 0:
            m = 1.0 - 0.15 * nerf
            s *= m if m > 0.6 else 0.6
        if s < 0:
            s /= 4
        _ASSET[k] = r = s
    return r


def side_raw_adj(
    vals_desc: Sequence[float], r_max: float, top_value: float
) -> tuple[float, list[tuple[float, float, int]]]:
    """`ktc_adjust.side_raw_adj(vals, r_max, cap, presorted=True)`, memoized.

    `vals_desc` MUST already be v-descending — the port's `presorted=True`
    contract, which every `Package.vals` satisfies by construction."""
    _ensure(top_value)
    half = 0.5 * r_max
    nerf = -1
    total = 0.0
    entries = []
    for v in vals_desc:
        if v < half:
            nerf += 1
        adj = asset_adj(v, r_max, nerf if nerf > 0 else 0)
        total += adj
        entries.append((v, adj, nerf))
    return total, entries


def raw_adj_total(
    vals_desc: Sequence[float], r_max: float, top_value: float
) -> float:
    """`trades._raw_adj_total`, memoized — the total with no entry list."""
    _ensure(top_value)
    half = 0.5 * r_max
    nerf = -1
    total = 0.0
    for v in vals_desc:
        if v < half:
            nerf += 1
        total += asset_adj(v, r_max, nerf if nerf > 0 else 0)
    return total


# ------------------------------------------------------------ reverse_adjust


def _reverse_adjust(e: float, a: float, t: float, r: int) -> int:
    """`ktc_adjust.reverse_adjust` verbatim, with M3 and `process_v` inlined —
    identical operations in identical order, so identical floats."""
    if e == 0:
        return 0
    sk = (a, t)
    s = _S.get(sk)
    if s is None:
        s = (0.05 * (a / t) ** 1.3 + 0.05 * (a / (1.05 * a)) ** 6 + 0.1) * a
        if s < 0:  # unreachable for a > 0; kept so the port maps 1:1
            s /= 4
        _S[sk] = s
    n = a
    if s < e:
        n = max(e / s * a * 0.8, a)
    d = 1.0
    u = 0
    c = 1.0
    m = -1.0
    o = None
    l = n / 2
    mul = None
    if r > 0:
        mul = 1.0 - 0.15 * r
        if mul < 0.6:
            mul = 0.6
    while d > 0.025 and u <= 10:
        dn = 1.05 * n
        i = (0.05 * (l / t) ** 1.3 + 0.05 * (l / dn) ** 6 + 0.1) * l
        if mul is not None:
            i *= mul
        if i < 0:
            i /= 4
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
                dn = 1.05 * n
                i = (0.05 * (l / t) ** 1.3 + 0.05 * (l / dn) ** 6 + 0.1) * l
                if mul is not None:
                    i *= mul
                if i < 0:
                    i /= 4
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
    return _FLOOR(l + 0.5)


# ------------------------------------------------------------------- the gate


def adjusted_totals_pre(
    total1: float,
    total2: float,
    r_max: float,
    e: float,
    entries1: Sequence[tuple[float, float, int]],
    a: float,
    entries2: Sequence[tuple[float, float, int]],
    top_value: float,
) -> tuple[float, float]:
    """`ktc_adjust.adjusted_totals` with M5's operands hoisted (§3.1, v6).

    `total1`/`total2` are the two raw Σv side totals, `r_max` the max asset over
    BOTH sides, and `(e, entries1)` / `(a, entries2)` the two `side_raw_adj`
    passes at that `r_max` — exactly what the pool scan already holds. Returns
    the two adjusted totals the calculator displays, which is what the §3.1 band
    and the §4a favor metric both read.

    See the module docstring's PRECONDITION: valid only for the `max_val*=None`
    call shape."""
    # `adjusted_totals` promises floats; the pool scan already hands us
    # `Package.v_sum` floats (so this is a no-op there), but a caller passing
    # int literals must not get ints back or the two paths stop comparing equal.
    total1 = float(total1)
    total2 = float(total2)
    if e == a:  # M10
        return total1, total2
    cap = _ensure(top_value)

    o = _O.get(r_max)
    if o is None:
        half = 0.5 * r_max
        _O[r_max] = o = (
            0.05 * (half / cap) ** 1.3 + 0.05 * (half / (1.05 * r_max)) ** 6 + 0.1
        ) * half

    # the port's zero guards: `h = e/total1 if total1 else 0.0` (a package of
    # all-zero-valued assets is legal input, if never a real trade)
    h = e / total1 if total1 else 0.0
    y = a / total2 if total2 else 0.0
    if e > a:
        gap = e - a
        ent = entries2
        topup = h > y
    else:
        gap = a - e
        ent = entries1
        topup = not (h > y)
    if not topup:  # M9 — the two check_equality calls run only here
        r_ = e + a
        n_ = min(100, gap / r_ * 100) if r_ != 0 else 0.0
        if not (_FLOOR(10 * n_ + 0.5) / 10 > 5):
            r2 = total1 + total2
            s2 = total1 - total2
            if s2 < 0:
                s2 = -s2
            n2 = min(100, s2 / r2 * 100) if r2 != 0 else 0.0
            topup = not (_FLOOR(10 * n2 + 0.5) / 10 > 5)

    v = _FLOOR(gap)
    T = 0
    if v < o:  # M4 — the port's sorted-by-adj-desc first hit, without the sort
        best_adj = None
        best_nerf = 0
        for _val, adj_, nerf_i in ent:
            if adj_ < v and (best_adj is None or adj_ > best_adj):
                best_adj = adj_
                best_nerf = nerf_i
        if best_adj is not None:
            T = best_nerf + 1

    if topup:
        k_ = (v, r_max, T)  # M1
        S = _RA.get(k_)
        if S is None:
            _RA[k_] = S = _reverse_adjust(v, r_max, cap, T)
        if e > a:
            A = total2 + S - total1
            if A > 0:
                return total1 + A, total2
            return total1, total2 - A
        A = total1 + S - total2
        if A > 0:
            return total1, total2 + A
        return total1 - A, total2

    # the port's rarely-taken fallback arms (NOT memoized — float target)
    V = -1
    if total1 < total2:
        V = 1
    elif total2 < total1:
        V = 2
    M = _reverse_adjust(gap, r_max, 10099, T)
    if M > 0 and V > 0:
        if e < a:  # the h > y fallback
            if V == 2:
                return total1, total2 + (M - (total1 - total2))
            R = M - (total2 - total1)
            if R > 0:
                if R > 10000:  # MAXPLAYERVAL — the port zeroes the adjustment
                    return total1, total2
                return total1, total2 + R
            return total1 - R, total2
        if V == 1:  # the h <= y fallback
            return total1 + (M - (total2 - total1)), total2
        R = M - (total1 - total2)
        if R > 0:
            if R > 10000:
                return total1, total2
            return total1 + R, total2
        return total1, total2 - R
    return total1, total2
