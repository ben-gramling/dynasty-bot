"""§11.14: `ktc_fast` is an IDENTITY over `ktc_adjust`, not an approximation.

The fast path exists only to remove redundant work from the gate. It earns that
right by agreeing with the pinned port BIT FOR BIT, so every assertion here
compares `repr()` (which round-trips floats exactly and distinguishes -0.0),
never `pytest.approx`.

Three layers of evidence:
  1. the §11.11 live-calculator trades, replayed through the fast path;
  2. real package geometry out of the committed fixture league;
  3. a synthetic fuzz built to REACH the fallback arms, which the fleece bracket
     hides in normal operation — the memo tables are on the top-up arm, so the
     fallback is exactly where a naive port would drift.
"""

from __future__ import annotations

import random

import pytest

from core.scoring import ktc_adjust as ka
from core.scoring import ktc_fast as kf
from core.scoring import trades as tr

from .test_ktc_adjust import LIVE_CASES, TOP_VALUE


def _slow(one, two, top_value):
    """The pinned port's adjusted totals for a (side one, side two) pair."""
    return ka.adjusted_totals(one, two, top_value)


def _fast(one, two, top_value):
    """The same, through the hoisted fast entry point."""
    cap = top_value + 80.0
    one = sorted(one, reverse=True)
    two = sorted(two, reverse=True)
    r_max = one[0] if one[0] >= two[0] else two[0]
    e, en1 = ka.side_raw_adj(one, r_max, cap, presorted=True)
    a, en2 = ka.side_raw_adj(two, r_max, cap, presorted=True)
    return kf.adjusted_totals_pre(
        sum(one), sum(two), r_max, e, en1, a, en2, top_value
    )


@pytest.mark.parametrize(
    "one,two",
    [(one, two) for var, one, two, _ in LIVE_CASES if var == 5],
)
def test_live_calculator_trades_match_through_the_fast_path(one, two):
    """§11.14(a): the §11.11 pins hold through `ktc_fast` too.

    Only the variance-5 cases apply — the §3.1 gate is defined at the
    calculator's default variance, which is all the fast path implements."""
    assert repr(_fast(one, two, TOP_VALUE)) == repr(_slow(one, two, TOP_VALUE))


def test_side_raw_adj_and_raw_adj_total_are_bit_identical(league):
    """§11.14(b): the memoized per-asset table (M6) reproduces the port."""
    top_v = league.top_ktc_value
    cap = top_v + 80.0
    kf.init(top_v)
    me_t = league.teams[league.me]
    pkgs = tr._packages(league, tr.give_list(league, me_t))
    for opp in league.opponents:
        pkgs.extend(tr._sorted_opp_pkgs(league, opp)[1])
    assert pkgs, "fixture league produced no packages"
    for p in pkgs[::13]:
        # both the package's own max and a dominating max — the pool scan uses
        # each, depending on which side carries the trade maximum
        for r_max in (p.vals[0], max(p.vals[0], 9000.0)):
            assert repr(ka.side_raw_adj(p.vals, r_max, cap, presorted=True)) == repr(
                kf.side_raw_adj(p.vals, r_max, top_v)
            )
            assert repr(tr._raw_adj_total(p.vals, r_max, cap)) == repr(
                kf.raw_adj_total(p.vals, r_max, top_v)
            )


def test_real_package_pairs_are_bit_identical(league):
    """§11.14(c): the gate agrees on real (my give, their get) geometry."""
    top_v = league.top_ktc_value
    kf.init(top_v)
    me_t = league.teams[league.me]
    mine = tr._packages(league, tr.give_list(league, me_t))
    theirs: list = []
    for opp in league.opponents:
        theirs.extend(tr._sorted_opp_pkgs(league, opp)[1])
    rnd = random.Random(20260801)
    compared = 0
    for _ in range(4000):
        g = mine[rnd.randrange(len(mine))]
        t = theirs[rnd.randrange(len(theirs))]
        assert repr(_fast(g.vals, t.vals, top_v)) == repr(
            _slow(g.vals, t.vals, top_v)
        ), f"{g.vals} vs {t.vals}"
        compared += 1
    assert compared == 4000


