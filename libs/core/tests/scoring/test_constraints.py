"""§4 v5 the constraint vocabulary: compilation of the three sources under
strict per-team precedence, the pinned §4 example compilations (§11.12(b)'s
shapes), conservative subject parsing, predicate semantics, and the
§11.12(f) posture-parity pin.

The five user examples ("ronak wants draft picks", "joey wants a running
back", "nobody wants stefon diggs", "josh b wants joe burrow", "colin is
willing to trade away treveon henderson") are pinned VERBATIM — the committed
fixtures really do roster Stefon Diggs and Joe Burrow on my team and TreVeyon
Henderson on cmgaither43's, and joeydavis299 really does roster RBs."""

from __future__ import annotations

import pytest

from core.scoring import constraints as cn
from core.scoring import trades as tr

# the user's five §4 examples as market-intel docs (the skill's protocol:
# kind, team, subject, active)
INTEL = [
    {"kind": "WANT", "team": "ronakpatel32", "subject": "draft picks", "active": True},
    {"kind": "WANT", "team": "joeydavis299", "subject": "a running back", "active": True},
    {"kind": "DONT_WANT", "team": "*", "subject": "Stefon Diggs", "active": True},
    {"kind": "WANT", "team": "josbaski", "subject": "Joe Burrow", "active": True},
    {"kind": "OFFERED", "team": "cmgaither43", "subject": "TreVeyon Henderson", "active": True},
]


def test_section4_example_compilation_pinned(league):
    """§11.12(b)/§12(b): the spec's own example compilations, exactly."""
    compiled, ignored = cn.compile_intel(league, INTEL)
    assert ignored == []
    got = [(c.who, c.side, c.what, c.with_, c.mode) for c in compiled]
    assert got == [
        ("ronakpatel32", "receives", ("class", "pick"), None, "require"),
        ("joeydavis299", "receives", ("pos", "RB"), None, "require"),
        ("*", "receives", ("asset", "Stefon Diggs"), None, "exclude"),
        ("josbaski", "receives", ("asset", "Joe Burrow"), None, "require"),
        ("me", "receives", ("asset", "TreVeyon Henderson"), "cmgaither43", "prefer"),
    ]
    assert all(c.source == "intel" for c in compiled)


def test_subject_parsing_is_conservative(league):
    """§4: exact rostered-asset names, pick/player class keywords, and position
    keywords parse; everything else compiles to NO constraint — never guessed."""
    assert cn.parse_subject(league, "Joe Burrow") == ("asset", "Joe Burrow")
    assert cn.parse_subject(league, "  joe  burrow ") == ("asset", "Joe Burrow")
    assert cn.parse_subject(league, "draft picks") == ("class", "pick")
    assert cn.parse_subject(league, "picks") == ("class", "pick")
    assert cn.parse_subject(league, "veteran players") == ("class", "player")
    assert cn.parse_subject(league, "a running back") == ("pos", "RB")
    assert cn.parse_subject(league, "RB") == ("pos", "RB")
    assert cn.parse_subject(league, "a quarterback") == ("pos", "QB")
    assert cn.parse_subject(league, "tight ends") == ("pos", "TE")
    for junk in ("an elite young cornerstone", "Tom Brady", "", None, "win now help"):
        assert cn.parse_subject(league, junk) is None, junk
    # unparseable subjects on ACTIVE docs are reported back, never guessed
    docs = [{"kind": "WANT", "team": "vishan", "subject": "win now help", "active": True}]
    compiled, ignored = cn.compile_intel(league, docs)
    assert compiled == [] and len(ignored) == 1
    assert "never" in ignored[0]["reason"] or "no constraint" in ignored[0]["reason"]
    # inactive docs are revoked: silently skipped, not reported
    docs[0]["active"] = False
    compiled, ignored = cn.compile_intel(league, docs)
    assert compiled == [] and ignored == []
    # NOTE docs never compile and say so
    notes = [{"kind": "NOTE", "team": "millj", "subject": "says he is rebuilding"}]
    compiled, ignored = cn.compile_intel(league, notes)
    assert compiled == [] and "never compiled" in ignored[0]["reason"]


def test_precedence_later_source_wins_per_team(league):
    """§4 strict precedence: intel drops the posture default of exactly the
    team it names; a query constraint drops both for its team; wildcard
    constraints are additive and never override. On the fixture, ronakpatel32
    is the BUYER and millj the SELLER — the only posture defaults."""
    base, _ = cn.compile_constraints(league)
    assert [(c.who, c.what, c.source) for c in base] == [
        ("millj", ("class", "pick"), "posture"),
        ("ronakpatel32", ("class", "player"), "posture"),
    ]
    # intel names ronak: his posture default is gone, millj's survives, the
    # wildcard Diggs exclusion rides alongside
    with_intel, _ = cn.compile_constraints(league, intel=INTEL)
    srcs = {(c.who, c.source) for c in with_intel}
    assert ("ronakpatel32", "posture") not in srcs
    assert ("ronakpatel32", "intel") in srcs
    assert ("millj", "posture") in srcs
    assert ("*", "intel") in srcs
    # a query naming ronak drops his intel constraint too; millj still posture
    q = [{"who": "ronakpatel32", "side": "receives", "what": {"pos": "WR"}, "mode": "require"}]
    with_q, _ = cn.compile_constraints(league, intel=INTEL, query=q)
    ron = [c for c in with_q if c.who == "ronakpatel32"]
    assert [(c.what, c.mode, c.source) for c in ron] == [(("pos", "WR"), "require", "query")]
    assert ("millj", "posture") in {(c.who, c.source) for c in with_q}
    assert any(c.who == "*" and c.source == "intel" for c in with_q)
    # toggles: use_posture/use_intel off removes those sources entirely
    none_at_all, ig = cn.compile_constraints(
        league, intel=INTEL, use_posture=False, use_intel=False
    )
    assert none_at_all == [] and ig == []


