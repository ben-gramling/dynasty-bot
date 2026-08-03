"""§11.11: the exact KTC calculator adjustment port.

The 13 verification cases below were captured from keeptradecut.com's live
trade calculator on 2026-07-27 (browser-observed `adjustment` state read out of
the page, one probe per URL) and are pinned here as in-file literals — the test
never reads any capture directory. Values are 1QB / tep=0 with the top overall
asset at 9,999; the `var` column is the calculator's variance slider.
"""

from __future__ import annotations

import pytest

from core.scoring.ktc_adjust import (
    ktc_adjustment,
    process_v,
    reverse_adjust,
)

TOP_VALUE = 9999  # playersArray[0].value on the capture date

# (var, side_one_values, side_two_values, {side, value, display, adj1, adj2})
LIVE_CASES = [
    (5, [6284, 5736], [6130, 6266],
     {"side": 2, "value": 831, "display": True, "adj1": 0, "adj2": 831}),
    (5, [5194, 8026], [6188, 6160],
     {"side": 1, "value": 2540, "display": True, "adj1": 2540, "adj2": 0}),
    (5, [5194, 8026, 6284, 5736], [6188, 6160, 6266, 6130],
     {"side": 1, "value": 2333, "display": True, "adj1": 2333, "adj2": 0}),
    (5, [7919], [6953],
     {"side": 1, "value": 2148, "display": True, "adj1": 2148, "adj2": 0}),
    (5, [7919, 1993], [5042, 4955],
     {"side": 1, "value": 3275, "display": True, "adj1": 3275, "adj2": 0}),
    (5, [9999], [5042, 5138],
     {"side": 1, "value": 5356, "display": True, "adj1": 5356, "adj2": 0}),
    (5, [9999], [3963, 3003, 2499],
     {"side": 1, "value": 6404, "display": True, "adj1": 6404, "adj2": 0}),
    (5, [7919, 1517], [3963, 3003, 2499],
     {"side": 1, "value": 4323, "display": True, "adj1": 4323, "adj2": 0}),
    (5, [7919, 6055, 975], [5129, 3963, 2499, 1993],
     {"side": 1, "value": 4319, "display": True, "adj1": 4319, "adj2": 0}),
    (1, [7919, 1993], [5042, 4955],
     {"side": 1, "value": 3275, "display": True, "adj1": 3275, "adj2": 0}),
    (20, [7919, 1993], [5042, 4955],
     {"side": 1, "value": 3275, "display": True, "adj1": 3275, "adj2": 0}),
    (5, [5815, 5042], [7919, 1517],
     {"side": 2, "value": 2904, "display": True, "adj1": 0, "adj2": 2904}),
    (5, [9999, 975], [5042],
     {"side": 1, "value": 2683, "display": True, "adj1": 2683, "adj2": 0}),
]


@pytest.mark.parametrize("var,one,two,expect", LIVE_CASES)
def test_live_calculator_trades_reproduce_integer_exact(var, one, two, expect):
    """§11.11: every captured calculator trade reproduces integer-exact."""
    r = ktc_adjustment(one, two, top_value=TOP_VALUE, variance=var)
    got = {k: r[k] for k in ("side", "value", "display", "adj1", "adj2")}
    assert got == expect
    # the adjustment always lands on exactly one side's displayed total
    assert r["adj_total1"] == sum(one) + r["adj1"]
    assert r["adj_total2"] == sum(two) + r["adj2"]


def test_all_thirteen_cases_pinned():
    """Guard against the pin set silently shrinking (§9: 13/13 live trades)."""
    assert len(LIVE_CASES) == 13


def test_zero_gap_short_circuits():
    """§11.11: a zero raw-adjustment gap short-circuits to S = 0 — the
    relative-tolerance loop would divide by it otherwise."""
    assert reverse_adjust(0, 5000, 10079, 0) == 0
    # identical packages: raw adjustments are equal, so the gap is 0 and no
    # adjustment is produced at all
    r = ktc_adjustment([5000, 3000], [5000, 3000], top_value=TOP_VALUE)
    assert r["raw_adj1"] == r["raw_adj2"]
    assert r["value"] == 0 and r["display"] is False
    assert r["adj_total1"] == r["adj_total2"] == 8000


def test_consolidation_does_not_cancel_headline():
    """§3.1 / §13 v3.4 headline: at EQUAL raw totals the concentrated side is
    credited +3,377 — the reason the fitted `c` coefficients were retired
    ("Value adjustments dont cancel out")."""
    r = ktc_adjustment([8000, 2000], [5000, 5000], top_value=TOP_VALUE)
    assert (r["side"], r["value"]) == (1, 3377)
    assert (r["adj_total1"], r["adj_total2"]) == (13377, 10000)
    # direction-symmetric: swapping the sides moves the same credit
    rev = ktc_adjustment([5000, 5000], [8000, 2000], top_value=TOP_VALUE)
    assert (rev["side"], rev["value"]) == (2, 3377)
    assert (rev["adj_total1"], rev["adj_total2"]) == (10000, 13377)


def test_nerf_ladder():
    """process_v: a side's k-th asset below half the trade max takes the
    max(0.6, 1 − 0.15k) haircut, floored at 0.60 (§3.1's 0.85/0.70/0.60)."""
    base = process_v(2000, 8000, 10079, -1)
    assert process_v(2000, 8000, 10079, 0) == base  # r > 0 gates the nerf
    assert process_v(2000, 8000, 10079, 1) == pytest.approx(0.85 * base)
    assert process_v(2000, 8000, 10079, 2) == pytest.approx(0.70 * base)
    assert process_v(2000, 8000, 10079, 3) == pytest.approx(0.60 * base)
    assert process_v(2000, 8000, 10079, 9) == pytest.approx(0.60 * base)  # floor


def test_nerf_indices_assigned_on_sub_half_max_assets_only():
    """The ladder counts only assets under r_max/2, in value-desc order — an
    asset at or above the half line never nerfs and never advances the index."""
    r = ktc_adjustment([8000, 4500, 2000, 1000], [8000], top_value=TOP_VALUE)
    idx = [(e["value"], e["nerfed"], e["nerf_index"]) for e in r["entries1"]]
    assert idx == [
        (8000, False, -1),
        (4500, False, -1),  # exactly at r_max/2: not below, no nerf
        (2000, True, 0),
        (1000, True, 1),
    ]


def test_reverse_adjust_inverts_process_v_within_tolerance():
    """reverse_adjust returns a value whose process_v lands inside KTC's own
    2.5% relative tolerance of the target — for targets reachable at the given
    trade max (above that the search rescales its own max, by design, and the
    result is only bounded by the live pins above)."""
    for target in (200.0, 800.0, 1500.0):
        x = reverse_adjust(target, 8000, 10079, 0)
        assert abs(process_v(x, 8000, 10079, 0) - target) / target <= 0.025
    # monotone in the target: a bigger gap always deserves a bigger top-up
    xs = [reverse_adjust(t, 8000, 10079, 0) for t in (200.0, 800.0, 1500.0)]
    assert xs == sorted(xs) and len(set(xs)) == 3