def test_fuzz_reaches_the_fallback_arms_and_still_matches(league):
    """§11.14(d): the un-memoized fallback arm is identical too.

    Built without the fleece window on purpose: unconstrained side pairs push
    `_adjust` off the top-up arm, which is the branch the fast path restructures
    most (M8/M9) and the one real traffic almost never reaches."""
    top_v = league.top_ktc_value
    cap = top_v + 80.0
    kf.init(top_v)
    me_t = league.teams[league.me]
    alphabet = sorted(
        {a.v for a in tr.team_assets(league, me_t).values()}
        | {
            p.vals[0]
            for opp in league.opponents
            for p in tr._sorted_opp_pkgs(league, opp)[1]
        },
        reverse=True,
    )
    assert len(alphabet) >= 20, "fixture alphabet too small to fuzz"
    rnd = random.Random(4242)
    fallback = 0
    for _ in range(6000):
        one = sorted(
            (alphabet[rnd.randrange(len(alphabet))] for _ in range(rnd.randint(1, 3))),
            reverse=True,
        )
        two = sorted(
            (alphabet[rnd.randrange(len(alphabet))] for _ in range(rnd.randint(1, 3))),
            reverse=True,
        )
        assert repr(_fast(one, two, top_v)) == repr(_slow(one, two, top_v)), (
            one,
            two,
        )
        r_max = max(one[0], two[0])
        e, _ = ka.side_raw_adj(one, r_max, cap, presorted=True)
        a, _ = ka.side_raw_adj(two, r_max, cap, presorted=True)
        if e != a:
            t1, t2 = sum(one), sum(two)
            h = e / t1 if t1 else 0.0  # the port's zero guard
            y = a / t2 if t2 else 0.0
            kb = ka.check_equality(t1, t2, 5) and ka.check_equality(e, a, 5)
            if not ((e > a and (kb or h > y)) or (a > e and (kb or not h > y))):
                fallback += 1
    assert fallback > 0, "fuzz never reached the fallback arm — it proves nothing"


def test_m5_hoist_precondition_holds_for_every_package(league):
    """§11.14(f): the pool scan hands the gate `Package.v_sum` and `vals[0]`
    instead of recomputing `sum()` / `max()`. That is only bit-exact if v_sum
    IS the float sum and vals ARE v-descending — assert it rather than assume."""
    me_t = league.teams[league.me]
    pkgs = tr._packages(league, tr.give_list(league, me_t))
    for opp in league.opponents:
        pkgs.extend(tr._sorted_opp_pkgs(league, opp)[1])
    assert pkgs
    for p in pkgs:
        assert repr(p.v_sum) == repr(float(sum(p.vals))), p.keys
        assert list(p.vals) == sorted(p.vals, reverse=True), p.keys


def test_pool_build_is_byte_identical_to_the_port(league, monkeypatch):
    """§11.14(g): the whole leg pool — every field of every leg — is unchanged
    by the fast gate. This is the assertion the optimisation actually rests on;
    the per-call tests above only cover the gate in isolation."""
    import hashlib

    def digest():
        h = hashlib.sha256()
        for leg in tr.build_pair_pool(league).legs:
            h.update(repr(leg).encode())
        return h.hexdigest()

    fast = digest()

    # force every fast entry point back through the pinned port
    monkeypatch.setattr(
        kf,
        "side_raw_adj",
        lambda vals, r_max, top_v: ka.side_raw_adj(
            vals, r_max, top_v + 80.0, presorted=True
        ),
    )
    monkeypatch.setattr(
        kf,
        "raw_adj_total",
        lambda vals, r_max, top_v: tr._raw_adj_total(vals, r_max, top_v + 80.0),
    )
    monkeypatch.setattr(
        kf,
        "adjusted_totals_pre",
        lambda t1, t2, r_max, e, en1, a, en2, top_v: ka.adjusted_totals(
            [v for v, _, _ in en1],
            [v for v, _, _ in en2],
            top_v,
            pre1=(e, en1),
            pre2=(a, en2),
            presorted=True,
        ),
    )
    assert digest() == fast


def test_cap_change_reinitialises_the_tables(league):
    """§11.14(e): `_RA` / `_ASSET` are keyed WITHOUT the cap, so a snapshot with
    a different top value must invalidate them.

    Not hypothetical: the port's fallback arm legitimately runs at cap = 10099
    while a snapshot's top-up cap is `top_value + 80`, so two caps genuinely
    coexist inside one process. `_ensure` is what keeps that safe — this test
    fails if anyone ever swaps it for a bare `init()`-once."""
    top_v = league.top_ktc_value
    one, two = [6284.0, 5736.0], [6130.0, 6266.0]
    kf.init(top_v)
    first = _fast(one, two, top_v)
    assert repr(first) == repr(_slow(one, two, top_v))
    # a DIFFERENT snapshot top value: same inputs, genuinely different answer
    other = top_v + 500.0
    assert repr(_fast(one, two, other)) == repr(_slow(one, two, other))
    # and back again — the tables must not be carrying the other cap's entries
    assert repr(_fast(one, two, top_v)) == repr(first)