def test_posture_defaults_reproduce_posture_allows_11_12f(league):
    """§11.12(f): with nothing overriding, the compiled posture defaults allow
    a give-package to a counterparty EXACTLY when v3.3's posture_allows lets
    that shape through — over every counterparty and a systematic sample of
    my real give-list packages (players-majority, picks-majority, and mixed
    shapes all occur in the sample)."""
    pcs = cn.posture_constraints(league)
    me_t = league.teams[league.me]
    pkgs = tr._packages(league, tr.give_list(league, me_t))[::37]
    shapes = {tr.offer_shape(p) for p in pkgs}
    assert shapes == {"players", "picks", "mixed"}  # all shapes exercised
    for opp in league.opponents:
        label = league.postures[opp]["label"]
        for p in pkgs:
            assert cn.package_allowed(pcs, opp, "give", p) == tr.posture_allows(
                label, tr.offer_shape(p)
            ), (opp, label, p.keys)
    # and the get side is never constrained by posture defaults (§4: they
    # compile on the receive side only)
    for opp in league.opponents:
        for p in tr._packages(league, tr.give_list(league, league.teams[opp]))[::197]:
            assert cn.package_allowed(pcs, opp, "get", p)


def test_predicate_semantics(league):
    """require {class} is MAJORITY, require {pos}/{asset} is containment,
    exclude is any-containment, `with` scopes to one counterparty, and
    prefer tags without excluding."""
    mine = tr.team_assets(league, league.teams[league.me])
    colin = tr.team_assets(league, league.teams["cmgaither43"])
    burrow_pick = tr.package_of(league, [mine["Joe Burrow"], mine["2027 R2 (own)"]])
    two_picks_burrow = tr.package_of(
        league, [mine["Joe Burrow"], mine["2027 R2 (own)"], mine["2028 R3 (own)"]]
    )
    diggs = tr.package_of(league, [mine["Stefon Diggs"]])
    compiled, _ = cn.compile_intel(league, INTEL)
    # require majority: a mixed 1-player/1-pick package is NOT picks-majority
    ron = [c for c in compiled if c.who == "ronakpatel32"]
    assert not cn.package_allowed(ron, "ronakpatel32", "give", burrow_pick)
    assert cn.package_allowed(ron, "ronakpatel32", "give", two_picks_burrow)
    # the same package is unconstrained toward a team the constraint not names
    assert cn.package_allowed(ron, "jaketoppen", "give", burrow_pick)
    # require containment: Burrow anywhere in the package satisfies josbaski
    jos = [c for c in compiled if c.who == "josbaski"]
    assert cn.package_allowed(jos, "josbaski", "give", burrow_pick)
    assert not cn.package_allowed(jos, "josbaski", "give", diggs)
    # exclude containment: Diggs poisons any package to ANY counterparty
    star = [c for c in compiled if c.who == "*"]
    for opp in ("jaketoppen", "ronakpatel32", "cmgaither43"):
        assert not cn.package_allowed(star, opp, "give", diggs)
        assert cn.package_allowed(star, opp, "give", burrow_pick)
    # prefer: tags the matching leg vs the named counterparty only, and only
    # on the preferred side; it never hard-filters
    hend = tr.package_of(league, [colin["TreVeyon Henderson"]])
    my_pick = tr.package_of(league, [mine["2027 R2 (own)"]])
    assert cn.leg_allowed(compiled, "cmgaither43", my_pick, hend)
    assert cn.leg_preferred(compiled, "cmgaither43", my_pick, hend) is True
    assert cn.leg_preferred(compiled, "cmgaither43", hend, my_pick) is False
    other = tr.package_of(league, [tr.team_assets(league, league.teams["jaketoppen"])["2028 R4 (own)"]])
    assert cn.leg_preferred(compiled, "jaketoppen", my_pick, other) is False


def test_query_constraint_validation(league):
    """§4 source 3: ad-hoc dicts are validated strictly — the user typed them,
    so malformed input raises instead of guessing."""
    ok = cn.query_constraint(
        league, {"who": "me", "side": "sends", "what": {"asset": "Joe Burrow"}, "mode": "exclude"}
    )
    assert (ok.who, ok.mode, ok.what) == ("me", "exclude", ("asset", "Joe Burrow"))
    ok2 = cn.query_constraint(
        league,
        {"who": "*", "side": "receives", "what": {"asset": "stefon diggs"}, "mode": "exclude"},
    )
    assert ok2.what == ("asset", "Stefon Diggs")  # canonicalized, case-insensitive
    for bad in [
        {"who": "nobody", "side": "receives", "what": {"pos": "RB"}, "mode": "require"},
        {"who": "millj", "side": "gets", "what": {"pos": "RB"}, "mode": "require"},
        {"who": "millj", "side": "receives", "what": {"pos": "K"}, "mode": "require"},
        {"who": "millj", "side": "receives", "what": {"class": "kicker"}, "mode": "require"},
        {"who": "millj", "side": "receives", "what": {"pos": "RB"}, "mode": "must"},
        {"who": "millj", "side": "receives", "what": {"pos": "RB", "class": "pick"}, "mode": "require"},
        {"who": "millj", "side": "receives", "what": {"asset": "Tom Brady"}, "mode": "require"},
        {"who": "millj", "side": "receives", "what": {"asset": "RB"}, "mode": "require", "with": "??"},
    ]:
        with pytest.raises(ValueError):
            cn.query_constraint(league, bad)
